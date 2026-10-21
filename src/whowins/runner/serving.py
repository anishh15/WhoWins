"""The fifteen models, the two places they are served, and what a request must be.
A machine is part of the experiment: every model names its environment, every record
carries it, and a claim about what an engine does lives in ENGINE_PROFILES, read out
of that version's source -- never in a config, which would let anyone declare it."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

from ..data import ROOT, read_json
from .rendering import Scenarios, render_dicts
from .run import Decoding, ServingStack, build_request
from .spec import TrialSpec

CONFIGS = os.path.join(ROOT, "configs")
ROSTER_FILE = os.path.join(CONFIGS, "models.json")
ENVIRONMENT_FILE = os.path.join(CONFIGS, "environments.json")
POLICY_FILE = os.path.join(CONFIGS, "decoding.json")
RUNS_DIR = os.path.join(CONFIGS, "runs")

SAMPLING_FIELDS = ("temperature", "top_p", "top_k", "min_p", "presence_penalty",
                   "frequency_penalty", "repetition_penalty", "seed", "max_tokens")
"""Every setting of one draw. A request that leaves one out gets the server's
default, which is vLLM's or the checkpoint's depending on how it was started."""

EFFORTS = ("low", "medium", "high")

POLICY_ROLES = ("study", "card-check", "effort-condition")
"""What a decoding policy is for. `study` is what the study runs on; `card-check`
reruns a slice under a model card's own numbers, to price the departure;
`effort-condition` is a condition inside a checkpoint, as #86 settled."""

SEPARATIONS = ("server", "client")
"""Who splits a model's thinking from its answer: the engine's reasoning parser,
or `whowins.runner.response` reading the raw text."""


# --- What each engine does, read out of its source ---


@dataclass(frozen=True)
class EngineProfile:
    """The rules of one engine version, and the flags it actually has.
    Per engine version rather than per environment: two machines on vLLM 0.28.0 obey the
    same rules. In code and not in configs, because every line was read out of that
    version's source and a JSON file would let someone declare a behaviour nobody checked."""

    key: str
    requires: Mapping[str, Any]
    forbids: tuple[str, ...]
    family_flags: Mapping[str, Mapping[str, Any]]
    notes: str = ""


_COMMON_REQUIRES: dict[str, Any] = {
    "generation-config": "vllm",
    "no-enable-prefix-caching": True,
    "seed": 0,
}
"""Held by every serve file, at either engine.

    generation-config vllm     no sampling default comes from the checkpoint
    no-enable-prefix-caching   a cached prefix was computed inside another batch,
                               and vLLM's caching for Qwen 3.5's linear-attention
                               layers is still experimental. The no- form fails
                               loudly if the flag ever goes away;
                               `enable-prefix-caching: false` would be dropped
                               without a word, leaving caching on
    seed 0                     the engine's seed, stated; each request brings its own

dtype, kv-cache-dtype and gpu-memory-utilization are required too, from the
environment: they differ by machine, and the V100 has no bfloat16.
"""

_COMMON_FORBIDS = (
    "enable-prefix-caching",
    "trust-remote-code",
    "speculative-config",
    "chat-template",
    "trust-request-chat-template",
    "language-model-only",
    "hf-overrides",
    "override-generation-config",
    "quantization",
)
"""Absent from every serve file. Each changes the prompt, the numerics or the
draw: speculative decoding samples differently, a chat-template flag replaces
the pinned template, a request allowed to bring its own template can do the
same, and `trust-remote-code` would run code from the Hub that none of these
repositories ships. `language-model-only` should leave text alone, but it is a
second code path, and one path for every rung is simpler than proving two agree."""

ENGINE_PROFILES: dict[str, EngineProfile] = {
    "vllm-0.28": EngineProfile(
        key="vllm-0.28",
        requires=dict(_COMMON_REQUIRES),
        forbids=_COMMON_FORBIDS,
        family_flags={
            "qwen3.5": {
                "enable-auto-tool-choice": True,
                "tool-call-parser": "qwen3_coder",
                "reasoning-parser": "qwen3",
                "default-chat-template-kwargs": {"enable_thinking": False},
            },
            "gpt-oss": {
                "enable-auto-tool-choice": True,
                "tool-call-parser": "openai",
            },
            "qwen3": {
                "enable-auto-tool-choice": True,
                "tool-call-parser": "hermes",
                "reasoning-parser": "qwen3",
                "default-chat-template-kwargs": {"enable_thinking": False},
            },
        },
        notes=(
            "The Qwen server's default of no thinking is a safety net only: every "
            "request says. Naming gpt-oss's tool parser is also what makes vLLM read "
            "the reply through its harmony parser. Qwen 3 keeps hermes, as on the V100: "
            "its template writes hermes JSON calls, and qwen3_coder reads Qwen 3.5's XML. "
            "The qwen3 reasoning parser starts in the reasoning state when thinking is "
            "on, so a Qwen 3 reply with no tag at all is filed as reasoning here, where "
            "the V100's client split reads it as the answer."
        ),
    ),
    "vllm-0.8": EngineProfile(
        key="vllm-0.8",
        requires={**_COMMON_REQUIRES, "no-enable-chunked-prefill": True},
        forbids=_COMMON_FORBIDS + (
            "reasoning-parser",
            "enable-reasoning",
            "default-chat-template-kwargs",
        ),
        family_flags={
            "qwen3": {
                "enable-auto-tool-choice": True,
                "tool-call-parser": "hermes",
            },
        },
        notes=(
            "hermes is the parser Qwen's own documentation names for Qwen 3, and the "
            "one 0.8.5 has: there is no qwen3_coder in that version. No reasoning "
            "parser is started: the only one 0.8.5 offers, deepseek_r1, returns the "
            "whole answer as reasoning whenever the reply has no </think>, which is "
            "every reply with thinking off. default-chat-template-kwargs does not "
            "exist in 0.8.5 either, so the thinking switch travels in every request "
            "and nowhere else. Chunked prefill is off: 0.8.5 turns it on by itself above "
            "32K tokens of context, and on the DGX-1's V100s the first chunked prompt "
            "killed the engine with a Triton compiler error ('LLVM ERROR: Failed to "
            "compute parent layout for slice layout'). Volta is the only place this "
            "engine runs."
        ),
    ),
}

SERVE_KEYS_OF_NOTE = ("model", "revision", "tokenizer-revision", "max-model-len",
                      "tensor-parallel-size")

