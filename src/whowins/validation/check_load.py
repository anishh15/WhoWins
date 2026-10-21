"""Is every load bundle fit to send? READ-ONLY.
Structure and the grid, every line a filler or a conflict member, every filler scorable,
each trial rendering as recorded, and each n-level one length in tokens under both pinned
Qwen tokenizers when they are in the local Hugging Face cache."""

from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import os
import re
import sys
from typing import Any, Mapping, Optional, Sequence

from ..runner import bundles
from ..runner.fillers import BY_TEXT, KINDS
from ..runner.rendering import RenderError, render_dicts
from ..runner.tools import tools_for_trial
from ..runner.trials import load_cell_headers, load_scenarios, reconstruct

WORKED_COMPONENTS_CELL = bundles.LOAD_CELL
FAMILIES = {"tool": 1, "path": 1, "format": 4}
"""What a bundle is made of, as the worked bundle is: one step, one destination, four formats."""


def pinned_tokenizers() -> dict[str, Any]:
    """family -> the tokenizer its roster pins, for each one found in the local cache."""
    try:
        import tokenizers
    except ImportError:
        return {}
    from ..runner.serving import load_roster
    out = {}
    for model in load_roster().values():
        family = model.family
        if family.name in out or family.name not in ("qwen3", "qwen3.5"):
            continue
        pattern = "~/.cache/huggingface/hub/models--Qwen--%s-*/snapshots/*/tokenizer.json" % (
            "Qwen3.5" if family.name == "qwen3.5" else "Qwen3")
        for path in sorted(glob.glob(os.path.expanduser(pattern))):
            with open(path, "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() == family.tokenizer_sha256:
                    out[family.name] = tokenizers.Tokenizer.from_file(path)
                    break
    return out


def token_count(tok: Any, text: str) -> int:
    return len(tok.encode(text, add_special_tokens=False).ids)


def check_bundle(bundle: Mapping[str, Any], scenarios: Mapping[str, Mapping[str, Any]], *,
                 others: Sequence[Mapping[str, Any]] = (),
                 tokenizers: Optional[Mapping[str, Any]] = None,
                 reserved: Optional[tuple[set, set]] = None) -> tuple[list[str], dict]:
    """Every problem with one bundle, and what was measured. `others` are the other bundles,
    which it must not share a component, a project, a task or a filler line with; `reserved`
    is the worked bundle's (components, filler lines), which no bundle may reuse either."""
    bid = bundle.get("bundle_id", "?")
    fails: list[str] = []
    info: dict[str, Any] = {"bundle_id": bid, "tokens": {}}

    def fail(message: str) -> None:
        fails.append(f"{bid}: {message}")

    for key in ("bundle_id", "authored_by", "project", "task", "component_scenarios",
                "rationale", "fillers", "trials"):
        if key not in bundle:
            fail(f"missing {key!r}")
    if fails:
        return fails, info
    if not re.fullmatch(r"lb-\d{2}", bid):
        fail("bundle_id is not lb-NN")
    project, task = bundle["project"], bundle["task"]
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+", project):
        fail(f"project {project!r} is not a kebab-case name like atlas-core")
    if project not in task or not task.endswith("."):
        fail("the task must name the project and end with a full stop")

    # The six components: one tool, one path, four formats, none shared with another bundle.
    comps = list(bundle["component_scenarios"])
    missing = [c for c in comps if c not in scenarios]
    if missing:
        fail(f"component scenarios {missing} are not in the collection")
        return fails, info
    families = collections.Counter(scenarios[c]["family"] for c in comps)
    if dict(families) != FAMILIES or len(set(comps)) != len(comps):
        fail(f"components must be six distinct scenarios, {FAMILIES}; got {dict(families)}")
    worked, worked_lines = reserved if reserved is not None else (
        set((load_cell_headers().get(WORKED_COMPONENTS_CELL) or {})
            .get("component_scenarios", ())), set(BY_TEXT))
    for other in others:
        shared = set(comps) & set(other.get("component_scenarios", ()))
        if shared:
            fail(f"shares {sorted(shared)} with {other.get('bundle_id')}")
        if other.get("project") == project or other.get("task") == task:
            fail(f"shares its project or task with {other.get('bundle_id')}")
    if set(comps) & worked:
        fail(f"shares {sorted(set(comps) & worked)} with the worked bundle")

    option_text = {(c, o["id"]): o["text"] for c in comps for o in scenarios[c]["options"]}
    all_options = set(option_text.values())

    # Fillers: a known kind, the right value, a line nobody else has written.
    seen_ids, texts = set(), set()
    taken = set(worked_lines) | {f["text"] for o in others for f in o.get("fillers", ())}
    for f in bundle["fillers"]:
        fid, text, kind = f.get("id"), f.get("text", ""), f.get("kind")
        if not re.fullmatch(r"F\d+", str(fid)) or fid in seen_ids:
            fail(f"filler id {fid!r} is not a fresh F<number>")
        seen_ids.add(fid)
        if not text.strip() or "\n" in text or not text.endswith("."):
            fail(f"{fid}: a filler is one line ending in a full stop")
        if text in texts:
            fail(f"{fid}: the same line twice")
        texts.add(text)
        if text in taken:
            fail(f"{fid}: {text!r} is already another bundle's line")
        if text in all_options:
            fail(f"{fid}: {text!r} is a conflict option's own text")
        if kind not in KINDS:
            fail(f"{fid}: kind {kind!r} is not one of {sorted(KINDS)}")
            continue
        wanted = KINDS[kind][0]
        value = f.get("value")
        if wanted is None and value is not None:
            fail(f"{fid}: {kind} takes no value")
        elif wanted is int and (not isinstance(value, int) or isinstance(value, bool)
                                or not 1 < value < 1000):
            fail(f"{fid}: {kind} needs a whole-number value")
        elif wanted is str and not (isinstance(value, str) and value.strip()):
            fail(f"{fid}: {kind} needs a word as its value")

    # The ten trials, on the grid, every line accounted for.
    trials = bundle["trials"]
    if [(t.get("n_instructions"), t.get("k_conflict_groups"), t.get("group_size"))
            for t in trials] != list(bundles.GRID):
        fail(f"the trials are not the grid {list(bundles.GRID)}, in that order")
    for i, trial in enumerate(trials, start=1):
        tid = trial.get("trial_id")
        if tid != f"{bid}-{i:02d}":
            fail(f"trial {i} is {tid!r}, not {bid}-{i:02d}")
        lines = trial.get("lines") or []
        if len(lines) != trial.get("n_instructions") or len(set(lines)) != len(lines):
            fail(f"{tid}: {len(lines)} lines, {len(set(lines))} distinct, for n = "
                 f"{trial.get('n_instructions')}")
        groups = trial.get("conflict_groups") or []
        members: set[str] = set()
        for j, g in enumerate(groups, start=1):
            if g.get("group") != f"G{j}" or g.get("scenario_id") not in comps:
                fail(f"{tid}: group {j} must be G{j} over a component scenario")
                continue
            ids = g.get("members") or []
            if len(ids) != trial.get("group_size") or len(set(ids)) != len(ids):
                fail(f"{tid}: {g['group']} has {len(ids)} members, not {trial.get('group_size')}")
            for oid in ids:
                text = option_text.get((g["scenario_id"], oid))
                if text is None:
                    fail(f"{tid}: {g['scenario_id']} has no option {oid!r}")
                elif lines.count(text) != 1:
                    fail(f"{tid}: {g['scenario_id']} {oid} ({text!r}) is not one of the lines")
                else:
                    members.add(text)
        if len({g.get("scenario_id") for g in groups}) != len(groups):
            fail(f"{tid}: two groups over one scenario")
        if trial.get("k_conflict_groups") == 6 and {g.get("scenario_id") for g in groups} != set(comps):
            fail(f"{tid}: six groups must use all six components")
        for line in lines:
            if line not in members and line not in texts:
                fail(f"{tid}: {line!r} is neither a conflict member nor one of the fillers")

    # Rendered as recorded, tools that do not clash, every filler scored.
    bank = bundles.bank_of(bundle, scenarios)
    head = bundles.header(bundle)
    for trial in bundles.as_trials(bundle):
        rec = reconstruct(trial, scenarios, head)
        if rec.spec is None or not rec.exact:
            fail(f"{trial['trial_id']}: does not render as recorded: {rec.diff()}")
            continue
        try:
            tools_for_trial(rec.spec, scenarios)
            render_dicts(rec.spec, scenarios)
        except RenderError as exc:
            fail(f"{trial['trial_id']}: {exc}")
        for line in trial["messages"][0]["content"].split("\n"):
            if line in bank and bank[line].check is None:
                fail(f"{trial['trial_id']}: {line!r} cannot be scored")

    # One length per n-level, in each pinned tokenizer.
    for family, tok in (tokenizers or {}).items():
        levels: dict[int, dict[str, int]] = collections.defaultdict(dict)
        for trial in trials:
            levels[trial["n_instructions"]][trial["trial_id"]] = token_count(
                tok, "\n".join(trial["lines"]))
        info["tokens"][family] = {n: dict(v) for n, v in sorted(levels.items())}
        for n, counts in sorted(levels.items()):
            if len(set(counts.values())) != 1:
                fail(f"{family} tokens differ at n = {n}: {counts}")
    return fails, info


def check_all(tokens: bool = True) -> tuple[list[str], list[dict]]:
    scenarios = load_scenarios()
    docs = bundles.load_bundles()
    toks = pinned_tokenizers() if tokens else {}
    fails, infos = [], []
    for i, doc in enumerate(docs):
        f, info = check_bundle(doc, scenarios, others=docs[:i] + docs[i + 1:], tokenizers=toks)
        fails += f
        infos.append(info)
    if tokens and len(toks) < 2:
        infos.append({"note": f"token lengths checked under {sorted(toks) or 'no'} tokenizer(s): "
                              f"the others are not in the local Hugging Face cache"})
    return fails, infos


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m whowins.validation.check_load",
                                     description="Check every load bundle in data/load/.")
    parser.add_argument("--lines", action="store_true",
                        help="also print every line's length in each pinned tokenizer")
    args = parser.parse_args(argv)
    fails, infos = check_all()
    toks = pinned_tokenizers() if args.lines else {}
    for info in infos:
        if "note" in info:
            print(f"  note: {info['note']}")
            continue
        print(f"{info['bundle_id']}")
        for family, levels in info["tokens"].items():
            print(f"  {family:8s} " + "  ".join(
                f"n={n}: {sorted(set(c.values()))}" for n, c in levels.items()))
        if args.lines:
            doc = bundles.by_id(info["bundle_id"])
            for text in sorted({line for t in doc["trials"] for line in t["lines"]}):
                print("    " + " ".join(f"{token_count(t, text):3d}" for t in toks.values())
                      + f"  {text}")
    for message in fails:
        print(f"  FAIL {message}")
    print(f"{len(infos) - sum('note' in i for i in infos)} bundles | {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(_main())
