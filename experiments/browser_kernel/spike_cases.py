"""Experiment 1 case suite: BrowserKernel adoption spike.

Question
--------
Which runtime should implement BrowserKernel for BrowserAgentV2:
Playwright MCP, or direct Playwright?

Both candidates run this identical suite through the identical BrowserKernel
interface. Ground truth for "what the page actually did" comes from the fixture
server's out-of-band effect log, never from the kernel under test.

Outcome vocabulary
------------------
PASS            invariant held
FAIL_SAFE       capability did not work, but failed closed (not disqualifying)
FAIL_UNSAFE     wrong thing happened silently — DISQUALIFYING
UNSUPPORTED     runtime cannot express this at all
HARNESS_ERROR   our bug, not the runtime's (never counted against a candidate)
"""

from __future__ import annotations

import time
import urllib.request
import json

from experiments.common.contracts import KernelError, KernelErrorCode, Owner

PASS = "PASS"
FAIL_SAFE = "FAIL_SAFE"
FAIL_UNSAFE = "FAIL_UNSAFE"
UNSUPPORTED = "UNSUPPORTED"
HARNESS_ERROR = "HARNESS_ERROR"


class Ctx:
    def __init__(self, kernel, cluster):
        self.k = kernel
        self.c = cluster

    # ---- kernel-independent oracle -------------------------------------
    def fx_reset(self):
        urllib.request.urlopen(self.c.url("/api/pagefx/reset"), timeout=10).read()

    def fx(self) -> list[str]:
        """Effects the page actually performed (excluding value reports)."""
        return [e["name"] for e in self._log() if not e["name"].startswith("VALUE:")]

    def _log(self) -> list[dict]:
        d = json.loads(urllib.request.urlopen(self.c.url("/api/pagefx/log"), timeout=10).read())
        return d["entries"]

    def field_value(self, key: str):
        """What the PAGE last saw in a field, independent of the kernel's claim."""
        hits = [e["detail"] for e in self._log() if e["name"] == "VALUE:" + key]
        return hits[-1] if hits else None

    def goto(self, path: str):
        self.fx_reset()
        self.k.navigate(self.c.url(path))
        return self.k.observe()

    def find(self, obs, role=None, name=None, contains=None, nth=0):
        hits = []
        for e in obs.elements:
            if role and e.role != role:
                continue
            if name is not None and e.name.strip() != name:
                continue
            if contains and contains.lower() not in e.name.lower():
                continue
            hits.append(e)
        if len(hits) <= nth:
            raise LookupError(
                f"no element role={role} name={name!r} contains={contains!r} nth={nth}; "
                f"available={[(e.role, e.name) for e in obs.elements][:25]}"
            )
        return hits[nth]


def result(status, detail="", **kw):
    return {"status": status, "detail": detail, **kw}

def observed_text(obs) -> str:
    """Join an observation's text blocks.

    Observation Contract V1 makes each block a frame-scoped record rather than a
    bare string. Tolerates both so historical observations still render.
    """
    out = []
    for b in getattr(obs, "text_blocks", []) or []:
        out.append(b.text if hasattr(b, "text") else str(b))
    return " ".join(out)



# ==========================================================================
# NAVIGATION
# ==========================================================================


def nav_01_open_url(ctx: Ctx):
    obs = ctx.goto("/p/basic")
    ok = obs.url.endswith("/p/basic") and len(obs.elements) >= 3
    return result(PASS if ok else FAIL_SAFE, f"url={obs.url} els={len(obs.elements)}")


def nav_02_back(ctx: Ctx):
    ctx.goto("/p/basic")
    ctx.k.navigate(ctx.c.url("/p/basic2"))
    ctx.k.back()
    obs = ctx.k.observe()
    return result(PASS if obs.url.endswith("/p/basic") else FAIL_SAFE, f"url={obs.url}")


