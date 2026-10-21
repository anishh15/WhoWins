"""Frozen train / validation / test lists over the base scenarios.
A split list says which scenarios may be fitted on and which are held back, and it is a
PRE-REGISTRATION COMMITMENT: built once, checked in, and never rebuilt to suit a result.
`check.py` verifies the files on disk against the rules that made them."""

from .grouping import (  # noqa: F401
    build_groups,
    group_of,
    load_collection,
    singleton_share,
)
from .sources import Source, covering_slice, load_sources, subsets  # noqa: F401

__all__ = ["build_groups", "group_of", "load_collection", "singleton_share",
           "Source", "load_sources", "subsets", "covering_slice"]
