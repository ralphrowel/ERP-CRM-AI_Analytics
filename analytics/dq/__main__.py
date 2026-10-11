"""
Entrypoint for `python -m analytics.dq`.
"""

import sys

from analytics.dq.cli import main

if __name__ == "__main__":
    sys.exit(main())
