"""Text extraction: recall and noise, old strategy vs new.

Issue C asked whether bare `<div>` text is a genuine observation defect or
whether equivalent semantic content is already represented elsewhere. This
answers it with numbers rather than opinion, and checks that fixing recall does
not explode observation size.

    old: fixed tag whitelist (h1-h3,p,li,td,label,span), element.textContent
    new: each element's OWN direct text nodes, any tag

Reproduce:
    python -m experiments.observation_contract.measure_text
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.common.fixture_server import FixtureCluster
from experiments.common.kernel_direct import DirectPlaywrightKernel

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

OLD_STRATEGY_JS = """
() => {
  const visible = (e) => {
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  return [...document.querySelectorAll('h1,h2,h3,p,li,td,label,span')]
      .filter(visible)
      .map(n => (n.textContent || '').replace(/\\s+/g,' ').trim())
      .filter(t => t.length > 1 && t.length < 400).slice(0, 120);
}
"""


def measure(page_path: str, kernel, cluster) -> dict:
    kernel.navigate(cluster.url(page_path))
    obs = kernel.observe()
    new_blocks = [b.text for b in obs.text_blocks]
    old_blocks = kernel.page_object().evaluate(OLD_STRATEGY_JS)

    def stats(blocks):
        joined = "\n".join(blocks)
        return {
            "blocks": len(blocks),
            "chars": len(joined),
            "approx_tokens": len(joined) // 4,
            "signal": sum(1 for b in blocks if "SIGNAL" in b),
            "noise_markers": sum(1 for b in blocks if "NOISE" in b),
            "duplicate_blocks": len(blocks) - len(set(blocks)),
        }

    return {
        "page": page_path,
        "old": stats(old_blocks),
        "new": stats(new_blocks),
        "old_blocks": old_blocks,
        "new_blocks": new_blocks,
    }


def main() -> dict:
    RESULTS.mkdir(parents=True, exist_ok=True)
    db = tempfile.mktemp(suffix=".sqlite")
    profile = tempfile.mkdtemp(prefix="bav2text_")
    cluster = FixtureCluster(db, primary=8971, secondary=8972).start()
    kernel = DirectPlaywrightKernel(profile, headless=True)
    kernel.start()
    try:
        out = {p: measure(p, kernel, cluster)
               for p in ("/p/text_variants", "/p/text_noise", "/p/verify_records")}
    finally:
        kernel.shutdown()
        cluster.stop()
        shutil.rmtree(profile, ignore_errors=True)

    print(f"{'page':22s} {'strategy':6s} {'blocks':>7s} {'chars':>7s} "
          f"{'~tok':>6s} {'signal':>7s} {'noise':>6s} {'dupes':>6s}")
    for page, m in out.items():
        for which in ("old", "new"):
            s = m[which]
            print(f"{page:22s} {which:6s} {s['blocks']:7d} {s['chars']:7d} "
                  f"{s['approx_tokens']:6d} {s['signal']:7d} "
                  f"{s['noise_markers']:6d} {s['duplicate_blocks']:6d}")

    tot_old = sum(m["old"]["chars"] for m in out.values())
    tot_new = sum(m["new"]["chars"] for m in out.values())
    delta = 100.0 * (tot_new - tot_old) / max(1, tot_old)
    print(f"\ntotal chars old={tot_old} new={tot_new} delta={delta:+.1f}%")
    out["_totals"] = {"old_chars": tot_old, "new_chars": tot_new,
                      "delta_pct": round(delta, 1)}
    (RESULTS / "text_measurement.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    main()
