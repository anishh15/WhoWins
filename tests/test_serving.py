"""The serving suite: fifteen models, two machines, and what reaches each one.
Three properties carry it: what a model sees is what the record says, a claim about an
engine lives in code read out of that version's source, and a request either engine would
rewrite is refused before it exists."""

from __future__ import annotations

import collections
import glob
import hashlib
import http.server
import importlib.metadata
import json
import os
import re
import shutil
import socket
import subprocess
import threading
from dataclasses import replace

import pytest

from whowins.data import ROOT
from whowins.runner import preflight, serving
from whowins.runner.response import completion_from, parse_completion, split_reasoning
from whowins.runner.run import Decoding, ServingStack, score
from whowins.runner.serving import (
    ENGINE_PROFILES,
    SAMPLING_FIELDS,
    ConfigError,
    NoFreeGpu,
    UndeliverableTrial,
    build_model_request,
    check_delivery,
    check_policy,
    choose_gpus,
    gpu_rows,
    load_environments,
    load_policies,
    load_roster,
    load_run,
    read_serve_config,
    request_seed,
    stack_for,
)
from whowins.runner.design import trials_for_run
from whowins.runner.tools import tools_for_trial
from whowins.runner.trials import load_scenarios, reconstruct_all

CONFIGS = os.path.join(ROOT, "configs")
ENVIRONMENTS = load_environments()
ROSTER = load_roster()
POLICIES = load_policies()
SCENARIOS = load_scenarios()
RECONS = {r.trial_id: r for r in reconstruct_all()}
QWEN3 = ROSTER["qwen3-1.7b"].family
QWEN35 = ROSTER["qwen3.5-2b"].family
GPT_OSS = ROSTER["gpt-oss-20b"].family

PINNED = {
    # The owner's two lists of 2026-09-12, each at the commit the Hugging Face API reported. Here as well as in models.json, so editing one alone goes red.
    "Qwen/Qwen3-0.6B": "c1899de289a04d12100db370d81485cdf75e47ca",
    "Qwen/Qwen3-1.7B": "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
    "Qwen/Qwen3-4B": "1cfa9a7208912126459214e8b04321603b3df60c",
    "Qwen/Qwen3-8B": "b968826d9c46dd6066d109eabc6255188de91218",
    "Qwen/Qwen3-14B": "40c069824f4251a91eefaf281ebe4c544efd3e18",
    "Qwen/Qwen3-32B": "9216db5781bf21249d130ec9da846c4624c16137",
    "Qwen/Qwen3.5-0.8B": "2fc06364715b967f1860aea9cf38778875588b17",
    "Qwen/Qwen3.5-2B": "15852e8c16360a2fea060d615a32b45270f8a8fc",
    "Qwen/Qwen3.5-4B": "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
    "Qwen/Qwen3.5-9B": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
    "Qwen/Qwen3.5-27B": "fc05daec18b0a78c049392ed2e771dde82bdf654",
    "Qwen/Qwen3.5-35B-A3B": "59d61f3ce65a6d9863b86d2e96597125219dc754",
    "Qwen/Qwen3.5-122B-A10B": "dc4d348443bc740c68e2d77492492c11606384d5",
    "openai/gpt-oss-20b": "6cee5e81ee83917806bbde320786a8fb61efebee",
    "openai/gpt-oss-120b": "b5c939de8f754692c1647ca79fbf85e8c1e70f8a",
}
QWEN3_TEMPLATE = "a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8"
SMALL_TEMPLATE = "273d8e0e683b885071fb17e08d71e5f2a5ddfb5309756181681de4f5a1822d80"
LARGE_TEMPLATE = "a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715"

V100 = "v100-vllm085"
SM80 = "sm80-vllm0280"


def _sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _dep(key, environment=None):
    model = ROSTER[key]
    return model.at(environment) if environment else model.deployment


# --- The roster and the two environments ---


def test_the_roster_is_the_fifteen_models_the_owner_chose_in_their_order():
    assert [m.hf_id for m in ROSTER.values()] == list(PINNED)


def test_every_model_is_pinned_to_the_commit_the_hub_reported():
    assert {m.hf_id: m.revision for m in ROSTER.values()} == PINNED


def test_each_model_belongs_to_the_family_its_organisation_names():
    for model in ROSTER.values():
        expected = {"Qwen/Qwen3-": "qwen3", "Qwen/Qwen3.5-": "qwen3.5",
                    "openai/gpt-oss-": "gpt-oss"}
        prefix = next(p for p in expected if model.hf_id.startswith(p))
        assert model.family.name == expected[prefix], model.key


def test_the_two_ladders_and_the_comparison_family():
    by_family = collections.Counter(m.family.name for m in ROSTER.values())
    assert by_family == {"qwen3": 6, "qwen3.5": 7, "gpt-oss": 2}
    assert [m.key for m in ROSTER.values() if m.family.name == "qwen3"] == [
        "qwen3-0.6b", "qwen3-1.7b", "qwen3-4b", "qwen3-8b", "qwen3-14b", "qwen3-32b"]


def test_every_qwen3_rung_thinks_unless_told_and_only_the_small_qwen3_5_do_not():
    """The templates' own defaults, which is why every request states the mode."""
    thinking = {m.key: m.thinking_by_default for m in ROSTER.values()}
    assert all(thinking[m.key] for m in ROSTER.values() if m.family.name == "qwen3")
    assert [k for k, v in thinking.items() if v is False] == ["qwen3.5-0.8b", "qwen3.5-2b"]
    assert [k for k, v in thinking.items() if v is None] == ["gpt-oss-20b", "gpt-oss-120b"]


def test_both_cross_family_pairs_are_mixtures_of_experts():
    pairs = ROSTER["qwen3.5-2b"].facts and json.load(
        open(os.path.join(CONFIGS, "models.json")))["comparison_pairs"]
    assert len(pairs) == 2
    for pair in pairs:
        for key in (pair["qwen"], pair["gpt_oss"]):
            assert ROSTER[key].facts["architecture"] == "moe", key


def test_every_model_is_served_somewhere_and_each_machine_runs_one_ladder():
    """The 32B is the one model served in two places: its last twelve main runs have a second
    copy on the 80 GB cards. Its first deployment stays the DGX-1's, as every Qwen 3 rung's does."""
    where = collections.defaultdict(list)
    for model in ROSTER.values():
        assert model.deployments, model.key
        home = V100 if model.family.name == "qwen3" else SM80
        assert next(iter(model.deployments)) == home and model.deployment.environment.key == home
        for env_key in model.deployments:
            where[env_key].append(model.family.name)
    assert set(where) == {V100, SM80}
    assert set(where[V100]) == {"qwen3"}
    assert set(where[SM80]) == {"qwen3.5", "gpt-oss", "qwen3"}
    assert [m.key for m in ROSTER.values() if len(m.deployments) > 1] == ["qwen3-32b"]


def test_the_v100_machine_serves_in_float16_because_it_has_no_bfloat16():
    """vLLM refuses bfloat16 below compute capability 8.0 -- "Bfloat16 is only
    supported on GPUs with compute capability of at least 8.0" -- and the
    checkpoints are bfloat16, so they are cast on load and the record says so."""
    v100 = ENVIRONMENTS[V100]
    assert (v100.dtype, v100.compute_capability, v100.engine_core) == ("float16", "7.0", "v0")
    assert ENVIRONMENTS[SM80].dtype == "bfloat16"
    for model in ROSTER.values():
        for env_key, dep in model.deployments.items():
            assert dep.serve["dtype"] == ENVIRONMENTS[env_key].dtype, dep.key
            assert model.facts["weights"].startswith("bfloat16") or model.quantisation


def test_the_v100_machine_splits_thinking_here_because_its_engine_cannot():
    """vLLM 0.8.5 has no qwen3 reasoning parser, and its deepseek_r1 parser files
    the whole answer as reasoning whenever a reply holds no </think> -- every
    reply with thinking off. Qwen's documentation says so outright. So no serve
    file there names a parser, and the environment says who splits instead."""
    assert ENVIRONMENTS[V100].reasoning_separation == "client"
    assert ENVIRONMENTS[SM80].reasoning_separation == "server"
    for dep in (m.at(V100) for m in ROSTER.values() if V100 in m.deployments):
        assert "reasoning-parser" not in dep.serve and "enable-reasoning" not in dep.serve
    for dep in (m.at(SM80) for m in ROSTER.values() if SM80 in m.deployments):
        if dep.model.family.name in ("qwen3", "qwen3.5"):
            assert dep.serve["reasoning-parser"] == "qwen3"


def test_each_machine_has_its_own_environment_and_builds_it_from_this_file():
    """Its own, never a share of another project's: the study pins an engine and
    a transformers version, and an upgrade made for something else would become a
    new serving snapshot without anyone deciding to."""
    names = {e.conda.env_name for e in ENVIRONMENTS.values()}
    assert names == {"ipb-v100", "ipb-sm80"}, "one environment per machine, and its own"
    v100 = ENVIRONMENTS[V100].conda
    assert v100.python == ENVIRONMENTS[V100].libraries["python"] == "3.10.18"
    assert "vllm==0.8.5.post1" in v100.pip
    assert "transformers==4.57.1" in v100.pip, \
        "vLLM 0.8.5 asks only for >=4.51.1, so a fresh install would take a 5.x"
    assert v100.commands()[0] == "conda create -y -n ipb-v100 python=3.10.18"
    assert v100.commands()[1] == "conda activate ipb-v100"
    assert v100.commands()[2].startswith("pip install vllm==0.8.5.post1")


def test_the_environment_installs_the_engine_version_it_claims_to_run():
    for key, environment in ENVIRONMENTS.items():
        assert f"{environment.engine}=={environment.engine_version}" in \
            environment.conda.pip, key
        if environment.openai_harmony:
            assert f"openai-harmony=={environment.openai_harmony}" in environment.conda.pip, key


def test_each_engine_profile_forbids_what_that_version_cannot_do():
    """0.8.5 has no default-chat-template-kwargs and no parser it could use, so a
    serve file naming either would be read as a flag that does not exist."""
    assert set(ENGINE_PROFILES["vllm-0.8"].forbids) - set(ENGINE_PROFILES["vllm-0.28"].forbids) \
        == {"reasoning-parser", "enable-reasoning", "default-chat-template-kwargs"}
    assert set(ENGINE_PROFILES["vllm-0.8"].family_flags) == {"qwen3"}
    assert set(ENGINE_PROFILES["vllm-0.28"].family_flags) == {"qwen3.5", "gpt-oss", "qwen3"}


# --- The serve files ---


