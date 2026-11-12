"""Entry point of the installed application: opens the desktop window (no terminal)."""

import multiprocessing
import sys

from owstudio.cli import main

if __name__ == "__main__":
    # Needed by frozen executables that start worker processes
    multiprocessing.freeze_support()
    sys.exit(main(sys.argv[1:] or ["desktop"]))
