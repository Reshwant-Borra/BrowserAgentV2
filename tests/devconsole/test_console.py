"""Developer Console contract + smoke tests (D-025: observational only).

The console must (a) report exactly the verdicts the backend/harness
computed, never its own; (b) never leak opaque adapter handles; (c) never
be imported by the backend; (d) actually serve over localhost.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from devconsole import views
from devconsole.server import make_server
from tests.computer_agent.campaign import run_trial
from tests.computer_agent.fixtures.scenarios import SCENARIO_NAMES

ROOT = Path(__file__).resolve().parents[2]
HANDLE = re.compile(r'"h-\d+"')


@pytest.mark.parametrize("scenario", SCENARIO_NAMES)
def test_m1_view_reports_backend_verdicts_verbatim(scenario):
    for seed in (0, 1, 17):
        view = views.m1_view(scenario, seed)
        record = run_trial(scenario, seed)
        assert view["grading"]["safety"] == record.safety
        assert view["dispatch"]["dispatched"] == record.dispatched
        assert view["resolution"]["outcome"] == record.resolution_outcome_t0
        if view["freshness"] is not None:
            assert view["freshness"]["outcome"] == record.freshness_outcome
        assert view == views.m1_view(scenario, seed), "same seed must render identically"


def test_views_never_emit_opaque_handles():
    for scenario in SCENARIO_NAMES:
        assert not HANDLE.search(json.dumps(views.m1_view(scenario, 5)))


def test_backend_never_imports_devconsole():
    for path in (ROOT / "computer_agent").rglob("*.py"):
        assert "devconsole" not in path.read_text(), path
    probe = "import sys, computer_agent, computer_agent.grounding; print('devconsole' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


@pytest.fixture
def server():
    srv = make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, r.read()


def test_server_smoke(server):
    status, body = _get(server + "/")
    assert status == 200 and b"Developer Console" in body
    catalog = json.loads(_get(server + "/api/scenarios")[1])
    assert catalog["m1"] == list(SCENARIO_NAMES)
    view = json.loads(_get(server + "/api/m1?scenario=overlay_inserted_colliding&seed=3")[1])
    assert view["grading"]["safety"] == run_trial("overlay_inserted_colliding", 3).safety
    for bad, code in (("/api/nope", 404), ("/api/m1?scenario=nope&seed=0", 400)):
        with pytest.raises(urllib.error.HTTPError) as exc:
            _get(server + bad)
        assert exc.value.code == code


def test_m2_view_reports_backend_verdicts_verbatim():
    from tests.computer_agent import m2_campaign
    from tests.computer_agent.fixtures.fixture_b import CASE_NAMES

    for case in CASE_NAMES:
        view = views.m2_view(case, 3)
        trial = m2_campaign.run_trial(case, 3)
        assert view["verdict"]["verification_outcome"] == trial.verdict
        assert view["executor_claim"]["ok"] == trial.executor_claim_ok
        assert view["grading"]["false_success"] == trial.false_success
        json.dumps(view)  # display-safe: fully serializable (indeterminate values rendered as text)


def test_m3_view_reports_backend_verdicts_verbatim():
    from computer_agent.types import EffectClass
    from tests.computer_agent import m3_campaign
    from tests.computer_agent.fixtures.fixture_c import COMBINED_SCENARIOS

    for name in COMBINED_SCENARIOS:
        view = views.m3_view(name, 2)
        trial = m3_campaign.run_combined(name, 2)
        assert view["verdict"]["task"] == trial.final
        assert {k: r["step_status"] for k, r in view["lifecycle"].items()} == trial.step_status
        assert not HANDLE.search(json.dumps(view))
    view = views.m3_view("crash:D:after_effect_before_return", 0)
    events = [e["event"] for e in view["timeline"]]
    assert events.index("CRASH") < events.index("RESTART") < events.index("OUTCOME_UNKNOWN") < events.index("NEEDS_REVIEW")
    assert view["verdict"]["task"] == m3_campaign.run_trial(EffectClass.NON_IDEMPOTENT_UNQUERYABLE,
                                                            "after_effect_before_return", 0).final