def test_every_serve_file_belongs_to_exactly_one_deployment():
    listed = {os.path.relpath(dep.serve_path, CONFIGS)
              for model in ROSTER.values() for dep in model.deployments.values()}
    on_disk = {os.path.relpath(p, CONFIGS)
               for p in glob.glob(os.path.join(CONFIGS, "vllm", "*.yaml"))}
    assert listed == on_disk


@pytest.mark.parametrize("key", list(ROSTER))
def test_yaml_reads_every_serve_file_the_way_the_package_does(key):
    """The package has no YAML dependency and reads these files itself, so the
    two readings must agree -- vLLM uses yaml.safe_load."""
    yaml = pytest.importorskip("yaml")
    for dep in ROSTER[key].deployments.values():
        with open(dep.serve_path) as fh:
            assert yaml.safe_load(fh) == read_serve_config(dep.serve_path)


@pytest.mark.parametrize("key", list(ROSTER))
def test_every_serve_file_pins_what_moves_the_numerics(key):
    model = ROSTER[key]
    for env_key, dep in model.deployments.items():
        serve, environment = dep.serve, ENVIRONMENTS[env_key]
        assert serve["model"] == model.hf_id
        assert serve["revision"] == serve["tokenizer-revision"] == PINNED[serve["model"]]
        assert serve["generation-config"] == "vllm"
        assert serve["no-enable-prefix-caching"] is True
        if environment.profile.key == "vllm-0.8":
            assert serve["no-enable-chunked-prefill"] is True
        assert serve["seed"] == 0 and type(serve["seed"]) is int
        assert serve["dtype"] == environment.dtype
        assert serve["kv-cache-dtype"] == environment.kv_cache_dtype
        assert serve["gpu-memory-utilization"] == environment.gpu_memory_utilization
        assert serve["max-model-len"] == 40960
        assert serve["tensor-parallel-size"] >= 1


def test_each_family_is_served_with_the_parsers_its_engine_has():
    """hermes is the parser Qwen's own documentation names for Qwen 3, and the
    one vLLM 0.8.5 ships; qwen3_coder does not exist in that version."""
    parsers = {m.key: {e: d.serve["tool-call-parser"] for e, d in m.deployments.items()}
               for m in ROSTER.values()}
    for key, by_env in parsers.items():
        family = ROSTER[key].family.name
        want = {"qwen3": "hermes", "qwen3.5": "qwen3_coder", "gpt-oss": "openai"}[family]
        assert set(by_env.values()) == {want}, key
        for dep in ROSTER[key].deployments.values():
            assert dep.serve["enable-auto-tool-choice"] is True


def test_the_qwen3_5_server_default_agrees_with_no_thinking():
    """A safety net under the rule that every request states the mode. vLLM 0.8.5
    has no such flag, which is why the V100 files carry none."""
    for model in ROSTER.values():
        if model.family.name == "qwen3.5":
            assert model.deployment.serve["default-chat-template-kwargs"] == \
                {"enable_thinking": False}


def test_gpt_oss_serving_pins_the_date_and_the_role_mapping():
    """Without VLLM_SYSTEM_START_DATE vLLM writes today's date into every gpt-oss
    prompt, so the same trial would be a different prompt on a different day."""
    env = ROSTER["gpt-oss-20b"].deployment.serve_env
    assert env["VLLM_SYSTEM_START_DATE"] == "2026-09-11"
    assert env["VLLM_GPT_OSS_HARMONY_SYSTEM_INSTRUCTIONS"] == "0"
    assert env["VLLM_USE_RUST_FRONTEND"] == "0"
    assert ROSTER["qwen3-1.7b"].deployment.serve_env == {"VLLM_USE_V1": "0"}


@pytest.mark.parametrize("body", [
    "model: Qwen/Qwen3-1.7B\n",              # a bare string: YAML reads it, JSON does not
    "max-model-len: 40960  # inline\n",      # a comment after a value
    "seed: 0\nseed: 0\n",                    # set twice
    "  seed: 0\n",                           # indented, as a nested key would be
    "seed 0\n",                              # no colon
])
def test_the_serve_reader_refuses_what_it_cannot_read_exactly(tmp_path, body):
    path = tmp_path / "x.yaml"
    path.write_text(body)
    with pytest.raises(ConfigError):
        read_serve_config(str(path))


# --- Planted faults: a damaged config never loads ---


def _sub(path, old, new, count=1):
    text = path.read_text()
    assert old in text, f"planted fault is a no-op: {old!r} not in {path.name}"
    path.write_text(text.replace(old, new, count))


def _append(path, line):
    with open(path, "a") as fh:
        fh.write(line)


_Q17 = "vllm/qwen3-1.7b.yaml"
_Q2 = "vllm/qwen3.5-2b.yaml"
_G20 = "vllm/gpt-oss-20b.yaml"
_Q32S = "vllm/qwen3-32b-sm80.yaml"

CONFIG_FAULTS = {
    "serve file and roster pin different commits":
        lambda d: _sub(d / _Q17, 'revision: "70d244cc', 'revision: "70d244cd'),
    "tokenizer left to the newest commit":
        lambda d: _sub(d / _Q17, 'tokenizer-revision: "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"\n', ""),
    "checkpoint sampling defaults let back in":
        lambda d: _sub(d / _Q2, 'generation-config: "vllm"', 'generation-config: "auto"'),
    "prefix caching back on":
        lambda d: _sub(d / _Q2, "no-enable-prefix-caching: true", "enable-prefix-caching: false"),
    "chunked prefill left to vLLM on the V100":
        lambda d: _sub(d / _Q17, "no-enable-chunked-prefill: true\n", ""),
    "a seed that equals 0 but is not 0":
        lambda d: _sub(d / _Q2, "seed: 0", "seed: false"),
    "speculative decoding added":
        lambda d: _append(d / _Q2, 'speculative-config: {"method": "mtp", "num_speculative_tokens": 1}\n'),
    "a flag nobody accounted for":
        lambda d: _append(d / _Q2, "max-num-seqs: 64\n"),
    "the other family's tool parser":
        lambda d: _sub(d / _G20, 'tool-call-parser: "openai"', 'tool-call-parser: "hermes"'),
    "a Qwen 3.5 server that thinks unless told":
        lambda d: _sub(d / _Q2, '{"enable_thinking": false}', '{"enable_thinking": true}'),
    "a copied template that is not the pinned file":
        lambda d: _append(d / "chat-templates" / "qwen3.5-small.jinja", "\n"),
    "the Qwen 3 template edited by a byte":
        lambda d: _append(d / "chat-templates" / "qwen3.jinja", "\n"),
    "a revision that is a branch, not a commit":
        lambda d: _sub(d / "models.json", '"revision": "15852e8c16360a2fea060d615a32b45270f8a8fc"',
                       '"revision": "main"'),
    # the two machines, and what tells them apart
    "bfloat16 asked of a V100":
        lambda d: _sub(d / _Q17, 'dtype: "float16"', 'dtype: "bfloat16"'),
    "float16 asked of the 80GB machine":
        lambda d: _sub(d / _Q2, 'dtype: "bfloat16"', 'dtype: "float16"'),
    "a reasoning parser on the engine that mishandles it":
        lambda d: _append(d / _Q17, 'reasoning-parser: "deepseek_r1"\n'),
    "a chat-template default on an engine with no such flag":
        lambda d: _append(d / _Q17, 'default-chat-template-kwargs: {"enable_thinking": false}\n'),
    "the memory fraction moved on one model only":
        lambda d: _sub(d / _Q17, "gpu-memory-utilization: 0.9", "gpu-memory-utilization: 0.8"),
    "a model deployed in an environment nobody described":
        lambda d: _sub(d / "models.json", '"deployments": {"v100-vllm085": "vllm/qwen3-1.7b.yaml"}',
                       '"deployments": {"a100-somewhere": "vllm/qwen3-1.7b.yaml"}'),
    "a family served on an engine its facts were never checked against":
        lambda d: _sub(d / "models.json", '"engine_profiles": ["vllm-0.8", "vllm-0.28"]',
                       '"engine_profiles": ["vllm-0.8"]'),
    "Qwen 3 on vLLM 0.28.0 with Qwen 3.5's tool parser":
        lambda d: _sub(d / _Q32S, 'tool-call-parser: "hermes"', 'tool-call-parser: "qwen3_coder"'),
    "Qwen 3 on the machine that splits on the server, with no parser to split":
        lambda d: _sub(d / _Q32S, 'reasoning-parser: "qwen3"\n', ""),
    "two models sharing one serve file":
        lambda d: _sub(d / "models.json", '"deployments": {"v100-vllm085": "vllm/qwen3-4b.yaml"}',
                       '"deployments": {"v100-vllm085": "vllm/qwen3-1.7b.yaml"}'),
    "a refused role with no reason anyone wrote down":
        lambda d: _sub(d / "models.json", '"developer": "developer-dropped-by-template"',
                       '"developer": "it-just-does-not-work"'),
    "a rule kept and its reason dropped":
        lambda d: _sub(d / "models.json", '"operator_first_reason": "one-operator-message-per-trial"',
                       '"operator_first_reason": null'),
    "a thinking switch with nothing said about what the template prefills":
        lambda d: _sub(d / "models.json", '"thinking_prefills_open_block": false',
                       '"thinking_prefills_open_block": null'),
    "a prefill claimed for a family that has no thinking switch":
        lambda d: _sub(d / "models.json", '"thinking_prefills_open_block": null',
                       '"thinking_prefills_open_block": true'),
    "a template looked for in a file that holds none":
        lambda d: _sub(d / "models.json", '"template_source": {"file": "tokenizer_config.json", "key": "chat_template"}',
                       '"template_source": {"file": "tokenizer_config.json"}'),
    "an environment that installs one engine version and claims another":
        lambda d: _sub(d / "environments.json", '"vllm==0.8.5.post1"', '"vllm==0.9.0"'),
    "an install line with no version on it":
        lambda d: _sub(d / "environments.json", '"transformers==4.57.1"', '"transformers"'),
    "a harmony version the environment does not install":
        lambda d: _sub(d / "environments.json", '"openai-harmony==0.0.8",\n          "pytest>=8.0"',
                       '"pytest>=8.0"'),
    "an environment whose python is not the one it reports":
        lambda d: _sub(d / "environments.json", '"python": "3.10.18",\n        "pip"',
                       '"python": "3.11",\n        "pip"'),
    "a library the machine reports that the environment never installed":
        lambda d: _sub(d / "environments.json", '"torch": "2.6.0+cu124"', '"torch": "2.7.0+cu124"'),
    "an engine profile nobody has read the source of":
        lambda d: _sub(d / "environments.json", '"engine_profile": "vllm-0.8"',
                       '"engine_profile": "vllm-0.9"'),
    "an environment that says nothing about who splits the thinking":
        lambda d: _sub(d / "environments.json", '"reasoning_separation": "client"',
                       '"reasoning_separation": "whoever"'),
    "a memory fraction above one":
        lambda d: _sub(d / "environments.json", '"gpu_memory_utilization": 0.9',
                       '"gpu_memory_utilization": 1.5'),
    "harmony's version dropped from the machine that builds harmony prompts":
        lambda d: _sub(d / "environments.json", '"openai_harmony_version": "0.0.8"',
                       '"openai_harmony_version": null'),
}


