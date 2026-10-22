"""The run loop: build the trials, send what is not already recorded, score it.
The log is the checkpoint, so a run that dies resumes where it stopped and an answer
is never sent twice. The only module here that opens a socket, exercised against a
stub server that answers, refuses, throttles, 500s and hangs up to order."""

from __future__ import annotations

import argparse
import collections
import contextlib
import dataclasses
import fcntl
import gzip
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any, Callable, Collection, Iterator, Mapping, Optional, Sequence

from ..checkers import fingerprint as checkers_fingerprint
from ..data import WORK
from ..logs import add_arguments, from_arguments, get_logger
from ..progress import Progress, humanise
from .design import trials_for_run
from .preflight import exit_status as preflight_status
from .preflight import run_checks
from .rendering import Scenarios
from .response import split_reasoning
from .run import RunRecord, score
from .serving import (
    ConfigError,
    Run,
    UndeliverableTrial,
    build_model_request,
    check_delivery,
    load_run,
    stack_for,
)
from .spec import TrialSpec
from .tools import stub_result, weak_scoring
from .trials import load_scenarios

RESULTS = os.path.join(WORK, "results")

_NOTHING = object()

log = get_logger(__name__)

RECORD, FAILURE = "record", "failure"
"""The two kinds of line in the log. A `record` is an answer that was scored,
whatever it said; a `failure` is a request that never came back."""


class TransportError(RuntimeError):
    """The request did not come back. Our problem, not the model's."""


class LogInUse(RuntimeError):
    """Another process is already sending this run."""


RETRYABLE_STATUS = frozenset({408, 429})
"""The 4xx codes that describe the server's load rather than our request.

429 is "too many requests" and 408 "the request timed out"; a proxy in front of
a busy vLLM sends both, and the same body a moment later is accepted. Every
other 4xx means the request itself is wrong and sending it again would be wrong
again, which is why they are not retried."""


def default_log(run_id: str) -> str:
    return os.path.join(RESULTS, run_id, "records.jsonl")


# --- The one HTTP call ---


