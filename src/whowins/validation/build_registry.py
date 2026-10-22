"""Regenerate REGISTRY.md from the collection. READ-ONLY over scenario content.
It summarises what already exists so the next batch cannot collide with it. Not a
generator: it never invents a scenario, it only lists ids already written."""

import glob, json, os

try:
    from ..data import IN_CHECKOUT, ROOT, WORK  # the checkout, or the data an installed package carries
except ImportError:  # run as a script, from a checkout
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    IN_CHECKOUT, WORK = True, ROOT
OUT = os.path.join(ROOT, "data/REGISTRY.md") if IN_CHECKOUT else os.path.join(WORK, "REGISTRY.md")


def main():
    # An author may be mid-write, so a file that does not parse is SKIPPED LOUDLY rather than silently producing a registry missing a batch.
    fams, skipped = {}, []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/scenarios/*/*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:
            skipped.append(f"{os.path.basename(f)} ({type(e).__name__}: {e})")
            continue
        for s in data:
            if "scenario_id" in s:
                fams.setdefault(s["family"], []).append(s)

    if skipped:
        print("!! SKIPPED unparseable files -- registry is INCOMPLETE, do not hand it out:")
        for x in skipped:
            print("   " + x)

    L = ["# Registry — everything already written",
         "",
         "Generated from the collection by `build_registry.py`. **Read this before authoring a batch.**",
         "Nothing you write may repeat a `seed_family`, a five-value set, or a task from this file.",
         ""]

    L.append(f"Collection: {sum(len(v) for v in fams.values())} scenarios — "
             + ", ".join(f"{k} {len(v)}" for k, v in sorted(fams.items())))
    L.append("")

    L.append("## Taken `seed_family` values — every one of these is unavailable")
    L.append("")
    allsf = sorted(s["seed_family"] for v in fams.values() for s in v)
    for i in range(0, len(allsf), 6):
        L.append("`" + "` · `".join(allsf[i:i + 6]) + "`")
    L.append("")

    for fam in sorted(fams):
        ss = sorted(fams[fam], key=lambda x: x["scenario_id"])
        L += [f"## {fam} — {len(ss)} taken", ""]
        if fam == "refusal":
            L.append("Every refusal item is `{comply, decline}` by nature, so distinctness lives in the "
                     "situation. Do not repeat any of these situations.")
            L += ["", "| id | seed_family | situation |", "|---|---|---|"]
            for s in ss:
                L.append(f"| {s['scenario_id']} | `{s['seed_family']}` | {s['task']} |")
        elif fam == "ordering":
            L.append("What must be unique is **which three steps**, not which permutations were kept. "
                     "Do not reuse any of these step triples.")
            L += ["", "| id | seed_family | steps | task |", "|---|---|---|---|"]
            for s in ss:
                steps = set()
                for o in s["options"]:
                    steps.update(o["checker"].split("==", 1)[1].strip("[]").split(","))
                L.append(f"| {s['scenario_id']} | `{s['seed_family']}` | {', '.join(sorted(steps))} | {s['task']} |")
        else:
            L.append("Do not reuse any of these five-value sets. A `checker_key` may be reused **only** "
                     "with a genuinely different set of five values.")
            L += ["", "| id | seed_family | key | the five values | task |", "|---|---|---|---|---|"]
            for s in ss:
                vals = ", ".join(o["checker"].split("==", 1)[1] for o in s["options"])
                L.append(f"| {s['scenario_id']} | `{s['seed_family']}` | `{s['checker_key']}` | {vals} | {s['task']} |")
        L.append("")

    text = "\n".join(L) + "\n"
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"REGISTRY.md: {sum(len(v) for v in fams.values())} scenarios, "
          f"{len(allsf)} seed_family values, {len(text.encode('utf-8'))} bytes")
    if skipped:
        raise SystemExit("registry incomplete -- rerun once the files above parse")


if __name__ == "__main__":
    main()
