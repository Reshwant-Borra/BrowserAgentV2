"""Playwright MCP BrowserKernel adapter (Experiment 1 candidate A).

Fairness note
-------------
This adapter deliberately does NOT re-implement freshness on top of MCP. It
translates our observation-scoped target IDs onto MCP snapshot refs and then
lets the MCP runtime decide what happens. That is the whole point of the
comparison: we are measuring what the *runtime* guarantees, not what a wrapper
can be made to guarantee. The only bookkeeping we add is the mapping from
`obs_id:frame:ref` back to the ref that MCP issued, which is pure translation.
"""

from __future__ import annotations

import glob
import itertools
import os
import re
import time
from typing import Optional

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
from .mcp_client import MCPStdioClient, result_text, is_error

MCP_VERSION = "0.0.81"

# MCP tools that must never be reachable from a model decision. Presence on the
# server is a finding; exposure to the decision schema would be a defect.
UNSAFE_TOOLS = {
    "browser_run_code_unsafe",
    "browser_evaluate",
    "browser_file_upload",
    "browser_network_request",
    "browser_webmcp_call",
}

SNAPSHOT_LINE = re.compile(
    r"^(?P<indent>\s*)-\s+(?P<role>[a-zA-Z]+)"
    r"(?:\s+\"(?P<name>(?:[^\"\\]|\\.)*)\")?"
    r"(?P<flags>(?:\s+\[[^\]]*\])*)"
    r"\s*:?\s*(?P<trailing>.*)$"
)
REF_RE = re.compile(r"\[ref=([^\]]+)\]")
LEVEL_RE = re.compile(r"\[(active|disabled|checked|expanded|selected)[^\]]*\]")


TEXT_LINE = re.compile(r"^\s*-\s+(?:text|paragraph|heading|generic)\b[^:]*:\s*(.+)$")


def parse_text_blocks(text: str) -> list[str]:
    """Static page text from an MCP snapshot.

    Snapshot lines without a [ref=...] carry the page's prose. Dropping them
    loses exactly the content a verifier needs (status markers, confirmation
    strings), so they are collected separately rather than discarded.
    """
    out = []
    for line in (text or "").splitlines():
        if "[ref=" in line:
            # an interactive node; its trailing value belongs to the element
            m = re.search(r"\[ref=[^\]]+\]\s*:\s*(.+)$", line)
            if m and m.group(1).strip() not in ("none", ""):
                out.append(m.group(1).strip())
            continue
        m = TEXT_LINE.match(line)
        if m:
            v = m.group(1).strip()
            if v and v != "none":
                out.append(v[:400])
    return out[:120]


def parse_snapshot(text: str) -> list[dict]:
    """Parse the MCP accessibility snapshot into flat element records."""
    out = []
    for line in text.splitlines():
        m = SNAPSHOT_LINE.match(line)
        if not m:
            continue
        flags = m.group("flags") or ""
        ref_m = REF_RE.search(flags)
        if not ref_m:
            continue
        role = m.group("role")
        name = (m.group("name") or "").replace('\\"', '"')
        trailing = (m.group("trailing") or "").strip()
        out.append(
            {
                "ref": ref_m.group(1),
                "role": role,
                "name": name,
                "value": trailing if trailing and trailing != "none" else "",
                "disabled": "[disabled]" in flags,
                "checked": "[checked]" in flags,
                "raw": line.strip(),
            }
        )
    return out