def post_completion(base_url: str, body: Mapping[str, Any], timeout: float = 600.0,
                    api_key: Optional[str] = None) -> dict[str, Any]:
    """POST one chat completion and return the parsed envelope.
    A 4xx is a ConfigError -- the request was wrong and would be wrong again. Everything
    else is a TransportError, which the caller retries. 408 and 429 are the exception:
    they are about timing, not the request, so they retry."""
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(base_url.rstrip("/") + "/v1/chat/completions",
                                     data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        if 400 <= exc.code < 500 and exc.code not in RETRYABLE_STATUS:
            raise ConfigError(f"the server refused the request ({exc.code}): {detail}")
        raise TransportError(f"HTTP {exc.code}: {detail}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise TransportError(str(exc)) from None
    try:
        payload = json.loads(raw)
    except ValueError:
        raise TransportError(f"the reply is not JSON: {raw[:200]!r}") from None
    if not isinstance(payload, Mapping):
        raise TransportError(f"the reply is not an object: {raw[:200]!r}")
    return dict(payload)


# --- The log ---


def log_file(path: str) -> Optional[str]:
    """The log as it is on disk: the file, or `<file>.gz` once a finished run is compressed
    to fit under GitHub's 100 MB limit. None when neither is there."""
    for candidate in (path, path + ".gz"):
        if os.path.exists(candidate):
            return candidate
    return None


def parsed_lines(path: str) -> Iterator[Optional[dict[str, Any]]]:
    """Every non-blank line of a log, parsed. Yields None for one that will not.
    An unparseable line is the one being written when the run was killed, perhaps inside a
    character, so the log is read as bytes. It is never repaired: the trial it belonged to has
    no answer yet and is sent again. A compressed log is read the same way."""
    found = log_file(path)
    if found is None:
        return
    with (gzip.open(found, "rb") if found.endswith(".gz") else open(found, "rb")) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                yield None


def read_records(path: str) -> Iterator[dict[str, Any]]:
    """Every scored record of a log, in order, one per draw. Failure rows are skipped.
    A draw logged twice keeps its first record: a resume before 2026-10-09 could send a
    trial's draw again, and counting both would weigh that draw double."""
    seen: set[tuple[str, int]] = set()
    twice = 0
    for row in parsed_lines(path):
        if row is None or row.get("line") != RECORD:
            continue
        if "repeat" in row:
            key = (row.get("trial_id"), row["repeat"])
            if key in seen:
                twice += 1
                continue
            seen.add(key)
        yield row
    if twice:
        log.warning("%s: %d draw(s) logged twice; the first of each is read", path, twice)


def read_log(path: str) -> tuple[dict[str, set[int]], int]:
    """(the repeats answered per trial id, failures), from a log that may be half-written."""
    answered: dict[str, set[int]] = collections.defaultdict(set)
    failures = 0
    for row in parsed_lines(path):
        if row is None:
            failures += 1
        elif row.get("line") == RECORD and row.get("trial_id"):
            answered[row["trial_id"]].add(row.get("repeat", 0))
        elif row.get("line") == FAILURE:
            failures += 1
    return dict(answered), failures


def append_line(path: str, row: Mapping[str, Any]) -> None:
    """One line, on disk before the next request goes out.
    flush and fsync, because a checkpoint still in a buffer is not a checkpoint. A log
    not ending in a newline is closed first: appending onto half a line would glue the
    fragment to the next record and lose that one too."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    line = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
    with open(path, "ab+") as fh:
        # The probe is one BYTE: in text mode, a kill inside a multi-byte character made it raise.
        if fh.seek(0, os.SEEK_END):
            fh.seek(-1, os.SEEK_END)
            if fh.read(1) != b"\n":
                line = b"\n" + line
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


@contextlib.contextmanager
def holding(path: str) -> Iterator[None]:
    """The log, held by this process while it sends. An advisory lock the kernel drops when
    the process dies, so a killed run never leaves the log locked. A filesystem that cannot
    lock at all is warned about and not refused."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "ab") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LogInUse(f"{path} is being written by another process. Two runs on one "
                           f"log would both send every trial still pending") from None
        except OSError as exc:
            log.warning("%s cannot be locked here (%s); do not start a second run on it",
                        path, exc)
        yield


def record_row(record: RunRecord, run: Run) -> dict[str, Any]:
    row = record.as_dict()
    row["line"] = RECORD
    row["run_id"] = run.run_id
    row["tool_turns"] = run.tool_turns
    # The first run recorded no time at all, so a gap where the server had died could not be told from one where it was merely slow.
    row["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    # Which checkers said so: two runs scored either side of a fix were scored by two different instruments.
    row["checker_fingerprint"] = checkers_fingerprint()
    return row


def failure_row(trial_id: str, attempt: int, run: Run, reason: str) -> dict[str, Any]:
    return {"line": FAILURE, "run_id": run.run_id, "trial_id": trial_id,
            "attempt": attempt, "error": reason, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}


# --- The run ---


def gpu_name(nvidia_smi: str = "nvidia-smi") -> Optional[str]:
    """What the machine calls its first visible GPU, or None if it cannot say."""
    try:
        out = subprocess.run([nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    first = out.stdout.strip().splitlines()
    return first[0].strip() if out.returncode == 0 and first else None


def server_version(base_url: str, timeout: float = 10.0) -> Optional[str]:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/version", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("version")
    except (urllib.error.URLError, OSError, ValueError, AttributeError):
        return None


def pending(specs: Sequence[TrialSpec], answered: Mapping[str, Collection[int]],
            repeats: int) -> list[tuple[TrialSpec, int]]:
    """(trial, repeat) pairs still to send: everything the log has no answer for.
    BREADTH FIRST -- every trial's first draw, then every trial's second. A run is
    stopped by the clock far more often than it finishes, and depth-first would leave
    three draws of the first third and none of the rest; breadth-first leaves a run."""
    out: list[tuple[TrialSpec, int]] = []
    for repeat in range(repeats):
        for spec in specs:
            # By repeat, not count: draws land out of order, so a log can hold draw 2 and not 1.
            if repeat not in answered.get(spec.trial_id, ()):
                out.append((spec, repeat))
    return out


def _reply(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """The assistant message of a completion, or an empty one.
    Tolerant on purpose: read mid-loop only to decide whether to answer a tool call, and
    an unreadable payload simply ends the loop and is handed to `score`, which is the one
    place allowed to call a reply malformed."""
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return {}
    return message if isinstance(message, Mapping) else {}


def _answer_calls(message: Mapping[str, Any], turn: int, context_result: Optional[str],
                  *, split: bool = False, prompt_opened: bool = False
                  ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The model's turn to echo back, and one stub result per call it made.
    The turn goes back verbatim apart from its reasoning: a server parser files that apart,
    and where none does (`split`) it is cut off here. Ids left out by a server are filled in
    both places at once, because `check_delivery` refuses a result that answers no call."""
    calls = []
    results = []
    for i, call in enumerate(message.get("tool_calls") or []):
        call = dict(call)
        call.setdefault("type", "function")
        if not call.get("id"):
            call["id"] = f"call_t{turn}_{i}"
        name = (call.get("function") or {}).get("name") or ""
        calls.append(call)
        results.append({"role": "tool", "tool_call_id": call["id"],
                        "content": stub_result(name, context_result)})
    content = message.get("content") or ""
    if split and isinstance(content, str):
        content = split_reasoning(content, prompt_opened=prompt_opened)[0]
    assistant = {"role": "assistant", "content": content, "tool_calls": calls}
    return assistant, results


def _context_result(messages: Sequence[Mapping[str, Any]]) -> Optional[str]:
    """What this trial's own tool result said, for a model that reads it again.
    Reading a configuration twice returns the same configuration; answering the second
    read with anything else would change what the model had been told mid-trial."""
    for message in messages:
        if message.get("role") == "tool":
            content = message.get("content")
            if isinstance(content, str):
                return content
    return None


CONTEXT_REFUSAL = "maximum context length"
"""What vLLM's 400 says when a prompt and max_tokens together pass max-model-len."""

MALFORMED_HEADER = "unexpected tokens remaining in message header"
"""What vLLM's 500 says when gpt-oss writes a tool-call header its harmony parser cannot read
(e.g. `to=functions.x <|constrain|>???`). The text is the model's own output, and the seed is
fixed per draw, so a retry often writes it again: two gpt-oss-20b draws failed this way 60
times running (9 Oct). After the last retry the turn is the model's reply, recorded with a
fault (unusable), not a transport failure the run can never close."""


def _malformed_reply(detail: str) -> dict[str, Any]:
    """The completion a malformed tool-call header stands for: no text, no tool call, the
    server's error kept beside it so the record shows what the model wrote."""
    return {"choices": [{"index": 0, "finish_reason": "malformed_tool_call",
                         "message": {"role": "assistant", "content": "", "tool_calls": []}}],
            "server_error": detail}


def _undeliverable(spec: TrialSpec, turn: int, exc: UndeliverableTrial) -> list[str]:
    """A request that would not reach the model as recorded costs this trial, not the run."""
    log.error("%s turn %d cannot be sent as the record would describe it: %s",
              spec.trial_id, turn + 1, exc)
    return [f"undeliverable at turn {turn + 1}: {exc}"]


def one_draw(spec: TrialSpec, repeat: int, run: Run, scenarios: Scenarios,
             stack: Any, base_url: str, *, timeout: float, retries: int,
             api_key: Optional[str], post: Callable[..., dict[str, Any]],
             sleep: Callable[[float], None]) -> tuple[Optional[RunRecord], list[str]]:
    """One trial, run to the end of its agent loop or the end of the retries.
    Every attempt uses the same seed -- a retry asks for the same draw again -- and the
    attempt number counts upward so both rows stay in the record. THE LOOP IS THE TRIAL:
    every completion is kept and they are scored together."""
    decoding = run.decoding(spec.trial_id, repeat)
    try:
        body = build_model_request(spec, scenarios, run.deployment, decoding)
    except UndeliverableTrial as exc:
        return None, _undeliverable(spec, 0, exc)
    family = run.model.family
    opened = bool(family.thinking_prefills_open_block) and bool(decoding.enable_thinking)
    split = run.environment.reasoning_separation == "client" and bool(decoding.enable_thinking)
    messages = [dict(m) for m in body["messages"]]
    context_result = _context_result(messages)
    errors: list[str] = []
    payloads: list[Mapping[str, Any]] = []
    attempts = 1
    stopped_by = "no_more_calls"

    for turn in range(run.tool_turns):
        payload = None
        too_long = malformed = False
        for attempt in range(1, retries + 1):
            attempts = max(attempts, attempt)
            try:
                payload = post(base_url, {**body, "messages": messages},
                               timeout=timeout, api_key=api_key)
                break
            except ConfigError as exc:
                # A later turn too long to fit beside the answer budget ends the loop, as turns do.
                if turn == 0 or CONTEXT_REFUSAL not in str(exc):
                    raise
                log.warning("%s turn %d no longer fits beside the %d-token answer budget; the "
                            "loop stops here", spec.trial_id, turn + 1, decoding.max_tokens)
                too_long = True
                break
            except TransportError as exc:
                errors.append(str(exc))
                if attempt < retries:
                    delay = min(2.0 ** attempt, 30.0)
                    log.warning("%s turn %d attempt %d/%d: %s -- retrying in %.0fs",
                                spec.trial_id, turn + 1, attempt, retries, exc, delay)
                    sleep(delay)
                elif MALFORMED_HEADER in str(exc):
                    log.warning("%s turn %d: the model's tool-call header is malformed on all "
                                "%d attempts; recorded as its reply, with a fault",
                                spec.trial_id, turn + 1, retries)
                    payload = _malformed_reply(str(exc))
                    malformed = True
                else:
                    log.error("%s turn %d: gave up after %d attempts: %s",
                              spec.trial_id, turn + 1, retries, exc)
        if malformed:
            payloads.append(payload)
            stopped_by = "malformed_tool_call"
            break
        if too_long:
            stopped_by = "context_limit"
            break
        if payload is None:
            return None, errors
        payloads.append(payload)

        message = _reply(payload)
        if not (message.get("tool_calls") or []):
            stopped_by = "no_more_calls"
            break
        if turn + 1 >= run.tool_turns:
            stopped_by = "turn_budget"
            break
        assistant, results = _answer_calls(message, turn, context_result,
                                           split=split, prompt_opened=opened)
        messages = [*messages, assistant, *results]
        try:
            check_delivery(messages, family, late_operator=bool(spec.meta.get("operator_late")))
        except UndeliverableTrial as exc:
            return None, _undeliverable(spec, turn + 1, exc) + errors

    record = score(spec, scenarios, payloads, stack, decoding, attempt=attempts,
                   prompt_opened_thinking=opened, messages=messages,
                   stopped_by=stopped_by)
    if stopped_by == "malformed_tool_call":
        record = dataclasses.replace(record, faults=(*record.faults, (
            f"turn {len(payloads)}: the server could not parse the model's tool-call header "
            f"({MALFORMED_HEADER}); the turn is scored as no text and no tool call")))
    return record, errors


def _run_concurrently(work: Callable[[Any], Any], land: Callable[[Any], None],
                      todo: Sequence[Any], concurrency: int) -> None:
    """Run `work` over `todo` with `concurrency` in flight, landing each as it finishes.
    `pool.map` yields in SUBMISSION order, so one slow trial holds back every trial behind
    it, unwritten, and a run killed then loses all of them. A bounded window of futures,
    cancelled on the way out, so Ctrl-C stops sending rather than draining the queue."""
    items = iter(todo)
    window = max(2, concurrency * 2)
    live: set[Future] = set()

    def fill() -> None:
        while len(live) < window:
            item = next(items, _NOTHING)
            if item is _NOTHING:
                return
            live.add(pool.submit(work, item))

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        try:
            fill()
            while live:
                done, _ = wait(live, return_when=FIRST_COMPLETED)
                for future in done:
                    live.discard(future)
                    land(future.result())
                fill()
        finally:
            for future in live:
                future.cancel()


def run_batch(run: Run, scenarios: Scenarios, base_url: str, log_path: str, *,
              concurrency: int = 1, timeout: float = 600.0, retries: int = 3,
              limit: Optional[int] = None, api_key: Optional[str] = None,
              gpu: Optional[str] = None, engine_version: Optional[str] = None,
              allow_unpinned: bool = False,
              post: Callable[..., dict[str, Any]] = post_completion,
              sleep: Callable[[float], None] = time.sleep,
              on_progress: Optional[Callable[[int, int, str], None]] = None
              ) -> dict[str, Any]:
    """Send every trial the log has no answer for, and append each one as it lands.
    The log is held for the whole pass, because what is pending is read once at the start."""
    stack = stack_for(run.deployment, gpu=gpu, engine_version=engine_version,
                      allow_unpinned=allow_unpinned)
    with holding(log_path):
        specs = trials_for_run(run, scenarios)
        answered, past_failures = read_log(log_path)
        todo = pending(specs, answered, run.repeats)
        if limit is not None:
            todo = todo[:limit]

        done = failed = 0
        total = len(todo)
        started = time.monotonic()
        log.info("%s: %d trials x %d draws; %d already answered, %d to send",
                 run.run_id, len(specs), run.repeats, len(answered), total)
        log.info("model %s at %s, policy %s, design %s, tool_turns %d",
                 run.model.key, run.environment.key, run.policy.name, run.design,
                 run.tool_turns)
        log.info("concurrency %d, timeout %.0fs, retries %d, log %s",
                 concurrency, timeout, retries, log_path)
        weak = weak_scoring({s.scenario_id: scenarios[s.scenario_id] for s in specs
                             if s.scenario_id in scenarios})
        if weak:
            log.warning("%d scenario(s) will be scored from what the reply says, not from a "
                        "tool call: %s", len(weak), " ".join(weak))

        def work(item: tuple[TrialSpec, int]
                 ) -> tuple[TrialSpec, int, Optional[RunRecord], list[str]]:
            spec, repeat = item
            record, errors = one_draw(spec, repeat, run, scenarios, stack, base_url,
                                      timeout=timeout, retries=retries, api_key=api_key,
                                      post=post, sleep=sleep)
            return spec, repeat, record, errors

        def land(result: tuple[TrialSpec, int, Optional[RunRecord], list[str]]) -> None:
            nonlocal done, failed
            spec, repeat, record, errors = result
            if record is None:
                failed += 1
                append_line(log_path, failure_row(spec.trial_id, len(errors), run,
                                                  "; ".join(errors)[:500]))
                log.error("%s draw %d: no answer after %d error(s); logged as a "
                          "failure and will be sent again", spec.trial_id, repeat,
                          len(errors))
            else:
                done += 1
                row = record_row(record, run)
                row["repeat"] = repeat
                row["concurrency"] = concurrency
                append_line(log_path, row)
                log.debug("%s draw %d: %s/%s in %d turn(s), stopped_by=%s%s",
                          spec.trial_id, repeat, row.get("behaviour"),
                          row.get("communication"), row.get("turns"),
                          row.get("stopped_by"),
                          "" if row.get("usable") else " (unusable)")
                if row.get("finish_reason") == "length":
                    log.warning("%s draw %d ran out of tokens; kept as a censored "
                                "measurement, never re-rolled", spec.trial_id, repeat)
                if row.get("faults"):
                    log.warning("%s draw %d: %s", spec.trial_id, repeat,
                                "; ".join(row["faults"])[:300])
            if on_progress:
                on_progress(done + failed, total, spec.trial_id)

        if concurrency > 1:
            _run_concurrently(work, land, todo, concurrency)
        else:
            for item in todo:
                land(work(item))

        elapsed = time.monotonic() - started
        summary = {"trials": len(specs), "already_answered": len(answered), "sent": total,
                   "scored": done, "failed": failed, "past_failures": past_failures,
                   "log": log_path}
        (log.warning if failed else log.info)(
            "%s: %d scored, %d failed, in %s", run.run_id, done, failed,
            humanise(elapsed))
        # A summary beside the log, rewritten after every pass. Derived from the log alone, so deleting it costs nothing.
        state = report(run, scenarios, log_path)
        path = os.path.join(os.path.dirname(log_path) or ".", "summary.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({**state, "last_pass": summary}, fh, indent=2)
            fh.write("\n")
        summary["summary"] = path
        return summary


def report(run: Run, scenarios: Scenarios, log_path: str) -> dict[str, Any]:
    """Where a run stands, read back from its log alone.
    `behaviour` counts every scored row; `behaviour_usable` leaves out the ones that
    measured nothing. Both, because the first run's summary quietly mixed them -- and
    dropping them silently would be worse than reporting two numbers."""
    specs = trials_for_run(run, scenarios)
    answered, failures = read_log(log_path)
    behaviour: collections.Counter = collections.Counter()
    usable_behaviour: collections.Counter = collections.Counter()
    communication: collections.Counter = collections.Counter()
    stopped: collections.Counter = collections.Counter()
    turns: collections.Counter = collections.Counter()
    faults = truncated = unusable = 0
    for row in read_records(log_path):
        behaviour[row.get("behaviour")] += 1
        communication[row.get("communication")] += 1
        stopped[row.get("stopped_by")] += 1
        turns[row.get("turns", 1)] += 1
        faults += bool(row.get("faults"))
        truncated += row.get("finish_reason") == "length"
        if row.get("usable"):
            usable_behaviour[row.get("behaviour")] += 1
        else:
            unusable += 1
    return {
        "run_id": run.run_id, "log": log_path,
        "design": run.design, "tool_turns": run.tool_turns,
        "arms": {str(n): sum(1 for s in specs if s.meta.get("n_competing") == n)
                 for n in run.composition_sizes},
        "trials": len(specs), "answered": len(answered),
        "remaining": len(pending(specs, answered, run.repeats)),
        "transport_failures": failures,
        "behaviour": dict(behaviour.most_common()),
        "behaviour_usable": dict(usable_behaviour.most_common()),
        "communication": dict(communication.most_common()),
        "stopped_by": dict(stopped.most_common()),
        "turns_taken": {str(k): v for k, v in sorted(turns.items())},
        "with_faults": faults, "truncated": truncated, "unusable": unusable,
    }




def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m whowins.runner.batch",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("run_id", help="a run in configs/runs/")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="the vLLM server to send to (default: %(default)s)")
    parser.add_argument("--out", metavar="PATH", default=None,
                        help="the records log to append to and resume from "
                             "(default: results/<run_id>/records.jsonl)")
    parser.add_argument("--concurrency", type=int, default=1,
                        help="requests in flight (default 1: one at a time, which "
                             "keeps every draw in its own batch)")
    parser.add_argument("--timeout", type=float, default=600.0, metavar="SECONDS",
                        help="how long one request may take before it counts as "
                             "a transport failure (default: %(default)s). Raise "
                             "it with --concurrency: each stream is slower when "
                             "they share the GPU")
    parser.add_argument("--retries", type=int, default=3, metavar="N",
                        help="attempts per turn on a transport failure, backing "
                             "off 2s, 4s, ... to 30s (default: %(default)s). An "
                             "answer is never re-rolled; only a request that "
                             "never came back is sent again")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="send at most this many pending trials, then stop. "
                             "A smoke test before the whole run")
    parser.add_argument("--api-key", metavar="KEY",
                        default=os.environ.get("VLLM_API_KEY") or None,
                        help="bearer token, if the server wants one "
                             "(default: $VLLM_API_KEY)")
    parser.add_argument("--dry-run", action="store_true",
                        help="build and check every request, send none")
    parser.add_argument("--report", action="store_true",
                        help="read the log and say where the run stands")
    parser.add_argument("--skip-preflight", action="store_true",
                        help="send without checking the server's version, model, "
                             "context length and chat template first")
    parser.add_argument("--allow-unpinned-engine", action="store_true",
                        help="record a server whose version is not the pinned one")
    add_arguments(parser)
    args = parser.parse_args(argv)
    written = from_arguments("run", args, args.run_id)

    try:
        run = load_run(args.run_id)
    except (ConfigError, KeyError, OSError) as exc:
        log.error("config error: %s", exc)
        return 2
    scenarios = load_scenarios()
    log_path = args.out or default_log(run.run_id)

    if args.report:
        state = report(run, scenarios, log_path)
        log.info("%s: %d of %d answered, %d remaining, %d transport failure(s)",
                 run.run_id, state["answered"], state["trials"],
                 state["remaining"], state["transport_failures"])
        print(json.dumps(state, indent=2))
        return 0

    if args.dry_run:
        log.info("%s: building every trial and checking it would reach %s as "
                 "recorded. Nothing will be sent", run.run_id, run.model.key)
        specs = trials_for_run(run, scenarios)
        with Progress(len(specs), label="Build", unit="trials",
                      mode=args.progress) as bar:
            for spec in specs:
                build_model_request(spec, scenarios, run.deployment,
                                    run.decoding(spec.trial_id, 0))
                bar.advance(note=spec.trial_id)
        answered, _ = read_log(log_path)
        left = len(pending(specs, answered, run.repeats))
        log.info("%d trials build and deliver; %d draw(s) still to send",
                 len(specs), left)
        if written:
            log.info("this run's log: %s", written)
        print(f"{len(specs)} trials build and would be delivered as recorded; "
              f"{left} still to send. Nothing was sent.")
        return 0

    if not args.skip_preflight:
        log.info("checking %s against the pins of %s before sending anything",
                 args.base_url, run.environment.key)
        checks = run_checks(run.deployment, args.base_url)
        for check in checks:
            (log.info if check.result == "PASS" else log.warning)(
                "%-12s %-16s %s", check.result, check.name, check.detail)
        status = preflight_status(checks)
        if status == 1:
            log.error("preflight failed: the server is not serving what this "
                      "run expects. Fix it, or pass --skip-preflight")
            return 1

    version = server_version(args.base_url)
    if version is None:
        # Falling back to the pinned version would record a config value as an observation.
        log.warning("%s did not report its engine version; it is recorded as 'unreported'",
                    args.base_url)
        version = "unreported"
    started = time.time()
    bar: Optional[Progress] = None

    def show(done: int, total: int, trial_id: str) -> None:
        nonlocal bar
        if bar is None:
            bar = Progress(total, label="Trials", unit="trials",
                           mode=args.progress)
        bar.advance(note=trial_id)

    try:
        summary = run_batch(
            run, scenarios, args.base_url, log_path,
            concurrency=max(1, args.concurrency), timeout=args.timeout,
            retries=max(1, args.retries), limit=args.limit, api_key=args.api_key,
            gpu=gpu_name(), engine_version=version,
            allow_unpinned=args.allow_unpinned_engine, on_progress=show)
    except ConfigError as exc:
        log.error("config error: %s", exc)
        return 2
    except LogInUse as exc:
        log.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        # Every answer is already on disk; say where it stopped and leave the rest to the same command.
        if bar is not None:
            bar.close()
        log.warning("interrupted; every answer so far is in %s, and the same "
                    "command carries on from there", log_path)
        return 130
    finally:
        if bar is not None:
            bar.close()
    summary["seconds"] = round(time.time() - started, 1)
    if written:
        log.info("this run's log: %s", written)
    print(json.dumps(summary, indent=2))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(_main())
