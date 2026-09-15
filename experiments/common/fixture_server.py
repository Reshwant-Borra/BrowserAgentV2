"""Deterministic local fixture web server used by every P0 experiment.

Design rules:
  * localhost only; never performs a real-world write;
  * static pages live as readable HTML under experiments/fixtures/pages/;
  * dynamic behaviour is confined to a handful of /api/ endpoints;
  * the mutation endpoint is *durable* and keyed by operation_id so that
    Experiment 6 can interrogate real server-side truth after a crash;
  * two origins are served (primary + secondary) so cross-origin iframe and
    cross-origin navigation policy can be tested without the public internet.

Run standalone:  python -m experiments.common.fixture_server --port 8799
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import threading
import uuid
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PAGES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "pages"

PRIMARY_PORT = 8799
SECONDARY_PORT = 8800


class OperationLedger:
    """Durable, idempotency-keyed record of state-changing operations.

    This stands in for "a real website that actually did something". It is the
    ground truth against which duplicate-side-effect claims are measured.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init()

    def _conn(self):
        c = sqlite3.connect(self.db_path, timeout=10)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def _init(self):
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS operations (
                       seq INTEGER PRIMARY KEY AUTOINCREMENT,
                       operation_id TEXT UNIQUE,
                       kind TEXT,
                       payload TEXT,
                       accepted_at REAL
                   )"""
            )
            # Every raw arrival is logged, including ones rejected as duplicates.
            c.execute(
                """CREATE TABLE IF NOT EXISTS arrivals (
                       seq INTEGER PRIMARY KEY AUTOINCREMENT,
                       operation_id TEXT,
                       kind TEXT,
                       duplicate INTEGER,
                       arrived_at REAL
                   )"""
            )

    def submit(self, operation_id: str, kind: str, payload: dict, dedupe: bool) -> dict:
        """Record an operation.

        dedupe=True  -> server enforces idempotency (best case web app)
        dedupe=False -> server accepts every arrival (worst case web app; this is
                        the mode that actually detects agent-side double submits)
        """
        with self._lock, self._conn() as c:
            row = c.execute(
                "SELECT seq, accepted_at FROM operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            is_dup = row is not None
            c.execute(
                "INSERT INTO arrivals(operation_id, kind, duplicate, arrived_at) VALUES (?,?,?,?)",
                (operation_id, kind, 1 if is_dup else 0, time.time()),
            )
            if is_dup and dedupe:
                return {
                    "status": "DUPLICATE_IGNORED",
                    "operation_id": operation_id,
                    "confirmation_seq": row[0],
                }
            if is_dup and not dedupe:
                # Worst-case app: a second effect really happens.
                cur = c.execute(
                    "INSERT INTO operations(operation_id, kind, payload, accepted_at) "
                    "VALUES (?,?,?,?)",
                    (f"{operation_id}#dup{time.time()}", kind, json.dumps(payload), time.time()),
                )
                return {
                    "status": "ACCEPTED_DUPLICATE_EFFECT",
                    "operation_id": operation_id,
                    "confirmation_seq": cur.lastrowid,
                }
            cur = c.execute(
                "INSERT INTO operations(operation_id, kind, payload, accepted_at) VALUES (?,?,?,?)",
                (operation_id, kind, json.dumps(payload), time.time()),
            )
            return {
                "status": "ACCEPTED",
                "operation_id": operation_id,
                "confirmation_seq": cur.lastrowid,
            }

    def lookup(self, operation_id: str) -> dict:
        """Durable evidence query: did this exact operation land?"""
        with self._conn() as c:
            row = c.execute(
                "SELECT seq, kind, payload, accepted_at FROM operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
        if row is None:
            return {"found": False, "operation_id": operation_id}
        return {
            "found": True,
            "operation_id": operation_id,
            "confirmation_seq": row[0],
            "kind": row[1],
            "payload": json.loads(row[2]),
            "accepted_at": row[3],
        }

    def effect_count(self, kind: str | None = None) -> int:
        with self._conn() as c:
            if kind:
                return c.execute(
                    "SELECT COUNT(*) FROM operations WHERE kind=?", (kind,)
                ).fetchone()[0]
            return c.execute("SELECT COUNT(*) FROM operations").fetchone()[0]

    def arrivals(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT operation_id, kind, duplicate, arrived_at FROM arrivals ORDER BY seq"
            ).fetchall()
        return [
            {"operation_id": r[0], "kind": r[1], "duplicate": bool(r[2]), "arrived_at": r[3]}
            for r in rows
        ]

    def reset(self):
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM operations")
            c.execute("DELETE FROM arrivals")


EFFECTS_TAG = '<script src="/effects.js"></script>\n'

# Synchronous XHR so that when a click handler returns, the server has *already*
# recorded the effect. This removes every race from the oracle.
EFFECTS_JS = """
window.__fired = window.__fired || [];
window.__effect = function(name, detail){
  window.__fired.push(name);
  try {
    var x = new XMLHttpRequest();
    x.open('GET', '/api/pagefx?name=' + encodeURIComponent(name)
                 + '&detail=' + encodeURIComponent(detail || '')
                 + '&doc=' + encodeURIComponent(window.__bav2_doc || '')
                 + '&url=' + encodeURIComponent(location.href), false);
    x.send();
  } catch (e) {}
  var el = document.getElementById('log') || document.getElementById('clicked');
  if (el) el.textContent = window.__fired.join(',');
  return name;
};