@pytest.fixture
def config_copy(tmp_path, monkeypatch):
    dst = tmp_path / "configs"
    shutil.copytree(CONFIGS, dst)
    monkeypatch.setattr(serving, "CONFIGS", str(dst))
    return dst


def _load_copy(config_copy):
    environments = load_environments(str(config_copy / "environments.json"))
    return load_roster(str(config_copy / "models.json"), environments=environments)


def test_an_undamaged_copy_of_the_configs_loads(config_copy):
    """The baseline for the faults below: without it, a fault that fails for an
    unrelated reason would look like a caught one."""
    assert list(_load_copy(config_copy)) == list(ROSTER)


@pytest.mark.parametrize("fault", list(CONFIG_FAULTS))
def test_a_damaged_config_stops_the_load(config_copy, fault):
    CONFIG_FAULTS[fault](config_copy)
    with pytest.raises(ConfigError):
        _load_copy(config_copy)


POLICY_FAULTS = {
    "a setting dropped, and left to the server":
        lambda d: _sub(d, '      "top_k": 20,\n', "", 1),
    "a setting misspelt, which is the same thing":
        lambda d: _sub(d, '"top_k": 20', '"topk": 20', 1),
    "a policy for nobody":
        lambda d: _sub(d, '"families": ["qwen3", "qwen3.5"]', '"families": []', 1),
    "a role nobody defined":
        lambda d: _sub(d, '"role": "study"', '"role": "the-good-one"', 1),
}


def test_an_undamaged_copy_of_the_policies_loads(tmp_path):
    shutil.copy(os.path.join(CONFIGS, "decoding.json"), tmp_path / "decoding.json")
    assert list(load_policies(str(tmp_path / "decoding.json"))) == list(POLICIES)


@pytest.mark.parametrize("fault", list(POLICY_FAULTS))
def test_a_damaged_policy_file_stops_the_load(tmp_path, fault):
    path = tmp_path / "decoding.json"
    shutil.copy(os.path.join(CONFIGS, "decoding.json"), path)
    POLICY_FAULTS[fault](path)
    with pytest.raises(ConfigError):
        load_policies(str(path))


# --- What reaches a Qwen model: the real templates, behind vLLM's rewrite ---

TEMPLATE_FILES = {"qwen3": "qwen3.jinja", "small": "qwen3.5-small.jinja",
                  "large": "qwen3.5-large.jinja"}
TEMPLATE_FAMILY = {"qwen3": "qwen3", "small": "qwen3.5", "large": "qwen3.5"}


def _template_text(which):
    with open(os.path.join(CONFIGS, "chat-templates", TEMPLATE_FILES[which]), encoding="utf-8") as fh:
        return fh.read()


def _family_of(which):
    return {"qwen3": QWEN3, "qwen3.5": QWEN35}[TEMPLATE_FAMILY[which]]


def _environment():
    """The Jinja environment transformers compiles chat templates in, which is
    what both vLLM versions call for Qwen."""
    jinja2 = pytest.importorskip("jinja2")
    from jinja2.ext import loopcontrols
    from jinja2.sandbox import ImmutableSandboxedEnvironment

    def raise_exception(message):
        raise jinja2.exceptions.TemplateError(message)

    env = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True,
                                        extensions=[loopcontrols])
    env.filters["tojson"] = (lambda value, ensure_ascii=False, indent=None, separators=None,
                             sort_keys=False: json.dumps(value, ensure_ascii=ensure_ascii,
                                                         indent=indent, separators=separators,
                                                         sort_keys=sort_keys))
    env.globals["raise_exception"] = raise_exception
    return env, jinja2.exceptions.TemplateError


def _vllm_rewrite(messages, template_text):
    """vLLM 0.28.0, vllm/renderers/hf.py, safe_apply_chat_template, reproduced.
    When any message is `developer` and the template never names that role, it is renamed and
    merged into the first system message -- silently, which is why the guard exists."""
    conv = [dict(m) for m in messages]
    if not any(m["role"] == "developer" for m in conv) \
            or '"developer"' in template_text or "'developer'" in template_text:
        return conv, False
    conv = [dict(m, role="system") if m["role"] == "developer" else m for m in conv]
    systems, rest, needs = [], [], False
    for i, m in enumerate(conv):
        if m["role"] == "system":
            if i > 0 or systems:
                needs = True
            if m.get("content"):
                systems.append(m["content"])
        else:
            rest.append(m)
    if needs:
        conv = [{"role": "system", "content": "\n\n".join(systems)}, *rest]
    return conv, True


def test_the_copied_templates_are_the_pinned_files():
    for which, pinned in (("qwen3", QWEN3_TEMPLATE), ("small", SMALL_TEMPLATE),
                          ("large", LARGE_TEMPLATE)):
        assert _sha256(os.path.join(CONFIGS, "chat-templates", TEMPLATE_FILES[which])) == pinned


def test_one_copied_template_covers_every_rung_of_each_qwen_family():
    """All six Qwen 3 checkpoints ship the same chat template, inside
    tokenizer_config.json rather than as a file of its own."""
    by_family = collections.defaultdict(set)
    for model in ROSTER.values():
        by_family[model.family.name].add(model.chat_template_sha256)
    assert by_family["qwen3"] == {QWEN3_TEMPLATE}
    assert by_family["qwen3.5"] == {SMALL_TEMPLATE, LARGE_TEMPLATE}
    assert QWEN3.template_source == {"file": "tokenizer_config.json", "key": "chat_template"}
    assert QWEN35.template_source == {"file": "chat_template.jinja"}


def test_what_silence_means_differs_by_family_and_by_rung():
    """Unasked, the three templates do three different things.
    Qwen 3 prefills nothing and the model opens its own block; Qwen 3.5's two smallest rungs
    differ again. What may be assumed about a reply with no `<think>` tag is a recorded fact
    per family, not a guess."""
    env, _ = _environment()
    convo = [{"role": "user", "content": "Write the note."}]
    rendered = {which: env.from_string(_template_text(which)) for which in TEMPLATE_FILES}

    def tail(which, **kw):
        out = rendered[which].render(messages=convo, add_generation_prompt=True, **kw)
        return out[out.index("<|im_start|>assistant\n") + len("<|im_start|>assistant\n"):]

    assert (tail("qwen3"), tail("small"), tail("large")) == \
        ("", "<think>\n\n</think>\n\n", "<think>\n")
    assert {tail(which, enable_thinking=False) for which in rendered} == {"<think>\n\n</think>\n\n"}
    assert (tail("qwen3", enable_thinking=True), tail("small", enable_thinking=True)) == \
        ("", "<think>\n")


def test_the_prefill_each_family_claims_is_what_its_template_actually_does():
    """The roster's `thinking_prefills_open_block` decides how a reply with no
    <think> tag is read, so it is checked against the templates themselves."""
    env, _ = _environment()
    for which in TEMPLATE_FILES:
        prompt = env.from_string(_template_text(which)).render(
            messages=[{"role": "user", "content": "Write the note."}],
            add_generation_prompt=True, enable_thinking=True)
        assert prompt.endswith("<think>\n") == _family_of(which).thinking_prefills_open_block, which


@pytest.mark.parametrize("which", list(TEMPLATE_FILES))
def test_what_the_guard_lets_through_reaches_qwen_as_recorded(which):
    """Soundness: every worked trial the guard accepts is left alone by the engine.
    It renders without error, keeps every message's text, and keeps every role as written."""
    env, _ = _environment()
    text = _template_text(which)
    template = env.from_string(text)
    family = _family_of(which)
    accepted = 0
    for tid, rec in RECONS.items():
        try:
            check_delivery(rec.rendered, family)
        except UndeliverableTrial:
            continue
        accepted += 1
        conv, rewritten = _vllm_rewrite(rec.rendered, text)
        assert not rewritten, tid
        prompt = template.render(messages=conv, tools=tools_for_trial(rec.spec, SCENARIOS) or None,
                                 add_generation_prompt=True, enable_thinking=False)
        for m in rec.rendered:
            assert m["content"].strip() in prompt, (tid, m["role"])
        roles = collections.Counter(m["role"] for m in rec.rendered)
        assert prompt.count("<|im_start|>user\n") == roles["user"], tid
        assert prompt.count("<|im_start|>assistant\n") == roles["assistant"] + 1, tid
    assert accepted == 48


@pytest.mark.parametrize("which", list(TEMPLATE_FILES))
def test_the_load_bundles_and_the_tiers_reach_qwen_as_built(which):
    """The two designs added for the main run, through the same engine and template: every
    load trial and a spread of tier trials arrive unrewritten, with every message's text."""
    from whowins.runner import design
    from whowins.runner.rendering import render_dicts
    env, _ = _environment()
    text = _template_text(which)
    template = env.from_string(text)
    specs = [*design.load_bundle_trials(SCENARIOS, "system"),
             *design.tier_trials(list(SCENARIOS.values()), "system")[::97]]
    for spec in specs:
        messages = render_dicts(spec, SCENARIOS)
        check_delivery(messages, _family_of(which))
        conv, rewritten = _vllm_rewrite(messages, text)
        assert not rewritten, spec.trial_id
        prompt = template.render(messages=conv, tools=tools_for_trial(spec, SCENARIOS) or None,
                                 add_generation_prompt=True, enable_thinking=False)
        for m in messages:
            assert m["content"].strip() in prompt, (spec.trial_id, m["role"])


def test_a_developer_message_is_rewritten_by_vllm_0_28_so_the_guard_refuses_it():
    text = _template_text("small")
    refused = [tid for tid, rec in RECONS.items()
               if any(m["role"] == "developer" for m in rec.rendered)]
    assert len(refused) == 9
    for tid in refused:
        conv, rewritten = _vllm_rewrite(RECONS[tid].rendered, text)
        assert rewritten and conv != RECONS[tid].rendered, tid
        assert all(m["role"] != "developer" for m in conv), tid
        with pytest.raises(UndeliverableTrial, match="no developer role"):
            check_delivery(RECONS[tid].rendered, QWEN35)


