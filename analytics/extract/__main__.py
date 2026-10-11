"""
Module entry point allowing execution via:
    python -m analytics.extract
"""

import sys

from analytics.extract.cli import main

if __name__ == "__main__":
    sys.exit(main())