// Independent value oracle. Whatever a kernel *claims* a field contains, this
// reports what the page itself saw. It is the only way to tell "the runtime
// cannot type" apart from "the runtime cannot read a value back".
(function(){
  var report = function(e){
    var t = e.target; if (!t) return;
    var id = t.id || t.getAttribute('aria-label') || t.name || t.tagName;
    var v = (t.isContentEditable ? t.textContent
             : (t.type === 'checkbox' || t.type === 'radio'
                ? (t.checked ? 'checked' : 'unchecked') : t.value));
    try {
      var x = new XMLHttpRequest();
      x.open('GET', '/api/pagefx?name=' + encodeURIComponent('VALUE:' + id)
                   + '&detail=' + encodeURIComponent(v == null ? '' : String(v)), false);
      x.send();
    } catch (err) {}
  };
  document.addEventListener('input', report, true);
  document.addEventListener('change', report, true);
})();
"""


class EffectLog:
    """Kernel-independent record of what the *page* actually did."""

    def __init__(self):
        self._lock = threading.Lock()
        self.entries: list[dict] = []

    def add(self, name, detail, doc, url):
        with self._lock:
            self.entries.append(
                {
                    "seq": len(self.entries) + 1,
                    "name": name,
                    "detail": detail,
                    "doc": doc,
                    "url": url,
                    "t": time.time(),
                }
            )

    def snapshot(self) -> list[dict]:
        with self._lock:
            return list(self.entries)

    def names(self) -> list[str]:
        return [e["name"] for e in self.snapshot()]

    def reset(self):
        with self._lock:
            self.entries.clear()


class FixtureHandler(BaseHTTPRequestHandler):
    server_version = "BAV2Fixture/1.0"
    protocol_version = "HTTP/1.1"

    # injected by make_server
    ledger: OperationLedger = None  # type: ignore
    effects: EffectLog = None  # type: ignore
    origin_label: str = "primary"
    peer_origin: str = ""
    nonce: str = ""

    def log_message(self, fmt, *args):  # silence
        pass

    # ---------------- helpers ----------------

    def _send(self, code: int, body: bytes, ctype="text/html; charset=utf-8", extra=None):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # Expected on the /slow timeout fixture: the browser aborts the
            # request when the kernel's navigation timeout fires.
            self.close_connection = True

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _page(self, name: str, subs: dict | None = None):
        p = PAGES_DIR / name
        if not p.exists():
            self._send(404, b"<h1>fixture page missing</h1>")
            return
        html = p.read_text(encoding="utf-8")
        html = html.replace("__PEER_ORIGIN__", self.peer_origin)
        html = html.replace("__ORIGIN_LABEL__", self.origin_label)
        for k, v in (subs or {}).items():
            html = html.replace(k, v)
        # Every fixture page gets the out-of-band effect reporter. Verification of
        # "which handler actually fired" must not run through the kernel under
        # test, or the kernel would be grading its own homework.
        self._send(200, (EFFECTS_TAG + html).encode("utf-8"))

    # ---------------- routing ----------------

    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)

        if path == "/" or path == "/index":
            self._page("index.html")
        elif path == "/effects.js":
            self._send(200, EFFECTS_JS.encode(), "application/javascript")
        elif path == "/api/pagefx":
            self.effects.add(
                (q.get("name") or [""])[0],
                (q.get("detail") or [""])[0],
                (q.get("doc") or [""])[0],
                (q.get("url") or [""])[0],
            )
            self._json(200, {"ok": True})
        elif path == "/api/pagefx/log":
            self._json(200, {"entries": self.effects.snapshot()})
        elif path == "/api/pagefx/reset":
            self.effects.reset()
            self._json(200, {"ok": True})
        elif path == "/api/health":
            self._json(200, {"ok": True, "origin": self.origin_label, "nonce": self.nonce})
        elif path == "/api/op":
            op = (q.get("operation_id") or [""])[0]
            self._json(200, self.ledger.lookup(op))
        elif path == "/api/effects":
            self._json(
                200,
                {
                    "count": self.ledger.effect_count((q.get("kind") or [None])[0]),
                    "arrivals": self.ledger.arrivals(),
                },
            )
        elif path == "/api/reset":
            self.ledger.reset()
            self._json(200, {"ok": True})
        elif path == "/slow":
            # Deterministic navigation delay for timeout tests.
            delay = float((q.get("ms") or ["5000"])[0]) / 1000.0
            time.sleep(delay)
            self._send(200, b"<title>Slow</title><h1>slow page</h1>")
        elif path == "/redirect":
            n = int((q.get("n") or ["3"])[0])
            if n <= 0:
                self._send(200, b"<title>Redirect End</title><h1>redirect end</h1>")
            else:
                self._send(
                    302, b"", extra={"Location": f"/redirect?n={n-1}"}
                )
        elif path == "/status404":
            self._send(404, b"<title>Not Found</title><h1>404 fixture</h1>")
        elif path == "/download/report.csv":
            body = b"id,name,value\n1,alpha,10\n2,beta,20\n"
            self._send(
                200,
                body,
                "text/csv",
                {"Content-Disposition": 'attachment; filename="report.csv"'},
            )
        elif path.startswith("/p/"):
            self._page(path[3:] + ".html")
        else:
            self._send(404, b"<title>Not Found</title><h1>no fixture route</h1>")

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode() or "{}")
        except Exception:
            # form encoded
            from urllib.parse import parse_qsl

            data = dict(parse_qsl(raw.decode()))

        if u.path == "/api/submit":
            op = data.get("operation_id") or ""
            kind = data.get("kind") or "generic"
            dedupe = str(data.get("dedupe", "false")).lower() in ("1", "true", "yes")
            delay_ms = float(data.get("delay_ms") or 0)
            if delay_ms:
                time.sleep(delay_ms / 1000.0)
            if not op:
                self._json(400, {"error": "operation_id required"})
                return
            res = self.ledger.submit(op, kind, data, dedupe)
            # post_delay_ms opens the crucial window for Experiment 6: the server
            # has ALREADY committed the effect, but the browser has not yet seen a
            # response. A controller that crashes here knows nothing, while the
            # world has already changed.
            post = float(data.get("post_delay_ms") or 0)
            if post:
                time.sleep(post / 1000.0)
            self._json(200, res)
        else:
            self._json(404, {"error": "no route"})


def make_server(
    port: int,
    ledger: OperationLedger,
    effects: EffectLog,
    origin_label: str,
    peer_origin: str,
    nonce: str = "",
):
    handler = type(
        f"FixtureHandler_{port}",
        (FixtureHandler,),
        {
            "ledger": ledger,
            "effects": effects,
            "origin_label": origin_label,
            "peer_origin": peer_origin,
            "nonce": nonce,
        },
    )
    # On Windows, SO_REUSEADDR lets a second socket bind a port that is already
    # listening, and which process receives a given connection is undefined. A
    # stale fixture server from a previous run then silently answers some
    # requests, which corrupts results in a way that looks like a runtime bug.
    # Fail loudly instead.
    class Srv(ThreadingHTTPServer):
        allow_reuse_address = False
        daemon_threads = True

    return Srv(("127.0.0.1", port), handler)


class FixtureCluster:
    """Primary + secondary origin, sharing one operation ledger."""

    def __init__(self, db_path: str, primary=None, secondary=None):
        # BAV2_PORT_BASE lets independent experiments run concurrently without
        # colliding on ports (and without silently sharing a server).
        base = os.environ.get("BAV2_PORT_BASE")
        if primary is None:
            primary = int(base) if base else PRIMARY_PORT
        if secondary is None:
            secondary = primary + 1
        self.primary_port = primary
        self.secondary_port = secondary
        self.primary_origin = f"http://127.0.0.1:{primary}"
        # localhost vs 127.0.0.1 are different origins to the browser, and we also
        # use a different port, so this is unambiguously cross-origin.
        self.secondary_origin = f"http://localhost:{secondary}"
        self.ledger = OperationLedger(db_path)
        self.effects = EffectLog()
        self.nonce = uuid.uuid4().hex
        self._servers = []
        self._threads = []

    def start(self):
        for port, label, peer in (
            (self.primary_port, "primary", self.secondary_origin),
            (self.secondary_port, "secondary", self.primary_origin),
        ):
            srv = make_server(port, self.ledger, self.effects, label, peer, self.nonce)
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            self._servers.append(srv)
            self._threads.append(t)
        self._verify_identity()
        return self

    def _verify_identity(self):
        """Prove that WE are the server answering on these ports.

        Without this, a stale server from a previous run can shadow ours and
        silently serve old fixtures.
        """
        import urllib.request

        for origin in (self.primary_origin, self.secondary_origin):
            with urllib.request.urlopen(origin + "/api/health", timeout=10) as r:
                got = json.loads(r.read()).get("nonce")
            if got != self.nonce:
                self.stop()
                raise RuntimeError(
                    f"another process is answering on {origin} "
                    f"(nonce {got!r} != {self.nonce!r}). Kill the stale fixture "
                    "server before running experiments."
                )

    def stop(self):
        for s in self._servers:
            try:
                s.shutdown()
                s.server_close()
            except Exception:
                pass

    def url(self, path: str) -> str:
        return self.primary_origin + path

    def peer_url(self, path: str) -> str:
        return self.secondary_origin + path

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(os.getcwd(), "fixture_ops.sqlite"))
    args = ap.parse_args()
    c = FixtureCluster(args.db).start()
    print(f"primary   {c.primary_origin}")
    print(f"secondary {c.secondary_origin}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        c.stop()