def test_a_developer_message_vanishes_from_a_qwen3_prompt_so_the_guard_refuses_it():
    """The V100 failure, and the worse of the two: vLLM 0.8.5 renames nothing, and
    the Qwen 3 template renders system, user, assistant and tool and ignores the
    rest. The instruction is simply not in the prompt, and nothing says so."""
    env, _ = _environment()
    template = env.from_string(_template_text("qwen3"))
    msgs = [{"role": "developer", "content": "Operator policy: write YAML."},
            {"role": "user", "content": "Task: write the config."}]
    conv, rewritten = _vllm_rewrite(msgs, _template_text("qwen3"))
    assert rewritten and conv[0]["role"] == "system"  # what 0.28 would have done
    # 0.8.5 does not: the template is handed the message as written
    prompt = template.render(messages=msgs, add_generation_prompt=True, enable_thinking=False)
    assert "Operator policy" not in prompt and "Task: write the config." in prompt
    with pytest.raises(UndeliverableTrial, match="vanish"):
        check_delivery(msgs, QWEN3)


def test_a_late_system_message_is_refused_by_the_template_so_the_guard_refuses_it():
    env, TemplateError = _environment()
    template = env.from_string(_template_text("small"))
    for tid in ("dec-06", "dec-08", "harn-10"):
        msgs = RECONS[tid].rendered
        assert not any(m["role"] == "developer" for m in msgs)
        with pytest.raises(TemplateError, match="System message must be at the beginning"):
            template.render(messages=msgs, add_generation_prompt=True, enable_thinking=False)
        with pytest.raises(UndeliverableTrial, match="after the first"):
            check_delivery(msgs, QWEN35)


def test_qwen3_would_render_a_late_system_message_and_the_study_refuses_it_anyway():
    """The one place the two templates differ on delivery. Qwen 3 renders a later
    system message as its own turn; Qwen 3.5 refuses the request. A trial built
    with two could not run on both ladders, so the study allows one, first, and
    the refusal says which reason applies."""
    env, _ = _environment()
    msgs = [{"role": "system", "content": "First policy."},
            {"role": "user", "content": "Task."},
            {"role": "system", "content": "Later policy."}]
    prompt = env.from_string(_template_text("qwen3")).render(
        messages=msgs, add_generation_prompt=True, enable_thinking=False)
    assert prompt.count("<|im_start|>system\n") == 2 and "Later policy." in prompt
    with pytest.raises(UndeliverableTrial, match="could not run on both ladders"):
        check_delivery(msgs, QWEN3)
    with pytest.raises(UndeliverableTrial, match="System message must be at the beginning"):
        check_delivery(msgs, QWEN35)


