"""The progress bar and the logging, and the one rule they must not break.
STDOUT IS A CONTRACT: `serving shell KEY` is eval'd by scripts/serve.sh and `batch --report`
prints JSON, so every log record and progress line goes to stderr."""

from __future__ import annotations

import io
import logging
import os
import time

import pytest

from whowins import logs, progress
from whowins.progress import Progress, bar, can_draw_blocks, clock, humanise, rate_text


class FakeTTY(io.StringIO):
    """A stream that claims to be a terminal and has no file descriptor."""

    def isatty(self) -> bool:
        return True

    def fileno(self) -> int:
        raise OSError("no descriptor here")


class FakePipe(io.StringIO):
    def isatty(self) -> bool:
        return False


# --- stdout is a contract ---


def test_nothing_a_command_reads_is_written_to_stdout(capsys):
    """A bar on stdout would corrupt `eval "$(serving shell qwen3-1.7b)"`."""
    p = Progress(10, label="x", mode="auto")
    for _ in range(10):
        p.advance()
    p.close()
    logs.setup("test", verbosity="DEBUG", to_file=False)
    logging.getLogger("whowins.test").error("a loud one")
    captured = capsys.readouterr()
    assert captured.out == "", f"something reached stdout: {captured.out!r}"


def test_the_shell_assignments_serve_sh_evals_are_still_only_assignments(capsys):
    """serve.sh runs `eval "$settings"`. One stray line and the GPU server runs
    something nobody wrote. This is why logging goes to stderr."""
    from whowins.runner.serving import _main

    logs.setup("test", verbosity="DEBUG", to_file=False)
    assert _main(["shell", "qwen3-1.7b"]) == 0
    out = capsys.readouterr().out
    assert out.strip(), "it printed nothing at all"
    for line in out.strip().splitlines():
        name, sep, _ = line.partition("=")
        assert sep == "=" and name.isidentifier() and name.isupper(), line


def test_importing_the_package_installs_no_output(capsys):
    """A library that prints because it was imported corrupts whatever its
    caller was writing. The NullHandler in whowins/__init__.py is what stops
    Python's last-resort handler putting WARNINGs on stderr by itself."""
    for handler in list(logging.getLogger("whowins").handlers):
        if not isinstance(handler, logging.NullHandler):
            logging.getLogger("whowins").removeHandler(handler)
    logging.getLogger("whowins.somewhere").warning("must not appear")
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    assert any(isinstance(h, logging.NullHandler)
               for h in logging.getLogger("whowins").handlers)


# --- The bar ---


def test_a_bar_with_nothing_to_do_draws_nothing():
    out = FakeTTY()
    for p in (Progress(0, stream=out), Progress(10, stream=out, mode="none")):
        p.advance()
        p.close()
    assert out.getvalue() == ""


def test_a_terminal_gets_one_line_redrawn_and_a_pipe_gets_whole_lines():
    tty, pipe = FakeTTY(), FakePipe()
    for stream, total in ((tty, 40), (pipe, 40)):
        p = Progress(total, label="run", stream=stream, mode="auto",
                       min_redraw=0.0, plain_steps=4)
        for i in range(total):
            p.advance(note=f"t{i}")
        p.close()
    assert "\r" in tty.getvalue(), "a terminal should be redrawn in place"
    assert "\r" not in pipe.getvalue(), (
        "carriage returns in a redirected log make one unreadable line")
    assert pipe.getvalue().count("\n") <= 14, "a redirected log must stay short"
    assert pipe.getvalue().count("\n") >= 4, "and must still say something"


def test_the_estimate_is_withheld_until_it_means_something():
    out = FakePipe()
    p = Progress(500, stream=out, mode="plain")
    p.advance()
    assert p.rate() is None and p.eta_seconds() is None
    assert "ETA --:--:--" in p._line()

    # A steady 20/s that started a minute ago: 380 left is 19 seconds.
    p._started = time.monotonic() - 60.0
    now = time.monotonic()
    p._samples.clear()
    for i in range(120):
        p._samples.append((now - (119 - i) * 0.05, i + 1))
    p.done = 120
    assert p.rate() == pytest.approx(20.0, rel=0.05)
    assert p.eta_seconds() == pytest.approx(19.0, rel=0.1)
    assert "ETA 00:00:19" in p._line()


