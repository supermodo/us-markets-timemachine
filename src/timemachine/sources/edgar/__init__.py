"""SEC EDGAR ticker-mapping source.

Captures the two ticker-mapping files the SEC overwrites in place daily and
keeps no public history of:

    company_tickers.json           — { "0": {cik_str, ticker, title}, "1": {...}, ... }
    company_tickers_exchange.json  — { "fields": [...], "data": [[...], [...], ...] }

The rest of EDGAR (10-K, 10-Q, Form 4, 13F, the full filing archive) is NOT
in scope: SEC archives all filings indefinitely, so mirroring them would
duplicate the SEC's own archive instead of preserving vanishing data.

SEC mandates every request carry a User-Agent of the form
"YourName your.email@example.com"; without it, requests are silently blocked.
The framework reads the contact email from `TIMEMACHINE_CONTACT_EMAIL` env var
and fails loudly at snapshot time if missing.
"""

from timemachine.sources.edgar.source import EdgarSource

__all__ = ["EdgarSource"]
