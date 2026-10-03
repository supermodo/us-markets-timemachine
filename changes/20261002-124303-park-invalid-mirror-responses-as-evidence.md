---
bump: patch
section: Fixed
scope: ["src/timemachine/sources/nasdaq/mirror.py", "tests/sources/nasdaq/test_mirror.py"]
---

Mirrored NASDAQ archive files (regsho, shorthalts, regnms) that fail validation are now kept as evidence under `data/nasdaq/_rejected/<YYYY>/<run-date>/<archive>/`, matching how captured files already behave. The real archive path stays empty, so the next run still retries the file.
