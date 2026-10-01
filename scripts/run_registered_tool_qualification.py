"""Opt-in report: registered-tool template gates recomputed from a pytest JUnit XML file.

Runs no test, target code or network call. Exit 0 only means the report was
written; use --require-offline-complete to fail on any unpassed offline gate.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev_integration_evaluator.registered_tool_qualification import main

if __name__ == '__main__':
    raise SystemExit(main())
