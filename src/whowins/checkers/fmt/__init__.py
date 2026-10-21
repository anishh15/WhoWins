"""Format-family classifiers, grouped by the axis they read.
Importing this package registers all 240 format keys. The modules are imported for their
side effects, which is why they look unused."""

from . import surface     # noqa: F401  fmt-0001..0030, surface-form axes
from . import wire        # noqa: F401  API and wire protocol
from . import editorial   # noqa: F401  prose, locale and calendar
from . import syntax      # noqa: F401  notation, delimiters, markup
from . import values      # noqa: F401  closed-vocabulary value renderings
from . import tooling     # noqa: F401  repository and tooling conventions
from . import prose       # noqa: F401  editorial axes that read a whole passage
from . import domain      # noqa: F401  specialist trade notations
from . import structural  # noqa: F401  keys that need a parser, not a rule table