def _round_trip(tool_call_id="call_0"):
    return [
        {"role": "system", "content": "Follow the operator policy."},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_0", "type": "function",
             "function": {"name": "config_read", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": tool_call_id, "content": "Stage them in /scratch/d."},
        {"role": "user", "content": "Task: stage the files."},
    ]


@pytest.mark.parametrize("which,call_marker", [
    ("small", "<function=config_read>"),
    ("qwen3", '<tool_call>\n{"name": "config_read", "arguments": {}}'),
])
def test_a_tool_result_that_answers_its_call_reaches_qwen_as_recorded(which, call_marker):
    env, _ = _environment()
    msgs = _round_trip()
    check_delivery(msgs, _family_of(which))
    # vLLM parses tool-call arguments from JSON before the template sees them
    conv = [dict(m, tool_calls=[{**c, "function": {**c["function"], "arguments": {}}}
                                for c in m["tool_calls"]]) if m.get("tool_calls") else m
            for m in msgs]
    prompt = env.from_string(_template_text(which)).render(
        messages=conv, add_generation_prompt=True, enable_thinking=False)
    assert call_marker in prompt
    assert "<tool_response>\nStage them in /scratch/d.\n</tool_response>" in prompt


# --- The delivery rules ---


def _first_refusal(msgs, family):
    try:
        check_delivery(msgs, family)
    except UndeliverableTrial as exc:
        text = str(exc)
        for label, needle in (("developer", "'developer' message"), ("system", "'system' message"),
                              ("late system", "after the first"), ("bare tool result", "tool result")):
            if needle in text:
                return label
        return text
    return None


def test_how_many_worked_trials_each_family_carries_as_written():
    """The worked trials were written for an abstract set of roles; the trial
    builder must put each trial in a shape its model can carry. Counted two
    ways when this was written -- by the guard, and by a scan of roles alone."""
    tallies = {}
    for family in (QWEN3, QWEN35, GPT_OSS):
        tallies[family.name] = collections.Counter(
            _first_refusal(rec.rendered, family) for rec in RECONS.values())
    carried = {None: 48, "developer": 9, "late system": 3, "bare tool result": 10}
    assert tallies["qwen3"] == carried
    assert tallies["qwen3.5"] == carried
    assert tallies["gpt-oss"] == {None: 10, "system": 57, "bare tool result": 3}


def test_gpt_oss_takes_operator_instructions_as_developer_anywhere():
    msgs = [{"role": "developer", "content": "Policy."}, {"role": "user", "content": "Hi."},
            {"role": "developer", "content": "Later policy."}, {"role": "user", "content": "Task."}]
    check_delivery(msgs, GPT_OSS)
    with pytest.raises(UndeliverableTrial, match="no developer role"):
        check_delivery(msgs, QWEN35)
    with pytest.raises(UndeliverableTrial, match="renders system, user, assistant and tool"):
        check_delivery(msgs, QWEN3)
    with pytest.raises(UndeliverableTrial, match="harmony developer message"):
        check_delivery([{"role": "system", "content": "Policy."},
                        {"role": "user", "content": "Task."}], GPT_OSS)


@pytest.mark.parametrize("family", ["qwen3", "qwen3.5"])
def test_qwen_takes_one_system_message_and_only_first(family):
    fam = {"qwen3": QWEN3, "qwen3.5": QWEN35}[family]
    system, user = {"role": "system", "content": "S."}, {"role": "user", "content": "U."}
    check_delivery([system, user], fam)
    check_delivery([user], fam)
    for msgs in ([system, system, user], [user, system, user]):
        with pytest.raises(UndeliverableTrial, match="after the first"):
            check_delivery(msgs, fam)


def test_a_tool_result_must_answer_an_earlier_call_by_id():
    for family in (QWEN3, QWEN35, GPT_OSS):
        good = _round_trip()
        if family is GPT_OSS:
            good[0] = {"role": "developer", "content": good[0]["content"]}
        check_delivery(good, family)
        wrong_id = [dict(m) for m in good]
        wrong_id[2]["tool_call_id"] = "call_9"
        call_after = [good[0], good[2], good[1], good[3]]
        bare = [good[0], {"role": "tool", "content": "Stage them in /scratch/d."}, good[3]]
        for msgs in (wrong_id, call_after, bare):
            with pytest.raises(UndeliverableTrial, match="answers no earlier assistant tool call"):
                check_delivery(msgs, family)


def test_a_conversation_without_a_user_message_is_refused():
    with pytest.raises(UndeliverableTrial, match="no user message"):
        check_delivery([{"role": "system", "content": "S."}], QWEN3)


# --- Policies and requests ---


def test_every_policy_states_every_setting_of_a_draw():
    for policy in POLICIES.values():
        decoding = policy.decoding(seed=1)
        assert all(getattr(decoding, name) is not None for name in SAMPLING_FIELDS), policy.name


def test_one_study_policy_per_mode_covers_every_qwen_model_of_both_generations():
    study = {name: p for name, p in POLICIES.items() if p.role == "study"}
    assert set(study) == {"study-nothink", "study-think", "study-think-gpt-oss"}
    for name in ("study-nothink", "study-think"):
        assert set(POLICIES[name].families) == {"qwen3", "qwen3.5"}
    assert POLICIES["study-nothink"].settings["enable_thinking"] is False
    assert POLICIES["study-think"].settings["enable_thinking"] is True


def test_gpt_oss_is_sampled_like_every_other_thinking_run_at_high_effort():
    """The owner's rule: one set of sampling values for thinking, one for not thinking. gpt-oss
    has no non-thinking mode, so it runs in the thinking arm only, with study-think's values.
    Written out here so an edit to one policy alone goes red."""
    think, oss = POLICIES["study-think"].settings, POLICIES["study-think-gpt-oss"].settings
    for name in SAMPLING_FIELDS:
        if name != "seed":
            assert oss[name] == think[name], name
    assert oss["reasoning_effort"] == "high" and oss["enable_thinking"] is None
    assert list(POLICIES["study-think-gpt-oss"].families) == ["gpt-oss"]


def test_no_study_policy_penalises_a_token_for_having_been_written():
    """A presence penalty pushes against answers that repeat tokens -- list
    markers, JSON quotes, the tool-call tags -- so it would favour some options
    over others for no reason the instructions give. The card policies keep the
    cards' own penalties, which is what they are for."""
    for policy in POLICIES.values():
        s = policy.settings
        if policy.role == "card-check":
            assert s["presence_penalty"] in (1.5, 2.0), policy.name
        else:
            assert (s["presence_penalty"], s["frequency_penalty"], s["repetition_penalty"]) \
                == (0.0, 0.0, 1.0), policy.name
        assert (s["frequency_penalty"], s["repetition_penalty"]) == (0.0, 1.0), policy.name


def test_the_study_settings_are_what_every_qwen_card_recommends():
    """Non-thinking is the Qwen 3 cards' non-thinking row and the Qwen 3.5
    4B-and-larger cards' 'Instruct (or non-thinking) mode for general tasks';
    thinking is the Qwen 3 cards' thinking row and every Qwen 3.5 card's
    'precise coding' row, presence penalty included."""
    nothink, think = POLICIES["study-nothink"].settings, POLICIES["study-think"].settings
    assert (nothink["temperature"], nothink["top_p"], nothink["top_k"], nothink["min_p"]) \
        == (0.7, 0.8, 20, 0.0)
    assert (think["temperature"], think["top_p"], think["top_k"], think["min_p"]) \
        == (0.6, 0.95, 20, 0.0)
    assert {p.settings["max_tokens"] for p in POLICIES.values()} == {32768}


def test_each_card_policy_carries_that_card_s_own_numbers():
    cards = {
        "card-qwen3.5-small-nothink": (1.0, 1.0, 20, 2.0, False),
        "card-qwen3.5-small-think": (1.0, 0.95, 20, 1.5, True),
        "card-qwen3.5-nothink": (0.7, 0.8, 20, 1.5, False),
        "card-qwen3.5-think": (1.0, 0.95, 20, 1.5, True),
    }
    for name, want in cards.items():
        s = POLICIES[name].settings
        assert (s["temperature"], s["top_p"], s["top_k"], s["presence_penalty"],
                s["enable_thinking"]) == want, name
        assert POLICIES[name].families == ("qwen3.5",), name
    assert not [p for p in POLICIES.values()
                if p.role == "card-check" and "qwen3" in p.families]
    for effort in ("low", "medium", "high"):
        s = POLICIES[f"gpt-oss-{effort}"].settings
        assert (s["temperature"], s["top_p"], s["top_k"], s["min_p"], s["reasoning_effort"],
                s["enable_thinking"]) == (1.0, 1.0, 0, 0.0, effort, None)


def test_a_decoding_is_accepted_only_by_a_family_whose_control_it_speaks():
    """`check_policy` sees a decoding, not a policy's name, so what it can refuse
    is a setting the family ignores: a thinking switch sent to gpt-oss, or an
    effort sent to Qwen. Which *named* policy a model may run under is a
    different rule, enforced where a run names one -- the test below."""
    for model in ROSTER.values():
        for policy in POLICIES.values():
            decoding = policy.decoding(seed=1)
            speaks = ("gpt-oss" in policy.families) == (model.family.name == "gpt-oss")
            if speaks:
                check_policy(model.deployment, decoding)
            else:
                with pytest.raises(ConfigError):
                    check_policy(model.deployment, decoding)


def test_a_run_may_not_name_a_policy_its_model_s_family_does_not_allow(tmp_path, monkeypatch):
    """The Qwen 3.5 card policies exist to price a departure from those cards.
    Run on a Qwen 3 model they would measure nothing, so a run naming one is
    refused before it starts."""
    monkeypatch.setattr(serving, "RUNS_DIR", str(tmp_path))
    body = json.load(open(os.path.join(CONFIGS, "runs", "initial-qwen3-1.7b.json")))
    body["run_id"] = "borrowed-card"
    body["decoding"] = "card-qwen3.5-nothink"
    (tmp_path / "borrowed-card.json").write_text(json.dumps(body))
    with pytest.raises(ConfigError, match=r"is for \['qwen3.5'\]"):
        load_run("borrowed-card")


def test_a_qwen_request_must_say_whether_to_think():
    silent = replace(POLICIES["study-nothink"].decoding(seed=1), enable_thinking=None)
    for key in ("qwen3-1.7b", "qwen3.5-2b"):
        with pytest.raises(ConfigError, match="whether thinking is on"):
            check_policy(_dep(key), silent)
    no_effort = replace(POLICIES["gpt-oss-low"].decoding(seed=1), reasoning_effort=None)
    with pytest.raises(ConfigError, match="reasoning effort"):
        check_policy(_dep("gpt-oss-20b"), no_effort)


@pytest.mark.parametrize("field", SAMPLING_FIELDS)
def test_a_decoding_that_leaves_a_setting_to_the_server_is_refused(field):
    leaky = replace(POLICIES["study-nothink"].decoding(seed=1), **{field: None})
    with pytest.raises(ConfigError, match="to the server"):
        check_policy(_dep("qwen3-1.7b"), leaky)


def test_the_answer_budget_leaves_room_for_the_prompt():
    """vLLM would shorten the answer's budget to fit a long prompt rather than
    refuse it, so the budget is checked here instead."""
    greedy = replace(POLICIES["study-nothink"].decoding(seed=1), max_tokens=32769)
    with pytest.raises(ConfigError, match="prompt budget"):
        check_policy(_dep("qwen3-1.7b"), greedy)


def test_the_request_the_initial_run_sends():
    run = load_run("initial-qwen3-1.7b")
    rec = RECONS["comp-01"]
    body = build_model_request(rec.spec, SCENARIOS, run.deployment, run.decoding("comp-01", 0))
    assert body["model"] == "Qwen/Qwen3-1.7B"
    assert body["messages"] == rec.rendered
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert [body[k] for k in ("temperature", "top_p", "top_k", "min_p", "presence_penalty",
                              "frequency_penalty", "repetition_penalty", "max_tokens")] \
        == [0.7, 0.8, 20, 0.0, 0.0, 0.0, 1.0, 32768]
    assert body["seed"] == request_seed(20260912, "comp-01", 0)
    assert "reasoning_effort" not in body


def test_a_gpt_oss_request_names_its_effort_and_nothing_of_qwens():
    rec = RECONS["dec-03"]
    body = build_model_request(rec.spec, SCENARIOS, _dep("gpt-oss-120b"),
                               POLICIES["gpt-oss-low"].decoding(seed=5))
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["reasoning_effort"] == "low" and body["top_k"] == 0
    assert "chat_template_kwargs" not in body


def test_an_undeliverable_trial_never_becomes_a_request():
    nothink = POLICIES["study-nothink"].decoding(seed=1)
    with pytest.raises(UndeliverableTrial):
        build_model_request(RECONS["dec-04"].spec, SCENARIOS, _dep("qwen3-1.7b"), nothink)
    with pytest.raises(UndeliverableTrial):
        build_model_request(RECONS["comp-01"].spec, SCENARIOS, _dep("gpt-oss-20b"),
                            POLICIES["gpt-oss-medium"].decoding(seed=1))


# --- Seeds, the stack, and the initial run ---


def test_one_draw_has_one_seed_and_different_draws_have_different_seeds():
    seed = request_seed(20260912, "comp-01", 0)
    assert seed == request_seed(20260912, "comp-01", 0)
    assert 0 <= seed < 2 ** 31
    assert len({seed, request_seed(20260912, "comp-01", 1), request_seed(20260912, "comp-02", 0),
                request_seed(20260911, "comp-01", 0)}) == 4
    every = [request_seed(20260912, tid, r) for tid in RECONS for r in range(3)]
    assert len(set(every)) == len(every)


def test_a_run_refuses_a_repeat_it_does_not_have():
    run = load_run("initial-qwen3-1.7b")
    with pytest.raises(ValueError):
        run.decoding("comp-01", run.repeats)


def test_the_stack_records_the_machine_as_well_as_the_model():
    qwen3 = stack_for(_dep("qwen3-1.7b"), gpu_count=1)
    assert (qwen3.weights_revision, qwen3.chat_template_sha256, qwen3.prompt_renderer,
            qwen3.dtype, qwen3.vllm_version) == \
        (PINNED["Qwen/Qwen3-1.7B"], QWEN3_TEMPLATE, "hf-jinja", "float16", "0.8.5.post1")
    assert (qwen3.environment, qwen3.engine, qwen3.attention_backend,
            qwen3.reasoning_separation) == (V100, "vllm", "XFORMERS", "client")
    assert qwen3.gpu == "Tesla V100-SXM2-32GB" and qwen3.libraries["torch"] == "2.6.0+cu124"

    qwen35 = stack_for(_dep("qwen3.5-2b"), gpu="H100 80GB", gpu_count=1)
    assert (qwen35.dtype, qwen35.chat_template_sha256, qwen35.reasoning_separation) == \
        ("bfloat16", SMALL_TEMPLATE, "server")
    oss = stack_for(_dep("gpt-oss-120b"), gpu="H100 80GB", gpu_count=1)
    assert (oss.chat_template_sha256, oss.prompt_renderer, oss.quantisation) == \
        (None, "openai-harmony==0.0.8", "mxfp4")
    assert len({s.fingerprint() for s in (qwen3, qwen35, oss)}) == 3


def test_the_same_weights_on_two_machines_would_be_two_snapshots():
    """What the fingerprint is for: nothing about the model changed, and every
    number it produces belongs to a different stack."""
    dep = _dep("qwen3-1.7b")
    here = stack_for(dep, gpu_count=1)
    elsewhere = replace(here, environment=SM80, dtype="bfloat16", vllm_version="0.28.0",
                        attention_backend=None, reasoning_separation="server")
    assert here.fingerprint() != elsewhere.fingerprint()


def test_an_unpinned_engine_is_recorded_only_on_purpose():
    with pytest.raises(ConfigError, match="different serving snapshot"):
        stack_for(_dep("qwen3-1.7b"), gpu_count=1, engine_version="0.9.0")
    stack = stack_for(_dep("qwen3-1.7b"), gpu_count=1, engine_version="0.9.0",
                      allow_unpinned=True)
    assert stack.vllm_version == "0.9.0"


def test_the_initial_run_is_the_1_7b_over_every_scenario_with_the_headline_sets_closed():
    run = load_run("initial-qwen3-1.7b")
    assert (run.model.key, run.environment.key, run.policy.name, run.status, run.confirmatory) \
        == ("qwen3-1.7b", V100, "study-nothink", "exploratory", False)
    assert run.scenario_count == len(SCENARIOS) == 1080
    assert run.composition_max_sources == 2
    assert (run.repeats, run.base_seed) == (1, 20260912)


SM80_COPY = "-sm80"
SM80_COPY_KINDS = ("ladder", "operator", "realism", "message", "free", "load", "tier")
"""The 32B's runs with a second copy on the 80 GB cards: every kind but the ladder from 2026-10-10,
and the ladder too from 2026-10-11, when every 32B result moved to those cards."""


def test_every_run_config_loads():
    """The list is written down so that adding a run is a decision.

    A run config is what a result is reproduced from, so one appearing without
    anybody noticing is the thing to stop."""
    main = sorted(f"main-{design}-{key}-{mode}" for key, model in ROSTER.items()
                  for mode in (("think",) if model.family.name == "gpt-oss"
                               else ("nothink", "think"))
                  for design in ("ladder", "operator", "realism", "message", "free", "load",
                                 "tier"))
    copies = [f"main-{kind}-qwen3-32b-{mode}{SM80_COPY}" for kind in SM80_COPY_KINDS
              for mode in ("nothink", "think")]
    assert serving.run_ids() == sorted(["balanced-qwen3-1.7b", "balanced-qwen3-14b",
                                        "initial-qwen3-1.7b", "ladder-qwen3-14b", *main,
                                        *copies])
    for run_id in serving.run_ids():
        load_run(run_id)


def test_every_main_run_differs_only_in_its_model_its_mode_and_its_seed():
    """The owner's settings, September and October 2026. Every Qwen model runs with thinking
    off and on, gpt-oss only on, each at the one policy of its mode; each kind of run shares its
    design, sizes, repeats and agent loop, so two main runs of a kind differ in nothing else. The
    tier runs take one draw, because capacity counts items and a repeat certifies nothing. The
    32B's copies on the 80 GB cards are read as their DGX-1 twins, on the other machine."""
    kinds = {"ladder": ("composition-ladder-flat", (1, 2, 3, 5), 3),
             "operator": ("operator-decomposition", (2,), 3), "realism": ("realism", (2,), 3),
             "message": ("one-message", (2,), 3),
             "free": ("free-predictions", (3, 4, 5), 3), "load": ("load-bundles", (2,), 3),
             "tier": ("declared-tiers-6", (2,), 1)}
    policy = {("qwen3", "nothink"): "study-nothink", ("qwen3", "think"): "study-think",
              ("qwen3.5", "nothink"): "study-nothink", ("qwen3.5", "think"): "study-think",
              ("gpt-oss", "think"): "study-think-gpt-oss"}
    main = [r for r in serving.run_ids() if r.startswith("main-")]
    for run_id in main:
        run = load_run(run_id)
        twin = run_id.removesuffix(SM80_COPY)
        kind, mode = twin.split("-")[1], twin.rsplit("-", 1)[1]
        design, sizes, repeats = kinds[kind]
        assert (run.design, run.composition_sizes) == (design, sizes), run_id
        assert run.policy.name == policy[(run.model.family.name, mode)], run_id
        assert (run.repeats, run.tool_turns, run.scenario_count) == (repeats, 6, 1080), run_id
        home = next(iter(run.model.deployments)) if twin == run_id else SM80
        assert run.environment.key == home, run_id
        assert run.confirmatory is False, "there is no pre-registration, so nothing is"
    assert len(main) == 7 * (2 * 13 + 2) + 2 * len(SM80_COPY_KINDS)


def test_the_ladder_run_asks_for_sets_above_a_pair():
    """The first run config that does. Until it exists, the study's headline --
    do pairwise measurements predict a three-way outcome -- has no data that
    could answer it, because `design.py` built sizes 1 and 2 and nothing else."""
    run = load_run("ladder-qwen3-14b")
    assert run.design == "composition-ladder"
    assert run.composition_sizes == (2, 3, 5), "the ladder dataset-plan.md declares"
    assert run.composition_max_sources == 5
    assert run.confirmatory is False, "a first run of a new design is never evidence"


def test_no_two_runs_share_a_seed_but_a_copy_of_one_run_on_another_machine():
    """A draw is (base_seed, trial_id, repeat), and trial ids repeat across runs by design.
    Two runs sharing a base seed would redraw the same samples for the same items and quietly
    turn a second measurement into a copy of the first. A copy meant to be one is the exception:
    a 32B -sm80 run shares its DGX-1 twin's seed, so either can stand in for the other."""
    by_seed = collections.defaultdict(list)
    for run_id in serving.run_ids():
        by_seed[load_run(run_id).base_seed].append(run_id)
    for runs in by_seed.values():
        if len(runs) == 1:
            continue
        assert len(runs) == 2, runs
        twin, copy = (load_run(r) for r in sorted(runs))
        assert copy.run_id == twin.run_id + SM80_COPY, runs
        assert (copy.model.key, twin.environment.key, copy.environment.key) == \
            (twin.model.key, V100, SM80), runs
    assert sum(len(runs) == 2 for runs in by_seed.values()) == 2 * len(SM80_COPY_KINDS)


def _sm80_copy_departures(configs):
    """Every way the 32B's runs on the 80 GB cards depart from their DGX-1 twins beyond what
    the machines force: the environment, the run id, the `_about` text, the tensor-parallel
    size, and the serve flags the two environments require differently."""
    want = [{**e.serve_requires, **e.profile.family_flags["qwen3"]}
            for e in (ENVIRONMENTS[V100], ENVIRONMENTS[SM80])]
    forced = {f for f in {*want[0], *want[1]} if want[0].get(f) != want[1].get(f)}
    forced.add("tensor-parallel-size")
    v100, sm80 = (read_serve_config(str(configs / "vllm" / name))
                  for name in ("qwen3-32b.yaml", "qwen3-32b-sm80.yaml"))
    out = [f"serve: {flag}" for flag in sorted({*v100, *sm80} - forced)
           if v100.get(flag) != sm80.get(flag)]
    for path in sorted((configs / "runs").glob(f"*{SM80_COPY}.json")):
        copy = json.loads(path.read_text())
        twin = json.loads((configs / "runs" / path.name.replace(SM80_COPY, "")).read_text())
        if (twin["environment"], copy["environment"]) != (V100, SM80) \
                or copy["run_id"] != twin["run_id"] + SM80_COPY:
            out.append(f"{path.stem}: environment or run id")
        out += [f"{path.stem}: {key}"
                for key in sorted({*copy, *twin} - {"environment", "run_id", "_about"})
                if copy.get(key) != twin.get(key)]
    return out


def test_the_32b_copies_on_the_80gb_cards_are_their_dgx1_twins_but_for_the_machine(config_copy):
    """A copy stands in for its DGX-1 twin, and the two ladders are compared, so each pair must
    be one experiment: the same settings and seed, the same trials, the same seed for every draw
    and the same request. Only the machine differs, with what it forces. A planted departure is
    caught."""
    assert _sm80_copy_departures(config_copy) == []
    for run_id in (r for r in serving.run_ids() if r.endswith(SM80_COPY)):
        copy, twin = load_run(run_id), load_run(run_id.removesuffix(SM80_COPY))
        specs = trials_for_run(copy, SCENARIOS)
        assert specs == trials_for_run(twin, SCENARIOS), run_id
        draws = [(s.trial_id, r) for s in specs for r in range(copy.repeats)]
        assert [copy.decoding(*d) for d in draws] == [twin.decoding(*d) for d in draws], run_id
        first = specs[0]
        assert build_model_request(first, SCENARIOS, copy.deployment,
                                   copy.decoding(first.trial_id, 0)) == \
            build_model_request(first, SCENARIOS, twin.deployment,
                                twin.decoding(first.trial_id, 0)), run_id
    _sub(config_copy / "runs" / "main-tier-qwen3-32b-think-sm80.json",
         '"base_seed": 20261209', '"base_seed": 20261210')
    _sub(config_copy / _Q32S, "max-model-len: 40960", "max-model-len: 32768")
    assert _sm80_copy_departures(config_copy) == [
        "serve: max-model-len", "main-tier-qwen3-32b-think-sm80: base_seed"]


def test_a_second_rung_changes_the_model_and_nothing_else():
    """Two runs that differ in two things cannot say which one moved a number.
    `balanced-qwen3-14b` exists to ask whether the 1.7B's position effect is the model or the
    setup, so everything except the weights and the seed is held fixed."""
    small, big = load_run("balanced-qwen3-1.7b"), load_run("balanced-qwen3-14b")
    for field in ("design", "composition_sizes", "composition_max_sources",
                  "repeats", "tool_turns", "scenario_count", "confirmatory"):
        assert getattr(small, field) == getattr(big, field), field
    assert small.policy.name == big.policy.name
    assert small.environment.key == big.environment.key
    assert small.model.key != big.model.key
    assert small.model.family.name == big.model.family.name, \
        "a different family would change the operator channel as well as the size"


def test_the_balanced_run_asks_for_the_control_arm_and_an_agent_loop():
    """The three things the first run could not do, stated in its successor's
    config rather than left to the code: each side of a conflict also asked on
    its own, more than one draw per item, and a loop that answers a tool call."""
    run = load_run("balanced-qwen3-1.7b")
    assert run.design == "pairwise-balanced"
    assert run.composition_sizes == (1, 2)
    assert run.tool_turns > 1 and run.repeats > 1
    assert run.confirmatory is False, "a shakedown is never confirmatory evidence"
    assert run.base_seed != load_run("initial-qwen3-1.7b").base_seed, \
        "the same seed would redraw the first run's samples for the same trial ids"


@pytest.mark.parametrize("field,value,match", [
    ("composition_sizes", [], "non-empty"),
    ("composition_sizes", [2, 2], "repeats a size"),
    ("composition_sizes", [0, 2], "at least 1"),
    ("composition_sizes", "1,2", "non-empty list"),
    ("tool_turns", 0, "from 1 to 12"),
    ("tool_turns", 99, "from 1 to 12"),
    ("tool_turns", True, "from 1 to 12"),
])
def test_a_run_config_that_states_the_new_settings_badly_is_refused(
        tmp_path, monkeypatch, field, value, match):
    doc = json.loads(open(os.path.join(serving.RUNS_DIR,
                                       "balanced-qwen3-1.7b.json")).read())
    doc[field] = value
    doc["run_id"] = "broken"
    monkeypatch.setattr(serving, "RUNS_DIR", str(tmp_path))
    (tmp_path / "broken.json").write_text(json.dumps(doc))
    with pytest.raises(ConfigError, match=match):
        load_run("broken")


# --- The reply: reasoning must not be mistaken for the answer, or lost as it ---

STACK = ServingStack(model="test-model")
CLIENT = ServingStack(model="test-model", reasoning_separation="client")


def _with_reasoning(text, reasoning, field="reasoning"):
    payload = completion_from(text=text)
    payload["choices"][0]["message"][field] = reasoning
    return payload


def test_reasoning_with_thinking_off_is_a_fault_not_an_empty_answer():
    """The failure vLLM's qwen3 parser produces when a request does not say:
    the whole answer filed as reasoning, `content` empty."""
    spec = RECONS["comp-01"].spec
    for field in ("reasoning", "reasoning_content"):
        payload = _with_reasoning("", "Stage them in /scratch/d.", field)
        off = score(spec, SCENARIOS, payload, STACK, Decoding(enable_thinking=False))
        assert not off.usable and any("thinking off" in f for f in off.faults), field
        on = score(spec, SCENARIOS, payload, STACK, Decoding(enable_thinking=True))
        assert not any("thinking off" in f for f in on.faults), field


def test_reasoning_markers_in_the_answer_are_a_fault_where_the_server_should_have_split():
    for text in ("Considering both.\n</think>\n\nStaged.", "<|channel|>final<|message|>Staged."):
        assert parse_completion(completion_from(text=text)).faults, text
    assert parse_completion(completion_from(text="Staged in /scratch/d.")).faults == ()


def test_where_this_package_splits_the_thinking_the_answer_is_what_follows_it():
    """The V100 machine's engine has no parser it can use, so the reply arrives
    whole: the model's thinking, then </think>, then the answer. The Qwen
    templates put the opening tag in the prompt, so a reply usually has only the
    closing one."""
    payload = completion_from(text="Weighing the two rules.\n</think>\n\nStaged in /scratch/d.")
    parsed = parse_completion(payload, reasoning_separation="client", thinking=True)
    assert parsed.response.text == "Staged in /scratch/d."
    assert parsed.reasoning.strip() == "Weighing the two rules."
    assert parsed.faults == ()
    echoed = parse_completion(completion_from(text="<think>Weighing.</think>\n\nStaged."),
                              reasoning_separation="client", thinking=True)
    assert (echoed.response.text, echoed.reasoning, echoed.faults) == ("Staged.", "Weighing.", ())


def test_a_reply_that_never_closed_its_reasoning_holds_no_answer():
    """The opposite of what vLLM 0.8.5's deepseek_r1 parser does with the same
    text. Scoring the thinking as the answer would invent a choice the model
    never made. A block is open either because the reply opened it -- Qwen 3 --
    or because the template did, which the family records."""
    opened = "<think>\nStill weighing the two rules and"
    answer, reasoning, faults = split_reasoning(opened)
    assert answer == "" and reasoning.startswith("<think>")
    assert any("never closed" in f for f in faults)
    parsed = parse_completion(completion_from(text=opened, finish_reason="length"),
                              reasoning_separation="client", thinking=True)
    assert parsed.response.text == "" and parsed.truncated
    assert any("never closed" in f for f in parsed.faults)
    assert split_reasoning("Still weighing", prompt_opened=True)[0] == ""


def test_a_qwen3_reply_with_no_tag_at_all_is_an_answer_not_thinking():
    """Qwen 3's template prefills nothing, so a model that answers without
    thinking writes no tag. Reading that as unfinished thinking would throw the
    answer away -- which is why the prefill is a recorded fact per family and not
    a guess."""
    assert QWEN3.thinking_prefills_open_block is False
    assert QWEN35.thinking_prefills_open_block is True
    answer, reasoning, faults = split_reasoning("Staged in /scratch/d.")
    assert (answer, reasoning, faults) == ("Staged in /scratch/d.", "", [])
    assert split_reasoning("Staged in /scratch/d.", prompt_opened=True)[0] == ""


def test_a_tool_call_inside_the_thinking_is_recorded_as_a_doubt():
    """Without a reasoning parser the engine's tool parser reads the whole reply,
    so a call the model only considered can be reported as one it made."""
    text = "Maybe <tool_call>\n{\"name\": \"write_file\"}\n</tool_call>\n</think>\n\nDone."
    parsed = parse_completion(completion_from(text=text), reasoning_separation="client",
                              thinking=True)
    assert parsed.response.text == "Done."
    assert any("only considered" in f for f in parsed.faults)


def test_a_thinking_reply_is_scored_from_its_answer_where_the_machine_splits():
    """End to end, through `score`: the same answer, once bare and once behind
    the thinking that produced it, is the same record on a client-split stack --
    and on a server-split stack the second is a fault, because the parser that
    was supposed to remove it did not."""
    from whowins.runner.tools import WRITE_TOOL
    spec = RECONS["comp-08"].spec
    answer = "These instructions conflict; going with the user's."
    calls = [{"name": WRITE_TOOL, "arguments": {"path": "/scratch/c/x"}}]
    thinking = Decoding(enable_thinking=True)
    bare = completion_from(text=answer, tool_calls=calls)
    behind = completion_from(text=f"<think>\nWeighing the two rules.\n</think>\n\n{answer}",
                             tool_calls=calls)

    plain = score(spec, SCENARIOS, bare, CLIENT, thinking)
    wrapped = score(spec, SCENARIOS, behind, CLIENT, thinking)
    assert plain.outcome.winning_option == "o3" and plain.communication == "flagged"
    assert (wrapped.outcome, wrapped.communication) == (plain.outcome, plain.communication)
    assert wrapped.faults == () and wrapped.usable

    served = score(spec, SCENARIOS, behind, STACK, thinking)
    assert served.faults and not served.usable


def test_thinking_off_on_the_client_machine_is_read_exactly_as_before():
    """With thinking off the template closes the block inside the prompt, so a
    marker in the reply means the mode and the template disagreed."""
    spec = RECONS["comp-01"].spec
    good = score(spec, SCENARIOS, completion_from(text="Staged in /scratch/d."), CLIENT,
                 Decoding(enable_thinking=False))
    assert good.faults == ()
    leaked = parse_completion(completion_from(text="Hm.\n</think>\n\nStaged."),
                              reasoning_separation="client", thinking=False)
    assert leaked.faults and leaked.response.text.startswith("Hm.")


# --- Free GPUs on a shared machine ---


def test_the_lowest_numbered_free_gpus_are_chosen():
    rows = [(0, 18304), (1, 6), (2, 2298), (3, 4), (4, 28034), (5, 2), (6, 31738), (7, 1644)]
    assert choose_gpus(rows, 1) == [1]
    assert choose_gpus(rows, 3) == [1, 3, 5]


def test_the_cards_you_name_are_used_once_they_are_checked():
    """Choosing them yourself is normal on a shared machine. Being told one is
    already taken is why the check still runs."""
    rows = [(0, 18304), (1, 6), (2, 2298), (3, 4)]
    assert choose_gpus(rows, 2, want=[3, 1]) == [3, 1]
    with pytest.raises(NoFreeGpu, match=r"in use: 0 \(18304 MiB\)"):
        choose_gpus(rows, 1, want=[0])
    with pytest.raises(NoFreeGpu, match="has no GPU"):
        choose_gpus(rows, 1, want=[9])
    with pytest.raises(NoFreeGpu, match="needs 2 GPU"):
        choose_gpus(rows, 2, want=[1])
    with pytest.raises(NoFreeGpu, match="named twice"):
        choose_gpus(rows, 2, want=[1, 1])


def test_a_busy_machine_refuses_rather_than_sharing_a_card():
    """vLLM takes a fraction of each card's total memory, not of what is free."""
    rows = [(0, 18304), (1, 6), (2, 2298)]
    with pytest.raises(NoFreeGpu, match=r"needs 2 free GPU\(s\) and 1 are free"):
        choose_gpus(rows, 2)
    with pytest.raises(NoFreeGpu, match="18304 MiB"):
        choose_gpus(rows, 2)


def _fake_nvidia_smi(tmp_path, body):
    path = tmp_path / "nvidia-smi"
    path.write_text(f"#!/bin/sh\ncat <<'EOF'\n{body}\nEOF\n")
    path.chmod(0o755)
    return str(path)


def test_the_gpu_reader_reads_what_nvidia_smi_prints(tmp_path):
    smi = _fake_nvidia_smi(tmp_path, "0, 18304\n1, 6\n2, 2298")
    assert gpu_rows(smi) == [(0, 18304), (1, 6), (2, 2298)]


def test_the_gpu_reader_refuses_output_it_cannot_read(tmp_path):
    with pytest.raises(NoFreeGpu):
        gpu_rows(_fake_nvidia_smi(tmp_path, "no devices were found"))


# --- The scripts ---


def _bash(*args, env=None):
    return subprocess.run(["bash", *args], cwd=ROOT, capture_output=True, text=True,
                          env=env if env is not None else dict(os.environ))


def test_every_script_parses():
    for script in sorted(glob.glob(os.path.join(ROOT, "scripts", "*.sh"))):
        assert _bash("-n", script).returncode == 0, script


@pytest.mark.parametrize("key", list(ROSTER))
def test_the_serve_script_prints_the_pinned_command_and_environment(key):
    out = _bash("scripts/serve.sh", "--print", key)
    assert out.returncode == 0, out.stderr
    assert f"configs/vllm/{key}.yaml" in out.stdout
    exports = set(re.findall(r"^export (\S+)$", out.stdout, re.M))
    assert exports == {f"{k}={v}" for k, v in ROSTER[key].deployment.serve_env.items()}


def test_the_env_script_prints_the_commands_that_build_this_machine_s_environment():
    out = _bash("scripts/create_env.sh", "--print", V100)
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines() == ENVIRONMENTS[V100].conda.commands()
    listing = _bash("scripts/create_env.sh")
    assert listing.returncode == 0 and "ipb-v100" in listing.stdout
    unknown = _bash("scripts/create_env.sh", "--print", "somebody-elses-box")
    assert unknown.returncode != 0 and "no environment" in unknown.stderr


def test_the_serve_script_names_the_environment_to_activate(tmp_path):
    """The likeliest mistake on a machine with several environments is running in
    the wrong one, so the refusal says which to activate and how to build it."""
    out = _bash("scripts/serve.sh", "qwen3-1.7b", env=_fake_vllm(tmp_path, "0.28.0"))
    assert out.returncode == 3
    assert "conda activate ipb-v100" in out.stderr
    assert "scripts/create_env.sh v100-vllm085" in out.stderr


def test_the_serve_script_refuses_an_unknown_model():
    out = _bash("scripts/serve.sh", "--print", "qwen3-3b")
    assert out.returncode != 0 and "no model" in out.stderr


def _fake_vllm(tmp_path, version, smi=None):
    """A `vllm` package reporting `version`, to an import and to the package metadata
    serve.sh reads first (so an installed vLLM cannot answer instead), a `vllm` command
    that prints what it was started with, and optionally a made-up machine for the GPU check."""
    pkg = tmp_path / "py" / "vllm"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(f'__version__ = "{version}"\n')
    info = tmp_path / "py" / f"vllm-{version}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: vllm\nVersion: {version}\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cmd = bin_dir / "vllm"
    cmd.write_text('#!/bin/sh\necho "ARGS: $*"\nenv | grep -E "^(VLLM_|CUDA_VISIBLE)" | sort\n')
    cmd.chmod(0o755)
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "py"),
           "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    if smi is not None:
        env["NVIDIA_SMI"] = _fake_nvidia_smi(tmp_path, smi)
    return env


