# Notice — `data/` provenance and per-source terms

This repository archives "vanishing" reference data from multiple US markets
institutions. Each source's data lives under its own subdirectory and carries
its own legal posture; **the per-source `NOTICE.md` is the authoritative
statement of terms for that subdirectory.**

| Source                                | Data subdirectory   | Notice                                      |
| ------------------------------------- | ------------------- | ------------------------------------------- |
| NASDAQ Trader Symbol Directory        | `data/nasdaq/`      | [`data/nasdaq/NOTICE.md`](data/nasdaq/NOTICE.md) |
| SEC EDGAR ticker mappings             | `data/edgar/`       | [`data/edgar/NOTICE.md`](data/edgar/NOTICE.md)   |

The MIT licence in [`LICENSE`](LICENSE) covers only the *code* in this
repository — the Python package, the GitHub Actions workflows, the
specification, the tests. It does **not** grant any rights to the contents of
`data/`. Each per-source notice lists what does (and does not) apply to that
source's data.

## Adding a new source

If you are adding a new source under `src/timemachine/sources/<name>/`, you
**must** also add `data/<name>/NOTICE.md` stating:

1. What upstream files are being mirrored (with URLs).
2. The publisher's terms — link to their site terms / data licence.
3. Whether the data is public domain (e.g. US government work under
   17 U.S.C. § 105) or under proprietary terms.
4. Why the data is "vanishing" (which is the project's mission filter — see
   [`docs/POTENTIAL-SOURCES.md`](docs/POTENTIAL-SOURCES.md)).

See [`docs/ADDING-A-SOURCE.md`](docs/ADDING-A-SOURCE.md) for the full
contributor checklist.