def test_the_estimate_follows_the_recent_rate_not_the_whole_run():
    """A run's first requests go out while the server is warming and the
    concurrency window is still filling. An average over those under-reports
    the rate for hours, which is worse than saying nothing."""
    p = Progress(1000, stream=FakePipe(), mode="plain")
    p._started = time.monotonic() - 600.0
    now = time.monotonic()
    # 100 items in the first ten minutes, then 100 in the last ten seconds.
    p._samples.clear()
    for i in range(100):
        p._samples.append((now - 10.0 + i * 0.1, 100 + i + 1))
    p.done = 200
    assert p.rate() == pytest.approx(10.0, rel=0.1), "measured over the window"
    assert p.eta_seconds() == pytest.approx(80.0, rel=0.1)


def test_a_duration_is_never_more_precise_than_it_is():
    assert humanise(12) == "12s"
    assert humanise(89) == "89s"
    assert humanise(95) == "2m"
    assert humanise(600) == "10m"
    assert humanise(6300) == "1h 45m"
    assert humanise(-1) == "--"


@pytest.mark.parametrize("width", [40, 46, 52, 61, 72, 80, 96, 120])
@pytest.mark.parametrize("note", ["", "t", "fmt-0009@S3",
                                  "a-very-long-trial-identifier@S1-S2"])
def test_a_narrow_terminal_never_wraps_the_bar(width, note, monkeypatch):
    """A line one character over the width wraps.
    A wrapped bar leaves a trail of half-lines behind it instead of one line being rewritten, so
    the width is swept rather than spot-checked."""
    monkeypatch.setattr(progress, "_terminal_width", lambda stream: width)
    for done, total in ((1, 9720), (5000, 9720), (9720, 9720), (7, 10)):
        p = Progress(total, label="run", stream=FakeTTY(), mode="auto",
                       min_redraw=0.0)
        p._started = time.monotonic() - 600.0
        now = time.monotonic()
        for i in range(30):
            p._samples.append((now - (29 - i) * 0.08, i + 1))
        p.done = done
        p._note = note
        line = p._line()
        assert len(line) <= width, f"{width} columns, {len(line)} written: {line!r}"


def test_a_log_record_does_not_land_in_the_middle_of_a_bar():
    """The bar is a line held open with a carriage return. A record written
    over it leaves half a bar in front of the message."""
    out = FakeTTY()
    p = Progress(10, label="run", stream=out, mode="auto", min_redraw=0.0)
    p.advance()
    drawn = out.getvalue()
    assert drawn and not drawn.endswith("\r")
    progress.clear_active()
    assert out.getvalue().endswith("\r"), "the bar was not wiped first"
    progress.redraw_active()
    assert not out.getvalue().endswith("\r"), "the bar was not put back"
    p.close()


def test_a_closed_bar_leaves_the_cursor_on_its_own_line():
    out = FakeTTY()
    p = Progress(4, label="run", stream=out, mode="auto", min_redraw=0.0)
    for _ in range(4):
        p.advance()
    p.close()
    assert out.getvalue().endswith("\n")
    assert "4/4  in 00:00:" in out.getvalue()
    p.close()  # twice is harmless
    assert out.getvalue().count("4/4  in") == 1


# --- The logging ---


def test_the_file_holds_everything_the_terminal_was_not_asked_to_show(tmp_path):
    """`-v` changes what the terminal prints and nothing else. When a run ends
    badly at 03:40 the answer used to exist only in surviving scrollback."""
    path = str(tmp_path / "a.log")
    stream = io.StringIO()
    assert logs.setup("t", verbosity="WARNING", log_file=path) == path
    console = next(h for h in logging.getLogger("whowins").handlers
                   if isinstance(h, logs.ProgressAwareHandler))
    console.setStream(stream)
    log = logging.getLogger("whowins.t")
    log.debug("the detail")
    log.info("the stage")
    log.warning("the problem")
    for handler in logging.getLogger("whowins").handlers:
        handler.flush()
    on_screen = stream.getvalue()
    on_disk = open(path).read()
    assert "the problem" in on_screen
    assert "the detail" not in on_screen and "the stage" not in on_screen
    assert all(m in on_disk for m in ("the detail", "the stage", "the problem"))


