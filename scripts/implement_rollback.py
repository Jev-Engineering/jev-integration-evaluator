"""Thin entry point for jev-integration-evaluator implement-rollback."""
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from jev_integration_evaluator.cli import main
    raise SystemExit(main(['implement-rollback', *sys.argv[1:]]))
