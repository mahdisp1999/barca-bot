"""The dependency rule: lower layers never import upper ones (or telegram)."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = {"settings", "services", "providers", "storage", "formatting",
           "bot_io", "commands", "jobs", "audit", "app"}
ALLOWED = {
    "settings": set(),
    "formatting": set(),
    "providers": {"settings"},
    "storage": {"settings"},
    "services": {"settings", "providers", "storage", "formatting"},
}


def _imports(path: Path) -> set:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def _files(layer: str):
    p = ROOT / layer
    return [ROOT / f"{layer}.py"] if not p.is_dir() else sorted(p.glob("*.py"))


def test_layers_respect_dependency_rule():
    for layer, allowed in ALLOWED.items():
        for f in _files(layer):
            bad = (_imports(f) & PROJECT) - allowed - {layer}
            assert not bad, f"{f.relative_to(ROOT)} imports {bad}"
            assert "telegram" not in _imports(f), f"{f.relative_to(ROOT)} imports telegram"
