"""A progress bar for the jobs that take long enough to wonder about.
No dependency: a bar is a carriage return and some characters. It writes to stderr, never
stdout, and draws nothing when stderr is not a terminal. The line is assembled so it fits
the width by construction rather than being truncated afterwards."""

from __future__ import annotations

import collections
import os
import shutil
import sys
import threading
import time
from typing import Any, Optional, TextIO

MODES = ("auto", "plain", "none")

_WINDOW_SECONDS = 120.0
"""How far back the rate is measured. Long enough to smooth a slow trial,
short enough to notice a server that has started struggling."""

_MIN_SAMPLES = 12
_MIN_ELAPSED = 15.0
"""Below either of these the estimate is noise and is not shown."""

BAR_WIDTH = 20
"""Characters of bar. Fixed rather than elastic: a bar that changes width as
the numbers beside it grow reads as progress going backwards."""

_BLOCKS = " \u258f\u258e\u258d\u258c\u258b\u258a\u2589\u2588"
"""Eighths of a block, 0/8 to 8/8. A twenty-character bar over 9,720 trials is
one character per 486 of them -- about two minutes at four a second -- so
without the partial block the bar would sit still for minutes at a time and
look stalled. Where the stream cannot encode these, `#` and `-` stand in."""

_FILLED, _EMPTY = "\u2588", "\u2591"
_ASCII_FILLED, _ASCII_EMPTY = "#", "-"

_active: list["Progress"] = []
_active_lock = threading.Lock()


def clear_active() -> None:
    """Wipe any drawn bar so something else can write a clean line."""
    with _active_lock:
        for bar in _active:
            bar._erase()


def redraw_active() -> None:
    """Put it back."""
    with _active_lock:
        for bar in _active:
            bar._redraw()


def humanise(seconds: float) -> str:
    """A duration a person reads at a glance. Never more precise than it is."""
    if seconds < 0:
        return "--"
    if seconds < 90:
        # Rounded, not truncated: int() turned an estimate of 18.9999 seconds into 18.
        return f"{int(round(seconds))}s"
    minutes = int(round(seconds / 60.0))
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def clock(seconds: Optional[float]) -> str:
    """A countdown as `HH:MM:SS`, or `--:--:--` when it is not known yet.

    Fixed width on purpose: the line is redrawn several times a second, and a
    field that changes length shifts everything to the right of it."""
    if seconds is None or seconds < 0:
        return "--:--:--"
    whole = int(round(seconds))
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    if hours > 99:
        return "99:59:59"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def bar(fraction: float, width: int = BAR_WIDTH, *, unicode_ok: bool = True) -> str:
    """`width` characters of bar, filled to `fraction`."""
    fraction = min(1.0, max(0.0, fraction))
    if not unicode_ok:
        filled = int(width * fraction)
        return _ASCII_FILLED * filled + _ASCII_EMPTY * (width - filled)
    exact = width * fraction
    whole = int(exact)
    out = _FILLED * whole
    if whole < width:
        eighths = int((exact - whole) * 8)
        if eighths:
            out += _BLOCKS[eighths]
        out += _EMPTY * (width - len(out))
    return out


def rate_text(rate: Optional[float], unit: str) -> str:
    """`4.2 trials/s`, with the width bounded so the line does not jump."""
    if not rate:
        return ""
    shown = f"{rate:,.0f}" if rate >= 100 else f"{rate:.1f}"
    return f"{shown} {unit}/s"


def can_draw_blocks(stream: TextIO) -> bool:
    """Whether this stream can carry the block characters.
    A stream with no encoding is held in memory and takes any string. One that cannot
    represent them -- a legacy console codepage -- gets `#` and `-` rather than a
    UnicodeEncodeError in the middle of a run."""
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return True
    try:
        (_FILLED + _EMPTY + _BLOCKS.strip()).encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


