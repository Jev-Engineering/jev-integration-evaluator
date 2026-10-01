"""Separately pinned source review for the retained Alpha 1.0.3 generation."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from jev_integration_evaluator.io import InputError, file_hash


ROOT = Path(__file__).resolve().parent
PINNED = {
    'pyproject.toml': 'f7f4ca92cd76f67862d1fd2e476114f28dc8da6d7db8ce68a904ff96fed706d9',
    'src/registered_alpha/__init__.py': 'ee3d08a82f10edefbf1cc563dbffecf18772db62fbd82d4bee5ad8a9425c371a',
    'src/registered_alpha/connected_authority.py': '7168e7a2b627301501f768272cb243c080c8bbd5fa50ba218c96d652238b7532',
    'src/registered_alpha/console.py': '19f152bfa720de7ab3baa9c6db24c000f9058904bec741a3a5f19fc8dd08f7c7',
    'src/registered_alpha/host.py': '097d23c5ce68b53c59038fb8ac195744d8ab9adafa2bdf1ce1939ed91a67d4e5',
    'src/registered_alpha/requirements.lock': '21ac598980a951f6b4e0f098bc1756ccfffbbe7e8c12d36a228c8381ca0c013b',
    'src/registered_alpha/runtime.json': '0c1f169e847504851b588cac189b805f24b317288411ca9699b16cbf41ea0252',
}


def source_matched_request(root: Path = ROOT):
    if any(file_hash(root / name) != sha for name, sha in PINNED.items()):
        raise InputError('connected_alpha_103_source_review_changed')
    original = Path(__file__).resolve().parents[1] / 'registered_alpha/qualification.py'
    spec = importlib.util.spec_from_file_location('registered_alpha_103_base_review', original)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.source_matched_request(root)
