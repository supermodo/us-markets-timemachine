# `data/edgar/` — provenance and terms

The files under `data/edgar/` are verbatim, gzipped copies of files published
by the U.S. Securities and Exchange Commission at <https://www.sec.gov/> —
specifically:

- `company_tickers.json` — <https://www.sec.gov/files/company_tickers.json>
- `company_tickers_exchange.json` — <https://www.sec.gov/files/company_tickers_exchange.json>

These two files map every active SEC-registered ticker to its CIK (Central
Index Key) and, for the exchange variant, to its listing exchange. The SEC
overwrites them in place; no public history of prior versions is maintained
by the SEC itself.

## Public domain (US government work)

Works of the United States Government — including these SEC-published data
files — are not subject to copyright protection in the United States under
[17 U.S.C. § 105](https://www.copyright.gov/title17/92chap1.html#105). They
are in the public domain and may be redistributed without permission.

The MIT licence in [`LICENSE`](../../LICENSE) covers only the *code* in this
repository. No additional grant is needed for the data here — but please cite
the SEC as the source if you build something on top of it.

## SEC access policy

The SEC asks every automated fetcher to identify itself with a real contact
email in the User-Agent header
([SEC EDGAR Fair Access policy](https://www.sec.gov/about/webmaster-faq#code-support)).
This project complies via the `TIMEMACHINE_CONTACT_EMAIL` environment variable
(see `docs/ADDING-A-SOURCE.md`). If you fork or redeploy this archive, set the
variable to your own contact email so the SEC can reach the actual operator.

## Why this archive exists

The two files are the only public, machine-readable mapping between SEC CIKs
and their current ticker symbols. When a company delists or its ticker is
reassigned, the SEC quietly removes or rewrites the row in place — there is
no public archive of yesterday's mapping. A study that needs *"what ticker did
this CIK trade under on 2024-08-01?"* has no other reliable answer than a
dated snapshot. This project keeps one snapshot per weekday, forever.
