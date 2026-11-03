---
bump: patch
section: Fixed
scope: ["src/timemachine/sources/nasdaq/ftp.py", "src/timemachine/sources/nasdaq/mirror.py", "src/timemachine/sources/nasdaq/discovery.py", "tests/sources/nasdaq/test_ftp.py"]
---

NASDAQ FTP directory listings now retry on transient errors such as timeouts, so one slow response no longer fails the daily run or opens an anomaly issue. Permanent FTP errors still fail immediately, and a listing that keeps failing is still recorded as `missing`.
