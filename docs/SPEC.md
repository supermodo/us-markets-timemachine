# us-markets-timemachine — Specification

What this project is for, and what it must produce. The runtime, the language,
the scheduling mechanism, and the build itself are deliberately **left open** —
those are decisions for whoever builds it. The Python implementation in
`src/timemachine/` is one such instantiation.

---

## 1. Purpose

US markets institutions — NASDAQ, the SEC, FINRA, the CFTC, the OCC, the Fed
and others — publish reference data about today's market every day, and
**most of it is overwritten in place every morning with no public history of
prior versions retained by the institution.** A snapshot captured today
silently omits every security that has since delisted, gone bankrupt, or been
acquired; every CIK whose ticker was reassigned; every short-interest figure
that was superseded. The only way to ever answer *"what did the market look
like on this exact historical date?"* is for someone to have captured the
relevant files every day and never thrown a day away.

This project is that someone. It keeps a dated, permanent, append-only
archive of every file in scope, from every registered source.

The mission is narrow on purpose: **vanishing data only**. If the
authoritative institution maintains a complete public history of a file
themselves, this project does not mirror it. The project's value is in
preserving what would otherwise be unrecoverable.

## 2. Why a new project

A scattered set of public repositories cover slivers of this ground
(`rreichel3/US-Stock-Symbols`, `datasets/nasdaq-listings`), but each archives
a *different* file from a single institution, none archive the raw publisher
files as dated point-in-time snapshots with all fields intact, and none cover
more than one institution at once. The unique angle of
`us-markets-timemachine` is **multi-source by design** — a contributor adding
SEC EDGAR ticker mappings or FINRA short-interest reports does not have to
build a new mirror infrastructure; the framework, the validation pipeline,
the manifest, the notification fan-out, and the daily commit job are all
shared.

---

## 3. What it must produce

### 3.1 The set of registered sources

Each source archives one upstream publisher's vanishing files. A source is a
self-contained code unit (`src/timemachine/sources/<name>/`) implementing the
Source protocol from section 4.1, plus a self-contained data subtree
(`data/<name>/`) carrying its own NOTICE.md and manifest history.

The currently integrated sources are catalogued in section 8. A complete tier list
of integrated, candidate, and out-of-scope sources lives in
[`docs/POTENTIAL-SOURCES.md`](POTENTIAL-SOURCES.md). The bar a proposed
source must clear is documented in [`docs/ADDING-A-SOURCE.md`](ADDING-A-SOURCE.md).

### 3.2 Output form

Every captured file from every source must be stored:

- **dated** — the date is in the path, so a point-in-time read is a plain
  file open: `data/<source>/<file>/<YYYY>/<YYYY-MM-DD>` for the daily set,
  and the original dated filename under `data/<source>/<archive>/<YYYY>/`
  for any source-internal mirror set;
- **compressed** — gzip; the corpus is large over decades;
- **append-only** — a previously captured day is **never** overwritten, and
  nothing is **ever** deleted;
- **kept under version control** — the archive is a repository, so the
  history is the file tree itself: browsable, clonable, with no external
  service to depend on.

A fetched file that fails validation (section 4.4) must be stored separately under
`data/<source>/_rejected/…`, never under a real date.

Two output forms were considered and set aside: keeping only the latest copy
with history in commit diffs (rejected — point-in-time reads become commit
archaeology); and pushing the data to external object storage (held in
reserve as a fallback if the licensing posture in section 6 ever forces code and
data apart for a particular source).

### 3.3 The manifest — the heartbeat

Every run of every source must write to a per-source append-only
`data/<source>/manifest-<kind>.json` recording exactly what happened, so
anything reading the archive can tell at a glance whether it is fresh and
whole. Each run records its timestamps and a per-file list; each file entry
records its `source`, `name`, `status` (`ok` / `invalid` / `missing` /
`schema_drift` / `discovered`), stored path, content hash, row count, and
where applicable the upstream's own creation time. Per-run copies must be
kept (not only the latest), and per-source manifests must never share a file
so one source's run never clobbers another's heartbeat.

The `source` field on every entry is intentionally redundant with the
manifest's filesystem location — this lets cross-source tooling identify
provenance from a single entry without needing the file's path context.

### 3.4 Scope boundaries (the mission filter)

A file is in scope only if **all** of the following are true:

1. It comes from a US markets authoritative institution (SEC, FINRA, NASDAQ,
   NYSE, Cboe, IEX, OCC, MSRB, CFTC, Fed, Treasury, NFA, etc.).
2. It is publicly accessible without authentication or paid subscription.
3. **The institution itself does not maintain a complete public history**
   of prior versions. (This is the load-bearing criterion. SEC archives 10-K
   and Form 4 filings forever, so those are out of scope; SEC overwrites
   `company_tickers.json` daily without history, so it is in scope.)
