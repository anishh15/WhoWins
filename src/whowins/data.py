"""Reading the repository's data files: one reader, and loud about a bad file.
`json.load` reports a parse error by line and column but never by file, so a trailing
comma surfaced as a traceback pointing at whichever loader tripped over it, with nothing
saying which file to open."""

from __future__ import annotations

import glob
import json
import os
from typing import Any, Iterator

CHECKOUT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""The repository root when this file is src/whowins/data.py of a checkout."""

IN_CHECKOUT = (os.path.isdir(os.path.join(CHECKOUT, "data", "scenarios"))
               and os.path.isfile(os.path.join(CHECKOUT, "configs", "models.json")))

ROOT = CHECKOUT if IN_CHECKOUT else os.path.join(os.path.dirname(os.path.abspath(__file__)), "_bundle")
"""Where data/ and configs/ are read: the checkout, or else the copy an installed package
carries in whowins/_bundle (setup.py puts it there at build time)."""

WORK = CHECKOUT if IN_CHECKOUT else os.getcwd()
"""Where logs/ and results/ are written: the checkout, or else the working directory, so an
installed package never writes into site-packages."""


class DataFileError(ValueError):
    """A data file that does not parse. The message names the file."""


def read_json(path: str) -> Any:
    """Parse one JSON file, naming it if it does not parse."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise DataFileError(
            f"{os.path.relpath(path, ROOT)}: not valid JSON at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise DataFileError(
            f"{os.path.relpath(path, ROOT)}: not valid UTF-8 at byte {exc.start}"
        ) from exc


def _data(*parts: str) -> str:
    """A path under ROOT/data. Missing, every glob would come back empty and read as an
    empty collection, which is what a non-editable install gives."""
    folder = os.path.join(ROOT, "data")
    if not os.path.isdir(folder):
        raise FileNotFoundError(
            f"{folder} does not exist. The collection is read from a checkout of the "
            f"repository (`pip install -e .` or PYTHONPATH=src) or from the copy a built "
            f"package carries")
    return os.path.join(folder, *parts)


def scenario_files() -> list[str]:
    return sorted(glob.glob(_data("scenarios", "*", "*.json")))


def iter_scenarios() -> Iterator[tuple[str, dict]]:
    """(batch file name, scenario) for every base scenario, in file order.

    Entries without a `scenario_id` are skipped, as every loader here always has."""
    for path in scenario_files():
        for entry in read_json(path):
            if "scenario_id" in entry:
                yield os.path.basename(path), entry


def trial_files() -> list[str]:
    return sorted(glob.glob(_data("trials", "*.json")))