def test_the_serve_script_refuses_an_unpinned_vllm(tmp_path):
    out = _bash("scripts/serve.sh", "qwen3.5-2b", env=_fake_vllm(tmp_path, "0.29.0"))
    assert out.returncode == 3
    assert "pins vLLM 0.28.0" in out.stderr and "ARGS:" not in out.stdout


def test_the_serve_script_pins_each_machine_to_its_own_engine(tmp_path):
    """0.28.0 is right for one machine and wrong for the other."""
    out = _bash("scripts/serve.sh", "qwen3-1.7b", env=_fake_vllm(tmp_path, "0.28.0"))
    assert out.returncode == 3 and "pins vLLM 0.8.5.post1" in out.stderr


def test_the_serve_script_starts_vllm_with_the_config_and_environment(tmp_path):
    out = _bash("scripts/serve.sh", "gpt-oss-20b", "--port", "8001",
                env=_fake_vllm(tmp_path, "0.28.0"))
    assert out.returncode == 0, out.stderr
    args = next(line for line in out.stdout.splitlines() if line.startswith("ARGS:"))
    assert args.endswith("configs/vllm/gpt-oss-20b.yaml --port 8001")
    assert args.startswith("ARGS: serve --config ")
    for k, v in ROSTER["gpt-oss-20b"].deployment.serve_env.items():
        assert f"{k}={v}" in out.stdout.splitlines()


