"""Deep structural validation of the whole collection. READ-ONLY.
`check_batch.py` enforces the cross-cutting screens; this checks the invariants specific to
each family, plus what a batch author could get wrong without breaking the schema."""

import glob, itertools, json, os, re, sys, collections

try:
    from ..data import ROOT  # the checkout, or the data an installed package carries
except ImportError:  # run as a script, from a checkout
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
fails, warns = [], []
def fail(m): fails.append(m)
def warn(m): warns.append(m)


def reset():
    """Empty both verdict lists, so a second run in one process starts clean."""
    fails.clear()
    warns.clear()


FAMILY_SPEC = {
    "format":   dict(prefix="fmt",  n=5, key=None,              src="classifier"),
    "tool":     dict(prefix="tool", n=5, key="first_tool_call", src="trace"),
    "path":     dict(prefix="path", n=5, key="write_target",    src="trace"),
    "ordering": dict(prefix="ord",  n=5, key="step_order",      src="trace"),
    "refusal":  dict(prefix="ref",  n=2, key="decision",        src="trace"),
}
TARGET = {"format": 240, "tool": 240, "path": 240, "ordering": 240, "refusal": 120}

STOP = set("""a an the of to in on at for with by from and or not is are be as it its this that
those these your you we our their his her they them he she if then than into over under about
each every all any some no nor but so such only just also more most other another same own can
will would should could may might must do does did done have has had been being when where which
who whom what how why while after before during until up down out off again further once here
there both few many much own too very s t don now one two three next last new old make made""".split())


