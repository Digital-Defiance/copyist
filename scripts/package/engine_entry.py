"""PyInstaller entry for the desktop engine sidecar.

Must use absolute imports: freezing copyist/__main__.py makes it a top-level
script named __main__, so `from .cli import main` fails with
"attempted relative import with no known parent package".
"""
from __future__ import annotations

import sys

from copyist.cli import main

if __name__ == "__main__":
    sys.exit(main())
