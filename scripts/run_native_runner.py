"""Thin wrapper for the opt-in standalone runner; no implicit installation."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jev_integration_evaluator.runners.isolated_python import main
if __name__=='__main__':raise SystemExit(main())
