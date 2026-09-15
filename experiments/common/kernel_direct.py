"""Direct Playwright BrowserKernel.

Target identity is bound to the **live DOM node**, not to a selector, a name, a
position or a URL. This is the single mechanism that makes "stale targets fail
closed" true rather than aspirational: a replaced element is a different JS
object, so an old target can never resolve onto it.

Page identity is minted at the page-creation event and is never derived from
title, URL or tab index.
"""

from __future__ import annotations

import itertools
import time
from typing import Optional

from playwright.sync_api import (
    sync_playwright,
    Error as PWError,
    TimeoutError as PWTimeout,
)

from .contracts import (
    KernelError,
    KernelErrorCode,
    Observation,
    ObservedElement,
    Owner,
    PageRecord,
    TabSummary,
)
from .kernel import BrowserKernel, InvalidationPolicy


# Every new document gets a fresh token. Navigation, reload and crash-recovery
# all produce a new document and therefore a new token, even when the URL and
# title are byte-identical.
INIT_SCRIPT = """
(() => {
  if (!window.__bav2_doc) {
    window.__bav2_doc = 'doc_' + Math.random().toString(36).slice(2) + '_' + Date.now();
  }
})();
"""

INTERACTIVE_SELECTOR = (
    "a[href], button, input, select, textarea, summary, "
    "[role=button], [role=link], [role=textbox], [role=checkbox], [role=radio], "
    "[role=combobox], [role=tab], [role=menuitem], [contenteditable=true], "
    "[onclick], [tabindex]:not([tabindex='-1'])"
)

# Collects metadata AND returns live node references in one round trip, with no
# DOM mutation (no marker attributes that a cloneNode rerender could copy).
COLLECT_JS = """
(sel) => {
  const seen = new Set();
  const els = [];
  for (const e of document.querySelectorAll(sel)) {
    if (seen.has(e)) continue;
    seen.add(e); els.push(e);
  }
  const accName = (e) => {
    const al = e.getAttribute('aria-label');
    if (al && al.trim()) return al.trim();
    const lb = e.getAttribute('aria-labelledby');
    if (lb) {
      const t = lb.split(/\\s+/).map(id => document.getElementById(id))
                 .filter(Boolean).map(n => n.textContent.trim()).join(' ').trim();
      if (t) return t;
    }
    if (e.id) {
      const lab = document.querySelector('label[for="' + CSS.escape(e.id) + '"]');
      if (lab && lab.textContent.trim()) return lab.textContent.trim();
    }
    const closest = e.closest && e.closest('label');
    if (closest && closest.textContent.trim()) return closest.textContent.trim();
    if (e.tagName === 'INPUT' && (e.type === 'submit' || e.type === 'button')) return e.value || '';
    const ph = e.getAttribute('placeholder'); if (ph) return ph.trim();
    const ti = e.getAttribute('title'); if (ti) return ti.trim();
    const alt = e.getAttribute('alt'); if (alt) return alt.trim();
    return (e.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 120);
  };
  const role = (e) => {
    const r = e.getAttribute('role'); if (r) return r;
    const t = e.tagName.toLowerCase();
    if (t === 'a') return e.hasAttribute('href') ? 'link' : 'generic';
    if (t === 'button') return 'button';
    if (t === 'select') return 'combobox';
    if (t === 'textarea') return 'textbox';
    if (t === 'summary') return 'button';
    if (t === 'input') {
      const ty = (e.type || 'text').toLowerCase();
      if (ty === 'checkbox') return 'checkbox';
      if (ty === 'radio') return 'radio';
      if (ty === 'submit' || ty === 'button' || ty === 'reset') return 'button';
      if (ty === 'password') return 'textbox';
      return 'textbox';
    }
    if (e.isContentEditable) return 'textbox';
    return 'generic';
  };
  const visible = (e) => {
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const value = (e) => {
    if (e.tagName === 'SELECT') return e.value || '';
    if (e.tagName === 'INPUT' && (e.type === 'checkbox' || e.type === 'radio'))
      return e.checked ? 'checked' : 'unchecked';
    if ('value' in e && typeof e.value === 'string') return e.value;
    if (e.isContentEditable) return e.textContent || '';
    return '';
  };
  // Nearest preceding heading in document order. Duplicate accessible names are
  // common and unavoidable; without a structural anchor the observation cannot
  // express "the Submit button in section B" and the model is forced to guess.
  // This is generic document structure, not site knowledge.
  const headings = [...document.querySelectorAll('h1,h2,h3,h4,legend,caption,[role=heading]')];
  const section = (e) => {
    let best = '';
    for (const h of headings) {
      const pos = h.compareDocumentPosition(e);
      if (pos & Node.DOCUMENT_POSITION_FOLLOWING) {
        best = (h.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 60);
      }
    }
    return best;
  };
  // A dropdown's option list is part of its state. Without it the model can see
  // that a combobox exists but cannot know what values are selectable, so it
  // cannot produce a correct SELECT argument. END_TO_END_SYSTEM_SPEC section 7
  // lists "select options" as Tier 3 enrichment for exactly this reason.
  const options = (e) => {
    if (e.tagName !== 'SELECT') return null;
    return [...e.options].slice(0, 30).map(o => ({
      value: o.value, label: (o.textContent || '').trim()
    }));
  };
  const meta = els.map(e => ({
    section: section(e),
    options: options(e),
    role: role(e), name: accName(e), value: value(e),
    enabled: !e.disabled && e.getAttribute('aria-disabled') !== 'true',
    visible: visible(e), tag: e.tagName.toLowerCase(),
    attrs: {id: e.id || '', type: (e.getAttribute('type') || ''),
            href: (e.getAttribute('href') || '').slice(0,120)}
  }));
  // Only text a person could actually read. Hidden nodes (an inactive wizard
  // step, a validation message that is not currently shown) would otherwise
  // describe a page state that does not exist.
  const text = [...document.querySelectorAll('h1,h2,h3,p,li,td,label,span')]
      .filter(visible)
      .map(n => (n.textContent || '').replace(/\\s+/g,' ').trim())
      .filter(t => t.length > 1 && t.length < 400).slice(0, 120);
  return { meta, els, text, doc: window.__bav2_doc || 'unknown' };
}
"""