class MCPKernel(BrowserKernel):
    name = "playwright_mcp"

    def __init__(
        self,
        user_data_dir: Optional[str] = None,
        headless: bool = True,
        cwd: str = "experiments",
        isolated: bool = False,
        policy: InvalidationPolicy = InvalidationPolicy.NODE_IDENTITY,
    ):
        self.user_data_dir = user_data_dir
        self.headless = headless
        self.cwd = cwd
        self.isolated = isolated
        self.policy = policy
        self.cli: Optional[MCPStdioClient] = None
        self._obs_seq = itertools.count(1)
        self._page_seq = itertools.count(1)
        self._event_seq = itertools.count(1)
        self._obs: dict[str, dict] = {}  # obs_id -> {"map": target->ref, "obs": Observation}
        self.registry: dict[str, PageRecord] = {}
        self._mcp_index_to_page: dict[int, str] = {}
        self._active_page_id: Optional[str] = None
        self.events: list[dict] = []
        self.last_snapshot_text: str = ""
        self.last_tool_text: str = ""
        self.capability_notes: list[str] = []

    def _log(self, kind, **kw):
        self.events.append({"seq": next(self._event_seq), "t": time.time(), "kind": kind, **kw})

    # -------------------------------------------------------------- lifecycle

    def start(self) -> None:
        cmd = ["npx", f"@playwright/mcp@{MCP_VERSION}"]
        if self.headless:
            cmd.append("--headless")
        if self.isolated:
            cmd.append("--isolated")
        elif self.user_data_dir:
            cmd += ["--user-data-dir", self.user_data_dir]
        self.cli = MCPStdioClient(cmd, cwd=self.cwd).start(timeout=240)
        names = set(self.cli.tool_names())
        present_unsafe = sorted(names & UNSAFE_TOOLS)
        if present_unsafe:
            self.capability_notes.append(
                "unsafe tools present on server (must be excluded from the model's "
                f"decision schema): {present_unsafe}"
            )
        self._log("kernel_start", server=self.cli.server_info, tools=len(names))
        # Seed page registry from the server's own tab list.
        self._sync_tabs(initial=True)

    def shutdown(self) -> None:
        if self.cli:
            try:
                self.cli.call_tool("browser_close", {}, timeout=30)
            except Exception:
                pass
            self.cli.stop()
        self._log("kernel_shutdown")

    def health(self) -> dict:
        try:
            r = self.cli.call_tool("browser_tabs", {"action": "list"}, timeout=20)
            return {"ok": not is_error(r)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------ calls

    def _call(self, tool: str, args: dict, timeout: float = 60.0) -> str:
        res = self.cli.call_tool(tool, args, timeout=timeout)
        txt = result_text(res)
        # Keep the raw envelope: the "### Modal state" section lives here, not in
        # the snapshot file the envelope points at.
        self.last_tool_text = txt
        if is_error(res):
            raise KernelError(_classify(txt), txt[:400], {"tool": tool, "args": args})
        return txt

    def _refresh_snapshot(self) -> str:
        """Some MCP tools (type, select, press) return only the generated
        Playwright code, with no page state. Values must be re-read explicitly."""
        self.last_snapshot_text = self._read_snapshot(self._call("browser_snapshot", {}))
        return self.last_snapshot_text

    # ------------------------------------------------------------------ pages

    def _sync_tabs(self, initial: bool = False):
        try:
            txt = self._call("browser_tabs", {"action": "list"}, timeout=30)
        except KernelError:
            return
        # Lines look like: "- 0: (current) [Title] (http://url)"
        idxs = []
        for line in txt.splitlines():
            m = re.match(r"\s*-?\s*(\d+):\s*(\(current\))?\s*\[(.*?)\]\s*\((.*?)\)", line)
            if m:
                idxs.append(
                    {
                        "index": int(m.group(1)),
                        "current": bool(m.group(2)),
                        "title": m.group(3),
                        "url": m.group(4),
                    }
                )
        for t in idxs:
            pid = self._mcp_index_to_page.get(t["index"])
            if pid is None:
                pid = f"page_{next(self._page_seq)}"
                self._mcp_index_to_page[t["index"]] = pid
                # MCP surfaces tabs only as an ordered list. There is no creation
                # event and no opener, so ownership cannot be established from the
                # runtime; UNKNOWN is the only honest value for a discovered tab.
                owner = Owner.AGENT if initial else Owner.UNKNOWN
                self.registry[pid] = PageRecord(
                    page_id=pid,
                    owner=owner,
                    opener_page_id=None,
                    created_event_id=next(self._event_seq),
                    url=t["url"],
                    title=t["title"],
                )
                self._log("page_discovered", page_id=pid, owner=owner.value, index=t["index"])
            else:
                self.registry[pid].url = t["url"]
                self.registry[pid].title = t["title"]
            if t["current"]:
                self._active_page_id = pid
        live = {self._mcp_index_to_page[i["index"]] for i in idxs}
        for pid, rec in self.registry.items():
            if pid not in live:
                rec.closed = True

    def list_pages(self) -> list[PageRecord]:
        self._sync_tabs()
        return list(self.registry.values())

    def new_tab(self, url: Optional[str] = None) -> str:
        args = {"action": "new"}
        if url:
            args["url"] = url
        self._call("browser_tabs", args)
        before = set(self.registry)
        self._sync_tabs()
        new = [p for p in self.registry if p not in before]
        if new:
            self.registry[new[0]].owner = Owner.AGENT
            self._active_page_id = new[0]
            return new[0]
        return self._active_page_id or ""

    def switch_tab(self, page_id: str) -> None:
        idx = self._index_for(page_id)
        self._call("browser_tabs", {"action": "select", "index": idx})
        self._active_page_id = page_id

    def close_agent_tab(self, page_id: str) -> dict:
        rec = self.registry.get(page_id)
        if rec is None:
            raise KernelError(KernelErrorCode.TARGET_NOT_FOUND, f"unknown page {page_id}")
        if rec.owner is not Owner.AGENT:
            raise KernelError(
                KernelErrorCode.PAGE_NOT_OWNED,
                f"refusing to close {rec.owner.value}-owned page {page_id}",
                {"owner": rec.owner.value},
            )
        self._call("browser_tabs", {"action": "close", "index": self._index_for(page_id)})
        rec.closed = True
        return {"closed": page_id}

    def _index_for(self, page_id: str) -> int:
        for i, p in self._mcp_index_to_page.items():
            if p == page_id:
                return i
        raise KernelError(KernelErrorCode.TARGET_NOT_FOUND, f"no mcp index for {page_id}")

    # ------------------------------------------------------------- navigation

    def navigate(self, url: str, page_id: Optional[str] = None) -> None:
        if page_id and page_id != self._active_page_id:
            self.switch_tab(page_id)
        self.last_snapshot_text = self._read_snapshot(self._call("browser_navigate", {"url": url}))

    def back(self, page_id: Optional[str] = None) -> None:
        self.last_snapshot_text = self._read_snapshot(self._call("browser_navigate_back", {}))

    # ------------------------------------------------------------ observation

    def _read_snapshot(self, tool_text: str) -> str:
        """MCP 0.0.81 may return the snapshot inline or as a file reference."""
        m = re.search(r"\[Snapshot\]\((.+?\.yml)\)", tool_text)
        if m:
            path = m.group(1)
            full = path if os.path.isabs(path) else os.path.join(self.cwd, path)
            for _ in range(20):
                if os.path.exists(full):
                    return open(full, encoding="utf-8").read()
                time.sleep(0.05)
            return ""
        # inline form
        if "### Page state" in tool_text or "- generic" in tool_text:
            return tool_text
        return tool_text

    def observe(self, page_id: Optional[str] = None) -> Observation:
        if page_id and page_id != self._active_page_id:
            self.switch_tab(page_id)
        txt = self._read_snapshot(self._call("browser_snapshot", {}))
        self.last_snapshot_text = txt
        rows = parse_snapshot(txt)
        obs_id = f"obs_{next(self._obs_seq):05d}"
        self._sync_tabs()
        pid = self._active_page_id or "page_1"
        rec = self.registry.get(pid)

        elements, mapping = [], {}
        frame_ids = set()
        for i, r in enumerate(rows):
            # MCP encodes frame scope inside the ref itself: "e7" is the top
            # frame, "f1e3" is element 3 of frame 1. Verified by direct probe:
            # clicking f1e3/f2e3/f3e3 hits the child/cross-origin/nested frame
            # respectively, never the top frame.
            fid = _frame_of(r["ref"])
            frame_ids.add(fid)
            target = f"{obs_id}:{fid}:{r['ref']}"
            mapping[target] = r["ref"]
            elements.append(
                ObservedElement(
                    target=target,
                    role=r["role"],
                    name=r["name"],
                    value=r["value"],
                    frame_id=fid,
                    enabled=not r["disabled"],
                    visible=True,
                    tag="",
                    attrs={},
                )
            )
        obs = Observation(
            observation_id=obs_id,
            page_id=pid,
            url=rec.url if rec else "",
            title=rec.title if rec else "",
            # MCP exposes no document-identity token; same-URL document replacement
            # is therefore invisible to this runtime.
            document_token="",
            document_generation=0,
            frame_tree_version=len(frame_ids),
            tabs=[
                TabSummary(r.page_id, r.url, r.title, r.owner.value, r.page_id == pid)
                for r in self.registry.values()
                if not r.closed
            ],
            modal=None,
            elements=elements,
            text_blocks=parse_text_blocks(txt),
        )
        obs.state_fingerprint = obs.compute_fingerprint()
        self._obs[obs_id] = {"map": mapping, "obs": obs}
        self._log("observed", observation_id=obs_id, elements=len(elements))
        return obs

    def invalidate_all_observations(self, reason: str) -> None:
        # MCP has no invalidation primitive; the best available action is to drop
        # our own mapping so no old target can be translated into a live ref.
        self._obs.clear()
        self._log("all_observations_invalidated", reason=reason)

    def _ref(self, target: str) -> tuple[str, str]:
        try:
            obs_id = target.split(":", 1)[0]
        except Exception:
            raise KernelError(KernelErrorCode.TARGET_NOT_FOUND, "malformed target")
        rec = self._obs.get(obs_id)
        if rec is None:
            raise KernelError(KernelErrorCode.TARGET_NOT_FOUND, f"unknown observation {obs_id}")
        ref = rec["map"].get(target)
        if ref is None:
            raise KernelError(KernelErrorCode.TARGET_NOT_FOUND, f"target not in {obs_id}")
        oe = rec["obs"].element(target)
        return ref, (oe.name if oe else "element")

    # ----------------------------------------------------------------- actions

    def click(self, target: str) -> dict:
        ref, name = self._ref(target)
        txt = self._call("browser_click", {"target": ref, "element": name or "element"})
        self.last_snapshot_text = self._read_snapshot(txt)
        return {"clicked": target, "name": name}

    def type_text(self, target: str, text: str, submit: bool = False, slowly: bool = False) -> dict:
        ref, name = self._ref(target)
        self._call(
            "browser_type",
            {
                "target": ref,
                "element": name or "element",
                "text": text,
                "submit": submit,
                "slowly": slowly,
            },
        )
        self._refresh_snapshot()
        actual = self._value_from_snapshot(ref)
        return {"target": target, "requested": text, "actual": actual, "exact": actual == text}

    def select(self, target: str, value: str) -> dict:
        ref, name = self._ref(target)
        self._call(
            "browser_select_option",
            {"target": ref, "element": name or "element", "values": [value]},
        )
        self._refresh_snapshot()
        return {"target": target, "requested": value, "actual": self._value_from_snapshot(ref)}

    def press(self, target: str, key: str) -> dict:
        ref, name = self._ref(target)
        self._call("browser_press_key", {"key": key, "target": ref, "element": name})
        self._refresh_snapshot()
        return {"target": target, "key": key}

    def read_value(self, target: str) -> str:
        ref, _ = self._ref(target)
        self._refresh_snapshot()
        return self._value_from_snapshot(ref)

    def _value_from_snapshot(self, ref: str) -> str:
        """Read a field value back from the accessibility snapshot.

        This is the only value-verification channel MCP offers, and its fidelity
        is one of the things Experiment 1 measures.
        """
        # An MCP snapshot renders a populated field as
        #   textbox "Label" [ref=e4]: the value
        # and an empty one as
        #   textbox "Label" [ref=e4]
        # so an absent trailing segment means an empty value. Falling back to the
        # accessible name here would report the *label* as the field's contents,
        # which would turn "the field is empty" into a false verification pass.
        for r in parse_snapshot(self.last_snapshot_text):
            if r["ref"] == ref:
                return r["value"]
        return ""

    # ------------------------------------------------------------------ dialogs

    def dialog_state(self) -> Optional[dict]:
        # MCP reports a modal as a "### Modal state" section inside the most
        # recent tool result. There is no queryable dialog state, so the caller
        # must have made a tool call since the dialog opened.
        txt = self.last_tool_text or ""
        if "### Modal state" in txt or "modal state" in txt.lower():
            for line in txt.splitlines():
                if "dialog with message" in line:
                    return {"raw": line.strip()[:400]}
            return {"raw": txt[:400]}
        return None

    def handle_dialog(self, accept: bool, prompt_text: str = "") -> dict:
        args = {"accept": accept}
        if prompt_text:
            args["promptText"] = prompt_text
        txt = self._call("browser_handle_dialog", args)
        self.last_snapshot_text = self._read_snapshot(txt)
        return {"accepted": accept}


FRAME_REF = re.compile(r"^f(\d+)e\d+$")


def _frame_of(ref: str) -> str:
    """MCP ref -> frame id. 'e7' is the top frame; 'f2e3' is frame 2."""
    m = FRAME_REF.match(ref or "")
    return f"f{m.group(1)}" if m else "f0"


def _classify(text: str) -> KernelErrorCode:
    t = (text or "").lower()
    if "ref=" in t and ("not found" in t or "no longer" in t or "stale" in t):
        return KernelErrorCode.TARGET_STALE
    if "no element found" in t or "not found" in t:
        return KernelErrorCode.TARGET_NOT_FOUND
    if "timeout" in t or "exceeded" in t:
        return KernelErrorCode.TIMEOUT
    if "modal" in t or "dialog" in t:
        return KernelErrorCode.DIALOG_BLOCKING
    if "disabled" in t:
        return KernelErrorCode.TARGET_DISABLED
    if "not visible" in t or "not stable" in t or "intercept" in t:
        return KernelErrorCode.TARGET_NOT_ACTIONABLE
    if "closed" in t:
        return KernelErrorCode.PAGE_CLOSED
    return KernelErrorCode.INTERNAL
