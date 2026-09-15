"""Minimal MCP stdio JSON-RPC client.

Only what the Experiment 1 spike needs: initialize, tools/list, tools/call.
Deliberately dependency-free so the experiment reproduces from a clean checkout
with nothing but `npm install` in experiments/.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Any, Optional


class MCPError(Exception):
    pass


class MCPStdioClient:
    def __init__(self, cmd: list[str], cwd: Optional[str] = None, env: Optional[dict] = None):
        self.cmd = cmd
        self.cwd = cwd
        self.env = {**os.environ, **(env or {})}
        self.proc: Optional[subprocess.Popen] = None
        self._id = 0
        self._lock = threading.Lock()
        self.stderr_lines: list[str] = []
        self.server_info: dict = {}
        self.tools: list[dict] = []

    # ------------------------------------------------------------------

    def start(self, timeout: float = 60.0):
        self.proc = subprocess.Popen(
            self.cmd,
            cwd=self.cwd,
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            shell=(os.name == "nt"),
        )
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        res = self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "bav2-experiment", "version": "1.0"},
            },
            timeout=timeout,
        )
        self.server_info = res.get("serverInfo", {})
        self.notify("notifications/initialized", {})
        self.tools = self.request("tools/list", {}, timeout=timeout).get("tools", [])
        return self

    def _drain_stderr(self):
        assert self.proc and self.proc.stderr
        for line in self.proc.stderr:
            self.stderr_lines.append(line.rstrip())
            if len(self.stderr_lines) > 500:
                del self.stderr_lines[:250]

    # ------------------------------------------------------------------

    def _send(self, obj: dict):
        assert self.proc and self.proc.stdin
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def notify(self, method: str, params: dict):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict, timeout: float = 60.0) -> dict:
        with self._lock:
            self._id += 1
            rid = self._id
            self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
            deadline = time.time() + timeout
            assert self.proc and self.proc.stdout
            while time.time() < deadline:
                line = self.proc.stdout.readline()
                if not line:
                    raise MCPError(
                        "MCP server closed stdout. stderr tail: "
                        + " | ".join(self.stderr_lines[-6:])
                    )
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("id") != rid:
                    continue  # notification or out-of-band message
                if "error" in msg:
                    raise MCPError(json.dumps(msg["error"])[:400])
                return msg.get("result", {})
            raise MCPError(f"timeout waiting for {method}")

    def call_tool(self, name: str, arguments: dict, timeout: float = 60.0) -> dict:
        return self.request(
            "tools/call", {"name": name, "arguments": arguments}, timeout=timeout
        )

    def tool_names(self) -> list[str]:
        return [t["name"] for t in self.tools]

    def stop(self):
        if self.proc:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            try:
                self.proc.terminate()
                self.proc.wait(timeout=10)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass


def result_text(res: dict) -> str:
    """Flatten an MCP tool result into text."""
    parts = []
    for c in res.get("content", []) or []:
        if c.get("type") == "text":
            parts.append(c.get("text", ""))
    return "\n".join(parts)


def is_error(res: dict) -> bool:
    return bool(res.get("isError"))
