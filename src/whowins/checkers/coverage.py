"""Which scenarios are executable, and which are not.
"Not implemented" must be a fact you can query, never a silent pass: `check` raises
UnknownCheckerKey on an unimplemented key, and this says how many there are and which
scenarios they block."""

from __future__ import annotations

from collections import defaultdict

from ..data import iter_scenarios
from .core import has_checker


def load_collection() -> list[dict]:
    return [s for _, s in iter_scenarios()]


def report() -> dict:
    collection = load_collection()
    per_family = defaultdict(lambda: {"total": 0, "executable": 0})
    missing_keys: dict[str, str] = {}

    for s in collection:
        fam = s["family"]
        per_family[fam]["total"] += 1
        if has_checker(s["checker_key"]):
            per_family[fam]["executable"] += 1
        else:
            missing_keys[s["checker_key"]] = s["scenario_id"]

    return {
        "total": len(collection),
        "executable": sum(v["executable"] for v in per_family.values()),
        "per_family": dict(per_family),
        "missing_keys": missing_keys,
    }


def main() -> None:
    r = report()
    print(f"WhoWins checker coverage: {r['executable']}/{r['total']} scenarios executable "
          f"({100 * r['executable'] / r['total']:.0f}%)\n")
    print(f"  {'family':10} {'executable':>12} {'total':>7}")
    for fam, v in sorted(r["per_family"].items()):
        print(f"  {fam:10} {v['executable']:>12} {v['total']:>7}")

    if not r["missing_keys"]:
        print("\nEvery checker key is implemented.")
        return

    print(f"\n{len(r['missing_keys'])} unimplemented keys:\n")
    for key, sid in sorted(r["missing_keys"].items(), key=lambda kv: kv[1]):
        print(f"      {sid}  {key}")
    print("\n  Write the classifier, or rewrite the scenario. Do not write one that")
    print("  guesses: a fake win for a guessed label is worse than no measurement.")


if __name__ == "__main__":
    main()
