# Adding a new source

This is the contributor playbook for adding a new data source to
`us-markets-timemachine`. Read it end-to-end before you write any code or
open an issue.

The project's mission is narrow on purpose: **archive vanishing US markets
data only**. The acceptance bar below is what protects that mission from
drifting. PRs that don't clear it will be closed with explanation, not
merged.

---

## Two ways to contribute a source

This document is the **implementer's playbook** — code + tests + manifest +
NOTICE. But you don't have to implement to contribute. A well-researched
proposal is itself a useful contribution:

- **Research-only PR** — add a tier entry to
  [`POTENTIAL-SOURCES.md`](POTENTIAL-SOURCES.md) with: upstream URL,
  retention evidence (institution's archive policy or proof none exists),
  expected daily size, file format, and a one-paragraph case for why the
  data is vanishing. No code, no fork-and-build. The mission filter in section 1
  still applies — research that fails it gets closed for the same reasons
  an implementation PR would.
- **Implementation PR** — the rest of this document. Either promotes an
  existing entry in `POTENTIAL-SOURCES.md` to "integrated" status, or
  proposes a fresh source (in which case section 1 doubles as both the research
  checklist and the build checklist).

A research PR isn't a bypass — it shifts work between contributors, not
down. The same bar applies. The contributor who lands the
`POTENTIAL-SOURCES.md` entry has already done the hardest part: proving
the source is in scope. The implementation PR after it is mostly mechanical.

---

## 1. The bar (acceptance criteria)

A proposed source MUST clear all of the following:

1. **US markets institution.** SEC, FINRA, NASDAQ, NYSE, Cboe, IEX, OCC,
   MSRB, CFTC, Fed, Treasury, NFA, etc. Not international markets. Not
   third-party data vendors.
2. **Publicly accessible without authentication.** No paid subscription, no
   API key, no captcha, no entitlements. Anyone with `curl` must be able to
   reach it.
3. **Truly vanishing.** The institution itself must NOT maintain a complete
   public history of prior versions. **You must demonstrate this in the
   issue / PR description** — link to the institution's archive policy or
   show that no such archive exists.
4. **Reasonable size.** ≤ 100 MB / year / source for the captured set. If
   the upstream is larger, propose a narrower selection that fits.
5. **Format stable enough to validate.** Plain text, CSV, TSV, JSON, or XML
   with a discoverable shape. Validators in `sources/<name>/validate.py`
   must be able to detect format drift (missing field, changed delimiter,
   shape change) without producing false positives every release.
6. **No PII / personal data.** Reference data only. If a file contains
   names of natural persons (e.g. SEC Form 4 insider transactions), the
   source is out of scope regardless of vanishing-ness.
7. **A working 7-day proof-of-life run.** Run the source against its real
   upstream from your own infra for 7 consecutive days before merging the
   PR. Attach the resulting manifest entries to the PR.

A proposed source MUST NOT be:

- Anything the publisher already archives (SEC EDGAR filings, Treasury
  auction history, FRED time series, CFTC swap data archive, CME daily
  settlements, etc.) — see [`POTENTIAL-SOURCES.md`](POTENTIAL-SOURCES.md)
  Tier C.
- A re-mirror of someone else's mirror (provenance and licensing of
  mirror-of-mirror data is its own problem we don't take on).
- A scraped pseudo-dataset assembled from HTML pages (use the publisher's
  own machine-readable file or wait for them to publish one).

If you're not sure whether a candidate fits, **open an issue first** before
writing any code. The BDFL (@supermac) will tag it `accepted` (proceed with
PR) or `out-of-scope` (close with explanation).

---

## 2. Step-by-step

Once an issue tagged `accepted` exists for your source:

### 2.1 Code

Create `src/timemachine/sources/<name>/` with at minimum:

- `__init__.py` — exports your `<Name>Source` class.
- `source.py` — the class itself, satisfying the `Source` protocol from
  `src/timemachine/sources/base.py`:

  ```python
  @dataclass(frozen=True)
  class FinraSource:
      name: str = "finra"
      display_name: str = "FINRA short-interest reports"

      def should_run(self, today: date) -> bool:
          # FINRA short interest is bi-monthly; True only on settlement Tuesdays.
          ...

      def snapshot(self, *, data_root, today, dry_run=False):
          # Fetch + validate + write; return Iterable[FileEntry].
          ...
  ```

- `config.py` — declared file specs (URLs, validators, size floors).
- `validate.py` (if your source has non-trivial validation rules) — return
  a per-source `ValidationResult` with `status`, `reason`, `row_count`.

Keep your code under your subdirectory. Do not edit any other source's
files. If you find yourself wanting to modify shared code in
`src/timemachine/{http,io,paths,manifest,notify}.py`, that's a separate
issue with separate review.

### 2.2 Storage

Add `data/<name>/NOTICE.md` stating:

- What upstream files you mirror (with URLs).
- The publisher's terms — link to their site terms / data policy.
- Whether the data is public domain (e.g. US government work under
  17 U.S.C. section 105) or under proprietary terms.
- Why the data is *vanishing* (one paragraph, evidence-based).

This NOTICE is the authoritative legal statement for `data/<name>/`. Get it
right.

Add a one-line entry to the top-level [`NOTICE-DATA.md`](../NOTICE-DATA.md)
table pointing at your NOTICE.

### 2.3 Tests

Create `tests/sources/<name>/` with:

- `__init__.py` (empty — pytest needs the package marker so basenames don't
  collide with other sources' tests).
- `test_source.py` — at minimum one happy-path test, one HTML-error test,
  one truncated/garbage test, one fetch-error test.
- `test_validate.py` (if you have a validator module) — direct tests for
  each validation rule.
- `fixtures/` — small (KB-sized) representative samples of valid,
  HTML-error, truncated, missing-field, and schema-drift content.

All tests must be **network-free**: inject a `fetcher` callable. The
EDGAR source is a good template.

### 2.4 Registration

Open `src/timemachine/sources/__init__.py` and add two lines:

```python
from timemachine.sources.finra import FinraSource

REGISTRY: dict[str, Source] = {
    NasdaqSource.name: NasdaqSource(),
    EdgarSource.name: EdgarSource(),
    FinraSource.name: FinraSource(),  # <— new
}
```

This is the single point where adding a source becomes a shipped feature.
Greppable, no magic.

### 2.5 CI

Add your source's name to the matrix in
`.github/workflows/daily.yml`:

```yaml
matrix:
  source: [nasdaq, edgar, finra]   # <— add your name
```

Confirm the workflow's per-source artifact / commit logic still produces
the layout you expect.

### 2.6 Documentation

- Update [`POTENTIAL-SOURCES.md`](POTENTIAL-SOURCES.md): move your source
  from Tier A "candidate" to Tier A "integrated" with a link to the PR.
- Update [`docs/SPEC.md`](SPEC.md) section 8 with a one-paragraph case study of
  your source (file list, why it's vanishing, daily size).
- Update the "Currently integrated sources" table in
  [`README.md`](../README.md).

### 2.7 Proof of life

Run your source against the real upstream for 7 consecutive days from your
own infrastructure before submitting the PR for review. Attach to the PR:

- The 7 manifest entries (or a summary jq output).
- The total bytes captured.
- Any anomalies you noticed (validation failures, schema drifts, etc.).

This is the most important step. It catches problems no test fixture can:
intermittent upstream issues, real schema variability, real size, real
cadence quirks.

---

## 3. Things that will get your PR closed

Common reasons:

- **Off-mission.** Source is one the publisher already archives.
- **Out-of-spec scope expansion.** Your PR also refactors core modules
  beyond what's needed for the source. Split it.
- **Plugin-system changes.** The Source protocol is intentionally minimal.
  If you want to add a method to the protocol, open a separate issue
  arguing for it; don't smuggle it through a source PR.
- **Missing NOTICE.md.** Non-negotiable.
- **Tests hit the network.** Refactor with an injected fetcher.
- **Backfill from third-party mirrors.** Forward-only; this project does
  not absorb other archives' data, only direct publisher data going forward.
- **Adds a runtime dependency.** Goal is stdlib-only (or near it). If you
  truly need a dep, open an issue arguing for it before the PR.

---

## 4. Help

If anything in this document is unclear, open an issue tagged `question`
before doing the work. A 10-minute clarifying issue costs everyone less
than a 2-week PR that has to be rewritten.