def test_setting_up_twice_does_not_print_everything_twice(tmp_path):
    """Judged on what is attached afterwards, not on a count taken before, which holds
    whatever earlier tests in the same process left behind."""
    for _ in range(3):
        logs.setup("t", log_file=str(tmp_path / "b.log"))
    attached = sorted(type(h).__name__ for h in logging.getLogger("whowins").handlers
                      if not isinstance(h, logging.NullHandler))
    assert attached == ["FileHandler", "ProgressAwareHandler"]


def test_a_log_file_that_cannot_be_written_does_not_stop_the_command(tmp_path):
    """A read-only checkout is not a reason to refuse to run a job."""
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("")
    assert logs.setup("t", log_file=str(blocked / "x.log")) is None
    logging.getLogger("whowins.t").info("still works")


@pytest.mark.parametrize("flags,want", [
    ([], "INFO"), (["-v"], "DEBUG"), (["-q"], "WARNING"),
])
def test_the_verbosity_flags_mean_the_same_thing_everywhere(flags, want, tmp_path,
                                                            monkeypatch):
    import argparse

    parser = argparse.ArgumentParser()
    logs.add_arguments(parser)
    args = parser.parse_args([*flags, "--no-log-file"])
    seen = {}
    monkeypatch.setattr(logs, "setup",
                        lambda *a, **k: seen.update(k) or None)
    logs.from_arguments("t", args)
    assert seen["verbosity"] == want and seen["to_file"] is False


def test_a_log_file_is_named_for_its_command_and_its_subject():
    path = logs.log_path("run", "balanced-qwen3-1.7b", when="20260914T031500")
    assert os.path.dirname(path) == logs.LOG_DIR
    assert os.path.basename(path) == "run-balanced-qwen3-1.7b-20260914T031500.log"
    assert "/" not in os.path.basename(logs.log_path("run", "a/b", when="x"))


def test_logs_are_not_committed():
    """A log is what this checkout did. What the study did is
    results/<run>/records.jsonl, which is kept outside this repository."""
    root = os.path.dirname(logs.LOG_DIR)
    ignore = open(os.path.join(root, ".gitignore"), encoding="utf-8").read()
    assert "logs/*.log" in ignore
    assert os.path.exists(os.path.join(logs.LOG_DIR, "README.md")), (
        "the directory is committed and empty, with a README saying what it is")


# --- Every command carries the same flags ---

CLIS = [
    ("whowins.runner.batch", True),
    ("whowins.runner.rescore", True),
    ("whowins.runner.analyse", False),
    ("whowins.runner.compare", False),
    ("whowins.stats.phase1", False),
    ("whowins.stats.strengths", False),
    ("whowins.stats.load_cell", False),
    ("whowins.stats.layouts", False),
    ("whowins.runner.design", False),
    ("whowins.runner.preflight", False),
]


@pytest.mark.parametrize("module,has_progress", CLIS, ids=[m for m, _ in CLIS])
def test_every_command_takes_the_same_output_flags(module, has_progress, capsys):
    """Knowing one command's flags is knowing all of them. runbook.md documents
    them once; this is what stops a command quietly not having them."""
    import importlib
    import sys

    mod = importlib.import_module(module)
    main = getattr(mod, "_main", None) or getattr(mod, "main")
    with pytest.raises(SystemExit):
        main(["--help"])
    text = capsys.readouterr().out
    for flag in ("--verbose", "--quiet", "--log-file", "--no-log-file"):
        assert flag in text, f"{module} is missing {flag}"
    assert ("--progress" in text) == has_progress, module
    assert "sys" in sys.modules


def test_a_command_started_with_dash_m_actually_logs():
    """The whole of this file can pass while logging is dead in production.
    `python3 -m` runs the module as `__main__`, which is not under "whowins" and reaches none of the
    handlers, so this starts a real command the real way and reads its stderr."""
    import subprocess
    import sys

    root = os.path.dirname(logs.LOG_DIR)
    env = dict(os.environ, PYTHONPATH=os.path.join(root, "src"))
    out = subprocess.run(
        [sys.executable, "-m", "whowins.runner.rescore", "no-such-run", "--no-log-file"],
        capture_output=True, text=True, cwd=root, env=env, timeout=120)
    assert out.returncode == 2
    assert "ERROR" in out.stderr, (
        f"the command logged nothing at all:\n{out.stderr!r}")
    assert "rescore error" in out.stderr