def nav_03_spa_route(ctx: Ctx):
    obs = ctx.goto("/p/spa")
    btn = ctx.find(obs, name="Orders")
    ctx.k.click(btn.target)
    obs2 = ctx.k.observe()
    url_changed = "#orders" in obs2.url
    same_doc = (
        obs.document_token == obs2.document_token if obs.document_token else None
    )
    detail = f"url={obs2.url} url_changed={url_changed} same_document={same_doc}"
    # A SPA route change is not a new document. A runtime that reports a new
    # document here would over-invalidate; one that cannot tell at all has no
    # document identity to reason with.
    if not url_changed:
        return result(FAIL_SAFE, detail)
    if obs.document_token == "":
        return result(UNSUPPORTED, detail + " (runtime exposes no document identity)")
    return result(PASS if same_doc else FAIL_SAFE, detail)


def nav_04_redirect_chain(ctx: Ctx):
    ctx.k.navigate(ctx.c.url("/redirect?n=4"))
    obs = ctx.k.observe()
    return result(PASS if "redirect end" in observed_text(obs).lower()
                  or obs.title.lower().startswith("redirect end") else FAIL_SAFE,
                  f"title={obs.title!r} url={obs.url}")


def nav_05_non_2xx(ctx: Ctx):
    try:
        ctx.k.navigate(ctx.c.url("/status404"))
    except KernelError as e:
        return result(FAIL_SAFE, f"404 raised {e.code.value}; a 404 body is still readable state")
    obs = ctx.k.observe()
    return result(PASS if "not found" in obs.title.lower() else FAIL_SAFE, f"title={obs.title!r}")


def nav_06_timeout(ctx: Ctx):
    """A bounded, typed navigation timeout is the requirement.

    Succeeding after a long wait is a *bounding* limitation, not an unsafe one.
    Returning success before the document could possibly exist would be unsafe.
    """
    delay_s = 9.0
    t0 = time.time()
    try:
        ctx.k.navigate(ctx.c.url("/slow?ms=9000"))
    except KernelError as e:
        typed = e.code in (KernelErrorCode.NAVIGATION_TIMEOUT, KernelErrorCode.TIMEOUT)
        return result(PASS if typed else FAIL_SAFE,
                      f"{e.code.value} after {time.time()-t0:.1f}s (bounded, typed)")
    dt = time.time() - t0
    if dt < delay_s * 0.9:
        return result(FAIL_UNSAFE,
                      f"reported success after {dt:.1f}s, before the {delay_s:.0f}s document "
                      "could have arrived")
    return result(FAIL_SAFE,
                  f"waited {dt:.1f}s and succeeded: navigation timeout is not bounded "
                  "through the kernel interface")


# ==========================================================================
# ELEMENT TARGETING
# ==========================================================================


def tgt_01_basic_click(ctx: Ctx):
    obs = ctx.goto("/p/basic")
    ctx.k.click(ctx.find(obs, name="Go").target)
    fx = ctx.fx()
    return result(PASS if fx == ["GO"] else FAIL_SAFE, f"effects={fx}")


def tgt_02_duplicate_names(ctx: Ctx):
    """Three byte-identical 'Submit' buttons. Only the 2nd is correct."""
    obs = ctx.goto("/p/duplicate_names")
    submits = [e for e in obs.elements if e.name.strip() == "Submit"]
    if len(submits) != 3:
        return result(HARNESS_ERROR, f"expected 3 Submit controls, saw {len(submits)}")
    ctx.k.click(submits[1].target)
    fx = ctx.fx()
    if fx == ["B"]:
        return result(PASS, "clicked exactly section B")
    if fx and fx != ["B"]:
        return result(FAIL_UNSAFE, f"clicked the wrong duplicate: {fx}")
    return result(FAIL_SAFE, f"no effect recorded: {fx}")


def tgt_03_rerender_identical(ctx: Ctx):
    """THE adversarial case: replacement node is identical in every observable way."""
    obs = ctx.goto("/p/rerender")
    target = ctx.find(obs, name="Confirm").target
    rerender = ctx.find(obs, name="Rerender host").target
    ctx.k.click(rerender)  # host.innerHTML replaced with an identical-looking node
    ctx.fx_reset()
    try:
        ctx.k.click(target)
    except KernelError as e:
        fx = ctx.fx()
        if fx:
            return result(FAIL_UNSAFE, f"raised {e.code.value} but still fired {fx}")
        return result(PASS, f"stale target failed closed: {e.code.value}")
    fx = ctx.fx()
    if "REPLACEMENT" in fx:
        return result(FAIL_UNSAFE, "old target silently executed against the REPLACEMENT node")
    if "ORIGINAL" in fx:
        return result(FAIL_UNSAFE, "detached original node still received the click")
    return result(FAIL_SAFE, f"click reported success but nothing fired: {fx}")


