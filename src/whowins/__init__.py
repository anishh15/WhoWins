"""WhoWins: which of several conflicting instructions an LLM agent follows.
Five seats send mutually exclusive instructions, the experiments vary only how they are
delivered, and code scores which one a reply followed; no language model judges anything."""

import logging as _logging

__version__ = "0.1.0"

_logging.getLogger(__name__).addHandler(_logging.NullHandler())
