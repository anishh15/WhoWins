"""Deterministic outcome checkers. No language model is involved anywhere.
Every scenario carries a checker string such as `key_casing==snake_case`, and a checker
turns one response into one label, so at most one option wins. Two kinds of key: `trace`
(840 scenarios, read off a structured trace) and `classifier` (the 240 format keys)."""

from .core import (  # noqa: F401
    CHOSE,
    FLAGGED,
    HEDGED,
    MULTIPLE,
    NO_ACTION,
    SILENT,
    UNRESOLVED,
    MalformedChecker,
    Outcome,
    Response,
    ToolCall,
    UnknownCheckerKey,
    check,
    has_checker,
    option_values,
    parse_checker,
    registered_keys,
)
from . import trace  # noqa: F401  registers the four trace keys
from . import fmt  # noqa: F401    registers the implemented format keys

__all__ = [
    "check", "Response", "ToolCall", "Outcome",
    "UNRESOLVED", "NO_ACTION", "MULTIPLE", "CHOSE", "FLAGGED", "HEDGED", "SILENT",
    "UnknownCheckerKey", "MalformedChecker",
    "registered_keys", "has_checker", "option_values", "parse_checker",
]


# The runner modules that also decide a verdict: what text a reply yields, which turn is the artifact, off-menu, fillers, the scoring path.
SCORING_MODULES = ("runner/response.py", "runner/run.py", "runner/fillers.py", "runner/tools.py")


def fingerprint(package: str = "") -> str:
    """A hash of the source that turns a reply into a verdict, recorded on every record scored.
    Two runs scored either side of a fix were scored by two different instruments. Over the
    SOURCE of this package and SCORING_MODULES, not behaviour: hashing what they do would mean
    running them. `package` is the `whowins` directory to read, for the suite."""
    import hashlib
    import os

    package = package or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    here = os.path.join(package, "checkers")
    paths = []
    for root, dirs, files in os.walk(here):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        paths += [os.path.join(root, f) for f in sorted(files) if f.endswith(".py")]
    digest = hashlib.sha256()
    for path in paths + [os.path.join(package, m) for m in SCORING_MODULES]:
        digest.update(os.path.relpath(path, package).encode())
        with open(path, "rb") as fh:
            digest.update(fh.read())
    return "sha256:" + digest.hexdigest()[:32]