class _ObsRecord:
    __slots__ = ("obs", "handles", "page_id", "doc_token", "superseded",
                 "invalidated", "invalidated_reason", "frames", "created")

    def __init__(self, obs, handles, page_id, doc_token, frames):
        self.obs = obs
        self.handles = handles  # target -> ElementHandle
        self.page_id = page_id
        self.doc_token = doc_token
        self.frames = frames  # frame_id -> Frame
        # superseded: set by the automatic policy (a mutating action happened).
        self.superseded = False
        # invalidated: set by an explicit controller command (handoff, resume,
        # reconnect). This is an order, not a heuristic, so it is honoured by
        # every policy.
        self.invalidated = False
        self.invalidated_reason = ""
        self.created = time.time()


class DirectPlaywrightKernel(BrowserKernel):
    name = "direct_playwright"

    def __init__(
        self,
        user_data_dir: str,
        headless: bool = True,
        policy: InvalidationPolicy = InvalidationPolicy.NODE_IDENTITY,
        action_timeout_ms: int = 4000,
        initial_pages_owner: Owner = Owner.AGENT,
    ):
        self.user_data_dir = user_data_dir
        self.headless = headless
        self.policy = policy
        self.action_timeout_ms = action_timeout_ms
        # AGENT when we launch the browser (the dedicated-profile default);
        # USER when attaching to a browser someone else started.
        self.initial_pages_owner = initial_pages_owner

        self._pw = None
        self.context = None
        self._pages: dict[str, object] = {}  # page_id -> Page
        self.registry: dict[str, PageRecord] = {}
        self._page_ids: dict[int, str] = {}  # id(Page) -> page_id
        self._obs: dict[str, _ObsRecord] = {}
        self._active_page_id: Optional[str] = None
        self._pending_dialog: Optional[dict] = None
        self._dialog_obj = None
        self._event_seq = itertools.count(1)
        self._obs_seq = itertools.count(1)
        self._page_seq = itertools.count(1)
        # Pages the kernel itself asked for; anything else that appears without an
        # agent opener is treated as USER-created.
        self._expecting_agent_page = False
        self.events: list[dict] = []

    # ------------------------------------------------------------------ util

    def _log(self, kind: str, **kw):
        self.events.append({"seq": next(self._event_seq), "t": time.time(), "kind": kind, **kw})

    def _mint_page_id(self) -> str:
        return f"page_{next(self._page_seq)}"

    # -------------------------------------------------------------- lifecycle

    def start(self) -> None:
        self._pw = sync_playwright().start()
        self.context = self._pw.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=self.headless,
            args=["--no-first-run", "--no-default-browser-check"],
            viewport={"width": 1280, "height": 900},
        )
        self.context.add_init_script(INIT_SCRIPT)
        self.context.set_default_timeout(self.action_timeout_ms)
        self.context.on("page", self._on_page)
        # Ownership of the pages present at start depends on how we got here.
        # We LAUNCHED this browser against a dedicated profile, so its initial
        # page is ours. When attaching to a browser we did not launch (the
        # deferred CDP mode), the same pages would be USER-owned — which is
        # precisely why that mode is deferred rather than default.
        for p in self.context.pages:
            self._register_page(p, self.initial_pages_owner, opener=None)
        if not self.context.pages:
            self._expecting_agent_page = True
            p = self.context.new_page()
            self._expecting_agent_page = False
            if id(p) not in self._page_ids:
                self._register_page(p, Owner.AGENT, opener=None)
        self._active_page_id = next(iter(self.registry))
        self._log("kernel_start", policy=self.policy.value)

    def shutdown(self) -> None:
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._log("kernel_shutdown")

    def health(self) -> dict:
        try:
            alive = self.context is not None and not self._closed()
            return {"ok": alive, "pages": len(self.context.pages) if alive else 0}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _closed(self) -> bool:
        try:
            _ = self.context.pages
            return False
        except Exception:
            return True

    # ---------------------------------------------------------- page registry

    def _on_page(self, page):
        """Page-creation event. Ownership is decided HERE and never revisited."""
        if id(page) in self._page_ids:
            return
        opener_id = None
        try:
            op = page.opener()
            if op is not None:
                opener_id = self._page_ids.get(id(op))
        except Exception:
            pass

        if self._expecting_agent_page:
            owner = Owner.AGENT
        elif opener_id is not None:
            # Popup inherits ownership from the page that opened it. A popup from
            # a USER page stays USER, which is what protects the human's tabs.
            owner = self.registry[opener_id].owner
        else:
            # Appeared with no opener and we did not ask for it: a human made it.
            owner = Owner.USER
        self._register_page(page, owner, opener_id)

    def _register_page(self, page, owner: Owner, opener: Optional[str]) -> str:
        pid = self._mint_page_id()
        self._page_ids[id(page)] = pid
        self._pages[pid] = page
        rec = PageRecord(
            page_id=pid,
            owner=owner,
            opener_page_id=opener,
            created_event_id=next(self._event_seq),
            url=_safe(lambda: page.url, ""),
            title="",
            closed=False,
            document_generation=0,
        )
        self.registry[pid] = rec
        page.on("close", lambda _p=page, _pid=pid: self._on_close(_pid))
        page.on("dialog", lambda d, _pid=pid: self._on_dialog(_pid, d))
        page.on(
            "framenavigated",
            lambda fr, _p=page, _pid=pid: self._on_navigated(_pid, _p, fr),
        )
        self._log("page_created", page_id=pid, owner=owner.value, opener=opener)
        return pid

    def _on_close(self, page_id: str):
        if page_id in self.registry:
            self.registry[page_id].closed = True
        self._supersede_page(page_id, "page_closed")
        if self._active_page_id == page_id:
            # The active page is gone. Leaving the pointer dangling would make
            # the next unqualified call fail with PAGE_CLOSED on a page nobody
            # asked about, so fall back to the most recent page still open.
            self._active_page_id = next(
                (pid for pid in reversed(list(self.registry))
                 if not self.registry[pid].closed),
                None,
            )
            self._log("active_page_reassigned", page_id=self._active_page_id)
        self._log("page_closed", page_id=page_id)

    def _on_navigated(self, page_id, page, frame):
        try:
            if frame != page.main_frame:
                return
        except Exception:
            return
        rec = self.registry.get(page_id)
        if rec:
            rec.document_generation += 1
            rec.url = _safe(lambda: page.url, rec.url)
        self._log("navigated", page_id=page_id, generation=rec.document_generation if rec else -1)

    def _on_dialog(self, page_id, dialog):
        # A native dialog is an explicit kernel state. It is never auto-dismissed,
        # because auto-dismissing is itself a decision the agent must not make.
        self._pending_dialog = {
            "page_id": page_id,
            "type": dialog.type,
            "message": dialog.message,
            "default_value": getattr(dialog, "default_value", ""),
        }
        self._dialog_obj = dialog
        self._log("dialog_opened", page_id=page_id, type=dialog.type)

    def list_pages(self) -> list[PageRecord]:
        # Snapshot first: refreshing url/title can pump Playwright events, and a
        # popup arriving mid-iteration would otherwise mutate the registry.
        for pid, rec in list(self.registry.items()):
            p = self._pages.get(pid)
            if p is None or rec.closed:
                continue
            rec.url = _safe(lambda: p.url, rec.url)
            if not self._pending_dialog:
                # page.title() evaluates in the page; behind a modal it would hang.
                rec.title = _safe(lambda: p.title(), rec.title)
        return list(self.registry.values())

    def new_tab(self, url: Optional[str] = None) -> str:
        self._expecting_agent_page = True
        try:
            page = self.context.new_page()
        finally:
            self._expecting_agent_page = False
        pid = self._page_ids.get(id(page))
        if pid is None:
            pid = self._register_page(page, Owner.AGENT, None)
        self.registry[pid].owner = Owner.AGENT
        if url:
            page.goto(url, wait_until="domcontentloaded")
        self._active_page_id = pid
        return pid

    def switch_tab(self, page_id: str) -> None:
        p = self._require_page(page_id)
        p.bring_to_front()
        self._active_page_id = page_id

    def close_agent_tab(self, page_id: str) -> dict:
        rec = self.registry.get(page_id)
        if rec is None:
            raise KernelError(KernelErrorCode.TARGET_NOT_FOUND, f"unknown page {page_id}")
        if rec.owner is not Owner.AGENT:
            # THE invariant: a non-AGENT page is never closed by cleanup logic.
            raise KernelError(
                KernelErrorCode.PAGE_NOT_OWNED,
                f"refusing to close {rec.owner.value}-owned page {page_id}",
                {"owner": rec.owner.value},
            )
        p = self._pages.get(page_id)
        if p is not None and not rec.closed:
            p.close()
        rec.closed = True
        return {"closed": page_id}

    def _require_page(self, page_id: Optional[str]):
        pid = page_id or self._active_page_id
        rec = self.registry.get(pid)
        if rec is None:
            raise KernelError(KernelErrorCode.TARGET_NOT_FOUND, f"unknown page {pid}")
        if rec.closed:
            raise KernelError(KernelErrorCode.PAGE_CLOSED, f"page {pid} is closed")
        p = self._pages.get(pid)
        if p is None:
            raise KernelError(KernelErrorCode.PAGE_CLOSED, f"page {pid} has no handle")
        return p

    # ------------------------------------------------------------- navigation

    def navigate(self, url: str, page_id: Optional[str] = None) -> None:
        p = self._require_page(page_id)
        pid = page_id or self._active_page_id
        try:
            resp = p.goto(url, wait_until="domcontentloaded", timeout=self.action_timeout_ms)
        except PWTimeout as e:
            self._supersede_page(pid, "navigation_timeout")
            raise KernelError(KernelErrorCode.NAVIGATION_TIMEOUT, str(e)[:200])
        except PWError as e:
            self._supersede_page(pid, "navigation_failed")
            raise KernelError(KernelErrorCode.NAVIGATION_FAILED, str(e)[:200])
        self._supersede_page(pid, "navigation")
        if resp is not None and resp.status >= 400:
            # Not an exception: a 404 is a real page the agent may need to read.
            self._log("navigate_non_2xx", page_id=pid, status=resp.status, url=url)

    def back(self, page_id: Optional[str] = None) -> None:
        p = self._require_page(page_id)
        pid = page_id or self._active_page_id
        p.go_back(wait_until="domcontentloaded", timeout=self.action_timeout_ms)
        self._supersede_page(pid, "back")

    # ------------------------------------------------------------ observation

    def observe(self, page_id: Optional[str] = None) -> Observation:
        if self._pending_dialog:
            # Observing behind a blocking dialog would produce a lie.
            raise KernelError(
                KernelErrorCode.DIALOG_BLOCKING,
                "dialog must be handled before observing",
                self._pending_dialog,
            )
        p = self._require_page(page_id)
        pid = page_id or self._active_page_id
        obs_id = f"obs_{next(self._obs_seq):05d}"

        frames = {}
        handles: dict[str, ObservedElement] = {}
        elements: list[ObservedElement] = []
        text_blocks: list[str] = []
        doc_token = ""

        frame_list = _safe(lambda: list(p.frames), [])
        for fi, frame in enumerate(frame_list):
            fid = f"f{fi}"
            try:
                if frame.is_detached():
                    continue
                h = frame.evaluate_handle(COLLECT_JS, INTERACTIVE_SELECTOR)
            except PWError:
                continue  # frame died mid-observation; simply absent from this observation
            try:
                meta = h.get_property("meta").json_value()
                els_handle = h.get_property("els")
                if fi == 0:
                    doc_token = h.get_property("doc").json_value() or ""
                    text_blocks = h.get_property("text").json_value() or []
                frames[fid] = frame
                for i, m in enumerate(meta):
                    target = f"{obs_id}:{fid}:e{i}"
                    eh = els_handle.get_property(str(i)).as_element()
                    if eh is None:
                        continue
                    oe = ObservedElement(
                        target=target,
                        role=m["role"],
                        name=m["name"],
                        value=m["value"],
                        frame_id=fid,
                        enabled=m["enabled"],
                        visible=m["visible"],
                        tag=m["tag"],
                        section=m.get("section", ""),
                        options=m.get("options") or [],
                        attrs=m["attrs"],
                    )
                    elements.append(oe)
                    handles[target] = eh
            finally:
                try:
                    h.dispose()
                except Exception:
                    pass

        rec = self.registry[pid]
        obs = Observation(
            observation_id=obs_id,
            page_id=pid,
            url=_safe(lambda: p.url, ""),
            title=_safe(lambda: p.title(), ""),
            document_token=doc_token,
            document_generation=rec.document_generation,
            frame_tree_version=len(frames),
            tabs=[
                TabSummary(r.page_id, r.url, r.title, r.owner.value, r.page_id == self._active_page_id)
                for r in self.list_pages()
                if not r.closed
            ],
            modal=self._pending_dialog,
            elements=elements,
            text_blocks=text_blocks,
        )
        obs.state_fingerprint = obs.compute_fingerprint()
        self._obs[obs_id] = _ObsRecord(obs, handles, pid, doc_token, frames)
        self._log("observed", page_id=pid, observation_id=obs_id, elements=len(elements))
        return obs

    def _supersede_page(self, page_id: str, reason: str):
        for r in self._obs.values():
            if r.page_id == page_id and not r.superseded:
                r.superseded = True
        self._log("observations_superseded", page_id=page_id, reason=reason)

    def invalidate_all_observations(self, reason: str) -> None:
        for r in self._obs.values():
            r.superseded = True
            r.invalidated = True
            r.invalidated_reason = reason
        self._log("all_observations_invalidated", reason=reason, count=len(self._obs))

    # -------------------------------------------------------- target resolve

    def _resolve(self, target: str, require_enabled=True):
        """Resolve an observation-scoped target to a live node, or fail closed.

        Returns (element_handle, observed_element, page_id).
        """
        # A pending native dialog blocks the page's JS thread. Any evaluate()
        # against it would hang forever, so the dialog must gate every path that
        # touches the page — this is why "dialog is an explicit kernel state" is
        # a correctness requirement and not merely tidy design.
        if self._pending_dialog:
            raise KernelError(
                KernelErrorCode.DIALOG_BLOCKING,
                "a modal dialog is open; handle it before acting on the page",
                dict(self._pending_dialog),
            )
        try:
            obs_id, fid, _ = target.split(":", 2)
        except ValueError:
            raise KernelError(KernelErrorCode.TARGET_NOT_FOUND, f"malformed target {target!r}")
        rec = self._obs.get(obs_id)
        if rec is None:
            raise KernelError(KernelErrorCode.TARGET_NOT_FOUND, f"unknown observation {obs_id}")

        oe = rec.obs.element(target)
        if oe is None:
            raise KernelError(KernelErrorCode.TARGET_NOT_FOUND, f"target not in {obs_id}")

        page_rec = self.registry.get(rec.page_id)
        if page_rec is None or page_rec.closed:
            raise KernelError(KernelErrorCode.PAGE_CLOSED, f"page {rec.page_id} closed")
        page = self._pages[rec.page_id]

        # Explicit invalidation outranks the invalidation policy. The policy
        # decides what the kernel notices on its own; this is the controller
        # stating that the world changed underneath it (handoff, resume,
        # reconnect), which no amount of DOM inspection could detect.
        if rec.invalidated:
            raise KernelError(
                KernelErrorCode.OBSERVATION_SUPERSEDED,
                f"observation {obs_id} was explicitly invalidated "
                f"({rec.invalidated_reason}); re-observe before acting",
                {"reason": rec.invalidated_reason},
            )

        pol = self.policy

        # ---- CONTROL policies (deliberately unsafe; measured, never shipped) --
        if pol is InvalidationPolicy.UNSAFE_URL_ONLY:
            if _safe(lambda: page.url, "") != rec.obs.url:
                raise KernelError(KernelErrorCode.TARGET_STALE, "url changed")
            eh = rec.handles.get(target)
            if eh is None:
                raise KernelError(KernelErrorCode.TARGET_NOT_FOUND, "no handle")
            return eh, oe, rec.page_id

        if pol is InvalidationPolicy.UNSAFE_NAME_RESOLVE:
            frame = rec.frames.get(fid)
            if frame is None or _safe(lambda: frame.is_detached(), True):
                raise KernelError(KernelErrorCode.FRAME_DETACHED, "frame gone")
            found = frame.evaluate_handle(
                """([sel, role, name]) => {
                     const norm = s => (s||'').replace(/\\s+/g,' ').trim();
                     for (const e of document.querySelectorAll(sel)) {
                       const al = e.getAttribute('aria-label');
                       const txt = al || (e.textContent||'');
                       if (norm(txt) === norm(name)) return e;
                     }
                     return null;
                   }""",
                [INTERACTIVE_SELECTOR, oe.role, oe.name],
            ).as_element()
            if found is None:
                raise KernelError(KernelErrorCode.TARGET_NOT_FOUND, "name no longer present")
            return found, oe, rec.page_id

        # ---- SAFE policies ---------------------------------------------------
        if pol is InvalidationPolicy.STRICT_SUPERSEDE and rec.superseded:
            raise KernelError(
                KernelErrorCode.OBSERVATION_SUPERSEDED,
                f"observation {obs_id} superseded; re-observe before acting",
            )

        frame = rec.frames.get(fid)
        if frame is None or _safe(lambda: frame.is_detached(), True):
            raise KernelError(KernelErrorCode.FRAME_DETACHED, f"frame {fid} detached")

        # Document identity: a new document is a different world even at the same URL.
        try:
            live_doc = frame.evaluate("() => window.__bav2_doc || 'unknown'")
        except PWError as e:
            raise KernelError(KernelErrorCode.DOCUMENT_CHANGED, f"context destroyed: {str(e)[:120]}")
        if fid == "f0" and rec.doc_token and live_doc != rec.doc_token:
            raise KernelError(
                KernelErrorCode.DOCUMENT_CHANGED,
                "document replaced since observation",
                {"observed": rec.doc_token, "live": live_doc},
            )

        eh = rec.handles.get(target)
        if eh is None:
            raise KernelError(KernelErrorCode.TARGET_NOT_FOUND, "no live handle for target")

        # Node identity: the recorded node must still be in the document.
        try:
            connected = eh.evaluate("e => e.isConnected === true")
        except PWError as e:
            raise KernelError(KernelErrorCode.TARGET_STALE, f"node unreachable: {str(e)[:120]}")
        if not connected:
            raise KernelError(
                KernelErrorCode.TARGET_STALE,
                "observed node is no longer attached to the document",
            )

        if require_enabled:
            try:
                disabled = eh.evaluate(
                    "e => !!e.disabled || e.getAttribute('aria-disabled') === 'true'"
                )
            except PWError:
                disabled = False
            if disabled:
                raise KernelError(KernelErrorCode.TARGET_DISABLED, "target is disabled")

        return eh, oe, rec.page_id

    # ------------------------------------------------------------- actions

    def click(self, target: str) -> dict:
        eh, oe, pid = self._resolve(target)
        try:
            eh.click(timeout=self.action_timeout_ms)
        except PWTimeout as e:
            # A native dialog opened by this click blocks the page, so the click
            # promise never settles. That is a dialog state, not an unactionable
            # target, and it must be reported as such.
            if self._pending_dialog:
                self._supersede_page(pid, "click_opened_dialog")
                raise KernelError(
                    KernelErrorCode.DIALOG_BLOCKING,
                    "click opened a modal dialog that must be handled",
                    dict(self._pending_dialog),
                )
            raise KernelError(KernelErrorCode.TARGET_NOT_ACTIONABLE, str(e)[:200])
        except PWError as e:
            raise KernelError(KernelErrorCode.INTERNAL, str(e)[:200])
        self._supersede_page(pid, "click")
        return {"clicked": target, "role": oe.role, "name": oe.name}

    def type_text(self, target: str, text: str, submit: bool = False, slowly: bool = False) -> dict:
        eh, oe, pid = self._resolve(target)
        try:
            if slowly:
                eh.click(timeout=self.action_timeout_ms)
                eh.evaluate("e => { if ('value' in e) e.value = ''; }")
                eh.type(text, delay=12, timeout=self.action_timeout_ms)
            elif oe.tag in ("input", "textarea"):
                eh.fill(text, timeout=self.action_timeout_ms)
            else:
                # contenteditable and other rich targets. Assigning textContent
                # would mutate the DOM without firing input/beforeinput, so any
                # framework listening for edits would never learn about the
                # change and the page's own state would silently diverge.
                eh.click(timeout=self.action_timeout_ms)
                eh.evaluate(
                    """e => {
                         const r = document.createRange();
                         r.selectNodeContents(e);
                         const s = window.getSelection();
                         s.removeAllRanges(); s.addRange(r);
                       }"""
                )
                page = eh.owner_frame().page
                page.keyboard.press("Delete")
                page.keyboard.insert_text(text)
        except PWTimeout as e:
            raise KernelError(KernelErrorCode.TARGET_NOT_ACTIONABLE, str(e)[:200])
        except PWError as e:
            raise KernelError(KernelErrorCode.INTERNAL, str(e)[:200])

        actual = self._read(eh)
        if submit:
            eh.press("Enter", timeout=self.action_timeout_ms)
        self._supersede_page(pid, "type")
        return {"target": target, "requested": text, "actual": actual, "exact": actual == text}

    def select(self, target: str, value: str) -> dict:
        eh, oe, pid = self._resolve(target)
        try:
            eh.select_option(value=value, timeout=self.action_timeout_ms)
        except PWError:
            try:
                eh.select_option(label=value, timeout=self.action_timeout_ms)
            except PWError as e:
                raise KernelError(KernelErrorCode.TARGET_NOT_ACTIONABLE, str(e)[:200])
        actual = self._read(eh)
        self._supersede_page(pid, "select")
        return {"target": target, "requested": value, "actual": actual}

    def press(self, target: str, key: str) -> dict:
        eh, oe, pid = self._resolve(target)
        eh.press(key, timeout=self.action_timeout_ms)
        self._supersede_page(pid, "press")
        return {"target": target, "key": key}

    def read_value(self, target: str) -> str:
        eh, _, _ = self._resolve(target, require_enabled=False)
        return self._read(eh)

    @staticmethod
    def _read(eh) -> str:
        return eh.evaluate(
            """e => {
                 if (e.tagName === 'SELECT') return e.value || '';
                 if (e.tagName === 'INPUT' && (e.type==='checkbox'||e.type==='radio'))
                     return e.checked ? 'checked' : 'unchecked';
                 if ('value' in e && typeof e.value === 'string') return e.value;
                 if (e.isContentEditable) return e.textContent || '';
                 return (e.textContent || '');
               }"""
        )

    # ------------------------------------------------------------- dialogs

    def dialog_state(self) -> Optional[dict]:
        return self._pending_dialog

    def handle_dialog(self, accept: bool, prompt_text: str = "") -> dict:
        if not self._dialog_obj:
            raise KernelError(KernelErrorCode.TARGET_NOT_FOUND, "no pending dialog")
        d = self._dialog_obj
        info = dict(self._pending_dialog or {})
        self._pending_dialog = None
        self._dialog_obj = None
        if accept:
            d.accept(prompt_text)
        else:
            d.dismiss()
        self._log("dialog_handled", accept=accept)
        return {"handled": info, "accepted": accept}

    # --------------------------------------------------------------- extras

    def page_object(self, page_id: Optional[str] = None):
        """Escape hatch for experiment harnesses only (never exposed to a model)."""
        return self._require_page(page_id)

    def storage_snapshot(self, page_id: Optional[str] = None) -> dict:
        p = self._require_page(page_id)
        return p.evaluate(
            """() => ({
                 local: Object.fromEntries(Object.entries(localStorage)),
                 cookie: document.cookie
               })"""
        )


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default