_REVISION = re.compile(r"[0-9a-f]{40}")
_SERVE_KEY = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_ENV_KEY = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")

REFUSED_ROLE_REASONS = {
    "developer-renamed-and-merged": (
        "Qwen 3.5's chat template has no developer role, and vLLM 0.28.0 does not "
        "refuse one: it renames it system and merges every system message into the "
        "first, so the model would see a conversation the record does not show. "
        "Operator instructions go in the one system message."
    ),
    "developer-dropped-by-template": (
        "Qwen 3's chat template renders system, user, assistant and tool and nothing "
        "else, and vLLM 0.8.5 hands it the role as written -- that version knows no "
        "developer role to rename. The instruction would vanish, with no error "
        "anywhere. Operator instructions go in the one system message."
    ),
    "system-becomes-developer": (
        "vLLM 0.28.0 gives gpt-oss every system or developer instruction as a "
        "harmony developer message, so the record would say system where the "
        "model saw developer. Operator instructions go in a developer message."
    ),
}
"""Why a role is refused, one entry per fact about an engine and a template. A
family names the code; the code holds the sentence, because the sentence is a
claim about source that was read."""

OPERATOR_FIRST_REASONS = {
    "system-after-first-refused-by-template": (
        "The Qwen 3.5 template refuses any system message after the first -- "
        "\"System message must be at the beginning.\" -- and the request fails."
    ),
    "one-operator-message-per-trial": (
        "A trial's operator instructions go in one message, first. The Qwen 3 "
        "template would render a later system message, and the Qwen 3.5 template "
        "refuses one, so a trial built with two could not run on both ladders."
    ),
}


class ConfigError(ValueError):
    """The configs disagree with each other, or with what the study pins."""


class UndeliverableTrial(ValueError):
    """These messages would not reach this model the way the record says."""


class NoFreeGpu(RuntimeError):
    """Not enough GPUs are free to serve this model where it was asked for."""


@dataclass(frozen=True)
class Conda:
    """The environment this machine's server runs in, and how to build it.
    Its own, never a share of another project's: an upgrade made for something else would
    silently become a new serving snapshot, and a run weeks apart would not be comparable
    with one before it."""

    env_name: str
    python: str
    pip: tuple[str, ...]

    def commands(self) -> list[str]:
        """The commands that build it, in order."""
        return [
            f"conda create -y -n {self.env_name} python={self.python}",
            f"conda activate {self.env_name}",
            "pip install " + " ".join(shlex.quote(p) for p in self.pip),
        ]


@dataclass(frozen=True)
class Environment:
    """One serving snapshot: an engine at one version, on one class of GPU, at
    one number format. Two of them differ in numerics even with the same weights,
    so each is named, recorded per run, and re-baselined rather than continued."""

    key: str
    name: str
    operator: str
    engine: str
    engine_version: str
    profile: EngineProfile
    openai_harmony: Optional[str]
    libraries: Mapping[str, str]
    conda: Conda
    gpu: Optional[str]
    gpu_memory_gib: Optional[int]
    compute_capability: str
    gpu_count: Optional[int]
    exclusive_gpus: bool
    dtype: str
    kv_cache_dtype: str
    gpu_memory_utilization: float
    engine_core: str
    attention_backend: Optional[str]
    reasoning_separation: str
    serve_env: Mapping[str, str]

    @property
    def serve_requires(self) -> dict[str, Any]:
        """What every serve file in this environment holds, engine and machine
        together."""
        return {**self.profile.requires,
                "dtype": self.dtype,
                "kv-cache-dtype": self.kv_cache_dtype,
                "gpu-memory-utilization": self.gpu_memory_utilization}


@dataclass(frozen=True)
class Family:
    """What one family's chat format carries, as its engine delivers it."""

    name: str
    prompt_renderer: str
    engine_profiles: tuple[str, ...]
    operator_role: str
    """Where operator instructions go: the one role that carries them."""
    operator_first_only: bool
    """True when a trial's operator message must be the first message."""
    operator_first_reason: Optional[str]
    delivered_roles: tuple[str, ...]
    refused_roles: Mapping[str, str]
    thinking_control: str
    thinking_prefills_open_block: Optional[bool]
    """Whether asking this family to think leaves a `<think>` block open at the
    end of the prompt. Qwen 3.5's template does; Qwen 3's prefills nothing and
    the model writes its own opening tag. It decides how a reply with no tag in
    it is read wherever this package splits the thinking itself."""
    template_source: Mapping[str, str]
    """Where the checkpoint keeps its chat template: a file of its own, or a key
    inside tokenizer_config.json. Qwen 3 ships no chat_template.jinja."""
    tokenizer_sha256: str
    serve_env: Mapping[str, str]
    download_ignore: tuple[str, ...]


@dataclass(frozen=True)
class Pins:
    """What the whole study pins, beside each model's own commit."""

    prompt_budget_tokens: int
    verified_on: str


@dataclass(frozen=True)
class Model:
    """One model of the study: its identity, and where it is served."""

    key: str
    hf_id: str
    revision: str
    family: Family
    pins: Pins
    quantisation: Optional[str]
    chat_template_sha256: str
    """The checkpoint's chat template at `revision`, hashed as the bytes of the
    template itself. vLLM renders Qwen prompts with it; for gpt-oss it is
    recorded but unused, because vLLM's chat endpoint renders harmony itself."""
    vendored_chat_template: Optional[str]
    thinking_by_default: Optional[bool]
    facts: Mapping[str, Any]
    """The roster entry as written, for everything above that is only recorded."""
    deployments: dict[str, "Deployment"] = field(default_factory=dict, repr=False)

    @property
    def deployment(self) -> "Deployment":
        """Where this model is served when nothing names a place: its first deployment.
        A later one is a second copy, reached only by naming its environment, so a script
        that names none keeps serving the model where it always has."""
        return next(iter(self.deployments.values()))

    def at(self, environment: str) -> "Deployment":
        try:
            return self.deployments[environment]
        except KeyError:
            raise ConfigError(
                f"{self.key} is not served in {environment!r}; it is served in "
                f"{sorted(self.deployments)}"
            ) from None


