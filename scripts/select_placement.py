#!/usr/bin/env python3
"""Thin source-checkout entrypoint; see references/experimental-selection.md."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev_integration_evaluator.selection import main

if __name__ == '__main__':
    raise SystemExit(main())