class Progress:
    """One job's progress, on stderr.

    `total` of 0 or a `mode` of "none" makes every method a no-op, so a caller
    never needs to branch on whether there is a bar."""

    def __init__(self, total: int, *, label: str = "", unit: str = "items",
                 stream: Optional[TextIO] = None, mode: str = "auto",
                 min_redraw: float = 0.12, plain_steps: int = 40,
                 plain_seconds: float = 60.0, bar_width: int = BAR_WIDTH,
                 unicode_ok: Optional[bool] = None) -> None:
        if mode not in MODES:
            raise ValueError(f"progress mode must be one of {MODES}, not {mode!r}")
        self.total = max(0, int(total))
        self.label = label
        self.unit = unit
        """What one item is. A run's item is a TRIAL, not a request: with
        `tool_turns` above 1 a trial is an agent loop that may be several
        requests, so calling the rate req/s would overstate it by whatever the
        model chose to do. The estimate counts what it is counting."""
        self.bar_width = bar_width
        self.stream = stream if stream is not None else sys.stderr
        self.done = 0
        self._lock = threading.RLock()
        self._drawn = 0
        self._started = time.monotonic()
        self._last_draw = 0.0
        self._last_plain = self._started
        self._samples: collections.deque = collections.deque()
        self._min_redraw = min_redraw
        self._plain_every = max(1, self.total // max(1, plain_steps))
        self._plain_seconds = plain_seconds
        self._closed = False

        tty = mode == "auto" and _is_tty(self.stream)
        self.enabled = mode != "none" and self.total > 0
        self.fancy = bool(tty)
        self.unicode_ok = (can_draw_blocks(self.stream) if unicode_ok is None
                           else bool(unicode_ok))
        if self.enabled:
            with _active_lock:
                _active.append(self)

    # -- the caller's side ------------------------------------------------

    def advance(self, n: int = 1, note: str = "") -> None:
        if not self.enabled:
            return
        with self._lock:
            self.done += n
            now = time.monotonic()
            self._samples.append((now, self.done))
            while self._samples and now - self._samples[0][0] > _WINDOW_SECONDS:
                self._samples.popleft()
            self._note = note
            if self.fancy:
                if now - self._last_draw >= self._min_redraw or self.done >= self.total:
                    self._last_draw = now
                    self._write(self._line())
            elif (self.done % self._plain_every == 0
                  or self.done >= self.total
                  or now - self._last_plain >= self._plain_seconds):
                self._last_plain = now
                self.stream.write(self._line() + "\n")
                self.stream.flush()

    def close(self, note: str = "") -> None:
        if not self.enabled or self._closed:
            return
        with self._lock:
            self._closed = True
            self._note = note or getattr(self, "_note", "")
            if self.fancy:
                self._erase()
            self.stream.write(self._line(final=True) + "\n")
            self.stream.flush()
        with _active_lock:
            if self in _active:
                _active.remove(self)

    def __enter__(self) -> "Progress":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- what it says -----------------------------------------------------

    def rate(self) -> Optional[float]:
        """Items per second over the window, or None when it means nothing."""
        if len(self._samples) < _MIN_SAMPLES:
            return None
        (t0, n0), (t1, n1) = self._samples[0], self._samples[-1]
        span = t1 - t0
        if span <= 0 or n1 <= n0:
            return None
        return (n1 - n0) / span

    def eta_seconds(self) -> Optional[float]:
        """Seconds left, or None when there is not enough to say."""
        if time.monotonic() - self._started < _MIN_ELAPSED:
            return None
        rate = self.rate()
        if not rate:
            return None
        left = self.total - self.done
        return left / rate if left > 0 else 0.0

    SLOTS = ("label", "bar", "counts", "pct", "rate", "eta", "note")
    DROP = ("note", "rate", "bar", "eta", "label")
    """The order the fields are written in, and the order they are given up.

    The trial id goes first because it is the one field a reader can do
    without; the count and the percentage are never dropped, because a bar
    that cannot say how far along it is has stopped being a progress bar.
    """

    def _line(self, final: bool = False) -> str:
        done, total = self.done, self.total
        fraction = (done / total) if total else 1.0
        counts = f"{done:,}/{total:,}"
        if final:
            elapsed = time.monotonic() - self._started
            speed = rate_text(done / elapsed if elapsed > 0 else 0.0, self.unit)
            parts = [self.label, counts, f"in {clock(elapsed)}",
                     f"({speed})" if speed else ""]
            return "  ".join(p for p in parts if p)

        field = {
            "label": self.label,
            "bar": bar(fraction, self.bar_width, unicode_ok=self.unicode_ok),
            "counts": counts,
            "pct": f"{int(fraction * 100):3d}%",
            "rate": rate_text(self.rate(), self.unit),
            "eta": f"ETA {clock(self.eta_seconds())}",
            "note": getattr(self, "_note", ""),
        }
        # A stream nobody is watching has no width, so the whole line is written -- that is what makes a redirected log worth reading.
        width = _terminal_width(self.stream) if self.fancy else None
        line = "  ".join(field[k] for k in self.SLOTS if field[k])
        if width is None:
            return line
        for give_up in self.DROP:
            if len(line) <= width:
                return line
            field[give_up] = ""
            line = "  ".join(field[k] for k in self.SLOTS if field[k])
        return line[:width]

    # -- drawing ----------------------------------------------------------

    def _write(self, line: str) -> None:
        pad = max(0, self._drawn - len(line))
        self.stream.write("\r" + line + " " * pad)
        self.stream.flush()
        self._drawn = len(line)

    def _erase(self) -> None:
        if self.fancy and self._drawn:
            self.stream.write("\r" + " " * self._drawn + "\r")
            self.stream.flush()
            self._drawn = 0

    def _redraw(self) -> None:
        if self.fancy and not self._closed:
            self._write(self._line())


def _is_tty(stream: TextIO) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def _terminal_width(stream: TextIO) -> int:
    try:
        fd = stream.fileno()
    except (AttributeError, ValueError, OSError):
        fd = None
    if fd is not None:
        try:
            return max(40, os.get_terminal_size(fd).columns)
        except OSError:
            pass
    return max(40, shutil.get_terminal_size((100, 24)).columns)