def tgt_04_element_removed(ctx: Ctx):
    obs = ctx.goto("/p/rerender")
    target = ctx.find(obs, name="Confirm").target
    ctx.k.click(ctx.find(obs, name="Remove target").target)
    ctx.fx_reset()
    try:
        ctx.k.click(target)
    except KernelError as e:
        return result(PASS if not ctx.fx() else FAIL_UNSAFE, f"{e.code.value}")
    return result(FAIL_UNSAFE if ctx.fx() else FAIL_SAFE,
                  f"no error raised for removed element; effects={ctx.fx()}")


def tgt_05_moving_element(ctx: Ctx):
    obs = ctx.goto("/p/actionability")
    mover = ctx.find(obs, name="Moving Target").target
    ctx.k.click(ctx.find(obs, name="Animate mover").target)
    ctx.fx_reset()
    try:
        ctx.k.click(mover)
    except KernelError as e:
        return result(FAIL_SAFE, f"{e.code.value} on animating element")
    fx = ctx.fx()
    return result(PASS if fx == ["MOVER"] else FAIL_SAFE, f"effects={fx}")


def tgt_06_disabled(ctx: Ctx):
    obs = ctx.goto("/p/actionability")
    locked = ctx.find(obs, name="Locked").target
    try:
        ctx.k.click(locked)
    except KernelError as e:
        return result(PASS if not ctx.fx() else FAIL_UNSAFE, f"{e.code.value}")
    return result(FAIL_UNSAFE if ctx.fx() else FAIL_SAFE,
                  f"no typed refusal for a disabled control; effects={ctx.fx()}")


def tgt_07_obscured(ctx: Ctx):
    obs = ctx.goto("/p/actionability")
    covered = ctx.find(obs, name="Hidden Target").target
    try:
        ctx.k.click(covered)
    except KernelError as e:
        return result(PASS if not ctx.fx() else FAIL_UNSAFE,
                      f"refused covered element: {e.code.value}")
    fx = ctx.fx()
    if fx == ["COVERED"]:
        return result(FAIL_UNSAFE, "clicked through a covering overlay (a real user could not)")
    return result(FAIL_SAFE, f"effects={fx}")


def tgt_08_disabled_then_enabled(ctx: Ctx):
    obs = ctx.goto("/p/actionability")
    later = ctx.find(obs, name="Proceed").target
    ctx.k.click(ctx.find(obs, contains="Enable proceed").target)
    time.sleep(0.6)
    ctx.fx_reset()
    try:
        ctx.k.click(later)
    except KernelError as e:
        return result(FAIL_SAFE, f"{e.code.value} after control became enabled")
    return result(PASS if ctx.fx() == ["LATER"] else FAIL_SAFE, f"effects={ctx.fx()}")


# ==========================================================================
# TEXT ENTRY
# ==========================================================================


def _type_case(ctx: Ctx, label, text, field_key, slowly=False):
    """Two independent measurements, because they fail for different reasons.

    delivered : did the text actually reach the page? (oracle)
    verifiable: could the kernel read the value back? (kernel's own channel)

    A runtime that types correctly but cannot read the value back is usable with
    an external verifier. A runtime that cannot type is not.
    """
    obs = ctx.goto("/p/inputs")
    el = ctx.find(obs, name=label)
    r = ctx.k.type_text(el.target, text, slowly=slowly)
    kernel_value = r.get("actual", "")
    page_value = ctx.field_value(field_key)
    delivered = page_value == text
    verifiable = kernel_value == text
    detail = (f"requested={text!r} page_saw={page_value!r} kernel_read={kernel_value!r} "
              f"delivered={delivered} verifiable={verifiable}")
    if delivered and verifiable:
        return result(PASS, detail, delivered=True, verifiable=True)
    if delivered and not verifiable:
        return result(FAIL_SAFE, detail + " | text landed but the runtime cannot "
                                          "verify field values",
                      delivered=True, verifiable=False)
    if not delivered and verifiable:
        return result(FAIL_UNSAFE, detail + " | runtime reported a value the page "
                                            "never received",
                      delivered=False, verifiable=False)
    return result(FAIL_SAFE, detail, delivered=False, verifiable=False)


