#!/usr/bin/env python3
"""Build a history-free release from an explicit source allowlist. No publish."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import tomllib
VERSION = tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
TOP_FILES = {'README.md','SKILL.md','LICENSE','MANIFEST.in','pyproject.toml','.gitignore','CONTRIBUTING.md','SECURITY.md','CHANGELOG.md'}
TOP_DIRS = {'src','docs','skills','requirements','tests','fixtures','examples','scripts','.github'}
EXCLUDED = {'.git','__pycache__','.pytest_cache','.cache','.venv','node_modules','build','dist'}


def source_paths(root=ROOT):
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if not path.is_file() or any(p in EXCLUDED or p.endswith('.egg-info') for p in rel.parts):
            continue
        if rel.parts[0] not in TOP_DIRS and str(rel) not in TOP_FILES:
            continue
        if path.suffix in {'.pyc','.pyo','.tmp'} or path.name == '.DS_Store':
            continue
        if path.is_symlink():
            raise ValueError('Release sources must be regular files: ' + str(rel))
        yield path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive(folder, output, prefix=''):
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():
                info = zipfile.ZipInfo(prefix + p.relative_to(folder).as_posix(), date_time=(2026,11,23,0,0,0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                z.writestr(info, p.read_bytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('Release target must be empty')
    out.mkdir(parents=True, exist_ok=True)
    source = out / 'career-os'
    source.mkdir()
    for p in source_paths():
        target = source / p.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
    files = {p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*')) if p.is_file()}
    fingerprint = hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    environment = dict(os.environ)
    environment['SOURCE_DATE_EPOCH'] = '1795392000'
    subprocess.run([sys.executable,'-m','pip','wheel','--no-deps','--no-build-isolation','--disable-pip-version-check','--wheel-dir',str(out),str(source)],check=True, env=environment)
    # pip writes build metadata into the isolated source. Archive only approved input files.
    archive_root = out / 'archive-source'
    for rel in files:
        target = archive_root / rel
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source / rel,target)
    archive(archive_root,out/f'career-os-{VERSION}-source.zip','career-os/')
    archive(source/'skills/career-os',out/f'career-os-{VERSION}-skill.zip','career-os/')
    manifest = {'version':VERSION,'source_fingerprint':fingerprint,'source_files':files,'history_included':False,'artifacts':{p.name:digest(p) for p in out.iterdir() if p.is_file()}}
    (out/'release-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'BUILT','source_fingerprint':fingerprint,'source_files':len(files),'artifacts':manifest['artifacts']},indent=2))

if __name__=='__main__':
    main()