@dataclass(frozen=True)
class Deployment:
    """One model in one environment, with the serve file that starts it."""

    model: Model
    environment: Environment
    serve_path: str
    serve: Mapping[str, Any]

    @property
    def key(self) -> str:
        return f"{self.model.key}@{self.environment.key}"

    @property
    def max_model_len(self) -> int:
        return self.serve["max-model-len"]

    @property
    def tensor_parallel_size(self) -> int:
        return self.serve["tensor-parallel-size"]

    @property
    def serve_env(self) -> dict[str, str]:
        """The environment the server is started with: the machine's, then the
        family's. A variable set differently by both is a config error, caught
        when the roster loads."""
        return {**self.environment.serve_env, **self.model.family.serve_env}


# --- Reading the configs ---


def _rel(path: str) -> str:
    return os.path.relpath(path, ROOT)


def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def read_serve_config(path: str) -> dict[str, Any]:
    """One serve file, read the way vLLM's `--config` reads it.
    The package keeps no YAML dependency, so the files are written in the part of YAML
    where YAML and JSON agree: one `key: value` per line, every value a JSON literal."""
    out: dict[str, Any] = {}
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            text = line.rstrip("\n")
            if not text.strip() or text.startswith("#"):
                continue
            key, sep, raw = text.partition(":")
            if not sep or not _SERVE_KEY.fullmatch(key):
                raise ConfigError(
                    f"{_rel(path)}:{n}: expected `key: value` starting the line, "
                    f"got {text!r}"
                )
            if key in out:
                raise ConfigError(f"{_rel(path)}:{n}: {key!r} is set twice")
            try:
                out[key] = json.loads(raw)
            except ValueError:
                raise ConfigError(
                    f"{_rel(path)}:{n}: the value of {key!r} is not a JSON literal: "
                    f"{raw.strip()!r}"
                ) from None
    return out


_PIN = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)(==|>=)([A-Za-z0-9][A-Za-z0-9.+_-]*)$")


def _conda(key: str, block: Mapping[str, Any], engine: str, engine_version: str,
           harmony: Optional[str], libraries: Mapping[str, str], where: str) -> Conda:
    """The environment block, checked against everything else the machine claims.
    An environment file saying one version and a roster saying another is the drift this
    directory exists to stop, so the pins are checked here -- against the engine, the
    harmony version, and what the machine reports installed."""
    pins: dict[str, tuple[str, str]] = {}
    for entry in block["pip"]:
        match = _PIN.fullmatch(entry)
        if not match:
            raise ConfigError(
                f"{where}: {key}'s conda.pip has {entry!r}, which names no version. "
                f"Every install line pins one, with == or >=, or the environment is "
                f"whatever the day it was built"
            )
        pins[match.group(1).lower()] = (match.group(2), match.group(3))

    def must_pin(package: str, version: str, what: str) -> None:
        got = pins.get(package)
        if got is None:
            raise ConfigError(f"{where}: {key} installs no {package}, and {what}")
        if got != ("==", version):
            raise ConfigError(
                f"{where}: {key} installs {package}{got[0]}{got[1]} and {what} "
                f"{version}. The environment and the snapshot have to be the same thing"
            )

    must_pin(engine, engine_version, "this environment's engine is")
    if harmony is not None:
        must_pin("openai-harmony", harmony, "this environment's harmony version is")

    for package, reported in libraries.items():
        if package == "python":
            if reported != block["python"]:
                raise ConfigError(f"{where}: {key} reports python {reported} and builds "
                                  f"python {block['python']}")
            continue
        pinned = pins.get(package.lower())
        # "2.6.0+cu124" against "2.6.0" pinned: the build tag is the machine's and the version is ours, and they agree up to it.
        if pinned and pinned[0] == "==" and not reported.startswith(pinned[1]):
            raise ConfigError(
                f"{where}: {key} reports {package} {reported} and installs "
                f"{package}=={pinned[1]}"
            )
    name = block["env_name"]
    if not _ENV_KEY.fullmatch(name.replace("_", "-")):
        raise ConfigError(f"{where}: {key}'s conda env name {name!r} is not a usable name")
    return Conda(env_name=name, python=block["python"], pip=tuple(block["pip"]))


def load_environments(path: str = ENVIRONMENT_FILE) -> dict[str, Environment]:
    """Every environment, keyed by its key. Raises when one names an engine
    profile nobody has read the source of."""
    doc = read_json(path)
    where = _rel(path)
    out: dict[str, Environment] = {}
    for key, e in doc["environments"].items():
        if not _ENV_KEY.fullmatch(key):
            raise ConfigError(f"{where}: {key!r} is not a usable environment key "
                              f"(lower case, digits, dots and dashes)")
        profile = ENGINE_PROFILES.get(e["engine_profile"])
        if profile is None:
            raise ConfigError(
                f"{where}: {key} names engine profile {e['engine_profile']!r}, which "
                f"has no rules in whowins.runner.serving.ENGINE_PROFILES. A profile is "
                f"added by reading that engine's source, not by naming it here"
            )
        if e["reasoning_separation"] not in SEPARATIONS:
            raise ConfigError(f"{where}: {key}'s reasoning_separation is "
                              f"{e['reasoning_separation']!r}, not one of {list(SEPARATIONS)}")
        util = e["gpu_memory_utilization"]
        if not isinstance(util, float) or not 0.0 < util <= 1.0:
            raise ConfigError(f"{where}: {key}'s gpu_memory_utilization must be a "
                              f"fraction above 0 and at most 1, got {util!r}")
        conda = _conda(key, e["conda"], e["engine"], e["engine_version"],
                       e["openai_harmony_version"], e["libraries"], where)
        out[key] = Environment(
            key=key, name=e["name"], operator=e["operator"], engine=e["engine"],
            engine_version=e["engine_version"], profile=profile,
            openai_harmony=e["openai_harmony_version"], libraries=dict(e["libraries"]),
            gpu=e["gpu"], gpu_memory_gib=e["gpu_memory_gib"],
            compute_capability=e["compute_capability"], gpu_count=e["gpu_count"],
            exclusive_gpus=bool(e["exclusive_gpus"]), dtype=e["dtype"],
            kv_cache_dtype=e["kv_cache_dtype"], gpu_memory_utilization=util,
            engine_core=e["engine_core"], attention_backend=e["attention_backend"],
            reasoning_separation=e["reasoning_separation"],
            serve_env=dict(e["serve_env"]), conda=conda,
        )
    if not out:
        raise ConfigError(f"{where}: no environments")
    return out