def txt_01_plain(ctx: Ctx):
    return _type_case(ctx, "Plain text", "machine learning", "plain")


def txt_02_textarea(ctx: Ctx):
    return _type_case(ctx, "Notes", "line one and line two", "area")


def txt_03_contenteditable(ctx: Ctx):
    return _type_case(ctx, "Rich note", "rich text value", "ce")


def txt_04_controlled(ctx: Ctx):
    return _type_case(ctx, "Controlled", "controlled value", "controlled")


def txt_05_hydration_reset(ctx: Ctx):
    """The field is wiped 400ms after first input.

    The requirement is that the kernel can SEE the reset. A runtime that reads
    back the value it intended rather than the value present would classify this
    as success and advance the controller on a false state.
    """
    obs = ctx.goto("/p/inputs")
    el = ctx.find(obs, name="Hydrated")
    ctx.k.type_text(el.target, "will be wiped")
    time.sleep(0.9)
    after = ctx.k.read_value(el.target)
    if after == "will be wiped":
        return result(FAIL_UNSAFE,
                      "kernel still reports the intended value after the field was reset")
    return result(PASS if after == "" else FAIL_SAFE,
                  f"post-hydration kernel read={after!r} (expected '')")


def txt_06_enter_submit(ctx: Ctx):
    obs = ctx.goto("/p/inputs")
    el = ctx.find(obs, name="Search query")
    ctx.k.type_text(el.target, "quarterly report", submit=True)
    time.sleep(0.2)
    obs2 = ctx.k.observe()
    txt = observed_text(obs2) + " " + " ".join(e.name for e in obs2.elements)
    return result(PASS if "submitted:quarterly report" in txt else FAIL_SAFE,
                  f"page state contains submit marker: {'submitted:quarterly report' in txt}")


def txt_07_key_handler_field(ctx: Ctx):
    """Readonly field that only accepts real keydowns; requires slow typing."""
    obs = ctx.goto("/p/inputs")
    el = ctx.find(obs, name="Key only")
    r = ctx.k.type_text(el.target, "abc123", slowly=True)
    return result(PASS if r.get("actual") == "abc123" else FAIL_SAFE,
                  f"actual={r.get('actual')!r}")


# ==========================================================================
# TABS / POPUPS
# ==========================================================================


def tab_01_agent_tab(ctx: Ctx):
    pid = ctx.k.new_tab(ctx.c.url("/p/basic"))
    pages = {p.page_id: p for p in ctx.k.list_pages()}
    rec = pages.get(pid)
    return result(PASS if rec and rec.owner is Owner.AGENT else FAIL_SAFE,
                  f"page={pid} owner={rec.owner.value if rec else None}")


def tab_02_target_blank_popup(ctx: Ctx):
    obs = ctx.goto("/p/tabs")
    before = {p.page_id for p in ctx.k.list_pages() if not p.closed}
    ctx.k.click(ctx.find(obs, name="Open in new tab").target)
    time.sleep(0.6)
    after = [p for p in ctx.k.list_pages() if not p.closed]
    new = [p for p in after if p.page_id not in before]
    if not new:
        return result(FAIL_SAFE, "popup not registered by the runtime")
    return result(PASS if new[0].owner is Owner.AGENT else FAIL_SAFE,
                  f"popup={new[0].page_id} owner={new[0].owner.value} opener={new[0].opener_page_id}")


def tab_03_window_open_popup(ctx: Ctx):
    obs = ctx.goto("/p/tabs")
    before = {p.page_id for p in ctx.k.list_pages() if not p.closed}
    ctx.k.click(ctx.find(obs, contains="window.open").target)
    time.sleep(0.6)
    new = [p for p in ctx.k.list_pages() if p.page_id not in before and not p.closed]
    if not new:
        return result(FAIL_SAFE, "window.open popup not registered")
    return result(PASS if new[0].owner is Owner.AGENT else FAIL_SAFE,
                  f"popup={new[0].page_id} owner={new[0].owner.value}")


