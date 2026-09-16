"""Invariants of Observation Contract V1, and proof of what was NOT changed.

Two jobs:

1. Pin the contract's structural guarantees so a later change has to break a
   test rather than drift.
2. Prove the boundaries this gate promised not to cross — specifically that no
   prompt text was tuned. That claim is worth an assertion rather than a
   sentence in a report.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.common.contracts import MAIN_FRAME

PARENT_COMMIT = "213779b"
PROMPT_BLOCKS = ("POLICY_BLOCK", "STRICT_JSON_OUTPUT_BLOCK",
                 "NATIVE_TOOLS_OUTPUT_BLOCK")


def _block(source: str, name: str) -> str:
    """Extract a triple-quoted module constant."""
    m = re.search(rf'^{name} = """(.*?)"""', source, re.S | re.M)
    assert m, f"{name} not found"
    return m.group(1)


def _parent_file(path: str) -> str:
    """Read a file as it was at the parent commit.

    Bytes, decoded as UTF-8 explicitly: `text=True` would use the locale
    codepage on Windows and mangle every non-ASCII character, which looks
    exactly like a spurious diff.
    """
    out = subprocess.run(
        ["git", "show", f"{PARENT_COMMIT}:{path}"],
        capture_output=True, cwd=str(ROOT),
    )
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")
    return out.stdout.decode("utf-8")


# ------------------------------------------------- what must NOT have changed


@pytest.mark.parametrize("block", PROMPT_BLOCKS)
def test_prompt_text_is_byte_identical_to_the_parent_commit(block):
    """No prompt tuning happened in this gate.

    The observation *rendering* changed, because new contract fields have to be
    serialised somewhere. The instruction and policy text did not.
    """
    old = _block(_parent_file("experiments/common/context_builder.py"), block)
    new = _block(
        (ROOT / "experiments/common/context_builder.py").read_text(encoding="utf-8"),
        block,
    )
    assert hashlib.sha256(old.encode()).hexdigest() == \
        hashlib.sha256(new.encode()).hexdigest(), (
        f"{block} changed; this gate may not tune prompts"
    )


def test_model_adapter_is_untouched():
    """Model, parameters and decision schema are out of scope for this gate."""
    old = _parent_file("experiments/common/model_adapter.py")
    new = (ROOT / "experiments/common/model_adapter.py").read_text(encoding="utf-8")
    assert old == new, "model adapter changed; Qwen configuration is frozen here"


def test_adequacy_threshold_is_untouched():
    old = _parent_file("experiments/qwen_adequacy/ADEQUACY_THRESHOLD.md")
    new = (ROOT / "experiments/qwen_adequacy/ADEQUACY_THRESHOLD.md").read_text(
        encoding="utf-8")
    assert old == new, "adequacy thresholds must not move"


@pytest.mark.parametrize("dataset", [
    "experiments/qwen_decision_interface/dataset_v1.json",
    "experiments/qwen_decision_interface/observations_v1.json",
    "experiments/qwen_adequacy/adequacy_v1.json",
    "experiments/qwen_adequacy/adequacy_observations_v1.json",
])
def test_frozen_datasets_are_unmodified(dataset):
    """Historical evidence stays byte-identical; no dataset was regenerated."""
    old = _parent_file(dataset)
    new = (ROOT / dataset).read_text(encoding="utf-8")
    assert old == new, f"{dataset} was modified"


def test_no_controller_planner_or_memory_was_added():
    production = ROOT / "browser_agent_v2"
    packages = sorted(p.name for p in production.iterdir()
                      if p.is_dir() and not p.name.startswith("__"))
    assert packages == ["verification"], (
        f"production gained packages beyond verification: {packages}"
    )


# -------------------------------------------------------- contract invariants


def test_frame_ids_are_minted_not_positional(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/frames_adversarial"))
    import time
    time.sleep(0.8)
    obs = kernel.observe()
    ids = [f.frame_id for f in obs.frames]
    assert ids, "no frames recorded"
    assert all(re.fullmatch(r"fr_\d+", i) for i in ids), ids
    assert not any(re.fullmatch(r"f\d+", i) for i in ids), (
        f"positional frame ids are still in use: {ids}"
    )


def test_main_frame_is_identified_and_unique(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/frames_adversarial"))
    import time
    time.sleep(0.8)
    obs = kernel.observe()
    mains = [f for f in obs.frames if f.is_main]
    assert len(mains) == 1
    assert obs.main_frame_id == mains[0].frame_id
    assert obs.resolve_frame_id(MAIN_FRAME) == obs.main_frame_id


def test_every_observation_content_item_is_frame_scoped(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/frames_adversarial"))
    import time
    time.sleep(0.8)
    obs = kernel.observe()
    known = {f.frame_id for f in obs.frames}
    assert all(e.frame_id in known for e in obs.elements)
    assert all(b.frame_id in known for b in obs.text_blocks)
    assert all(g.frame_id in known for g in obs.groups)


def test_targets_encode_observation_and_frame(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/verify_records"))
    obs = kernel.observe()
    for e in obs.elements:
        obs_id, frame_id, local = e.target.split(":", 2)
        assert obs_id == obs.observation_id
        assert frame_id == e.frame_id
        assert local.startswith("e")


def test_group_ids_are_frame_qualified(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/verify_records"))
    obs = kernel.observe()
    assert obs.groups
    for g in obs.groups:
        assert g.group_id.startswith(g.frame_id + ":g")


def test_observation_is_json_serialisable(kit):
    import json

    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/tables_adversarial"))
    obs = kernel.observe()
    blob = json.dumps(obs.to_json())
    round_tripped = json.loads(blob)
    for key in ("main_frame_id", "frames", "groups", "text_blocks", "elements"):
        assert key in round_tripped, key


def test_observation_ids_are_monotonic(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/verify_records"))
    a = kernel.observe()
    b = kernel.observe()
    assert int(a.observation_id.split("_")[1]) < int(b.observation_id.split("_")[1])