def _check_serve(key: str, entry: Mapping[str, Any], family: Family,
                 environment: Environment, serve: Mapping[str, Any],
                 where: str) -> None:
    """Refuse a serve file that disagrees with the roster, the environment, or
    the study."""

    def fail(message: str) -> None:
        raise ConfigError(f"{where}: {message}")

    if serve.get("model") != entry["hf_id"]:
        fail(f"serves {serve.get('model')!r}, but the roster says {key} is "
             f"{entry['hf_id']!r}")
    for flag in ("revision", "tokenizer-revision"):
        if serve.get(flag) != entry["revision"]:
            fail(f"{flag} is {serve.get(flag)!r}; the roster pins {entry['revision']!r}")
    profile = environment.profile
    family_flags = profile.family_flags.get(family.name)
    if family_flags is None:
        fail(f"{family.name} has no serve rules at engine profile {profile.key} "
             f"(see ENGINE_PROFILES in whowins.runner.serving)")
    for flag, want in {**environment.serve_requires, **family_flags}.items():
        got = serve.get(flag)
        # type() as well as ==: in Python 0 == False, so `seed: false` would pass
        if got != want or type(got) is not type(want):
            fail(f"{flag} must be {json.dumps(want)}, and it is "
                 f"{json.dumps(got) if flag in serve else 'missing'}")
    for flag in profile.forbids:
        if flag in serve:
            fail(f"{flag} is set, and no serve file at {profile.key} may set it "
                 f"(see ENGINE_PROFILES in whowins.runner.serving)")
    known = set(SERVE_KEYS_OF_NOTE) | set(environment.serve_requires) | set(family_flags)
    unknown = sorted(set(serve) - known)
    if unknown:
        fail(f"sets {unknown}, which the study does not account for. A flag that "
             f"changes nothing measured still has to be added here on purpose")
    for flag in ("max-model-len", "tensor-parallel-size"):
        value = serve.get(flag)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            fail(f"{flag} must be a positive whole number, got {value!r}")


def _family(name: str, f: Mapping[str, Any], where: str) -> Family:
    for role, code in f["refused_roles"].items():
        if code not in REFUSED_ROLE_REASONS:
            raise ConfigError(
                f"{where}: {name} refuses {role!r} for reason {code!r}, which has no "
                f"sentence in whowins.runner.serving.REFUSED_ROLE_REASONS"
            )
        if role in f["delivered_roles"]:
            raise ConfigError(f"{where}: {name} both carries and refuses {role!r}")
    reason = f["operator_first_reason"]
    if bool(f["operator_first_only"]) != (reason is not None):
        raise ConfigError(
            f"{where}: {name} says operator_first_only={f['operator_first_only']} and "
            f"operator_first_reason={reason!r}; a rule needs its reason, and a reason "
            f"without the rule is never shown"
        )
    if reason is not None and reason not in OPERATOR_FIRST_REASONS:
        raise ConfigError(
            f"{where}: {name}'s operator_first_reason {reason!r} has no sentence in "
            f"whowins.runner.serving.OPERATOR_FIRST_REASONS"
        )
    for profile in f["engine_profiles"]:
        if profile not in ENGINE_PROFILES:
            raise ConfigError(f"{where}: {name} names engine profile {profile!r}, "
                              f"which whowins.runner.serving does not know")
    prefills = f["thinking_prefills_open_block"]
    if (f["thinking_control"] == "enable_thinking") != isinstance(prefills, bool):
        raise ConfigError(
            f"{where}: {name} controls thinking with {f['thinking_control']!r} and says "
            f"thinking_prefills_open_block={prefills!r}. A family with a thinking "
            f"switch says what its template prefills when the switch is on, because "
            f"that decides how a reply with no <think> tag in it is read; one without "
            f"a switch says nothing"
        )
    source = f["template_source"]
    if source["file"] not in ("chat_template.jinja", "tokenizer_config.json"):
        raise ConfigError(f"{where}: {name}'s template_source names "
                          f"{source['file']!r}, which preflight cannot read")
    if (source["file"] == "tokenizer_config.json") != ("key" in source):
        raise ConfigError(f"{where}: {name}'s template_source needs a key when the "
                          f"template lives inside tokenizer_config.json, and none "
                          f"when it is a file of its own")
    family = Family(
        name=name, prompt_renderer=f["prompt_renderer"],
        engine_profiles=tuple(f["engine_profiles"]),
        operator_role=f["operator_role"],
        operator_first_only=bool(f["operator_first_only"]),
        operator_first_reason=reason,
        delivered_roles=tuple(f["delivered_roles"]),
        refused_roles=dict(f["refused_roles"]),
        thinking_control=f["thinking_control"],
        thinking_prefills_open_block=prefills,
        template_source=dict(source),
        tokenizer_sha256=f["tokenizer_sha256"],
        serve_env=dict(f["serve_env"]),
        download_ignore=tuple(f["download_ignore"]),
    )
    if family.operator_role not in family.delivered_roles:
        raise ConfigError(f"{where}: {name} puts operator instructions in "
                          f"{family.operator_role!r}, a role it does not carry")
    return family


