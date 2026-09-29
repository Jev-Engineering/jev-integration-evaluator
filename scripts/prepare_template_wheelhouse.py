"""Explicitly acquire a pinned offline test wheelhouse outside the checkout."""
from __future__ import annotations

import argparse
import importlib.metadata
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='New private external wheelhouse directory')
    args = parser.parse_args()
    out = Path(args.out).absolute()
    if out.exists() or out == ROOT or out.is_relative_to(ROOT):
        parser.error('Output must be a new directory outside the checkout')
    out.mkdir(mode=0o700, parents=False)
    tools = {name: importlib.metadata.version(name) for name in ('pip', 'setuptools', 'wheel')}
    commands = [
        [sys.executable, '-m', 'pip', 'wheel', '--wheel-dir', str(out), str(ROOT)],
        [sys.executable, '-m', 'pip', 'download', '--only-binary=:all:', '--dest', str(out),
         *(f'{name}=={version}' for name, version in tools.items())],
    ]
    for command in commands:
        subprocess.run(command, cwd=out, check=True)
    print(out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
