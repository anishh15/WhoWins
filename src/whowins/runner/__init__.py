"""Turning a base scenario into something a model can be asked, and back.
vocabulary, spec, rendering, trials, design, tools, response, run, serving, preflight,
batch, rescore, analyse, compare, fillers. Only `batch` opens a socket. The renderer is
verified against the 70 hand-written trials, not against itself."""

from .rendering import RenderError, render, render_dicts  # noqa: F401
from .response import MalformedCompletion, parse_completion  # noqa: F401
from .run import (  # noqa: F401
    Decoding,
    GroupOutcome,
    RunRecord,
    ServingStack,
    build_request,
    score,
)
from .spec import Block, ConflictGroup, Message, Span, Task, TrialSpec  # noqa: F401
from .tools import scoring_path, tools_for, tools_for_trial  # noqa: F401
from .vocabulary import UnknownVocabulary  # noqa: F401

__all__ = ["render", "render_dicts", "RenderError", "Block", "ConflictGroup",
           "Message", "Span", "Task", "TrialSpec", "UnknownVocabulary",
           "parse_completion", "MalformedCompletion", "tools_for",
           "tools_for_trial", "scoring_path", "build_request", "score",
           "Decoding", "ServingStack", "RunRecord", "GroupOutcome"]
"""The pure core, re-exported for convenience.

`batch`, `serving`, `design`, `rescore`, `analyse`, `compare` and `preflight`
are deliberately NOT here. Importing this package would then pull in the run loop, the roster and
every config file just to render a message, and `whowins.data` exists precisely so
that reading the collection does not drag the rest of the package with it.
Import them by their own names: `from whowins.runner.batch import run_batch`."""
