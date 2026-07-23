"""`python -m edp.run` entry point -- delegates to the CLI."""

from __future__ import annotations

import sys

from edp.cli import main

if __name__ == "__main__":
    sys.exit(main())