def test_the_real_module_name_is_recovered_from_the_spec(monkeypatch):
    import sys
    import types

    fake = types.SimpleNamespace(__spec__=types.SimpleNamespace(name="whowins.runner.batch"))
    monkeypatch.setitem(sys.modules, "__main__", fake)
    assert logs.get_logger("__main__").name == "whowins.runner.batch"
    assert logs.get_logger("whowins.splits.check").name == "whowins.splits.check"
    # A loose script has no spec, and is left alone rather than guessed at.
    monkeypatch.setitem(sys.modules, "__main__", types.SimpleNamespace(__spec__=None))
    assert logs.get_logger("__main__").name == "__main__"


# --- The runbook documents every flag, and is checked against the code ---

COMMANDS = [
    ("whowins.runner.batch", "_main"),
    ("whowins.runner.rescore", "_main"),
    ("whowins.runner.analyse", "_main"),
    ("whowins.runner.compare", "_main"),
    ("whowins.stats.phase1", "_main"),
    ("whowins.stats.strengths", "_main"),
    ("whowins.stats.capacity", "_main"),
    ("whowins.stats.load_cell", "_main"),
    ("whowins.stats.layouts", "_main"),
    ("whowins.validation.check_realism", "_main"),
    ("whowins.stats.pooled", "_main"),
    ("whowins.validation.check_load", "_main"),
    ("whowins.runner.design", "_main"),
    ("whowins.runner.preflight", "_main"),
    ("whowins.splits.build", "main"),
    ("whowins.splits.check", "main"),
]


