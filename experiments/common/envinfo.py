"""Environment capture. Every experiment result file embeds one of these.

MASTER_VALIDATION_PLAN section 1: "A regression that cannot be reproduced
against a pinned environment is not closed."
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path


def _run(cmd, timeout=30):
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=(os.name == "nt")
        )
        return (r.stdout or r.stderr).strip()
    except Exception as e:
        return f"<unavailable: {e}>"


def _git(args):
    return _run(["git"] + args)


def capture(extra: dict | None = None) -> dict:
    info = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "os": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "git": {
            "commit": _git(["rev-parse", "HEAD"]),
            "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"]),
            "dirty": bool(_git(["status", "--porcelain"])),
        },
    }

    # GPU
    gpu = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader",
        ]
    )
    info["gpu"] = gpu

    # Node / npm
    info["node"] = _run(["node", "--version"])
    info["npm"] = _run(["npm", "--version"])

    # Playwright + browser
    try:
        import playwright

        info["playwright"] = getattr(playwright, "__version__", "unknown")
    except Exception:
        info["playwright"] = "<not installed>"
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            info["chromium_version"] = b.version
            info["chromium_path"] = p.chromium.executable_path
            b.close()
    except Exception as e:
        info["chromium_version"] = f"<unavailable: {e}>"

    # Playwright MCP (pinned in experiments/package.json)
    pkg = Path(__file__).resolve().parent.parent / "node_modules" / "@playwright" / "mcp" / "package.json"
    if pkg.exists():
        try:
            info["playwright_mcp"] = json.loads(pkg.read_text())["version"]
        except Exception:
            info["playwright_mcp"] = "<unreadable>"
    else:
        info["playwright_mcp"] = "<not installed>"

    # Ollama + models
    info["ollama_version"] = _run(["ollama", "--version"])
    info["ollama_models"] = _run(["ollama", "list"])
    info.update(extra or {})
    return info


def capture_model(model: str, host: str = "http://127.0.0.1:11434") -> dict:
    """Exact local model identity: digest, quantization, context, parameters."""
    import urllib.request

    out = {"model": model, "host": host}
    try:
        req = urllib.request.Request(
            host + "/api/show",
            data=json.dumps({"model": model}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        out["details"] = d.get("details", {})
        out["model_info"] = {
            k: v
            for k, v in (d.get("model_info") or {}).items()
            if any(
                s in k
                for s in (
                    "context_length",
                    "embedding_length",
                    "block_count",
                    "parameter_count",
                    "architecture",
                    "head_count",
                )
            )
        }
        out["capabilities"] = d.get("capabilities", [])
        out["parameters"] = d.get("parameters", "")
        out["template_sha"] = (
            __import__("hashlib").sha256((d.get("template") or "").encode()).hexdigest()[:16]
        )
    except Exception as e:
        out["error"] = str(e)
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=30) as r:
            tags = json.loads(r.read())
        for m in tags.get("models", []):
            if m.get("name") == model or m.get("model") == model:
                out["digest"] = m.get("digest")
                out["size_bytes"] = m.get("size")
                out["modified_at"] = m.get("modified_at")
    except Exception:
        pass
    return out


if __name__ == "__main__":
    print(json.dumps(capture(), indent=2))
