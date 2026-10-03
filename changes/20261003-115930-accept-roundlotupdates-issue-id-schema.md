---
bump: patch
section: Fixed
scope: ["src/timemachine/sources/nasdaq/config.py", "tests/sources/nasdaq/test_validate.py", "docs/SPEC.md", "data/nasdaq/NasdaqListedRoundLotUpdates/2026/2026-10-01.txt.gz", "data/nasdaq/NasdaqListedRoundLotUpdates/2026/2026-10-02.txt.gz"]
---

`NasdaqListedRoundLotUpdates.txt` is captured again after NASDAQ added an `issue_id` column on 2026-10-01; snapshots from that date on carry 5 columns instead of 4. The 2026-10-01 and 2026-10-02 snapshots, rejected while the format was unrecognized, are restored from their parked copies.
