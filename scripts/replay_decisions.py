"""Compatibility entry point for the replay command; use --help for its options."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jev_integration_evaluator.cli import main

if __name__=="__main__":
    raise SystemExit(main(["replay",*sys.argv[1:]]))
