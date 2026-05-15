# `data/nasdaq/` — provenance and terms

The files under `data/nasdaq/` are **not** the project's own work. They are
verbatim, gzipped copies of files published by NASDAQ at
<https://www.nasdaqtrader.com/> — specifically:

- The **Symbol Directory** files at
  <https://www.nasdaqtrader.com/dynamic/SymDir/> — `nasdaqtraded.txt`,
  `nasdaqlisted.txt`, `otherlisted.txt`, `TradingSystemAddsDeletes.txt`,
  `NasdaqWhenIssueWhenDistributed.txt`, `NasdaqListedRoundLotUpdates.txt`.
- The **Regulation SHO threshold lists** under
  <https://www.nasdaqtrader.com/dynamic/SymDir/regsho/>.
- The **short-sale circuit-breaker halts** under
  <https://www.nasdaqtrader.com/dynamic/SymDir/shorthalts/>.
- The **Reg NMS pilot lists** under
  <https://www.nasdaqtrader.com/dynamic/SymDir/regnms/>.

NASDAQ publishes these files daily. They are reference data describing US
exchange listings, listing actions, and regulatory programs.

## NASDAQ's terms apply

NASDAQ's website terms apply to the contents of `data/nasdaq/`. Read them
before redistributing or building any product that depends on this archive:

- NASDAQ Trader site terms: <https://www.nasdaqtrader.com/Trader.aspx?id=SiteTerms>
- NASDAQ data terms (general): <https://www.nasdaq.com/about/terms-and-conditions>

The MIT licence in [`LICENSE`](../../LICENSE) covers only the *code* in this
repository — the Python package, the GitHub Actions workflows, the
specification, the tests. It does **not** grant any rights to the contents of
`data/nasdaq/`.

## Why this archive exists

NASDAQ overwrites several of these files in place every day and keeps no
history of prior versions. A snapshot captured today silently omits every
security that has since delisted, gone bankrupt, or been acquired. The only
way to ever answer *"what did the market look like on this exact historical
date?"* is for someone to have captured the files every day and never thrown a
day away. See [`docs/SPEC.md`](../../docs/SPEC.md) for the full rationale.

## If you operate this archive publicly

Before any public promotion, it is worth contacting NASDAQ subscriber services
to confirm the scope of NASDAQ's "events data without restriction" carve-out
for these specific reference files. The factual content carries thin copyright
protection at best, and prior-art repositories have mirrored some of these
files for years, but explicit written confirmation is cheap insurance.
