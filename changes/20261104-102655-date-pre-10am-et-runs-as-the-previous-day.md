---
bump: patch
section: Fixed
scope: [".github/workflows/daily.yml", "README.md", "docs/SPEC.md", "src/timemachine/cli.py", "src/timemachine/dates.py", "src/timemachine/sources/nasdaq/capture.py", "src/timemachine/sources/nasdaq/discovery.py", "src/timemachine/sources/nasdaq/mirror.py", "src/timemachine/sources/nasdaq/source.py", "tests/test_cli.py", "tests/test_dates.py"]
---

Daily snapshots from a run before 10:00 ET are now filed under the previous day. A scheduled run that starts after midnight ET no longer takes the next day's date and costs that evening's snapshot, and a morning rerun no longer blocks the coming night's capture. Files already stored under the wrong date stay as they are and are listed in `docs/SPEC.md`.
