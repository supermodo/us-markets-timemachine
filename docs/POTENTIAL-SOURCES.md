# Potential sources

A non-binding wish list to guide contributors toward mission-fit proposals.
Inclusion in this list is **not** a commitment that the source will be
integrated — it indicates that the source is *plausibly* in scope under the
mission filter (`docs/SPEC.md` §3.4) and worth a contributor PR following
[`ADDING-A-SOURCE.md`](ADDING-A-SOURCE.md).

Conversely, exclusion does not strictly forbid a source — it means we
haven't evaluated it yet. Open an issue if you have a candidate not listed
here.

URLs and accessibility were last verified **2026-05-15**. Publishers reshape
their download endpoints frequently — re-verify before opening a PR.

---

## Tier A — integrated or accepted candidates

These pass the mission filter (truly vanishing, US, public, small,
format-stable) on the most recent verification. Candidates need a contributor
PR clearing the bar in [`ADDING-A-SOURCE.md`](ADDING-A-SOURCE.md).

| Status        | Source                              | Verified URL / notes                                                                                                |
| ------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| ✅ integrated  | NASDAQ Trader Symbol Directory      | `data/nasdaq/` — daily HTTPS + FTP via `nasdaqtrader.com`; verified working.                                         |
| ✅ integrated  | SEC EDGAR `company_tickers{,_exchange}.json` | `data/edgar/` — `https://www.sec.gov/files/company_tickers{,_exchange}.json`; verified working with proper UA.       |
| 🟡 candidate   | NYSE CTA Symbol Files               | Open directory at `https://ftp.nyse.com/cta_symbol_files/` — files named `CTA.Symbol.File.YYYYMMDD.csv`, ~300 KB each, daily on trading days. Observed retention ~1 year (May 2025 → present at verification time); older files appear to vanish. **Candidate confirmed accessible.** |
| 🟡 candidate   | Cboe Listed Symbols                 | `https://www.cboe.com/us/equities/market_statistics/listed_symbols/?format=csv` — page reports last update timestamp, suggesting overwrite-in-place. **URL works; archival policy needs explicit confirmation in the PR.** |
| 🟡 needs research | IEX Eligible Symbols             | IEX equities exchange remains operational (IEX *Cloud* shut down Aug 2024 — different product). The page at `https://iextrading.com/trading/eligible-symbols/` exists but no obvious downloadable CSV URL was discoverable from the surface. **A PR proposing this source must first identify the actual machine-readable file URL.** |

A candidate moves to integrated when (1) someone opens an issue tagged
`accepted` and (2) the resulting PR clears the bar in `ADDING-A-SOURCE.md`,
including the 7-day proof-of-life run.

---

## Tier B — borderline (institutional history exists but partial / format-unstable / cadence-uncertain)

May fit the mission depending on closer investigation. Open an issue with
evidence (specifically: how far back does the publisher's own archive go,
and is older history truly inaccessible?) before starting work.

| Source                                | Concern                                                                             |
| ------------------------------------- | ----------------------------------------------------------------------------------- |
| FINRA Short Interest (bi-monthly)     | Distinct from "short sale volume" (which is in Tier C — FINRA archives back to 2018). The bi-monthly position-snapshot reports' retention policy needs verification before committing. |
| CFTC Commitments of Traders (weekly)  | CFTC archives, but old formats have been lost on past site redesigns. Worth investigating which historical periods are actually missing.               |
| MSRB EMMA municipal data              | Depends on free-tier access; some endpoints are subscription-walled.                                                                                |
| Fed H.15 daily rates                  | Fed maintains history, but format has shifted; old historical files may not match current schema.                                                   |

---

## Tier C — out of scope (institution maintains complete public history, OR fails another scope criterion)

These do NOT fit the mission. Mirroring them would either duplicate the
publisher's own archive, or violate the "publicly accessible without
authentication" rule. PRs proposing them will be closed.

| Source                                              | Why out of scope                                                                                                  |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **FINRA Daily Short Sale Volume**                   | FINRA archives back to 2018-08-01 at `https://cdn.finra.org/equity/regsho/daily/{prefix}shvol{YYYYMMDD}.txt` (six prefixes: CNMS, FNQC, FNSQ, FNYX, FNRA, FORF). Complete public history maintained by FINRA. |
| **OCC Daily Volume / Open Interest**                | `https://marketdata.theocc.com/daily-open-interest?reportDate=MM/DD/YYYY&action=download&format=csv` accepts arbitrary historical dates. Complete archive maintained by OCC. |
| **TRACE Corporate / Agency Debt files**             | Downloads at `https://download.finratraqs.org` require **NASDAQ Web Security Framework (NWSF) authentication**. Fails §3.4 criterion #2 (publicly accessible without authentication). |
| SEC EDGAR filings (10-K, 10-Q, Form 4, 13F)         | SEC archives every filing indefinitely.                                                                           |
| Treasury auction results                            | Treasury archives auction history.                                                                                |
| FRED time series (Fed economic data)                | Fed archives all historical observations.                                                                         |
| CME daily settlement files (when archived)          | CME publishes history.                                                                                            |
| CFTC swap data archive                              | CFTC archives.                                                                                                    |
| Any "scraped from HTML" pseudo-dataset              | Use the publisher's own machine-readable file, or wait for one.                                                   |
| Any non-US markets data                             | Project scope is explicitly US.                                                                                   |

---

## Mission filter, restated

A source is in scope only if **the institution itself does not maintain a
complete public history** of the relevant files. This is the load-bearing
criterion. Several historically attractive candidates (FINRA daily short-sale
volume, OCC daily open interest) fail this filter on close inspection: the
publisher already archives them, sometimes for many years.

If your candidate doesn't pass the filter, the project is not the right home
for the work — but `archive.org` or a domain-specific mirror project might be.

The filter exists to keep this archive's contents *unrecoverable elsewhere*.
Once a file lives somewhere stable and public besides this repo, this repo's
copy is just storage cost without unique value.
