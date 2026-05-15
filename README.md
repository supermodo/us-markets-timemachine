# US Markets TimeMachine

_A time machine for vanishing US markets data — point-in-time snapshots of
files US institutions publish without keeping a public history._

[![daily](https://github.com/supermodo/us-markets-timemachine/actions/workflows/daily.yml/badge.svg)](https://github.com/supermodo/us-markets-timemachine/actions/workflows/daily.yml)
[![ci](https://github.com/supermodo/us-markets-timemachine/actions/workflows/ci.yml/badge.svg)](https://github.com/supermodo/us-markets-timemachine/actions/workflows/ci.yml)

## Why this exists

Every day, US markets institutions — NASDAQ, the SEC, FINRA, the CFTC and
others — publish reference data about today's market and write the new day
directly over the old one. The files don't wait. Miss a day and that day is
simply gone: no archive, no "previous version," no way back to it.

NASDAQ overwrites the symbol directory in place daily. The SEC overwrites
`company_tickers.json` in place daily. Neither institution keeps a public
history of yesterday's version. A study that needs to ask _"what was Apple's
ticker in 2024?"_ or _"which CIKs were marked financially deficient on
2025-08-01?"_ has no answer unless someone was capturing every day.

So this is a time machine. Every night it wakes up, copies the in-scope files
exactly as their publishers published them, stamps each one with its date,
and keeps it. Forever. Nothing is overwritten. Nothing is deleted.

## Currently integrated sources

| Source                                                                       | Why it's vanishing                                                          |
| ---------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| **NASDAQ Trader Symbol Directory** ([`data/nasdaq/`](data/nasdaq/NOTICE.md)) | NASDAQ overwrites the symbol-directory files daily; no public history kept. |
| **SEC EDGAR ticker mappings** ([`data/edgar/`](data/edgar/NOTICE.md))        | SEC overwrites `company_tickers.json` in place; no public history kept.     |

A non-binding wish list of additional candidate sources lives in
[`docs/POTENTIAL-SOURCES.md`](docs/POTENTIAL-SOURCES.md). Contributions are
welcome — see [`docs/ADDING-A-SOURCE.md`](docs/ADDING-A-SOURCE.md) for the
acceptance bar and step-by-step.

## What it does

For every registered source:

- **Daily snapshot** — captures the publisher's files exactly as they appear
  today, stores under `data/<source>/<file>/<YYYY>/<YYYY-MM-DD>.gz`.
- **Per-source mirror** (where applicable) — for sources that publish their
  own dated archives (NASDAQ's `regsho/`, `shorthalts/`, `regnms/`),
  delta-syncs only what isn't already held.
- **Validates before it stores** — a fetched file that turns out to be an
  HTML error page, or is truncated, or has lost its header / shape, is
  parked as evidence under `data/<source>/_rejected/`, never saved as if it
  were real data.
- **Notices change** — a file that vanishes upstream is recorded as missing;
  a file that _appears_ upstream and isn't known yet is flagged. Together
  that's how a silent rename gets caught.
- **Leaves a heartbeat** — every run writes a per-source `manifest-<kind>.json`
  so anything reading the archive can tell, at a glance, whether it's fresh
  and whole.

## What it produces

A growing, permanent archive: one dated, gzipped snapshot per file per day,
per source, stored under `data/<source>/<file>/<YYYY>/<YYYY-MM-DD>` (and
the original dated filenames for any per-source mirror archives). Nothing is
ever overwritten or deleted. Each run also writes a per-source
`manifest-<kind>.json` heartbeat. The full output spec — every captured file,
the storage form, the manifest, the resilience guarantees — is in
[`docs/SPEC.md`](docs/SPEC.md).

## Resilience, in one line

Never delete, never overwrite a good day, never store bytes that haven't
been validated — and never let _"we didn't look"_ be mistaken for _"nothing
was there."_

## Running it

The worker is a small Python package with **zero runtime dependencies** (the
stdlib does it all). It runs autonomously on GitHub Actions cron and can also
be run locally for development.

### How autonomous mode works

The `.github/workflows/daily.yml` workflow fires every day at **00:00 UTC**.
A matrix job runs every registered source in parallel; a final commit job
downloads each source's data artifact and produces a single daily commit.

Per-source failures are isolated: if EDGAR has a transient error, NASDAQ's
data still gets committed.

#### Required and optional secrets

| Secret                                   | Purpose                                                                                              |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `GITHUB_TOKEN` (auto-provisioned)        | Commit data + manifests back to `main`; open issues for anomalies.                                   |
| `TIMEMACHINE_CONTACT_EMAIL`              | Required for SEC EDGAR fetches (SEC's published policy). Set it to your operator email.              |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Optional. Push a message to a Telegram chat **only on failure or anomaly**. Success runs are silent. |

The worker also opens a labeled GitHub issue per distinct anomaly (deduped
by title; same anomaly recurring → comment thread, not new issue).

#### First-time label bootstrap

The issue-opening step uses three labels per issue (`worker-anomaly`,
`status:<x>`, `kind:<y>`). `gh issue create` rejects unknown labels and the
worker fail-softs on the failure — so on a fresh repo / fork, anomalies
arrive on Telegram but no GitHub issue ever appears. Run the bootstrap once
to create the labels (idempotent):

    scripts/bootstrap-labels.sh                # uses gh's default repo
    scripts/bootstrap-labels.sh OWNER/REPO     # explicit

After this, future anomalies open + comment on issues as the spec describes.

### Running locally

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .[dev]

    # set your contact email for SEC's policy
    export TIMEMACHINE_CONTACT_EMAIL=you@example.com

    # full daily run (every registered source)
    us-markets-timemachine daily --output-dir data

    # smoke test: only EDGAR, no writes, no notifications
    us-markets-timemachine daily --only edgar --dry-run --no-notify --output-dir /tmp/tm

    # surgical: rerun NASDAQ only after a transient failure
    us-markets-timemachine daily --only nasdaq

    # see what's registered and what each source thinks of today
    us-markets-timemachine list-sources

    # tests + lint
    pytest -q
    ruff check .

### What lives where

    src/timemachine/
        cli.py                    — multi-source CLI (entry point)
        http.py, io.py, dates.py  — generic plumbing
        manifest.py, paths.py     — generic, source-namespaced
        notify.py                 — Telegram + GitHub-issue fan-out
        sources/
            base.py               — the Source protocol every source must satisfy
            __init__.py           — REGISTRY: explicit import per source
            nasdaq/               — NASDAQ Trader source
            edgar/                — SEC EDGAR source

    data/
        nasdaq/  NOTICE.md  manifest-*.json  <captured / mirrored / rejected files>
        edgar/   NOTICE.md  manifest-*.json  <captured / rejected files>

    docs/
        SPEC.md                   — what the project produces and why
        ADDING-A-SOURCE.md        — contributor playbook + acceptance bar
        POTENTIAL-SOURCES.md      — wish list of candidate sources, tiered
        GOVERNANCE.md             — BDFL model, what gets merged

    NOTICE-DATA.md                — top-level index of per-source NOTICE.md files
    CONTRIBUTING.md               — dev setup, PR process

## Contributing

Contributions are warmly welcomed. The mission is deliberately narrow —
only data that US institutions publish without keeping public history —
so a short discussion before writing code saves both sides time.

By intent:

- **Suggesting a source without writing code.** Open a PR adding an entry
  to [`docs/POTENTIAL-SOURCES.md`](docs/POTENTIAL-SOURCES.md) with the
  research: upstream URL, retention evidence, expected daily size, format,
  and a one-paragraph case for why the data is vanishing. The mission
  filter still applies; the implementation can come later — from you or
  someone else.
- **Implementing a new source.** [`docs/ADDING-A-SOURCE.md`](docs/ADDING-A-SOURCE.md)
  — acceptance bar + step-by-step playbook. Open an issue first.
- **Already-considered candidates.** [`docs/POTENTIAL-SOURCES.md`](docs/POTENTIAL-SOURCES.md)
  — tiered list (integrated, candidate, borderline, out-of-scope).
- **Dev setup, PR process, conventions.** [`CONTRIBUTING.md`](CONTRIBUTING.md).
- **Governance and what gets merged.** [`docs/GOVERNANCE.md`](docs/GOVERNANCE.md).

Bug reports with concrete reproductions and documentation typo fixes
are always welcome without preamble.

## Licensing

The code carries an MIT licence ([`LICENSE`](LICENSE)). The data under each
`data/<source>/` is verbatim from its upstream publisher — each subdirectory
carries its own NOTICE.md stating provenance and applicable terms. See
[`NOTICE-DATA.md`](NOTICE-DATA.md) for the index.

## Specification

[`docs/SPEC.md`](docs/SPEC.md) — what the project is for, what it must
produce, and how it must behave. The runtime, language, and build are
intentionally left open; the Python implementation here is one such
instantiation.