def test_the_serve_script_takes_free_gpus_on_the_shared_machine(tmp_path):
    env = _fake_vllm(tmp_path, "0.8.5.post1", smi="0, 18304\n1, 6\n2, 2298\n3, 4")
    out = _bash("scripts/serve.sh", "qwen3-1.7b", env=env)
    assert out.returncode == 0, out.stderr
    assert "CUDA_VISIBLE_DEVICES=1" in out.stdout.splitlines()
    assert "VLLM_USE_V1=0" in out.stdout.splitlines()


def test_the_serve_script_tolerates_vllm_noisy_import(tmp_path):
    """With no package metadata serve.sh imports vllm, which prints as it loads."""
    try:
        importlib.metadata.version("vllm")
        pytest.skip("an installed vLLM's metadata answers first, so the import is never reached")
    except importlib.metadata.PackageNotFoundError:
        pass
    env = _fake_vllm(tmp_path, "0.8.5.post1", smi="0, 18304\n1, 6\n2, 2298\n3, 4")
    shutil.rmtree(tmp_path / "py" / "vllm-0.8.5.post1.dist-info")
    init_py = tmp_path / "py" / "vllm" / "__init__.py"
    init_py.write_text(
        'print("INFO 09-13 01:38:14 [__init__.py:239] Automatically detected platform cuda.")\n'
        '__version__ = "0.8.5.post1"\n'
    )
    out = _bash("scripts/serve.sh", "qwen3-1.7b", env=env)
    assert out.returncode == 0, out.stderr
    assert "CUDA_VISIBLE_DEVICES=1" in out.stdout.splitlines()


