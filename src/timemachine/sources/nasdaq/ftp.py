"""Anonymous FTP directory listing for NASDAQ's SymbolDirectory tree.

FTP is the only way to enumerate these directories: HTTPS LIST returns 403
from nasdaqtrader.com.
"""

import time
from ftplib import FTP, all_errors, error_perm

from timemachine.http import DEFAULT_BACKOFF_BASE, DEFAULT_MAX_RETRIES

FTP_HOST = "ftp.nasdaqtrader.com"
FTP_BASE_DIR = "/SymbolDirectory"


def list_directory(directory: str = FTP_BASE_DIR, *, timeout: float = 30.0) -> list[str]:
    """Return the non-blank raw LIST lines for `directory`.

    The server occasionally times out on one of a run's several listings, and a
    failed listing turns the whole run red and opens an issue, so transient
    errors get the same bounded retry as HTTPS fetches. Permanent replies
    (error_perm, e.g. 550) would only fail again and are raised at once.
    """
    for attempt in range(DEFAULT_MAX_RETRIES):
        # Fresh per attempt: an interrupted LIST leaves a partial directory.
        lines: list[str] = []
        try:
            with FTP(FTP_HOST, timeout=timeout) as conn:
                conn.login()  # anonymous
                conn.cwd(directory)
                conn.retrlines("LIST", lines.append)
            break
        except error_perm:
            raise
        except all_errors:
            if attempt + 1 == DEFAULT_MAX_RETRIES:
                raise
            time.sleep(DEFAULT_BACKOFF_BASE * (2**attempt))
    return [line for line in lines if line.strip()]
