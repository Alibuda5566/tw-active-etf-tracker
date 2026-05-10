"""Compatibility entrypoint for a full data update.

The original project mentioned a Selenium-based fallback here.  This rebuilt
version keeps the command available and runs the REST-based holdings update.
"""

from __future__ import annotations

import sys
import os

import fetch_finmind


def main() -> None:
    if "--holdings" not in sys.argv:
        sys.argv.append("--holdings")
    token = os.environ.get("FINMIND_TOKEN", "").strip()
    if token and "--token" not in sys.argv:
        sys.argv.extend(["--token", token])
    fetch_finmind.main()


if __name__ == "__main__":
    main()