def load():
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/scenarios/*/*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:
            fail(f"{os.path.relpath(f, ROOT)}: does not parse ({type(e).__name__}: {e})")
            continue
        for s in data:
            if "scenario_id" in s:
                s["_file"] = os.path.relpath(f, ROOT)
                s["_dir"] = f.split(os.sep)[-2]
                out.append(s)
    return out


def check(s):
    sid, fam = s["scenario_id"], s.get("family")
    spec = FAMILY_SPEC.get(fam)

    if fam != s["_dir"]:
        fail(f"{sid}: family {fam!r} but lives in {s['_dir']}/")
        return
    if not spec:
        fail(f"{sid}: unknown family {fam!r}")
        return
    if not sid.startswith(spec["prefix"] + "-"):
        fail(f"{sid}: id prefix does not match family {fam}")
    if s.get("key_source") != spec["src"]:
        fail(f"{sid}: key_source {s.get('key_source')!r}, expected {spec['src']!r}")

    opts = s.get("options", [])
    if len(opts) != spec["n"]:
        fail(f"{sid}: {len(opts)} options, family {fam} requires {spec['n']}")
    want_ids = [f"o{i+1}" for i in range(len(opts))]
    if [o.get("id") for o in opts] != want_ids:
        fail(f"{sid}: option ids {[o.get('id') for o in opts]}, expected {want_ids}")

    keys = {o["checker"].split("==", 1)[0] for o in opts if "checker" in o}
    if spec["key"] and keys != {spec["key"]}:
        fail(f"{sid}: uses keys {sorted(keys)}, family {fam} requires {spec['key']!r}")

    for fld in ("task", "exclusivity", "seed_family"):
        if not str(s.get(fld, "")).strip():
            fail(f"{sid}: empty {fld}")
    for o in opts:
        if not str(o.get("text", "")).strip():
            fail(f"{sid}/{o.get('id')}: empty option text")

    vals = [o["checker"].split("==", 1)[1] for o in opts if "checker" in o]

    # ---- family-specific invariants
    if fam == "refusal":
        if set(vals) != {"comply", "decline"}:
            fail(f"{sid}: refusal values {vals}, must be exactly comply/decline")
        if s.get("binary") is not True:
            warn(f"{sid}: refusal item missing \"binary\": true")
        # The gated action is what makes comply readable from the trace. All 120 once lacked one and were scored from prose.
        tool = s.get("action_tool")
        if not tool:
            fail(f"{sid}: refusal item names no action_tool -- comply could be read "
                 f"only from prose")
        elif not re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", str(tool)):
            fail(f"{sid}: action_tool {tool!r} is not a snake_case name of two "
                 f"words or more")
    elif "action_tool" in s:
        fail(f"{sid}: action_tool on a {fam} item -- only refusal items gate an action")

    if fam == "ordering":
        seqs = []
        for v in vals:
            if not (v.startswith("[") and v.endswith("]")):
                fail(f"{sid}: step_order value {v!r} is not bracketed")
                continue
            seqs.append(v[1:-1].split(","))
        if seqs:
            if any(len(x) != 3 for x in seqs):
                fail(f"{sid}: every ordering value must name exactly three steps")
            base = set(seqs[0])
            if len(base) != 3:
                fail(f"{sid}: repeated step inside one ordering: {seqs[0]}")
            for x in seqs[1:]:
                if set(x) != base:
                    fail(f"{sid}: options are not permutations of one step set "
                         f"({sorted(base)} vs {sorted(set(x))})")
            if len({tuple(x) for x in seqs}) != len(seqs):
                fail(f"{sid}: repeated permutation among options")

            # `dropped_permutation` must name the order the options leave out. Written "a, b, c" while option values are "[a,b,c]", so both are normalised first.
            wellformed = (len(base) == 3 and len(seqs) == 5
                          and all(set(x) == base for x in seqs)
                          and len({tuple(x) for x in seqs}) == 5)
            dp = s.get("dropped_permutation")
            if dp is None:
                warn(f"{sid}: ordering item has no dropped_permutation")
            elif wellformed:
                missing = [list(p) for p in itertools.permutations(sorted(base))
                           if list(p) not in seqs]
                got = [w.strip() for w in str(dp).strip("[]").split(",")]
                if got != missing[0]:
                    fail(f"{sid}: dropped_permutation says {got}, "
                         f"but the options omit {missing[0]}")

    if fam == "path":
        root = s.get("sandbox_root")
        if not root:
            warn(f"{sid}: path item has no sandbox_root")
        else:
            outside = [v for v in vals if not v.startswith(root)]
            if outside:
                fail(f"{sid}: targets outside sandbox_root {root!r}: {outside}")

    if fam == "tool":
        ta = s.get("tools_available")
        if ta is None:
            warn(f"{sid}: tool item has no tools_available")
        elif sorted(ta) != sorted(vals):
            fail(f"{sid}: tools_available {sorted(ta)} != option values {sorted(vals)}")

    # ---- giveaway, stopwords removed
    task_w = set(re.findall(r"[a-z]+", str(s.get("task", "")).lower())) - STOP
    tok = {o["id"]: set(re.split(r"[_\-/.\[\],]", o["checker"].split("==", 1)[1].lower()))
           for o in opts if "checker" in o}
    if len(tok) > 1:
        shared = set.intersection(*tok.values())
        hit = [(k, sorted((v - shared) & task_w)) for k, v in tok.items() if (v - shared) & task_w]
        if len(hit) == 1 and hit[0][1]:
            warn(f"GIVEAWAY {sid}: task word {hit[0][1]} singles out {hit[0][0]}"
                 f"{'' if s.get('note') else '  [no note]'}")


def check_collection(all_s):
    by = collections.defaultdict(list)
    for s in all_s:
        by[s.get("family")].append(s)
    for fam, want in TARGET.items():
        got = len(by[fam])
        if got != want:
            fail(f"{fam}: {got} scenarios, plan target is {want}")
        ids = sorted(int(x["scenario_id"].split("-")[1]) for x in by[fam])
        missing = [n for n in range(1, want + 1) if n not in set(ids)]
        if missing:
            fail(f"{fam}: ids not contiguous 1..{want}, missing {missing[:10]}")

    # each refusal item gates its own action
    named = collections.Counter(s["action_tool"] for s in all_s if s.get("action_tool"))
    for tool, n in sorted(named.items()):
        if n > 1:
            fail(f"action_tool {tool!r} is named by {n} refusal items -- each gates "
                 f"its own action")

    # trials must still point at real scenarios with matching checkers
    # .get throughout: a scenario missing a field has its FAIL from check(), and must not raise here.
    idx = {s["scenario_id"]: {o.get("id"): o.get("checker") for o in s.get("options", [])}
           for s in all_s}
    for f in sorted(glob.glob(os.path.join(ROOT, "data/trials/*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                trials = json.load(fh)
        except Exception as e:
            fail(f"{os.path.relpath(f, ROOT)}: does not parse ({type(e).__name__}: {e})")
            continue
        for t in trials:
            if "trial_id" not in t:
                continue
            groups = [(t.get("scenario_id"), t.get("checkers", {}))] + \
                     [(g["scenario_id"], g["checkers"]) for g in t.get("conflict_groups", [])]
            for sid, cks in groups:
                if sid is None:
                    continue
                if sid not in idx:
                    fail(f"trial {t['trial_id']}: unknown scenario {sid}")
                    continue
                for oid, ck in cks.items():
                    if oid not in idx[sid]:
                        fail(f"trial {t['trial_id']}: {sid} has no option {oid}")
                    elif idx[sid][oid] != ck:
                        fail(f"trial {t['trial_id']}: {sid}/{oid} checker drift\n"
                             f"      trial:    {ck}\n      scenario: {idx[sid][oid]}")


def main():
    reset()
    S = load()
    for s in S:
        check(s)
    check_collection(S)
    g = [w for w in warns if w.startswith("GIVEAWAY")]
    o = [w for w in warns if not w.startswith("GIVEAWAY")]
    print(f"{len(S)} scenarios | {len(fails)} FAIL | {len(o)} warn | {len(g)} giveaway")
    for m in fails: print("  FAIL " + m)
    for m in o[:40]: print("  warn " + m)
    if len(o) > 40: print(f"  ... {len(o)-40} more warns")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
