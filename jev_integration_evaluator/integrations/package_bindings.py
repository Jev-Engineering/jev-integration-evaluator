"""Versioned, non-executing resolution of a bounded Python package binding graph.

Only explicit absolute or relative ``from x import y`` re-exports are followed.
The caller must supply the package root and namespace policy; discovery does not
guess whether an absent ``__init__.py`` denotes a namespace package.
"""
from __future__ import annotations

import ast
import keyword
import re
from pathlib import Path

from ..io import InputError, file_hash, safe_child
from .errors import MissingBinding, UnsupportedShape

CONTRACT_VERSION = '1.0'
_IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z_0-9]*\Z')


def module_layout(root: Path, source: str, *, namespace: bool = False) -> tuple[str, str, list[str]]:
    """Return import root, dotted module and package initializers for one source."""
    rel = Path(source)
    parts = rel.parts
    if not parts or any(not _IDENTIFIER.fullmatch(p) or keyword.iskeyword(p)
                        for p in (*parts[:-1], rel.stem)) or rel.suffix != '.py':
        raise UnsupportedShape('Unsupported Python module path')
    prefix = 'src' if parts[0] == 'src' else ''
    module_parts = parts[1:] if prefix else parts
    if not module_parts or module_parts == ('__init__.py',):
        raise UnsupportedShape('A package initializer cannot be the selected host module')
    if module_parts[-1] == '__init__.py':
        raise UnsupportedShape('A package initializer cannot be the selected host module')
    package_parts = module_parts[:-1]
    initializers = []
    for depth in range(1, len(package_parts) + 1):
        init = Path(prefix, *package_parts[:depth], '__init__.py') if prefix else Path(*package_parts[:depth], '__init__.py')
        path = safe_child(root, init.as_posix())
        if path.is_file(): initializers.append(init.as_posix())
        elif not namespace:
            raise UnsupportedShape('Missing regular package initializer: ' + init.as_posix())
    return prefix, '.'.join((*package_parts, rel.stem)), initializers


class StaticBindings:
    def __init__(self, root: Path, source: str, *, namespace: bool = False):
        self.root = Path(root)
        self.import_root, self.module, initializers = module_layout(self.root, source, namespace=namespace)
        self.namespace = namespace
        self.dependencies: dict[str, str] = {}
        for rel in initializers:
            tree = self._read(rel)
            for node in tree.body:
                if isinstance(node, (ast.ImportFrom, ast.Pass)): continue
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    continue
                raise UnsupportedShape('Dynamic package initializer requires separate review: ' + rel)

    def _rel(self, module: str) -> str:
        parts = module.split('.')
        if any(not _IDENTIFIER.fullmatch(p) or keyword.iskeyword(p) for p in parts):
            raise UnsupportedShape('Invalid static import target')
        stem = '/'.join(filter(None, (self.import_root, *parts)))
        source = stem + '.py'
        initializer = stem + '/__init__.py'
        if safe_child(self.root, source).is_file(): return source
        if safe_child(self.root, initializer).is_file(): return initializer
        return source

    def _read(self, rel: str) -> ast.Module:
        p = safe_child(self.root, rel)
        if not p.is_file(): raise MissingBinding('Missing static binding module: ' + rel)
        raw = p.read_bytes()
        if len(raw) > 2_000_000 or raw.startswith(b'\xef\xbb\xbf'):
            raise UnsupportedShape('Unsupported static binding module encoding or size: ' + rel)
        try: tree = ast.parse(raw.decode('utf-8'), filename=rel)
        except (SyntaxError, UnicodeError): raise UnsupportedShape('Invalid UTF-8 Python binding module: ' + rel) from None
        self.dependencies[rel] = file_hash(p)
        return tree

    def resolve(self, name: str) -> tuple[str, str, ast.FunctionDef]:
        """Resolve an exported top-level function; cycles and ambiguous stores fail."""
        return self._resolve(self.module, name, ())

    def _resolve(self, module: str, name: str, visiting: tuple[tuple[str, str], ...]):
        key = (module, name)
        if key in visiting: raise UnsupportedShape('Cyclic static binding: ' + module + ':' + name)
        rel = self._rel(module)
        tree = self._read(rel)
        # Count all module-scope writes, including conditional rebinding. Function
        # bodies do not change the module namespace during import.
        from .recipes import _module_bindings
        nodes = _module_bindings(tree).get(name, [])
        if len(nodes) != 1: raise MissingBinding('Missing or ambiguous static binding: ' + module + ':' + name)
        node = nodes[0]
        if isinstance(node, ast.FunctionDef) and node in tree.body:
            if node.decorator_list:
                raise UnsupportedShape('Decorated static binding: ' + module + ':' + name)
            return rel, name, node
        if not isinstance(node, ast.ImportFrom) or node not in tree.body:
            raise UnsupportedShape('Dynamic or shadowed static binding: ' + module + ':' + name)
        aliases = [a for a in node.names if (a.asname or a.name) == name]
        if len(aliases) != 1 or node.module is None and node.level == 0:
            raise UnsupportedShape('Ambiguous static import: ' + module + ':' + name)
        if node.level:
            package = module.split('.')[:-1]
            if node.level > len(package):
                raise UnsupportedShape('Relative import escapes declared package: ' + module)
            target = package[:len(package) - node.level + 1]
            if node.module: target.extend(node.module.split('.'))
            imported_module = '.'.join(target)
        else:
            imported_module = node.module
        if not imported_module or imported_module.split('.')[0] != self.module.split('.')[0]:
            raise UnsupportedShape('Static binding crosses declared package boundary: ' + module + ':' + name)
        return self._resolve(imported_module, aliases[0].name, (*visiting, key))
