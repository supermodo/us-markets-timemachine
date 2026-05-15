# Contributing

Thanks for your interest in `us-markets-timemachine`.

## Before you write code

If you're proposing a new data source, **read
[`docs/ADDING-A-SOURCE.md`](docs/ADDING-A-SOURCE.md) first** and open a
discussion issue before opening a PR. The mission scope is narrow on purpose
and not every well-intentioned PR will fit.

If you're proposing a change to shared core code (anything outside
`src/timemachine/sources/<name>/`), open an issue first describing the
problem and the proposed approach. Ad-hoc PRs to shared infrastructure
will probably need to be rewritten after discussion.

For typo fixes and one-line clarifications: just open a PR.

Governance specifics are in [`docs/GOVERNANCE.md`](docs/GOVERNANCE.md).

## Dev setup

Requires Python 3.12+.

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .[dev]

For local SEC EDGAR runs, set the contact email so the User-Agent passes
SEC's policy check:

    export TIMEMACHINE_CONTACT_EMAIL=you@example.com

## Running tests + lint

    pytest -q          # all tests, network-free
    ruff check .       # lint

CI will run both on every PR.

## Project conventions

- **Stdlib only** for the runtime package. Dev / test deps (`pytest`,
  `ruff`) are fine, but the package itself must `pip install` with no
  third-party runtime dependencies. This keeps the worker immune to
  supply-chain churn over decades.
- **Network-free tests.** Inject a `fetcher` callable; never call live
  upstreams from a test. The EDGAR and NASDAQ source tests are good
  templates.
- **One source = one subdirectory** under `src/timemachine/sources/<name>/`
  AND `data/<name>/` AND `tests/sources/<name>/`. Sources do not import
  from each other.
- **Shared core stays shared.** If your change touches `http.py`, `io.py`,
  `paths.py`, `manifest.py`, `notify.py`, `cli.py`, or `dates.py`, that's
  a cross-cutting change that needs explicit BDFL approval (see GOVERNANCE).
- **Append-only data.** `data/` files are never overwritten by code paths
  other than the manifest writer (which atomically replaces). Tests assert
  this; reviewers will too.
- **Comments explain *why*, not *what*.** The code already says what it's
  doing; comments should add the non-obvious context.
- **Atomic PR per concern.** A new source PR shouldn't also refactor the
  CLI. A CLI refactor PR shouldn't also touch sources. Easier to review,
  easier to revert.

## PR template (suggested)

When opening a PR, include:

- **What:** one sentence on the change.
- **Why:** the motivating problem; link to the issue that authorised it.
- **How:** the approach in 2-3 sentences.
- **Test plan:** what you ran locally; for source PRs, the 7-day proof-of-
  life manifest summary.
- **Rollback plan:** what to delete / revert if this needs to come out.

## Code review expectations

- Reviews are typically within a week, sometimes longer.
- Substantive feedback is the norm; please don't take it personally.
- If a review is taking too long, see the escalation path in
  [`docs/GOVERNANCE.md`](docs/GOVERNANCE.md).

## Credit

Contributors are listed in commit history. Sustained contributors to a
specific source may be invited to become CODEOWNERS for that source's
subdirectory; see GOVERNANCE.md for the path.