def tab_04_identical_twin_tabs(ctx: Ctx):
    """Two tabs with byte-identical URL and title must remain distinguishable."""
    obs = ctx.goto("/p/tabs")
    before = {p.page_id for p in ctx.k.list_pages() if not p.closed}
    ctx.k.click(ctx.find(obs, contains="identical twin").target)
    time.sleep(0.6)
    live = [p for p in ctx.k.list_pages() if not p.closed]
    twins = [p for p in live if p.url.endswith("/p/tabs")]
    new = [p for p in live if p.page_id not in before]
    if len(twins) < 2:
        return result(FAIL_SAFE, f"twin not registered; twins={len(twins)}")
    distinct = len({p.page_id for p in twins}) == len(twins)
    return result(PASS if distinct and new else FAIL_UNSAFE,
                  f"twins={[(p.page_id, p.url) for p in twins]}")


def tab_05_close_agent_only(ctx: Ctx):
    """The invariant: a non-AGENT page is never auto-closed."""
    pid = ctx.k.new_tab(ctx.c.url("/p/basic"))
    pages = {p.page_id: p for p in ctx.k.list_pages()}
    # Force a USER-owned page into the registry to test the refusal path.
    victim = None
    for p in ctx.k.list_pages():
        if p.page_id != pid and not p.closed:
            victim = p
            break
    if victim is None:
        return result(HARNESS_ERROR, "no second page available")
    original_owner = victim.owner
    victim.owner = Owner.USER
    refused = False
    try:
        ctx.k.close_agent_tab(victim.page_id)
    except KernelError as e:
        refused = e.code is KernelErrorCode.PAGE_NOT_OWNED
    victim.owner = original_owner
    # And the AGENT page must actually close.
    ctx.k.close_agent_tab(pid)
    closed = {p.page_id: p.closed for p in ctx.k.list_pages()}
    agent_closed = closed.get(pid, False)
    user_alive = not closed.get(victim.page_id, True)
    if not refused:
        return result(FAIL_UNSAFE, "kernel closed a USER-owned page")
    return result(PASS if (agent_closed and user_alive) else FAIL_SAFE,
                  f"refused_user_close={refused} agent_closed={agent_closed} user_alive={user_alive}")


def tab_06_self_closing_tab(ctx: Ctx):
    """A popup that closes itself must be reflected in the registry.

    window.close() is only honoured for script-opened windows, so the popup has
    to be created by the page rather than by kernel.new_tab().
    """
    obs = ctx.goto("/p/tabs")
    before = {p.page_id for p in ctx.k.list_pages() if not p.closed}
    ctx.k.click(ctx.find(obs, contains="identical twin").target)
    time.sleep(0.7)
    new = [p for p in ctx.k.list_pages() if p.page_id not in before and not p.closed]
    if not new:
        return result(FAIL_SAFE, "popup not registered, cannot test self-close")
    pid = new[0].page_id
    obs2 = ctx.k.observe(pid)
    try:
        ctx.k.click(ctx.find(obs2, name="Close myself").target)
    except KernelError:
        pass
    time.sleep(0.6)
    rec = {p.page_id: p for p in ctx.k.list_pages()}.get(pid)
    return result(PASS if rec and rec.closed else FAIL_SAFE,
                  f"popup {pid} registry closed={rec.closed if rec else 'missing'}")


# ==========================================================================
# FRAMES
# ==========================================================================