4. It is reasonable size for a git repository (≤ 100 MB / year / source).
5. Its format is stable enough that schema drift can be detected and flagged.
6. It contains no personal data / PII.

Rejected by these filters: SEC EDGAR filings, CFTC swap data archive,
Treasury auction history, FRED time series — all because the institution
maintains a complete public history of its own.

---

## 4. How sources must behave

These are behavioral requirements, not an implementation. _How_ they are met —
language, scheduler, libraries — is open.

### 4.1 The Source protocol

Every source must expose, at minimum:

| Attribute / method                    | Purpose                                                         |
| ------------------------------------- | --------------------------------------------------------------- |
| `name` (str)                          | Directory-safe identifier; used for `data/<name>/`, manifests, CLI flags. |
| `display_name` (str)                  | Human-readable label for logs and notifications.                |
| `should_run(today: date) -> bool`     | Cheap calendar gate; False on days the publisher does not produce data. |
| `snapshot(*, data_root, today, dry_run) -> Iterable[FileEntry]` | Fetch, validate, write, and return one FileEntry per file handled. |

The Python implementation makes this a `Protocol` in
`src/timemachine/sources/base.py`. New sources are added by writing a class
satisfying it under `src/timemachine/sources/<name>/source.py` and registering
it in `src/timemachine/sources/__init__.py:REGISTRY`.

The contract is intentionally minimal: a larger contract (forcing every
source into a 3-phase capture+mirror+discover shape) would push NASDAQ's
quirks onto sources that don't share them. Sources that DO need multiple
internal phases (NASDAQ today) compose them privately inside their own
`snapshot()`.

### 4.2 Capture cadence

Each source decides via `should_run(today)` whether the framework should call
its `snapshot()` on a given date. The framework runs daily; sources that
publish weekday-only (EDGAR) skip weekends; sources that publish bi-monthly
(FINRA short interest, when integrated) return False on every other day.
A skipped run is recorded as a no-op in the manifest, not as a failure.

### 4.3 Snapshot semantics

For each declared file in a source's `snapshot()`:
fetch → validate → on pass, store under its dated path; on fail, park under
`_rejected/`; if the fetch fails outright, record it as `missing`. **One file
must never crash another, and one source must never crash another.**

### 4.4 Content validation — before anything is stored as data

Every source must validate fetched content before it is trusted. Every
source must at minimum detect HTML error pages (publishers redirect dead
files to HTML; a naive fetcher would archive that HTML under a real date)
and enforce a per-file minimum size. Beyond that, validation is per-source:
NASDAQ's text files have headers, delimiters, and trailers; EDGAR's JSON
files have shape, required keys, and row-width invariants.

**Schema drift is lenient by design:** a *new trailing column* (NASDAQ) or
*new optional field* (EDGAR) must not fail validation — the raw file is
still stored faithfully — but it is flagged `schema_drift` for a human to
look at.

### 4.5 Discovery (optional, per-source)

A source MAY (not MUST) implement discovery: after capturing its declared
files, list its upstream directory and compare against the declared list,
recording anything present upstream that is neither captured nor explicitly
ignored. NASDAQ does this because its SymDir/ index changes shape over time;
EDGAR does not because its filename set is fixed. Discovery findings land in
the source's manifest with status `discovered`; they are never auto-promoted
to canonical paths — promotion requires a human PR.

---

## 5. Resilience contract

One invariant holds everything together: **never delete, never overwrite a
good day, never store bytes that have not been validated.**

| Failure                          | Required behaviour                                                                                              |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| A declared file 404s / disappears | Recorded `missing` for that day; prior days untouched; other files still captured; the run does not crash       |
| A file is an HTML error page     | Caught by validation → `invalid`, parked in `_rejected/`, never stored as data                                  |
| A filename changes upstream      | Old name → `missing`; discovery (where implemented) flags the new name — together, a visible rename             |
| Schema drift (new column / field) | `schema_drift`; the raw file is still stored; flagged for review                                                |
| Upstream unreachable             | Recorded as an error; no day is fabricated; the next run resumes                                                |
| One source fails entirely        | Other sources still run; the matrix CI commits whatever did succeed                                             |
| A scheduled run is missed        | That day is an honest gap (the publisher has overwritten it); a manual run can still catch it the same day      |

And for anything consuming the archive: a missing file or day means
*"not observed"* — never *"nothing was listed."* Otherwise a capture outage
looks like a mass delisting.

---

## 6. Licensing

Not legal advice. Intended posture:

- The **code** is the project's own work and carries an MIT licence
  ([`LICENSE`](../LICENSE)).
- The **archived data** is *not* the project's work. Each source's
  `data/<source>/NOTICE.md` is the authoritative statement of provenance and
  terms for that source's subtree.
  Some sources (e.g. SEC EDGAR — public domain under 17 U.S.C. section 105)
  carry no restrictions; others (e.g. NASDAQ Trader — proprietary site
  terms) require careful reading before redistribution.
