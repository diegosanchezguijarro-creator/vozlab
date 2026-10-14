#!/usr/bin/env python3
"""Dev entry point: run Scribe from a source checkout (python run_vozlab.py)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vozlab import DISPLAY_NAME, VERSION  # noqa: E402

if "--version" in sys.argv:
    print(f"{DISPLAY_NAME} {VERSION}")
    sys.exit(0)

from vozlab.app import main  # noqa: E402

if __name__ == "__main__":
    main()
