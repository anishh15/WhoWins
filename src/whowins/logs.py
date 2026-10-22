"""Where this repository's commands say what they are doing.
Every log record and progress line goes to stderr and to a file under logs/; the prints
that produce a command's report stay on stdout, because stdout is a contract here.
Importing the package installs no output anywhere."""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Optional

from .data import WORK
from .progress import clear_active, redraw_active

LOG_DIR = os.path.join(WORK, "logs")

PACKAGE = "whowins"

FILE_FORMAT = "%(asctime)s %(levelname)-8s %(name)-24s %(message)s"
STDERR_FORMAT = "%(levelname)-7s %(message)s"

_configured = False


def get_logger(name: str) -> logging.Logger:
    """The logger for one module. `get_logger(__name__)`, always.
    `__name__` IS "__main__" under `python3 -m`, which is not under "whowins" and reaches none
    of the handlers -- so every module logger in a running command wrote nothing. The real
    dotted name is read back off `__spec__`."""
    if name == "__main__":
        spec = getattr(sys.modules.get("__main__"), "__spec__", None)
        name = getattr(spec, "name", None) or name
    return logging.getLogger(name)


class ProgressAwareHandler(logging.StreamHandler):
    """A stderr handler that does not write through a progress bar.
    A bar is a line held open with a carriage return; a record written over it leaves half a
    bar in front of the message and the rest orphaned below. The bar is wiped, the record
    written, the bar redrawn."""

    def emit(self, record: logging.LogRecord) -> None:
        clear_active()
        try:
            super().emit(record)
        finally:
            redraw_active()


def log_path(tool: str, tag: Optional[str] = None, *,
             when: Optional[str] = None) -> str:
    """Where this invocation's file goes: logs/<tool>[-<tag>]-<timestamp>.log."""
    stamp = when or time.strftime("%Y%m%dT%H%M%S")
    name = f"{tool}-{tag}-{stamp}" if tag else f"{tool}-{stamp}"
    return os.path.join(LOG_DIR, f"{_safe(name)}.log")


def setup(tool: str, tag: Optional[str] = None, *, verbosity: str = "INFO",
          log_file: Optional[str] = None, to_file: bool = True) -> Optional[str]:
    """Point the package's logging at this terminal and at a file.
    Returns the file it is writing to, or None. Calling it twice replaces the handlers rather
    than doubling them, so a test calling a `_main` in process does not get six copies of
    every line."""
    global _configured
    logger = logging.getLogger(PACKAGE)
    for handler in list(logger.handlers):
        if not isinstance(handler, logging.NullHandler):
            logger.removeHandler(handler)
            handler.close()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    console = ProgressAwareHandler()
    console.setLevel(getattr(logging, verbosity.upper(), logging.INFO))
    console.setFormatter(logging.Formatter(STDERR_FORMAT))
    logger.addHandler(console)

    path = None
    if to_file:
        path = log_file or log_path(tool, tag)
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            # delay=True: a command that logs nothing leaves no file, so the directory holds records rather than empties.
            handler = logging.FileHandler(path, encoding="utf-8", delay=True)
        except OSError as exc:
            # A read-only checkout or a full disk is not a reason to refuse to run; the terminal still gets everything.
            console.handle(logging.LogRecord(
                PACKAGE, logging.WARNING, __file__, 0,
                "no log file (%s): %s", (path, exc), None))
            path = None
        else:
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(logging.Formatter(FILE_FORMAT))
            logger.addHandler(handler)
    _configured = True
    return path


def add_arguments(parser, *, progress: bool = True) -> None:
    """The flags every command of this repository shares.
    One set of names, one meaning each, so knowing one command is knowing all of them.
    Documented in runbook.md, and `tests/test_logs.py` asserts every command carries them."""
    group = parser.add_argument_group("output")
    group.add_argument("-v", "--verbose", action="store_true",
                       help="print every step to stderr (DEBUG). The log file "
                            "always holds DEBUG regardless")
    group.add_argument("-q", "--quiet", action="store_true",
                       help="print only warnings and errors to stderr")
    group.add_argument("--log-file", metavar="PATH", default=None,
                       help="write the run log here (default: logs/<tool>-<when>.log)")
    group.add_argument("--no-log-file", action="store_true",
                       help="write no log file; stderr only")
    if progress:
        group.add_argument("--progress", choices=MODES_HELP, default="auto",
                           help="auto: a bar on a terminal, whole lines when "
                                "redirected. plain: always whole lines. "
                                "none: nothing (default: auto)")


MODES_HELP = ("auto", "plain", "none")


def from_arguments(tool: str, args, tag: Optional[str] = None) -> Optional[str]:
    """`setup` from what `add_arguments` parsed."""
    verbosity = "DEBUG" if getattr(args, "verbose", False) else (
        "WARNING" if getattr(args, "quiet", False) else "INFO")
    return setup(tool, tag, verbosity=verbosity,
                 log_file=getattr(args, "log_file", None),
                 to_file=not getattr(args, "no_log_file", False))


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in name)
