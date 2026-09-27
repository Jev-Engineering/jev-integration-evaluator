"""Thin entrypoint for read-only repository discovery and semantic review."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev_integration_evaluator.repository_discovery import main

if __name__ == "__main__":
    raise SystemExit(main())