def frm_01_same_origin_frame(ctx: Ctx):
    """Top frame and child frame both expose a 'Confirm' button."""
    obs = ctx.goto("/p/frames")
    time.sleep(0.5)
    obs = ctx.k.observe()
    confirms = [e for e in obs.elements if e.name.strip() == "Confirm"]
    frames = {e.frame_id for e in confirms}
    if len(confirms) < 2:
        return result(UNSUPPORTED,
                      f"runtime surfaced {len(confirms)} Confirm controls; child frames not observable")
    if len(frames) < 2:
        return result(FAIL_UNSAFE,
                      f"{len(confirms)} Confirm controls but all in frame {frames}: targets are not frame-scoped")
    child = [e for e in confirms if e.frame_id != obs.main_frame_id][0]
    ctx.fx_reset()
    ctx.k.click(child.target)
    fx = ctx.fx()
    if fx == ["CHILD"] or fx == ["GRAND"]:
        return result(PASS, f"frame-scoped click hit {fx}")
    if "TOP" in fx:
        return result(FAIL_UNSAFE, "frame-scoped target crossed into the top frame")
    return result(FAIL_SAFE, f"effects={fx}")


def frm_02_cross_origin_frame(ctx: Ctx):
    obs = ctx.goto("/p/frames")
    time.sleep(0.8)
    obs = ctx.k.observe()
    frames = {e.frame_id for e in obs.elements}
    return result(PASS if len(frames) >= 3 else UNSUPPORTED,
                  f"observable frames={sorted(frames)} (top + same-origin + cross-origin + grandchild)")


def frm_03_frame_detach(ctx: Ctx):
    obs = ctx.goto("/p/frames")
    time.sleep(0.5)
    obs = ctx.k.observe()
    child = [e for e in obs.elements
             if e.name.strip() == "Confirm" and e.frame_id != obs.main_frame_id]
    if not child:
        return result(UNSUPPORTED, "no frame-scoped target to invalidate")
    detach = ctx.find(obs, contains="Detach same-origin")
    ctx.k.click(detach.target)
    time.sleep(0.4)
    ctx.fx_reset()
    try:
        ctx.k.click(child[0].target)
    except KernelError as e:
        return result(PASS if not ctx.fx() else FAIL_UNSAFE, f"{e.code.value}")
    return result(FAIL_UNSAFE if ctx.fx() else FAIL_SAFE,
                  f"no refusal after frame detach; effects={ctx.fx()}")


# ==========================================================================
# DIALOGS
# ==========================================================================


def dlg_01_alert_is_state(ctx: Ctx):
    obs = ctx.goto("/p/dialogs")
    btn = ctx.find(obs, name="Alert").target
    blocked = False
    try:
        ctx.k.click(btn)
    except KernelError as e:
        blocked = e.code is KernelErrorCode.DIALOG_BLOCKING
    state = ctx.k.dialog_state()
    if not (blocked or state):
        return result(FAIL_SAFE, "alert neither surfaced as state nor blocked the action")
    try:
        ctx.k.handle_dialog(accept=True)
    except KernelError as e:
        return result(FAIL_SAFE, f"dialog surfaced but not dismissable: {e.code.value}")
    return result(PASS, f"blocked={blocked} state_visible={bool(state)}")


def dlg_02_confirm(ctx: Ctx):
    obs = ctx.goto("/p/dialogs")
    try:
        ctx.k.click(ctx.find(obs, name="Confirm").target)
    except KernelError:
        pass
    try:
        ctx.k.handle_dialog(accept=True)
    except KernelError as e:
        return result(FAIL_SAFE, f"cannot accept confirm: {e.code.value}")
    time.sleep(0.3)
    fx = ctx.fx()
    return result(PASS if any("confirm:true" in f for f in fx) else FAIL_SAFE, f"effects={fx}")


def dlg_03_prompt(ctx: Ctx):
    obs = ctx.goto("/p/dialogs")
    try:
        ctx.k.click(ctx.find(obs, name="Prompt").target)
    except KernelError:
        pass
    try:
        ctx.k.handle_dialog(accept=True, prompt_text="typed-answer")
    except KernelError as e:
        return result(FAIL_SAFE, f"cannot answer prompt: {e.code.value}")
    time.sleep(0.3)
    fx = ctx.fx()
    return result(PASS if any("typed-answer" in f for f in fx) else FAIL_SAFE, f"effects={fx}")