def _flags(module: str, entry: str) -> set:
    """Every long flag one command takes, read off its own parser."""
    import contextlib
    import importlib
    import io
    import re
    import sys

    mod = importlib.import_module(module)
    buf = io.StringIO()
    argv = sys.argv
    sys.argv = [module, "--help"]
    try:
        with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
            fn = getattr(mod, entry)
            try:
                fn(["--help"])
            except TypeError:
                fn()
    finally:
        sys.argv = argv
    found = set(re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", buf.getvalue()))
    return found - {"--help"}


@pytest.mark.parametrize("module,entry", COMMANDS, ids=[m for m, _ in COMMANDS])
def test_the_runbook_documents_every_flag(module, entry):
    """A flag nobody wrote down is a flag nobody uses, and a runbook that has
    fallen behind the code is worse than none: the reader trusts it. So the
    reference in runbook.md is checked against the parsers rather than kept in
    step by hand."""
    root = os.path.dirname(logs.LOG_DIR)
    runbook = open(os.path.join(root, "runbook.md"), encoding="utf-8").read()
    undocumented = sorted(f for f in _flags(module, entry) if f not in runbook)
    assert undocumented == [], (
        f"{module} takes {undocumented}, and runbook.md does not mention "
        f"them. Add them to 'The flags'.")


def test_the_shell_scripts_flags_are_documented_too():
    import glob
    import re

    root = os.path.dirname(logs.LOG_DIR)
    runbook = open(os.path.join(root, "runbook.md"), encoding="utf-8").read()
    missing = []
    for path in sorted(glob.glob(os.path.join(root, "scripts", "*.sh"))):
        body = open(path, encoding="utf-8").read()
        # `--gpus) ...` in the case statement, and `== "--print"` in the ifs.
        flags = set(re.findall(r'^\s*(--[a-z-]+)\)', body, re.M))
        flags |= set(re.findall(r'==\s*"(--[a-z-]+)"', body))
        for flag in sorted(flags):
            if flag not in runbook:
                missing.append((os.path.basename(path), flag))
    assert missing == [], f"undocumented shell flags: {missing}"


# --- The fields of the bar ---


def test_a_countdown_is_a_clock_and_says_so_when_it_does_not_know():
    """Fixed width, because the line is redrawn several times a second and a
    field that changes length shifts everything to the right of it."""
    assert clock(None) == "--:--:--"
    assert clock(-1) == "--:--:--"
    assert clock(0) == "00:00:00"
    assert clock(1741) == "00:29:01"
    assert clock(6300) == "01:45:00"
    assert clock(359_999) == "99:59:59"
    assert clock(10 ** 9) == "99:59:59", "it stays eight characters"
    assert len({len(clock(s)) for s in (0, 59, 61, 3599, 3601, 86_400)}) == 1


def test_the_bar_moves_between_whole_characters():
    """Twenty characters over 9,720 trials is one character per 486 of them --
    about two minutes at four a second. Without the partial block the bar would
    sit still for minutes at a time and look stalled."""
    assert bar(0.0) == "░" * 20
    assert bar(1.0) == "█" * 20
    assert bar(0.5) == "█" * 10 + "░" * 10
    moved = {bar(i / 400.0) for i in range(0, 401)}
    assert len(moved) > 100, "the bar has fewer steps than a plain block bar"
    for fraction in (0.0, 0.013, 0.25, 0.5, 0.999, 1.0, -5.0, 7.0):
        assert len(bar(fraction)) == 20, fraction
        assert len(bar(fraction, unicode_ok=False)) == 20, fraction


def test_a_stream_that_cannot_carry_a_block_gets_hashes():
    """A legacy console codepage raising UnicodeEncodeError in the middle of a
    run would take the run with it."""
    assert bar(0.5, unicode_ok=False) == "#" * 10 + "-" * 10

    class Latin1(io.StringIO):
        encoding = "latin-1"

    class Utf8(io.StringIO):
        encoding = "utf-8"

    assert can_draw_blocks(Latin1()) is False
    assert can_draw_blocks(Utf8()) is True
    assert can_draw_blocks(io.StringIO()) is True, "an in-memory stream takes anything"
    assert Progress(10, stream=Latin1(), mode="plain").unicode_ok is False


def test_the_rate_counts_trials_and_not_requests():
    """A trial is an agent loop. With `tool_turns` above 1 it may be several
    requests, so calling the rate req/s would overstate it by whatever the
    model chose to do."""
    assert rate_text(4.23, "trials") == "4.2 trials/s"
    assert rate_text(0.4, "records") == "0.4 records/s"
    assert rate_text(142.7, "trials") == "143 trials/s"
    assert rate_text(12_345.0, "trials") == "12,345 trials/s"
    assert rate_text(None, "trials") == "" and rate_text(0.0, "trials") == ""


def test_the_fields_are_given_up_in_order_as_the_terminal_narrows(monkeypatch):
    """The trial id first, because it is the field a reader can do without; the
    count and the percentage last, because a bar that cannot say how far along
    it is has stopped being one."""
    def line_at(width):
        monkeypatch.setattr(progress, "_terminal_width", lambda stream: width)
        p = Progress(9720, label="Trials", unit="trials", stream=FakeTTY(),
                     mode="auto", min_redraw=0.0)
        p._started = time.monotonic() - 600.0
        now = time.monotonic()
        for i in range(40):
            p._samples.append((now - (39 - i) / 4.2, i + 1))
        p.done = 2430
        p._note = "fmt-0009@S3"
        return p._line()

    wide = line_at(120)
    assert "Trials" in wide and "2,430/9,720" in wide and " 25%" in wide
    assert "trials/s" in wide and "ETA 00:" in wide and "fmt-0009@S3" in wide
    assert "█" in wide and "░" in wide

    assert "fmt-0009@S3" not in line_at(80), "the id goes first"
    assert "trials/s" in line_at(80)
    assert "trials/s" not in line_at(72), "then the rate"
    assert "█" in line_at(72)
    assert "█" not in line_at(52), "then the bar"
    for width in (120, 80, 72, 52, 44, 40):
        assert "2,430/9,720" in line_at(width) and "25%" in line_at(width)


def test_a_redirected_run_keeps_the_trial_id():
    """A terminal drops it for width. A log file has no width, and the id is
    what makes the file worth reading afterwards."""
    p = Progress(9720, label="Trials", unit="trials", stream=FakePipe(),
                 mode="plain", plain_steps=4)
    for i in range(2430):
        p.advance(note="fmt-0009@S3")
    written = p.stream.getvalue()
    assert "fmt-0009@S3" in written
    assert "2,430/9,720" in written
    assert "\r" not in written
