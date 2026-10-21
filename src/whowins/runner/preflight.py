"""Check a running server against its environment's pins before sending anything.
Reads only: it asks the server what it is serving and compares that with the roster.
Run it after `serve.sh` and before `run_trials.sh`."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from ..logs import add_arguments, from_arguments, get_logger
from .serving import ConfigError, Deployment, Model, load_roster

PASS, FAIL, NOT_CHECKED = "PASS", "FAIL", "NOT CHECKED"


@dataclass(frozen=True)
class Check:
    name: str
    result: str
    detail: str


def _get_json(base_url: str, path: str, timeout: float) -> Any:
    with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def hf_cache_dir() -> str:
    """Where huggingface_hub keeps downloads, following its own environment rules."""
    if os.environ.get("HF_HUB_CACHE"):
        return os.environ["HF_HUB_CACHE"]
    home = os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache",
                                                     "huggingface")
    return os.path.join(home, "hub")


def cached_template(model: Model, cache_dir: str) -> str:
    """The downloaded file a model's chat template lives in.
    Qwen 3.5 and gpt-oss ship a `chat_template.jinja`; Qwen 3 keeps its template as a string
    inside `tokenizer_config.json`, which is where transformers -- and so vLLM -- reads it.
    The family says which."""
    org, name = model.hf_id.split("/", 1)
    return os.path.join(cache_dir, f"models--{org}--{name}", "snapshots", model.revision,
                        model.family.template_source["file"])


def template_bytes(model: Model, path: str) -> bytes:
    """The template itself, as the bytes the roster's hash is over."""
    source = model.family.template_source
    with open(path, "rb") as fh:
        raw = fh.read()
    if "key" not in source:
        return raw
    value = json.loads(raw.decode("utf-8")).get(source["key"])
    if not isinstance(value, str):
        raise ValueError(f"{path} has no {source['key']!r} string in it")
    return value.encode("utf-8")


def _installed(distribution: str) -> Optional[str]:
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover - Python < 3.8
        return None
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def run_checks(deployment: Deployment, base_url: str, *, cache_dir: Optional[str] = None,
               timeout: float = 10.0, harmony_version: Optional[str] = None) -> list[Check]:
    """Every check, in order. `harmony_version` stands in for the installed one,
    for a caller that knows it from elsewhere."""
    checks: list[Check] = []
    model = deployment.model
    environment = deployment.environment
    pinned = environment.engine_version

    try:
        reported = _get_json(base_url, "/version", timeout).get("version")
        ok = reported == pinned
        checks.append(Check(f"{environment.engine} version", PASS if ok else FAIL,
                            f"server reports {reported!r}; {environment.key} pins {pinned!r}"))
    except (urllib.error.URLError, OSError, ValueError, AttributeError) as exc:
        checks.append(Check(f"{environment.engine} version", FAIL,
                            f"could not read /version: {exc}"))

    try:
        listed = _get_json(base_url, "/v1/models", timeout).get("data") or []
        ids = [m.get("id") for m in listed]
        if ids != [model.hf_id]:
            checks.append(Check("served model", FAIL,
                                f"server lists {ids}; expected exactly [{model.hf_id!r}]"))
        else:
            checks.append(Check("served model", PASS, model.hf_id))
            got = listed[0].get("max_model_len")
            want = deployment.max_model_len
            checks.append(Check("context length", PASS if got == want else FAIL,
                                f"server {got}; serve file {want}"))
    except (urllib.error.URLError, OSError, ValueError, AttributeError) as exc:
        checks.append(Check("served model", FAIL, f"could not read /v1/models: {exc}"))

    if model.family.prompt_renderer == "hf-jinja":
        path = cached_template(model, cache_dir or hf_cache_dir())
        if not os.path.exists(path):
            checks.append(Check("chat template", NOT_CHECKED,
                                f"{path} is not on this machine; run preflight on the "
                                f"server host, after scripts/download_models.sh"))
        else:
            try:
                digest = hashlib.sha256(template_bytes(model, path)).hexdigest()
            except (ValueError, UnicodeDecodeError) as exc:
                checks.append(Check("chat template", FAIL, f"{path}: {exc}"))
            else:
                ok = digest == model.chat_template_sha256
                checks.append(Check("chat template", PASS if ok else FAIL,
                                    f"{digest[:12]}...; pinned "
                                    f"{model.chat_template_sha256[:12]}..."))
    if model.family.prompt_renderer == "openai-harmony":
        found = harmony_version if harmony_version is not None else _installed("openai-harmony")
        if found is None:
            checks.append(Check("openai-harmony", NOT_CHECKED,
                                "not installed in this Python; run preflight in the "
                                "server's environment"))
        else:
            ok = found == environment.openai_harmony
            checks.append(Check("openai-harmony", PASS if ok else FAIL,
                                f"installed {found!r}; {environment.key} pins "
                                f"{environment.openai_harmony!r}"))
    return checks


def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m whowins.runner.preflight",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("model", help="model key, as in configs/models.json")
    parser.add_argument("--environment", default=None,
                        help="which environment's server this is, for a model served "
                             "in more than one (default: the first it lists)")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="the server to check (default: %(default)s)")
    parser.add_argument("--cache-dir", default=None,
                        help="Hugging Face hub cache (default: from HF_HUB_CACHE or HF_HOME)")
    parser.add_argument("--timeout", type=float, default=10.0, metavar="SECONDS",
                        help="how long to wait for /version and /v1/models "
                             "(default: %(default)s)")
    add_arguments(parser, progress=False)
    args = parser.parse_args(argv)
    from_arguments("preflight", args, args.model)
    log = get_logger(__name__)
    try:
        roster = load_roster()
        if args.model not in roster:
            log.error("no model %r; the keys are %s", args.model, list(roster))
            return 2
        model = roster[args.model]
        deployment = model.at(args.environment) if args.environment else model.deployment
    except (ConfigError, OSError) as exc:
        log.error("config error: %s", exc)
        return 2
    log.info("checking %s at %s against the pins of %s",
             deployment.model.key, args.base_url, deployment.environment.key)
    checks = run_checks(deployment, args.base_url, cache_dir=args.cache_dir,
                        timeout=args.timeout)
    for c in checks:
        # DEBUG, not INFO: the table below is this command's report and goes to stdout.
        log.debug("%-12s %-16s %s", c.result, c.name, c.detail)
    for c in checks:
        print(f"{c.result:<12} {c.name:<16} {c.detail}")
    return exit_status(checks)


def exit_status(checks: list[Check]) -> int:
    """0 all passed, 1 something failed, 3 nothing failed but something went
    unchecked -- which a script must not read as a pass."""
    if any(c.result == FAIL for c in checks):
        return 1
    if any(c.result == NOT_CHECKED for c in checks):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(_main())
