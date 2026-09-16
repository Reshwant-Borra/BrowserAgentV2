# Campaign notes

Process notes for the P0 experiment campaign. Findings live in the per-experiment
reports; this is the record of how the campaign was run and what went wrong in
the running of it.

## Experiment 1 could not be reconciled from git

The campaign brief described a completed BrowserKernel spike on branch
`experiment/browser-kernel-spike` at commit `b8f851b`, with specific results
(295 cases per candidate, MCP 275/295, direct Playwright 285/295), and asked for
it to be verified and pushed.

**It does not exist in this repository.** Checked exhaustively:

```text
git for-each-ref          only main and origin/main
git reflog --all          a single entry: "clone: from ...BrowserAgentV2.git"
git stash list            empty
git fsck --lost-found     no dangling objects
git worktree list         one worktree
git cat-file -t b8f851b   fatal: Not a valid object name
git ls-remote --heads     only refs/heads/main
```

Sibling directories were also checked: `~/Desktop/V2Browser` is empty, and
`~/BrowserAgentChrome` is a Chrome profile directory, not a repository.

The brief was explicit that Experiment 1 must not be fabricated if absent, so
the spike was **re-run from scratch** on the current machine. The verdict
matches the one described (`ADOPT_DIRECT_PLAYWRIGHT`) but the numbers are our
own and are reproducible: 105 graded runs per candidate, not 295. See
[E1](browser_kernel/REPORT.md).

## Obsidian tooling

An Obsidian integration for Claude Code already exists and is already installed
through the supported plugin mechanism:

```text
plugin:      obsidian@obsidian-skills
marketplace: github:kepano/obsidian-skills
skills:      obsidian-markdown, obsidian-cli, obsidian-bases,
             json-canvas, defuddle
```

The source is `kepano`, an Obsidian maintainer, so it clears the "official /
trusted" bar. Nothing needed installing and no binaries were downloaded.

**It was deliberately not used to shape the repository.** Its value here would
be wikilinks and canvases, and both would make the knowledge base less portable
for the sake of one editor. Everything in this campaign is plain Markdown with
**repository-relative links**, which renders correctly on GitHub, in an IDE, and
in Obsidian alike. Obsidian is a developer convenience for navigating the graph;
it is not a dependency, it is not in the runtime, and no file is in a
proprietary format.

## Fairness rules the campaign held itself to

1. **The kernel under test never grades itself.** The fixture server records what
   the page actually did, over a synchronous XHR that completes before the click
   handler returns. This caught several cases where a runtime reported success
   for something that never happened.
2. **Controls that should fail are included.** `UNSAFE_NAME_RESOLVE`,
   `UNSAFE_URL_ONLY` and `blind_replay` exist so a clean sweep cannot be
   mistaken for evidence.
3. **Harness bugs are not runtime failures.** Every runner has a separate
   `HARNESS_ERROR` outcome. Four dramatic-looking MCP failures turned out to be
   our adapter's bugs and were fixed and re-run rather than reported.
4. **Metrics were corrected against the winner.** Both mid-campaign metric fixes
   (end-to-end accuracy, hallucination severity) made the eventual loser look
   better, which is the direction that matters.
5. **Thresholds were written down first.** The adequacy bar was committed before
   the evaluation ran and did not move when the model missed it by 0.78 points.

## Things that went wrong in the running of it

**A stale server silently corrupted a round of results.** On Windows,
`SO_REUSEADDR` lets a second socket bind a port that is already listening, and
which process receives a connection is undefined. A fixture server left over
from a killed run answered some requests with an older `effects.js`, which made
both kernels appear to fail every typing test. The cluster now mints a nonce at
startup and refuses to start if anything else answers.

**A tag collision overwrote raw data.** The first dev matrix wrote both
interfaces to the same filename because the tag did not include the interface.
Summaries survived in the log, the raw rows did not. Re-run with unique tags.

**Two thinking-mode arms measured a token cap rather than a model.** Both hit
`num_predict: 300` exactly, so their schema failures were truncation. Re-run at
1600.

**An adequacy run lost ~10 minutes of inference to a `KeyError` at the save
step.** Results are now written defensively, and `common/rescore.py` exists so
that a scoring change never requires re-running a model.

## Reproduction

Everything is one command per experiment; see [`README.md`](README.md).
Environment is pinned in [`ENVIRONMENT.md`](ENVIRONMENT.md) and embedded in
every result file.
