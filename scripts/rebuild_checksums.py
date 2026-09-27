"""Validate this package and explicitly rebuild its exact release-file checksum manifest."""
from pathlib import Path
import argparse
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from jev_integration_evaluator.io import InputError,atomic_text,file_hash
from validate_package import validate


def included(path):
    parts=path.relative_to(ROOT).parts
    return (path.is_file() and path.name!='SHA256SUMS' and path.suffix not in ('.pyc','.pyo','.zip','.whl')
            and not any(x in ('node_modules','.venv','.git','__pycache__','.pytest_cache','build','dist')
                        or x.endswith('.egg-info') for x in parts))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true',required=True)
    parser.parse_args()
    try:
        validate()
        files=sorted((p for p in ROOT.rglob('*') if included(p)),key=lambda p:p.relative_to(ROOT).as_posix())
        if any(any(c in p.relative_to(ROOT).as_posix() for c in ('\n','\r','\\')) for p in files):
            raise InputError('Manifest paths must have unambiguous portable line encoding')
        atomic_text(ROOT/'SHA256SUMS',''.join(file_hash(p)+'  '+p.relative_to(ROOT).as_posix()+'\n' for p in files))
        print('Validated and hashed '+str(len(files))+' release files.')
        return 0
    except Exception as exc:
        print('Checksum rebuild failed: '+str(exc),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
