"""Build a reproducible ZIP/checksum from this local skill directory; no publication."""
from pathlib import Path
import argparse,hashlib,os,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
SKIP={'__pycache__','.pytest_cache','.venv','.git','node_modules','build','dist'}

def include(path):
    parts=path.relative_to(ROOT).parts
    return path.is_file() and not path.is_symlink() and not any(p in SKIP or p.endswith('.egg-info') for p in parts) and path.suffix not in ('.pyc','.pyo','.zip','.whl')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True);args=parser.parse_args()
    output=Path(args.out).resolve()
    if output.is_relative_to(ROOT):raise SystemExit('Use an output ZIP outside the source package')
    files=sorted((p for p in ROOT.rglob('*') if include(p) and p.name!='SHA256SUMS'),
                 key=lambda p:p.relative_to(ROOT).as_posix())
    manifest=''.join(sha(p)+'  '+p.relative_to(ROOT).as_posix()+'\n' for p in files)
    (ROOT/'SHA256SUMS').write_text(manifest)
    files.append(ROOT/'SHA256SUMS');files.sort(key=lambda p:p.relative_to(ROOT).as_posix())
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in files:
            relative=ROOT.name+'/'+path.relative_to(ROOT).as_posix()
            info=zipfile.ZipInfo(relative,date_time=(2026,9,26,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            archive.writestr(info,path.read_bytes())
    check=output.with_suffix(output.suffix+'.sha256')
    check.write_text(sha(output)+'  '+output.name+'\n')
    print(str(output));print('Files: '+str(len(files)));print('SHA-256: '+sha(output))

if __name__=='__main__':main()