def load_roster(path: str = ROSTER_FILE,
                environments: Optional[Mapping[str, Environment]] = None
                ) -> dict[str, Model]:
    """Every model, keyed by its short key, each read with its serve files.
    Raises ConfigError when a serve file and the roster disagree, when a serve file breaks
    a rule of the study or its engine, when a model is deployed in an environment its
    family was never checked against, or when a vendored template is not the pinned file."""
    doc = read_json(path)
    where = _rel(path)
    pins = Pins(prompt_budget_tokens=doc["prompt_budget_tokens"],
                verified_on=doc["verified_on"])
    if environments is None:
        environments = load_environments(os.path.join(CONFIGS, "environments.json"))

    families = {name: _family(name, f, where) for name, f in doc["families"].items()}

    models: dict[str, Model] = {}
    seen_ids: set[str] = set()
    for entry in doc["models"]:
        key = entry["key"]
        if key in models or entry["hf_id"] in seen_ids:
            raise ConfigError(f"{where}: {key} ({entry['hf_id']}) is listed twice")
        seen_ids.add(entry["hf_id"])
        family = families.get(entry["family"])
        if family is None:
            raise ConfigError(f"{where}: {key} names an unknown family "
                              f"{entry['family']!r}")
        if not _REVISION.fullmatch(entry["revision"]):
            raise ConfigError(f"{where}: {key}'s revision {entry['revision']!r} is "
                              f"not a full commit hash, and only a commit pins a model")

        vendored = entry.get("vendored_chat_template")
        if family.prompt_renderer == "hf-jinja":
            if not vendored:
                raise ConfigError(f"{where}: {key} is rendered by its chat template, "
                                  f"and names no vendored copy to check it against")
            copy = os.path.join(CONFIGS, vendored)
            if _sha256(copy) != entry["checkpoint_chat_template_sha256"]:
                raise ConfigError(
                    f"{where}: {_rel(copy)} is not the chat template {key} pins "
                    f"({entry['checkpoint_chat_template_sha256'][:12]}...)"
                )

        model = Model(
            key=key, hf_id=entry["hf_id"], revision=entry["revision"],
            family=family, pins=pins, quantisation=entry.get("quantisation"),
            chat_template_sha256=entry["checkpoint_chat_template_sha256"],
            vendored_chat_template=vendored,
            thinking_by_default=entry.get("thinking_by_default"),
            facts=dict(entry),
        )

        deployments = entry.get("deployments") or {}
        if not deployments:
            raise ConfigError(f"{where}: {key} is served nowhere; every model names "
                              f"at least one environment under `deployments`")
        for env_key, serve_config in deployments.items():
            environment = environments.get(env_key)
            if environment is None:
                raise ConfigError(f"{where}: {key} is deployed in {env_key!r}, which "
                                  f"environments.json does not describe")
            if environment.profile.key not in family.engine_profiles:
                raise ConfigError(
                    f"{where}: {key} is deployed in {env_key} ({environment.profile.key}), "
                    f"and {family.name} has only been checked against "
                    f"{list(family.engine_profiles)}. Read that engine's source for "
                    f"this family before serving it there"
                )
            if family.prompt_renderer == "openai-harmony" \
                    and environment.openai_harmony is None:
                raise ConfigError(
                    f"{where}: {key}'s prompts are built by openai-harmony, and "
                    f"{env_key} pins no version of it. The library builds the prompt, "
                    f"so its version is part of the snapshot"
                )
            clash = [name for name, value in environment.serve_env.items()
                     if family.serve_env.get(name, value) != value]
            if clash:
                raise ConfigError(f"{where}: {key}'s environment and family set "
                                  f"{clash} to different values")
            serve_path = os.path.join(CONFIGS, serve_config)
            if not os.path.exists(serve_path):
                raise ConfigError(f"{where}: {key}'s serve file {_rel(serve_path)} "
                                  f"does not exist")
            serve = read_serve_config(serve_path)
            _check_serve(key, entry, family, environment, serve, _rel(serve_path))
            model.deployments[env_key] = Deployment(
                model=model, environment=environment, serve_path=serve_path, serve=serve)

        models[key] = model

    seen_serve: dict[str, str] = {}
    for model in models.values():
        for dep in model.deployments.values():
            other = seen_serve.setdefault(dep.serve_path, dep.key)
            if other != dep.key:
                raise ConfigError(f"{where}: {_rel(dep.serve_path)} is the serve file "
                                  f"of both {other} and {dep.key}")
    return models


# --- Decoding policies and runs ---

_POLICY_KEYS = frozenset({
    "families", "role", "enable_thinking", "reasoning_effort", "temperature",
    "top_p", "top_k", "min_p", "presence_penalty", "frequency_penalty",
    "repetition_penalty", "max_tokens", "source",
})

_SETTING_KEYS = tuple(sorted(_POLICY_KEYS - {"families", "role", "source"}))


@dataclass(frozen=True)
class Policy:
    """A named decoding policy: every setting of a draw but its seed."""

    name: str
    families: tuple[str, ...]
    role: str
    settings: Mapping[str, Any]
    source: str

    def decoding(self, seed: int) -> Decoding:
        return Decoding(seed=seed, **self.settings)


def load_policies(path: str = POLICY_FILE) -> dict[str, Policy]:
    """Every named policy. A policy with a missing or unknown key raises: a
    misspelt `top_k` would otherwise be dropped and its value left to the server."""
    doc = read_json(path)
    out: dict[str, Policy] = {}
    for name, fields in doc["policies"].items():
        keys = set(fields)
        if keys != _POLICY_KEYS:
            raise ConfigError(
                f"{_rel(path)}: policy {name!r} is missing "
                f"{sorted(_POLICY_KEYS - keys)} and has unknown {sorted(keys - _POLICY_KEYS)}"
            )
        if fields["role"] not in POLICY_ROLES:
            raise ConfigError(f"{_rel(path)}: policy {name!r} has role "
                              f"{fields['role']!r}, not one of {list(POLICY_ROLES)}")
        families = fields["families"]
        if not isinstance(families, list) or not families:
            raise ConfigError(f"{_rel(path)}: policy {name!r} names no families")
        settings = {k: fields[k] for k in _SETTING_KEYS}
        out[name] = Policy(name=name, families=tuple(families), role=fields["role"],
                           settings=settings, source=fields["source"])
    return out


@dataclass(frozen=True)
class Run:
    """One run: which model, where, which policy, how seeds are drawn, what
    stays closed."""

    run_id: str
    status: str
    confirmatory: bool
    deployment: Deployment
    policy: Policy
    base_seed: int
    repeats: int
    scenario_count: int
    composition_max_sources: int
    """Composition trials with more sources than this are not sent on this
    run's model. The initial run's is 2: its model is also a rung of the
    ladder, and stage one predicts every larger set from pairs alone."""
    design: str
    """How `whowins.runner.design` turns the scenarios into the trials this run
    sends. Named rather than implied, so a second way of building them is a
    second name and not a silent change to the first."""
    composition_sizes: tuple[int, ...] = (2,)
    """How many sources compete in the trials this run sends.

    `1` is the control arm: the same scenario, the same option, the same source,
    the same place in the conversation -- with nobody disagreeing. Without it an
    option the model simply cannot produce is indistinguishable from an option
    it declined to take, and the first run could not tell those apart for the
    154 format trials nothing could label.

    `2` is the conflict. Larger sizes are the composition ladder, which only
    the two ladder designs build; `composition_max_sources` is what
    keeps them closed on a model that is also a rung of the scale ladder."""
    tool_turns: int = 1
    """How many times the run loop will answer a tool call and ask again.

    1 is a single request -- what the first run did, and why 29 ordering trials
    recorded one step of a three-step sequence and were scored UNRESOLVED, and
    why 51 format trials spent their only turn on a context read and wrote no
    artifact. It is a property of the harness, not of the model, so it is a run
    setting and it is recorded on every row."""

    @property
    def model(self) -> Model:
        return self.deployment.model

    @property
    def environment(self) -> Environment:
        return self.deployment.environment

    def decoding(self, trial_id: str, repeat: int) -> Decoding:
        """The decoding for one draw of one trial."""
        if not 0 <= repeat < self.repeats:
            raise ValueError(f"{self.run_id} has {self.repeats} repeat(s); "
                             f"repeat {repeat} is not one of them")
        return self.policy.decoding(request_seed(self.base_seed, trial_id, repeat))


