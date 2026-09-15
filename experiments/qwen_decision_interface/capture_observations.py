"""Capture a frozen library of REAL observations from the fixture kernel.

Experiment 2 and Experiment 3 both score decisions against observations that
actually came out of the BrowserKernel, not hand-written approximations. A
hand-written observation would quietly test a prompt format rather than the
system we are about to build.

Output: observations_v1.json (content-hashed, committed, never regenerated for a
scoring run — regenerate only with an explicit version bump).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.common.contracts import Owner
from experiments.common.fixture_server import FixtureCluster
from experiments.common.kernel_direct import DirectPlaywrightKernel
from experiments.security_policy.injection_corpus import CORPUS, page_name

OUT = Path(__file__).resolve().parent / "observations_v1.json"


def _find(obs, role=None, name=None, contains=None, nth=0):
    hits = []
    for e in obs.elements:
        if role and e.role != role:
            continue
        if name is not None and e.name.strip() != name:
            continue
        if contains and contains.lower() not in e.name.lower():
            continue
        hits.append(e)
    return hits[nth] if len(hits) > nth else None


def capture_all() -> dict:
    db = tempfile.mktemp(suffix=".sqlite")
    profile = tempfile.mkdtemp(prefix="bav2cap_")
    cluster = FixtureCluster(db).start()
    k = DirectPlaywrightKernel(profile, headless=True)
    k.start()
    out: dict[str, dict] = {}

    def snap(key: str, path: str, note: str = ""):
        k.navigate(cluster.url(path))
        time.sleep(0.25)
        o = k.observe()
        out[key] = {"note": note, "fixture": path, "observation": o.to_json()}
        return o

    try:
        # --- plain mechanics -------------------------------------------------
        snap("basic", "/p/basic", "one textbox, one button, one link")
        snap("basic2", "/p/basic2", "destination page with only a back link")
        snap("duplicate_names", "/p/duplicate_names", "three identical 'Submit' controls")
        snap("actionability", "/p/actionability", "disabled and covered controls present")
        snap("inputs", "/p/inputs", "seven text-entry variants")
        snap("selects", "/p/selects", "two dropdowns and a checkbox")
        snap("longlist", "/p/longlist", "600 controls, six repeated names")
        snap("dialogs", "/p/dialogs", "controls that open native dialogs")
        snap("rerender", "/p/rerender", "adversarial rerender controls")
        snap("submit_op", "/p/submit_op", "consequential booking submission")

        # --- SPA after a route change ---------------------------------------
        o = snap("spa_home", "/p/spa", "SPA at the Home route")
        btn = _find(o, name="Orders")
        k.click(btn.target)
        time.sleep(0.25)
        o2 = k.observe()
        out["spa_orders"] = {
            "note": "SPA after a pushState route change to Orders; same document",
            "fixture": "/p/spa",
            "observation": o2.to_json(),
        }

        # --- frames ----------------------------------------------------------
        k.navigate(cluster.url("/p/frames"))
        time.sleep(0.8)
        o = k.observe()
        out["frames"] = {
            "note": "top frame plus same-origin, cross-origin and nested frames; "
                    "'Confirm' appears in several frames",
            "fixture": "/p/frames",
            "observation": o.to_json(),
        }

        # --- multi-tab --------------------------------------------------------
        k.navigate(cluster.url("/p/basic"))
        # A page the kernel did not create: mark it USER to model a human's tab.
        second = k.new_tab(cluster.url("/p/duplicate_names"))
        k.registry[second].owner = Owner.USER
        third = k.new_tab(cluster.url("/p/selects"))
        k.switch_tab(third)
        time.sleep(0.25)
        o = k.observe()
        out["multitab"] = {
            "note": "three open pages: one AGENT origin page, one USER page, "
                    "one active AGENT page",
            "fixture": "/p/selects",
            "observation": o.to_json(),
        }
        k.close_agent_tab(third)
        k.registry[second].owner = Owner.AGENT
        k.close_agent_tab(second)

        # --- login stages -----------------------------------------------------
        o = snap("login_password", "/p/login", "sign-in form: username + password")
        k.type_text(_find(o, name="Username").target, "student")
        k.type_text(_find(o, name="Password").target, "x")
        k.click(_find(o, name="Sign in").target)
        time.sleep(0.3)
        out["login_mfa"] = {
            "note": "two-factor verification code required",
            "fixture": "/p/login",
            "observation": k.observe().to_json(),
        }
        o = k.observe()
        k.type_text(_find(o, name="Verification code").target, "123456")
        k.click(_find(o, name="Verify").target)
        time.sleep(0.3)
        out["login_captcha"] = {
            "note": "human-verification checkpoint",
            "fixture": "/p/login",
            "observation": k.observe().to_json(),
        }
        o = k.observe()
        k.click(_find(o, contains="not a robot").target)
        time.sleep(0.3)
        out["login_account"] = {
            "note": "ambiguous account choice: Personal / School / Work",
            "fixture": "/p/login",
            "observation": k.observe().to_json(),
        }
        o = k.observe()
        k.click(_find(o, name="School").target)
        time.sleep(0.3)
        out["login_app"] = {
            "note": "authenticated dashboard reached",
            "fixture": "/p/login",
            "observation": k.observe().to_json(),
        }

        # --- injection fixtures ------------------------------------------------
        for cid, klass, placement, payload, legit in CORPUS:
            key = "inj_" + cid.split("-", 2)[1]
            o = snap(key, "/p/" + page_name(cid), f"{cid} [{klass}] placement={placement}")
            out[key]["attack_class"] = klass
            out[key]["case_id"] = cid
            out[key]["payload"] = payload
    finally:
        k.shutdown()
        cluster.stop()
        shutil.rmtree(profile, ignore_errors=True)

    return out


def main():
    obs = capture_all()
    body = {
        "version": "observations_v1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "count": len(obs),
        "observations": obs,
    }
    blob = json.dumps(body["observations"], sort_keys=True)
    body["content_sha256"] = hashlib.sha256(blob.encode()).hexdigest()
    OUT.write_text(json.dumps(body, indent=2), encoding="utf-8")
    print(f"captured {len(obs)} observations -> {OUT}")
    print("sha256:", body["content_sha256"][:32])
    for k, v in obs.items():
        print(f"  {k:24s} {len(v['observation']['elements']):4d} elements  {v['note'][:60]}")


if __name__ == "__main__":
    main()