def test_the_serve_script_serves_on_the_cards_you_name(tmp_path):
    env = _fake_vllm(tmp_path, "0.8.5.post1", smi="0, 18304\n1, 6\n2, 2298\n3, 4")
    out = _bash("scripts/serve.sh", "--gpus", "3,1", "--tp", "2", "qwen3-14b", env=env)
    assert out.returncode == 0, out.stderr
    assert "CUDA_VISIBLE_DEVICES=3,1" in out.stdout.splitlines()
    busy = _bash("scripts/serve.sh", "--gpus", "0", "qwen3-1.7b", env=env)
    assert busy.returncode == 4 and "ARGS:" not in busy.stdout


def test_the_serve_script_leaves_a_choice_you_already_made_alone(tmp_path):
    env = _fake_vllm(tmp_path, "0.8.5.post1", smi="0, 18304\n1, 6")
    env["CUDA_VISIBLE_DEVICES"] = "5"
    out = _bash("scripts/serve.sh", "qwen3-1.7b", env=env)
    assert out.returncode == 0 and "CUDA_VISIBLE_DEVICES=5" in out.stdout.splitlines()
    assert "already set" in out.stderr


def test_the_serve_script_can_be_told_not_to_check_at_all(tmp_path):
    env = _fake_vllm(tmp_path, "0.8.5.post1", smi="0, 31000\n1, 31000")
    out = _bash("scripts/serve.sh", "--any-gpu", "qwen3-1.7b", env=env)
    assert out.returncode == 0 and "not checking" in out.stderr


@pytest.mark.parametrize("flags,expected", [
    (["--tp", "2"], "--tensor-parallel-size 2"),
    (["--gpu-mem", "0.85"], "--gpu-memory-utilization 0.85"),
    (["--max-seqs", "32"], "--max-num-seqs 32"),
])
def test_the_serve_script_takes_an_override_and_says_so_loudly(flags, expected):
    """vLLM takes the command line over the config file, so an override really
    does change the snapshot. It is printed where it cannot be missed."""
    out = _bash("scripts/serve.sh", "--print", *flags, "qwen3-8b")
    assert out.returncode == 0, out.stderr
    assert expected in out.stdout
    assert "OVERRIDING" in out.stderr and "different" in out.stderr
    plain = _bash("scripts/serve.sh", "--print", "qwen3-8b")
    assert expected.split()[0] not in plain.stdout and "OVERRIDING" not in plain.stderr


def test_the_serve_script_refuses_to_start_beside_another_job(tmp_path):
    env = _fake_vllm(tmp_path, "0.8.5.post1", smi="0, 18304\n1, 6\n2, 2298\n3, 31000")
    out = _bash("scripts/serve.sh", "qwen3-14b", env=env)  # needs two free
    assert out.returncode == 4 and "ARGS:" not in out.stdout
    assert "free" in out.stderr


def test_the_download_script_fetches_every_model_at_its_commit():
    out = _bash("scripts/download_models.sh", "--print", "all")
    assert out.returncode == 0, out.stderr
    lines = out.stdout.strip().splitlines()
    assert len(lines) == 15
    for line, (hf_id, revision) in zip(lines, PINNED.items()):
        assert f"repo_id={hf_id!r}" in line and f"revision={revision!r}" in line
        assert ("ignore_patterns=['original/*', 'metal/*']" in line) == hf_id.startswith("openai/")


def test_download_hands_the_hub_the_pin():
    calls = []
    serving.download(ROSTER["gpt-oss-20b"], fetch=lambda **kw: calls.append(kw) or "/cache")
    serving.download(ROSTER["qwen3-1.7b"], fetch=lambda **kw: calls.append(kw) or "/cache")
    assert calls == [
        {"repo_id": "openai/gpt-oss-20b", "revision": PINNED["openai/gpt-oss-20b"],
         "ignore_patterns": ["original/*", "metal/*"]},
        {"repo_id": "Qwen/Qwen3-1.7B", "revision": PINNED["Qwen/Qwen3-1.7B"]},
    ]


# --- Preflight, against a stub server on this machine ---


class _Stub(http.server.BaseHTTPRequestHandler):
    routes: dict = {}

    def do_GET(self):  # noqa: N802 - the name http.server calls
        body = self.routes.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def stub():
    routes: dict = {}
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                             type("Handler", (_Stub,), {"routes": routes}))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", routes
    server.shutdown()
    server.server_close()


def _serve(routes, dep, version=None, ids=None, max_len=None):
    routes["/version"] = {"version": version or dep.environment.engine_version}
    routes["/v1/models"] = {"object": "list", "data": [
        {"id": i, "object": "model", "max_model_len": max_len or dep.max_model_len}
        for i in (ids or [dep.model.hf_id])]}


def _cache(tmp_path, model, content):
    """The Hugging Face cache as scripts/download_models.sh leaves it, with the
    template in the file that model's family keeps it in."""
    org, name = model.hf_id.split("/")
    snap = tmp_path / f"models--{org}--{name}" / "snapshots" / model.revision
    snap.mkdir(parents=True)
    source = model.family.template_source
    if "key" in source:
        content = json.dumps({"model_max_length": 40960,
                              source["key"]: content.decode("utf-8")}).encode()
    (snap / source["file"]).write_bytes(content)
    return str(tmp_path)


def _template_bytes(which):
    with open(os.path.join(CONFIGS, "chat-templates", TEMPLATE_FILES[which]), "rb") as fh:
        return fh.read()


@pytest.mark.parametrize("key,which", [("qwen3.5-2b", "small"), ("qwen3-1.7b", "qwen3")])
def test_preflight_passes_a_server_that_matches_the_pins(stub, tmp_path, key, which):
    url, routes = stub
    dep = _dep(key)
    _serve(routes, dep)
    checks = preflight.run_checks(dep, url,
                                  cache_dir=_cache(tmp_path, dep.model, _template_bytes(which)))
    assert [(c.name, c.result) for c in checks] == [
        ("vllm version", "PASS"), ("served model", "PASS"), ("context length", "PASS"),
        ("chat template", "PASS")]
    assert preflight.exit_status(checks) == 0


@pytest.mark.parametrize("fault,failing", [
    (dict(version="0.29.0"), "vllm version"),
    (dict(ids=["Qwen/Qwen3.5-4B"]), "served model"),
    (dict(ids=["Qwen/Qwen3.5-2B", "a-lora-adapter"]), "served model"),
    (dict(max_len=262144), "context length"),
])
def test_preflight_fails_a_server_that_does_not(stub, tmp_path, fault, failing):
    url, routes = stub
    dep = _dep("qwen3.5-2b")
    _serve(routes, dep, **fault)
    checks = preflight.run_checks(dep, url,
                                  cache_dir=_cache(tmp_path, dep.model, _template_bytes("small")))
    assert [c.name for c in checks if c.result == "FAIL"] == [failing]
    assert preflight.exit_status(checks) == 1


@pytest.mark.parametrize("key,which", [("qwen3.5-2b", "small"), ("qwen3-1.7b", "qwen3")])
def test_preflight_fails_a_cached_template_that_is_not_the_pinned_one(stub, tmp_path, key, which):
    url, routes = stub
    dep = _dep(key)
    _serve(routes, dep)
    checks = preflight.run_checks(
        dep, url, cache_dir=_cache(tmp_path, dep.model, _template_bytes(which) + b"\n"))
    assert [c.name for c in checks if c.result == "FAIL"] == ["chat template"]


def test_preflight_fails_a_tokenizer_config_with_no_template_in_it(stub, tmp_path):
    url, routes = stub
    dep = _dep("qwen3-1.7b")
    _serve(routes, dep)
    org, name = dep.model.hf_id.split("/")
    snap = tmp_path / f"models--{org}--{name}" / "snapshots" / dep.model.revision
    snap.mkdir(parents=True)
    (snap / "tokenizer_config.json").write_text(json.dumps({"model_max_length": 40960}))
    checks = preflight.run_checks(dep, url, cache_dir=str(tmp_path))
    assert [c.name for c in checks if c.result == "FAIL"] == ["chat template"]


def test_preflight_says_what_it_could_not_check_and_does_not_pass_it(stub, tmp_path):
    url, routes = stub
    dep = _dep("qwen3.5-2b")
    _serve(routes, dep)
    checks = preflight.run_checks(dep, url, cache_dir=str(tmp_path))
    assert checks[-1].result == "NOT CHECKED"
    assert preflight.exit_status(checks) == 3


def test_preflight_checks_the_harmony_version_for_gpt_oss(stub):
    url, routes = stub
    dep = _dep("gpt-oss-20b")
    _serve(routes, dep)
    good = preflight.run_checks(dep, url, harmony_version="0.0.8")
    assert [c.result for c in good] == ["PASS"] * 4 and good[-1].name == "openai-harmony"
    old = preflight.run_checks(dep, url, harmony_version="0.0.4")
    assert [c.name for c in old if c.result == "FAIL"] == ["openai-harmony"]


def test_preflight_fails_a_server_it_cannot_reach():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    checks = preflight.run_checks(_dep("qwen3-1.7b"), f"http://127.0.0.1:{port}", timeout=2)
    assert [c.result for c in checks[:2]] == ["FAIL", "FAIL"]