def run_ids() -> list[str]:
    return sorted(name[:-len(".json")] for name in os.listdir(RUNS_DIR)
                  if name.endswith(".json"))


def load_run(run_id: str, *, roster: Optional[Mapping[str, Model]] = None,
             policies: Optional[Mapping[str, Policy]] = None) -> Run:
    path = os.path.join(RUNS_DIR, f"{run_id}.json")
    doc = read_json(path)
    where = _rel(path)
    if doc.get("run_id") != run_id:
        raise ConfigError(f"{where}: says it is {doc.get('run_id')!r}")
    roster = roster if roster is not None else load_roster()
    policies = policies if policies is not None else load_policies()
    model = roster.get(doc["model"])
    if model is None:
        raise ConfigError(f"{where}: no model {doc['model']!r} in the roster")
    deployment = model.at(doc["environment"])
    policy = policies.get(doc["decoding"])
    if policy is None:
        raise ConfigError(f"{where}: no decoding policy {doc['decoding']!r}")
    if model.family.name not in policy.families:
        raise ConfigError(f"{where}: policy {policy.name!r} is for "
                          f"{list(policy.families)}, and {model.key} is "
                          f"{model.family.name}")
    for name, low in (("base_seed", 0), ("repeats", 1), ("scenario_count", 1),
                      ("composition_max_sources", 2)):
        value = doc.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < low:
            raise ConfigError(f"{where}: {name} must be a whole number of at "
                              f"least {low}, got {value!r}")
    sizes = doc.get("composition_sizes", [2])
    if not isinstance(sizes, list) or not sizes or any(
            not isinstance(n, int) or isinstance(n, bool) or n < 1 for n in sizes):
        raise ConfigError(f"{where}: composition_sizes must be a non-empty list "
                          f"of whole numbers of at least 1, got {sizes!r}")
    if sorted(set(sizes)) != sorted(sizes):
        raise ConfigError(f"{where}: composition_sizes repeats a size: {sizes!r}")
    turns = doc.get("tool_turns", 1)
    if not isinstance(turns, int) or isinstance(turns, bool) or not 1 <= turns <= 12:
        raise ConfigError(f"{where}: tool_turns must be a whole number from 1 to "
                          f"12, got {turns!r}. It bounds the agent loop, so a run "
                          f"cannot spend a night on one model talking to itself")
    check_policy(deployment, policy.decoding(seed=0))
    from .design import DESIGNS
    if doc.get("design") not in DESIGNS:
        raise ConfigError(f"{where}: design {doc.get('design')!r} is not one "
                          f"whowins.runner.design builds: {list(DESIGNS)}")
    return Run(run_id=run_id, status=doc["status"], confirmatory=bool(doc["confirmatory"]),
               deployment=deployment, policy=policy, base_seed=doc["base_seed"],
               repeats=doc["repeats"], scenario_count=doc["scenario_count"],
               composition_max_sources=doc["composition_max_sources"],
               design=doc["design"], composition_sizes=tuple(sorted(sizes)),
               tool_turns=turns)