- Code and data must be kept cleanly separable, and per-source isolation
  must be preserved so any single source can be added or dropped without
  legal entanglement of the rest.

The top-level [`NOTICE-DATA.md`](../NOTICE-DATA.md) is an index of per-source
notices. Adding a new source requires a per-source NOTICE.md as part of the
PR — see [`docs/ADDING-A-SOURCE.md`](ADDING-A-SOURCE.md).

---

## 7. Governance and contributions

The project is BDFL-governed by @supermac. All PRs require BDFL review and
approval. The acceptance bar for new sources is documented in
[`docs/ADDING-A-SOURCE.md`](ADDING-A-SOURCE.md); the broader governance
model is in [`docs/GOVERNANCE.md`](GOVERNANCE.md).

Backfill is **forward-only**: each source begins archiving the day its PR
merges. No third-party backfill (e.g. from archive.org snapshots) is
attempted; provenance and licensing of mirror-of-a-mirror data raises
questions this project deliberately does not take on.

---

## 8. Currently integrated sources

### 8.1 NASDAQ Trader Symbol Directory — `data/nasdaq/`

Captured (overwritten daily by NASDAQ; we snapshot):

| File                                | What it carries                                                                              |
| ----------------------------------- | -------------------------------------------------------------------------------------------- |
| `nasdaqtraded.txt`                  | Superset universe; `Financial Status`, `Test Issue`, `Round Lot`, `Market Category`, ETF flag |
| `nasdaqlisted.txt`                  | NASDAQ-listed detail                                                                         |
| `otherlisted.txt`                   | NYSE / Arca / BATS / IEX-listed detail                                                       |
| `TradingSystemAddsDeletes.txt`      | Daily per-venue listing / delisting event feed                                               |
| `NasdaqWhenIssueWhenDistributed.txt` | When-issued / when-distributed state flags                                                  |
| `NasdaqListedRoundLotUpdates.txt`   | Monthly round-lot + average-closing-price series                                             |

Mirrored (already dated by NASDAQ; we delta-sync):

| Directory     | Range | What it carries                                       |
| ------------- | ----- | ----------------------------------------------------- |
| `regsho/`     | 2005→ | Reg SHO threshold (hard-to-borrow) securities         |
| `shorthalts/` | 2011→ | Short-sale circuit-breaker halts, with trigger times  |
| `regnms/`     | 2007→ | Reg NMS pilot membership lists                        |

Discovered (auto-staged for human curation): anything in SymDir/ that is
neither captured nor explicitly ignored.

Out of scope for this source: `regshopilot/` (3.7 GB tick-level data, not
directory data); options files; long-stale files (`bondslist.txt`,
`otclist.txt`, `pbot.csv`, `bxo_lmm.csv`); marginal files
(`bxtraded.txt`, `psxtraded.txt`, `mpidlist.txt` — deferred until concrete
need).

Daily steady-state size: ~2 MB raw / ~450 KB gzipped per day → ~165 MB/year
+ ~130 MB one-time regulatory backfill.

### 8.2 SEC EDGAR ticker mappings — `data/edgar/`

Captured (overwritten in place by SEC; we snapshot):

| File                              | What it carries                                                       |
| --------------------------------- | --------------------------------------------------------------------- |
| `company_tickers.json`            | Numeric-keyed map of every active CIK → `{cik_str, ticker, title}`. ~150 KB. |
| `company_tickers_exchange.json`   | Same data plus listing exchange, in column-array form. ~250 KB.        |

The rest of EDGAR (10-K, 10-Q, Form 4, 13F, the full filing archive) is NOT
in scope per section 3.4: the SEC archives all filings indefinitely.

SEC requires a contactable email in every fetcher's User-Agent. The framework
reads it from `TIMEMACHINE_CONTACT_EMAIL` env var. Snapshot fails loudly at
startup if the email is malformed.

Daily steady-state size: ~400 KB raw / ~80 KB gzipped per day → ~20 MB/year.

---

## 9. Open questions

- Confirm the exact scope of NASDAQ's "events data without restriction"
  carve-out before any public promotion.
- Whether to add the marginal NASDAQ files (`bxtraded`, `psxtraded`,
  `mpidlist`) to the captured set later, or keep deferring them.
- Whether daily capture for any source should run more than once a day
  (NASDAQ updates its files "periodically throughout the day," but one
  settled end-of-day snapshot is enough for a daily archive).
- Cboe Symbol Directory, NYSE Listed Issues, IEX Eligible Symbols, FINRA
  Short Interest, OCC Daily Volume, TRACE Bond Reference — all candidates
  in [`docs/POTENTIAL-SOURCES.md`](POTENTIAL-SOURCES.md), awaiting
  contributor PRs that pass the section 3.4 mission filter.
