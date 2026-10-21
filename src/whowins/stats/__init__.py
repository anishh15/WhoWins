"""The strengths fit, the families it is compared with, and the simulation that gates them.
Stdlib only: five sources is 120 rankings, Fraction makes "identical pairwise rates"
exact, and `normal` does the orthant integrals. Deferred: random effects, and the
pre-registration.
"""

from .choice import Choice, Dataset, Option, from_records  # noqa: F401
from .rankings import RankingWorld, luce_world  # noqa: F401

__all__ = ["Choice", "Option", "Dataset", "from_records",
           "RankingWorld", "luce_world"]