def request_seed(base_seed: int, trial_id: str, repeat: int) -> int:
    """The seed of one draw.
    The same run, trial and repeat always get the same seed, so repeats are separate draws
    rather than one draw sent twice. The attempt number is deliberately not an input: a
    retry after a transport fault asks for the same draw again."""
    digest = hashlib.sha256(f"{base_seed}\x1f{trial_id}\x1f{repeat}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


# --- The stack, the policy and the messages ---


def stack_for(deployment: Deployment, *, gpu: Optional[str] = None,
              gpu_count: Optional[int] = None, engine_version: Optional[str] = None,
              tensor_parallel_size: Optional[int] = None,
              allow_unpinned: bool = False) -> ServingStack:
    """The ServingStack a run records, from the configs and the hardware.
    `engine_version` is what the server reports at /version, not what the study hoped for.
    A version other than the environment's is refused unless `allow_unpinned`: it is a
    different serving snapshot, and recording one should be a decision."""
    environment = deployment.environment
    model = deployment.model
    reported = engine_version if engine_version is not None else environment.engine_version
    if reported != environment.engine_version and not allow_unpinned:
        raise ConfigError(
            f"{environment.key} pins {environment.engine} {environment.engine_version} "
            f"and the server reports {reported}. A different version is a different "
            f"serving snapshot; pass allow_unpinned=True to record one on purpose"
        )
    hf = model.family.prompt_renderer == "hf-jinja"
    renderer = "hf-jinja" if hf else f"openai-harmony=={environment.openai_harmony}"
    return ServingStack(
        model=model.hf_id,
        weights_revision=model.revision,
        dtype=deployment.serve["dtype"],
        quantisation=model.quantisation,
        vllm_version=reported,
        tensor_parallel_size=tensor_parallel_size or deployment.tensor_parallel_size,
        gpu=gpu if gpu is not None else environment.gpu,
        gpu_count=gpu_count if gpu_count is not None else deployment.tensor_parallel_size,
        chat_template_sha256=model.chat_template_sha256 if hf else None,
        prompt_renderer=renderer,
        environment=environment.key,
        engine=environment.engine,
        attention_backend=environment.attention_backend,
        reasoning_separation=environment.reasoning_separation,
        libraries=dict(environment.libraries) or None,
    )


def check_policy(deployment: Deployment, decoding: Decoding) -> None:
    """Refuse a decoding that leaves any setting to the server, uses the other
    family's reasoning control, or lets vLLM shorten the answer's budget."""
    model = deployment.model
    unset = [name for name in SAMPLING_FIELDS if getattr(decoding, name) is None]
    if unset:
        raise ConfigError(f"{model.key}: the decoding leaves {unset} to the server. "
                          f"Every draw states every setting")
    control = model.family.thinking_control
    if control == "enable_thinking":
        if not isinstance(decoding.enable_thinking, bool):
            raise ConfigError(
                f"{model.key}: a {model.family.name} request must say whether thinking "
                f"is on. Every template in the family has a default and they disagree "
                f"-- Qwen 3 thinks unless told not to, Qwen 3.5's two smallest rungs do "
                f"not -- and vLLM's qwen3 parser assumes thinking when a request is "
                f"silent, which files the whole answer as reasoning"
            )
        if decoding.reasoning_effort is not None:
            raise ConfigError(
                f"{model.key}: reasoning_effort is gpt-oss's control. {model.family.name} "
                f"ignores it, so a record carrying one would claim a setting that did nothing"
            )
    elif control == "reasoning_effort":
        if decoding.reasoning_effort not in EFFORTS:
            raise ConfigError(f"{model.key}: a gpt-oss request names its reasoning "
                              f"effort, one of {list(EFFORTS)}; got "
                              f"{decoding.reasoning_effort!r}")
        if decoding.enable_thinking is not None:
            raise ConfigError(f"{model.key}: enable_thinking is Qwen's control, "
                              f"and gpt-oss ignores it")
    else:
        raise ConfigError(f"{model.family.name}: unknown thinking control {control!r}")
    room = deployment.max_model_len - model.pins.prompt_budget_tokens
    if decoding.max_tokens > room:
        raise ConfigError(
            f"{model.key}: max_tokens {decoding.max_tokens} leaves less than the "
            f"{model.pins.prompt_budget_tokens}-token prompt budget inside "
            f"max-model-len {deployment.max_model_len}. vLLM would not refuse a longer "
            f"prompt; it would shorten the answer's budget to fit, so where an "
            f"answer is cut off would depend on how long its prompt was"
        )


LATE_OPERATOR_WAIVABLE = frozenset({"one-operator-message-per-trial"})
"""Operator-first reasons that are this study's rule rather than the template's. A trial built
to send the operator late says so in `meta["operator_late"]` and may waive these, never a
template's refusal. What vLLM 0.8.5 and 0.28.0 do with a late operator message, read from their
source, is in docs/codebase/17_layouts.md, section 1."""


def late_operator_possible(family: Family) -> bool:
    """Whether a trial built to send the operator late can reach this family as written."""
    return not family.operator_first_only \
        or family.operator_first_reason in LATE_OPERATOR_WAIVABLE


def check_delivery(messages: Sequence[Mapping[str, Any]], family: Family, *,
                   late_operator: bool = False) -> None:
    """Refuse messages that would not reach this family as they are written.
    Four rules, each tied to what the family's engine does: every role is one the family carries
    as itself; operator instructions are one message, first, unless a late-operator trial waives
    our own rule; every tool result answers an earlier call by id; nothing is silently renamed."""
    for i, message in enumerate(messages):
        role = message.get("role")
        if role not in family.delivered_roles:
            code = family.refused_roles.get(role)
            reason = REFUSED_ROLE_REASONS.get(
                code,
                f"{family.name} carries only {list(family.delivered_roles)}.",
            )
            raise UndeliverableTrial(f"message {i} is a {role!r} message. {reason}")
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise UndeliverableTrial(f"message {i}'s content is not text")

    if family.operator_first_only and not (late_operator and late_operator_possible(family)):
        late = [i for i, m in enumerate(messages)
                if m.get("role") == family.operator_role and i > 0]
        if late:
            raise UndeliverableTrial(
                f"message {late[0]} is a {family.operator_role} message after the "
                f"first. {OPERATOR_FIRST_REASONS[family.operator_first_reason]}"
            )

    calls: set[str] = set()
    for i, message in enumerate(messages):
        if message.get("role") == "assistant":
            for call in message.get("tool_calls") or ():
                if isinstance(call, Mapping) and call.get("id"):
                    calls.add(call["id"])
        elif message.get("role") == "tool":
            if message.get("tool_call_id") not in calls:
                raise UndeliverableTrial(
                    f"message {i} is a tool result that answers no earlier assistant "
                    f"tool call. gpt-oss would receive it from a function with an "
                    f"empty name, and on either family it is a result nobody asked "
                    f"for. Put the call it answers in an assistant message before it, "
                    f"and give the result that call's id"
                )

    if not any(m.get("role") == "user" for m in messages):
        raise UndeliverableTrial("there is no user message, and the task is one")


def build_model_request(spec: TrialSpec, scenarios: Scenarios, deployment: Deployment,
                        decoding: Decoding) -> dict[str, Any]:
    """The exact body to POST for one draw of one trial on one deployment.
    `build_request` with every check in front of it, so the messages reach the model as the
    record will say they did. Anything else raises, and no request exists."""
    check_policy(deployment, decoding)
    check_delivery(render_dicts(spec, scenarios), deployment.model.family,
                   late_operator=bool(spec.meta.get("operator_late")))
    return build_request(spec, scenarios, ServingStack(model=deployment.model.hf_id),
                         decoding)


# --- Free GPUs, for a machine that is shared ---

GPU_FREE_MIB = 512
"""A GPU with less than this in use is free. An idle card on the owner's DGX-1
reports 6 MiB; the smallest busy one seen reported 1,644 MiB."""


def choose_gpus(rows: Sequence[tuple[int, int]], need: int,
                free_mib: int = GPU_FREE_MIB,
                want: Optional[Sequence[int]] = None) -> list[int]:
    """The GPUs to serve on: the ones asked for, or the lowest-numbered free ones.
    vLLM takes a fraction of a card's TOTAL memory, not of what is free, so starting beside
    another job either fails at startup or takes memory that job needs. Named cards are
    still checked."""
    if need < 1:
        raise ValueError(f"need must be at least 1, got {need}")
    used_by = {index: used for index, used in rows}
    if want is not None:
        if len(want) != need:
            raise NoFreeGpu(f"this model needs {need} GPU(s) and {len(want)} were "
                            f"named: {list(want)}")
        if len(set(want)) != len(want):
            raise NoFreeGpu(f"a GPU is named twice: {list(want)}")
        missing = [i for i in want if i not in used_by]
        if missing:
            raise NoFreeGpu(f"this machine has no GPU {missing}; it has "
                            f"{sorted(used_by)}")
        busy = [(i, used_by[i]) for i in want if used_by[i] >= free_mib]
        if busy:
            raise NoFreeGpu(
                "asked for GPU(s) that are in use: "
                + ", ".join(f"{i} ({u} MiB)" for i, u in busy)
                + f". Free is under {free_mib} MiB. Pick others, or wait"
            )
        return list(want)
    free = [index for index, used in sorted(rows) if used < free_mib]
    if len(free) < need:
        busy = ", ".join(f"{index} ({used} MiB)" for index, used in sorted(rows)
                         if used >= free_mib)
        raise NoFreeGpu(
            f"this model needs {need} free GPU(s) and {len(free)} are free "
            f"(under {free_mib} MiB in use). In use: {busy or 'none'}. Wait, "
            f"name others with --gpus, or serve a smaller rung"
        )
    return free[:need]


def gpu_rows(nvidia_smi: str = "nvidia-smi") -> list[tuple[int, int]]:
    """(index, memory used in MiB) for every GPU this machine has."""
    out = subprocess.run(
        [nvidia_smi, "--query-gpu=index,memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True).stdout
    rows: list[tuple[int, int]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        index, _, used = line.partition(",")
        try:
            rows.append((int(index.strip()), int(float(used.strip()))))
        except ValueError:
            raise NoFreeGpu(f"could not read nvidia-smi's line {line!r}") from None
    if not rows:
        raise NoFreeGpu(f"{nvidia_smi} listed no GPUs")
    return rows


# --- What the scripts read ---


def shell_assignments(deployment: Deployment) -> str:
    """Variables for scripts/serve.sh, quoted for bash to `eval`."""
    q = shlex.quote
    environment = deployment.environment
    exports = " ".join(q(f"{k}={v}") for k, v in sorted(deployment.serve_env.items()))
    ignore = " ".join(q(p) for p in deployment.model.family.download_ignore)
    return "\n".join([
        f"HF_ID={q(deployment.model.hf_id)}",
        f"REVISION={q(deployment.model.revision)}",
        f"SERVE_CONFIG={q(_rel(deployment.serve_path))}",
        f"ENVIRONMENT={q(environment.key)}",
        f"CONDA_ENV={q(environment.conda.env_name)}",
        f"ENGINE_VERSION={q(environment.engine_version)}",
        f"GPUS_NEEDED={deployment.tensor_parallel_size}",
        f"EXCLUSIVE_GPUS={1 if environment.exclusive_gpus else 0}",
        f"EXPORTS=({exports})",
        f"IGNORE=({ignore})",
    ])


def download(model: Model, *, print_only: bool = False,
             fetch: Optional[Callable[..., Any]] = None) -> str:
    """Fetch one model's files at its pinned commit into the Hugging Face cache.
    With `print_only`, only say what would be fetched. gpt-oss skips its original/ and
    metal/ folders, which hold the same weights in formats vLLM does not load."""
    kwargs: dict[str, Any] = {"repo_id": model.hf_id, "revision": model.revision}
    if model.family.download_ignore:
        kwargs["ignore_patterns"] = list(model.family.download_ignore)
    if print_only:
        return "snapshot_download(" + ", ".join(f"{k}={v!r}" for k, v in kwargs.items()) + ")"
    if fetch is None:
        from huggingface_hub import snapshot_download as fetch
    return str(fetch(**kwargs))


def _deployment_for(roster: Mapping[str, Model], key: str,
                    environment: Optional[str] = None) -> Deployment:
    if key not in roster:
        raise ConfigError(f"no model {key!r}; the keys are {list(roster)}")
    model = roster[key]
    return model.at(environment) if environment else model.deployment


def _main(argv: Sequence[str]) -> int:
    usage = ("usage: python3 -m whowins.runner.serving "
             "{check | keys | env [ENVIRONMENT] | shell KEY [ENVIRONMENT] | "
             "gpus KEY [ENVIRONMENT] [--need N] [--want 0,1] | "
             "download [--print] KEY... | download [--print] all}")
    if not argv:
        print(usage, file=sys.stderr)
        return 2
    command, rest = argv[0], list(argv[1:])
    try:
        environments = load_environments()
        roster = load_roster(environments=environments)
        if command == "check":
            policies = load_policies()
            runs = [load_run(r, roster=roster, policies=policies) for r in run_ids()]
            deployments = sum(len(m.deployments) for m in roster.values())
            print(f"{len(roster)} models in {len(environments)} environments "
                  f"({deployments} deployments), {len(policies)} decoding policies and "
                  f"{len(runs)} run(s) agree with each other and with the study's rules.")
            return 0
        if command == "keys":
            print("\n".join(roster))
            return 0
        if command == "env" and len(rest) == 1:
            environment = environments.get(rest[0])
            if environment is None:
                raise ConfigError(f"no environment {rest[0]!r}; they are "
                                  f"{list(environments)}")
            print("\n".join(environment.conda.commands()))
            return 0
        if command == "env" and not rest:
            for key, environment in environments.items():
                print(f"{key}\t{environment.conda.env_name}\t{environment.operator}")
            return 0
        if command == "shell" and 1 <= len(rest) <= 2:
            print(shell_assignments(_deployment_for(roster, rest[0],
                                                    rest[1] if len(rest) > 1 else None)))
            return 0
        if command == "gpus":
            want: Optional[list[int]] = None
            need: Optional[int] = None
            keys: list[str] = []
            it = iter(rest)
            for arg in it:
                if arg == "--want":
                    want = [int(i) for i in next(it, "").split(",") if i != ""]
                elif arg == "--need":
                    need = int(next(it, "0"))
                else:
                    keys.append(arg)
            if not 1 <= len(keys) <= 2:
                print(usage, file=sys.stderr)
                return 2
            deployment = _deployment_for(roster, keys[0],
                                         keys[1] if len(keys) > 1 else None)
            chosen = choose_gpus(gpu_rows(os.environ.get("NVIDIA_SMI", "nvidia-smi")),
                                 need or deployment.tensor_parallel_size, want=want)
            print(",".join(str(i) for i in chosen))
            return 0
        if command == "download":
            print_only = "--print" in rest
            keys = [a for a in rest if a != "--print"]
            if keys == ["all"]:
                keys = list(roster)
            if not keys:
                print(usage, file=sys.stderr)
                return 2
            unknown = [k for k in keys if k not in roster]
            if unknown:
                raise ConfigError(f"no model {unknown}; the keys are {list(roster)}")
            for key in keys:
                print(download(roster[key], print_only=print_only))
            return 0
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    except NoFreeGpu as exc:
        print(f"no free GPU: {exc}", file=sys.stderr)
        return 4
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"could not run nvidia-smi: {exc}", file=sys.stderr)
        return 4
    print(usage, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