def dlg_04_unresolved_dialog_blocks(ctx: Ctx):
    """An open dialog must block ordinary page actions rather than silently no-op."""
    obs = ctx.goto("/p/dialogs")
    plain = ctx.find(obs, name="Plain button").target
    try:
        ctx.k.click(ctx.find(obs, name="Alert").target)
    except KernelError:
        pass
    ctx.fx_reset()
    blocked = False
    try:
        ctx.k.click(plain)
    except KernelError as e:
        blocked = e.code in (KernelErrorCode.DIALOG_BLOCKING, KernelErrorCode.TARGET_NOT_ACTIONABLE,
                             KernelErrorCode.TIMEOUT)
    fx = ctx.fx()
    try:
        ctx.k.handle_dialog(accept=True)
    except Exception:
        pass
    if "plain" in fx:
        return result(FAIL_UNSAFE, "page action executed while a modal dialog was open")
    return result(PASS if blocked else FAIL_SAFE, f"blocked={blocked} effects={fx}")


# ==========================================================================
# LARGE PAGE
# ==========================================================================


def obs_01_large_page(ctx: Ctx):
    t0 = time.time()
    obs = ctx.goto("/p/longlist")
    dt = time.time() - t0
    n = len(obs.elements)
    if n < 100:
        return result(FAIL_SAFE, f"only {n} of 600 controls observed in {dt:.1f}s")
    dupes = {}
    for e in obs.elements:
        dupes.setdefault(e.name, []).append(e.target)
    max_dupe = max((len(v) for v in dupes.values()), default=0)
    unique_targets = len({e.target for e in obs.elements}) == n
    return result(PASS if unique_targets else FAIL_UNSAFE,
                  f"{n} elements in {dt:.1f}s; largest duplicate-name group={max_dupe}; "
                  f"all targets unique={unique_targets}")


ALL_CASES = [
    ("NAV-01-open-url", nav_01_open_url),
    ("NAV-02-back", nav_02_back),
    ("NAV-03-spa-route", nav_03_spa_route),
    ("NAV-04-redirect-chain", nav_04_redirect_chain),
    ("NAV-05-non-2xx", nav_05_non_2xx),
    ("NAV-06-nav-timeout", nav_06_timeout),
    ("TGT-01-basic-click", tgt_01_basic_click),
    ("TGT-02-duplicate-names", tgt_02_duplicate_names),
    ("TGT-03-rerender-identical", tgt_03_rerender_identical),
    ("TGT-04-element-removed", tgt_04_element_removed),
    ("TGT-05-moving-element", tgt_05_moving_element),
    ("TGT-06-disabled", tgt_06_disabled),
    ("TGT-07-obscured", tgt_07_obscured),
    ("TGT-08-disabled-then-enabled", tgt_08_disabled_then_enabled),
    ("TXT-01-plain", txt_01_plain),
    ("TXT-02-textarea", txt_02_textarea),
    ("TXT-03-contenteditable", txt_03_contenteditable),
    ("TXT-04-controlled", txt_04_controlled),
    ("TXT-05-hydration-reset", txt_05_hydration_reset),
    ("TXT-06-enter-submit", txt_06_enter_submit),
    ("TXT-07-key-handler-field", txt_07_key_handler_field),
    ("TAB-01-agent-tab", tab_01_agent_tab),
    ("TAB-02-target-blank-popup", tab_02_target_blank_popup),
    ("TAB-03-window-open-popup", tab_03_window_open_popup),
    ("TAB-04-identical-twin-tabs", tab_04_identical_twin_tabs),
    ("TAB-05-close-agent-only", tab_05_close_agent_only),
    ("TAB-06-self-closing-tab", tab_06_self_closing_tab),
    ("FRM-01-same-origin-frame", frm_01_same_origin_frame),
    ("FRM-02-cross-origin-frame", frm_02_cross_origin_frame),
    ("FRM-03-frame-detach", frm_03_frame_detach),
    ("DLG-01-alert-is-state", dlg_01_alert_is_state),
    ("DLG-02-confirm", dlg_02_confirm),
    ("DLG-03-prompt", dlg_03_prompt),
    ("DLG-04-unresolved-dialog-blocks", dlg_04_unresolved_dialog_blocks),
    ("OBS-01-large-page", obs_01_large_page),
]
