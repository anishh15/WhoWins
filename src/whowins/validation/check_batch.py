"""Review harness. READ-ONLY, and not a generator.
Run at review time against the whole collection; a batch is committed only if this reports
no FAIL. It always screens duplication against everything, even when given one batch file."""

import glob, itertools, json, os, re, sys

try:
    from ..data import ROOT  # the checkout, or the data an installed package carries
except ImportError:  # run as a script, from a checkout
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
fails, warns = [], []


def fail(m): fails.append(m)
def warn(m): warns.append(m)


def reset():
    """Empty both verdict lists. They are module-level so every screen can reach
    them, which means a second run in one process -- a test, say -- would
    otherwise inherit the first run's failures and report ones already fixed."""
    fails.clear()
    warns.clear()


def load():
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/scenarios/*/*.json"))):
        rel = os.path.relpath(f, ROOT)
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
        except ValueError as e:  # JSONDecodeError and UnicodeDecodeError both are
            fail(f"{rel}: does not parse -- {e}")
            continue
        for s in data:
            if "scenario_id" in s:
                s["_file"] = rel
                out.append(s)
    return out


def words(t): return t.split()


def vset(s):
    return (s["checker_key"], frozenset(o["checker"].split("==", 1)[1] for o in s["options"]))


def skeleton(s):
    """Words shared by every option: two scenarios with one key and one core are one template.
    Skipped for refusal, ordering, tool and path, whose families have a fixed option vocabulary
    that would make every item look like a template of every other."""
    if s["family"] in ("refusal", "ordering", "tool", "path"):
        return None
    sets = [set(words(o["text"])) for o in s["options"]]
    core = set.intersection(*sets)
    # A one- or two-word overlap ("the", "as") is English, not a template.
    if len(core) < 3:
        return None
    return frozenset(core)


def suffix_set(s):
    """For tool and path: the distinguishing part of each value once the shared
    prefix is removed. Two scenarios reusing {a,b,c,d,e} or {1,2,3,4,5} are one
    template; two using {leak,heap,stack} and {api,abi,runtime} are not."""
    if s["family"] not in ("tool", "path"):
        return None
    tok = [set(re.split(r"[_\-/.]", o["checker"].split("==", 1)[1].lower()))
           for o in s["options"]]
    shared = set.intersection(*tok)
    return frozenset(frozenset(t - shared) for t in tok)


def content_key(s):
    """What has to be unique across the collection, per family.
    refusal is {comply, decline} by nature, so its labels carry no uniqueness and its
    distinctness lives in the task and the two option texts instead."""
    if s["family"] == "refusal":
        return None
    if s["family"] == "ordering":
        steps = set()
        for o in s["options"]:
            steps.update(o["checker"].split("==", 1)[1].strip("[]").split(","))
        return ("ordering_steps", frozenset(steps))
    return vset(s)


def jaccard(a, b):
    A, B = set(words(a.lower())), set(words(b.lower()))
    return len(A & B) / len(A | B) if A | B else 0.0


# ---------------------------------------------------------------- per scenario

# Vendor product names, which may never appear. Standards, languages, platform triples and package schemes used as CONTEXT are excluded: the line is whether the name is the choice being measured or the setting it sits in.
REAL_NAMES = ["datadog", "valgrind", "asan", "eslint", "pylint", "jest", "pytest", "mypy",
              "prettier", "ruff", "clang", "kubectl", "terraform", "ansible", "jenkins",
              "grafana", "sentry", "splunk", "kafka", "redis", "postgres", "mysql",
              "nginx", "snyk", "trivy", "github", "gitlab", "jira", "slack", "stripe",
              "npm", "pypi", "maven", "gradle", "webpack", "babel", "django", "laravel",
              "prometheus", "elasticsearch", "kibana", "rabbitmq", "airflow", "dbt",
              "snowflake", "databricks", "tableau", "okta", "auth0", "zendesk",
              "intercom", "hubspot", "shopify", "salesforce", "twilio", "sendgrid",
              "cloudflare", "vercel", "netlify", "heroku", "etcd", "cassandra",
              "dynamodb", "clickhouse", "neo4j"]

# Brand names that are also ordinary English words. These WARN rather than fail, because a ship has a helm and a human decides.
AMBIGUOUS_NAMES = ["cargo", "helm", "spring", "rails", "celery", "consul", "vault",
                   "nomad", "looker", "segment", "signal", "edge", "square", "meta",
                   "linear", "sketch", "flask", "monday", "teams"]
# Where a vendor name is legitimately the SETTING rather than the choice. Each is a reviewed exception, not a blanket allowance.
NAME_EXEMPT = {
    "pypi": ["path-0139", "path-0154"],   # pypi:// scheme; choice is opaque slot codes
    "maven": ["path-0137", "path-0157"],  # mvn:// scheme; choice is opaque slot codes
    "cargo": ["path-0144"],               # cargo:// scheme; choice is opaque slot codes
    "helm": ["path-0056", "path-0117", "path-0151", "tool-0070"],  # chart path / operation
    "npm": ["path-0126", "path-0131", "path-0153"],  # named only in a note or seed_family
    "gradle": ["path-0147"],              # plugin slot; choice is opaque
}

# SCREEN 6 -- nothing reachable. The collection's synthetic destinations use an UNDOTTED authority and are deliberately left alone; an IP address only warns, because a four-part version is the same shape.
HOST_FAILS = [
    (re.compile(r"https?://", re.I), "a URL"),
    (re.compile(r"\bgithub\.com\b", re.I), "a real host"),
    (re.compile(r"@[a-z0-9.-]+\.[a-z]{2,}", re.I), "an email address"),
    (re.compile(r"(?<![a-z0-9+.-])(?!https?://)[a-z][a-z0-9+.-]*://[a-z0-9-]+(?:\.[a-z0-9-]+)+",
                re.I), "a URL naming a network host"),
    (re.compile(r"(?<![a-z0-9_.@/-])(?:[a-z0-9-]+\.)+(?:com|org|net|io|dev|edu|gov)(?![a-z0-9_-])",
                re.I), "a public domain name"),
]
IP_LIKE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")


def host_findings(blob):
    """Every way `blob` names something reachable, as (level, reason) pairs."""
    out = [("fail", why) for pat, why in HOST_FAILS if pat.search(blob)]
    out += [("warn", f"{ip!r}, which is shaped like an IP address -- confirm it names "
                     f"nothing real") for ip in IP_LIKE.findall(blob)]
    return out


REQUIRED = ["scenario_id", "family", "seed_family", "domain", "difficulty",
            "task", "checker_key", "key_source", "exclusivity", "options",
            "authored_by", "source"]


DELIBERATES = re.compile(
    r"^(decide|say|choose|pick|settle|determine|work out|agree|figure)\b", re.I)
"""Openings that ask for a position rather than for something written.

Applied to the format family only. The other four are scored off a trace, where
"Work out what changed in payments.py" is answered by calling a tool and the
call is the measurement -- so the same opening is perfectly sound there.
"""


def check_one(s):
    sid = s["scenario_id"]
    missing = [k for k in REQUIRED if k not in s]
    for k in missing:
        fail(f"{sid}: missing field '{k}'")
    if missing:
        return

    n_expected = 2 if s.get("binary") or s.get("family") == "refusal" else 5
    if len(s["options"]) != n_expected:
        fail(f"{sid}: {len(s['options'])} options, expected {n_expected}")

    # SCREEN 2 -- exclusivity by construction
    keys = {o["checker"].split("==", 1)[0] for o in s["options"]}
    if len(keys) != 1:
        fail(f"{sid}: options mix checker keys {sorted(keys)} -- an output could satisfy two")
    elif s.get("checker_key") not in keys:
        fail(f"{sid}: checker_key '{s.get('checker_key')}' != key used in options {sorted(keys)}")
    vals = [o["checker"].split("==", 1)[1] for o in s["options"]]
    if len(set(vals)) != len(vals):
        fail(f"{sid}: repeated checker value inside the set: {vals}")
    if len(s.get("exclusivity", "")) < 60:
        warn(f"{sid}: exclusivity argument is thin ({len(s.get('exclusivity',''))} chars)")

    # SCREEN 3 -- length
    L = [len(words(o["text"])) for o in s["options"]]
    spread = (max(L) - min(L)) / (sum(L) / len(L))
    if spread > 0.20:
        fail(f"{sid}: option length spread {spread:.0%} > 20% (words {min(L)}-{max(L)})")

    # SCREEN 6 -- honest sourcing
    src = s.get("source", {})
    if src.get("status") != "synthetic-preview":
        fail(f"{sid}: source.status is {src.get('status')!r}, expected 'synthetic-preview'")
    if src.get("url") is not None:
        fail(f"{sid}: source.url must be null, got {src.get('url')!r}")
    blob = json.dumps(s)
    for level, why in host_findings(blob):
        (fail if level == "fail" else warn)(f"{sid}: contains {why}")

    # SCREEN 4 signal -- does the task itself single out one option?
    task_words = set(re.findall(r"[a-z]+", s["task"].lower()))
    tok = {o["id"]: set(re.split(r"[_\-/.]", o["checker"].split("==", 1)[1].lower()))
           for o in s["options"]}
    if len(tok) > 1:
        shared_tok = set.intersection(*tok.values())
        hit = [(k, sorted((v - shared_tok) & task_words)) for k, v in tok.items()
               if (v - shared_tok) & task_words]
        if len(hit) == 1:
            warn(f"{sid}: task mentions {hit[0][1]}, which singles out option {hit[0][0]} -- "
                 f"a model could answer this without reference to any source")

    # SCREEN 9 -- does a format task ask for an artifact? A task opening "Decide how..." asks for a position, and the 21 items below chose an option in 11% of trials against 25% for the rest. It WARNS: a keyword does not condemn an item, the solo arm decides.
    if s.get("family") == "format" and DELIBERATES.match(s["task"]):
        warn(f"{sid}: the task asks the model to decide rather than to produce "
             f"({s['task']!r}) -- a position is not an artifact, and this family "
             f"is scored from one. Check it against the solo arm before rewriting")

    # SCREEN 6 -- no real products, companies or people
    for name in REAL_NAMES:
        # not \b -- underscore is a word char, so \bdatadog\b misses "export_datadog"
        if re.search(rf"(?<![a-z0-9]){name}(?![a-z0-9])", blob, re.I):
            if sid in NAME_EXEMPT.get(name, []):
                continue
            fail(f"{sid}: names a real product or company ({name!r})")
    for name in AMBIGUOUS_NAMES:
        if re.search(rf"(?<![a-z0-9]){name}(?![a-z0-9])", blob, re.I):
            if sid in NAME_EXEMPT.get(name, []):
                continue
            warn(f"{sid}: contains {name!r}, which is both an ordinary word and a "
                 f"product name -- confirm it reads as the ordinary word")

    if s.get("difficulty") not in ("easy", "medium", "hard"):
        fail(f"{sid}: difficulty {s.get('difficulty')!r} not easy/medium/hard")
    if not re.fullmatch(r"[a-z0-9-]+/[a-z0-9.-]+", str(s.get("authored_by", ""))):
        fail(f"{sid}: authored_by {s.get('authored_by')!r} is not <pipeline>/<model>")


# ------------------------------------------------------------- across the collection

def check_collection(all_s):
    def dup(getter, label, screen):
        seen = {}
        for s in all_s:
            k = getter(s)
            if k in seen:
                fail(f"[{screen}] {label} repeated: {seen[k]} and {s['scenario_id']} -> {k}")
            seen[k] = s["scenario_id"]

    dup(lambda s: s["scenario_id"], "scenario_id", "dup")
    dup(lambda s: s["seed_family"], "seed_family", "dup")

    seen = {}
    for s in all_s:
        k = content_key(s)
        if k is None:
            continue
        if k in seen:
            fail(f"[dup] content repeated: {seen[k]} and {s['scenario_id']} -> {k}")
        seen[k] = s["scenario_id"]

    # near-duplicate value sets: same key, all but one label shared
    keyed = [s for s in all_s if content_key(s) is not None]
    for a, b in itertools.combinations(keyed, 2):
        ka, va = content_key(a)
        kb, vb = content_key(b)
        if ka == kb and va != vb and len(va & vb) >= len(va) - 1:
            fail(f"[dup] near-duplicate value set: {a['scenario_id']} and {b['scenario_id']} "
                 f"share {len(va & vb)}/{len(va)} of key '{ka}'")

    # scenarios sharing most of their option text
    for a, b in itertools.combinations(all_s, 2):
        ta = {o["text"] for o in a["options"]}
        tb = {o["text"] for o in b["options"]}
        if len(ta & tb) >= max(2, len(ta) - 1):
            fail(f"[dup] {a['scenario_id']} and {b['scenario_id']} share "
                 f"{len(ta & tb)}/{len(ta)} identical option texts")

    # near-duplicate tasks
    for a, b in itertools.combinations(all_s, 2):
        j = jaccard(a["task"], b["task"])
        if j >= 0.80:
            fail(f"[dup] tasks {j:.0%} alike: {a['scenario_id']} / {b['scenario_id']}\n"
                 f"        {a['task']}\n        {b['task']}")

    shapes = {}
    for s in all_s:
        ss = suffix_set(s)
        if ss is not None:
            shapes.setdefault(ss, []).append(s["scenario_id"])
    for shape, ids in shapes.items():
        if len(ids) > 1:
            fail(f"[template] {len(ids)} scenarios reuse one suffix set: {ids}")

    # SCREEN 8 -- templating. Same key + same shared-word core = one template reused.
    shapes = {}
    for s in all_s:
        sk = skeleton(s)
        if sk is not None:
            shapes.setdefault(sk, []).append(s["scenario_id"])
    for shape, ids in shapes.items():
        if len(ids) > 1:
            fail(f"[template] {len(ids)} scenarios share one option skeleton "
                 f"{sorted(shape)}: {ids}")

    # templating, second signal: options that differ from each other by exactly one word
    for s in all_s:
        pairs = list(itertools.combinations([o["text"] for o in s["options"]], 2))
        one_word = sum(1 for x, y in pairs
                       if len(set(words(x)) ^ set(words(y))) <= 2 and len(words(x)) == len(words(y)))
        if (s["family"] not in ("refusal", "ordering") and pairs and one_word == len(pairs)
                and len(words(s["options"][0]["text"])) > 6):
            warn(f"[template] {s['scenario_id']}: every option pair differs by one word -- "
                 f"check this was written, not permuted")


def report(all_s, focus):
    fam = {}
    for s in all_s:
        fam.setdefault(s["family"], []).append(s)
    print("COLLECTION")
    for f, ss in sorted(fam.items()):
        print(f"  {f:9} {len(ss):>4} scenarios, {len(set(x['domain'] for x in ss))} domains")
    print(f"  {'TOTAL':9} {len(all_s):>4}")
    by = {}
    for s_ in all_s:
        by[s_.get("authored_by", "?")] = by.get(s_.get("authored_by", "?"), 0) + 1
    print("  authored by " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))

    if focus:
        b = [s for s in all_s if s["_file"].endswith(focus)]
        if b:
            print(f"\nBATCH {focus}  ({len(b)} scenarios)")
            for label, key in (("domain", "domain"), ("difficulty", "difficulty")):
                c = {}
                for s in b:
                    c[s[key]] = c.get(s[key], 0) + 1
                print(f"  {label:11} {dict(sorted(c.items(), key=lambda x: -x[1]))}")
            print(f"  distinct keys   {len(set(s['checker_key'] for s in b))}")
            print(f"  distinct vsets  {len(set(vset(s) for s in b))}")

    print(f"\n{len(fails)} FAIL, {len(warns)} WARN")
    for m in fails:
        print("  FAIL " + m)
    for m in warns:
        print("  warn " + m)
    return 1 if fails else 0


def check_all(scenarios):
    """Every screen, one scenario at a time and then across them. Returns the ones the
    collection screens read: a scenario missing a field already has its FAIL."""
    for sc in scenarios:
        check_one(sc)
    whole = [sc for sc in scenarios if all(k in sc for k in REQUIRED)]
    check_collection(whole)
    return whole


def main(argv):
    reset()
    return report(check_all(load()), argv[0] if argv else None)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
