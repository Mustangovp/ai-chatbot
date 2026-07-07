"""
REFACTOR-001 — Architecture invariants (dependency-layering guard).

These tests PROVE, by scanning the real import graph, the structural rules the
system depends on. They add NO behavior; they fail loudly if a future change
violates the layering:

    Brain  →  Enforcement  →  Human State  →  Adaptive Coach

  1. The Brain imports none of human_state / coaching / recommend  (Brain is independent).
  2. Human State imports nothing from brain                        (HSE never touches the Brain).
  3. Adaptive Coach imports no Brain organ                         (coach is downstream, read-only).
  4. Recommendation imports nothing from brain                     (recommend stays downstream).
  5. The cascade (the one Brain entrypoint) has a single non-test consumer: app.py.
  6. No import cycles among the four layers.
"""
import ast
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _module_imports(pkg_dir):
    """Top-level module names imported by every .py under pkg_dir (recursively)."""
    imports = set()
    for py in (_ROOT / pkg_dir).rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imports.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.split(".")[0])
    return imports


# ── 1 · Brain is independent ─────────────────────────────────────────────────
def test_brain_imports_no_downstream_layer():
    forbidden = {"human_state", "coaching", "recommend"}
    leaked = _module_imports("brain") & forbidden
    assert not leaked, f"Brain must not import downstream layers, found: {leaked}"


# ── 2 · Human State never touches the Brain ──────────────────────────────────
def test_human_state_imports_no_brain():
    assert "brain" not in _module_imports("human_state"), \
        "human_state must never import the Brain"


# ── 3 · Adaptive Coach imports no Brain organ ────────────────────────────────
def test_coaching_imports_no_brain():
    assert "brain" not in _module_imports("coaching"), \
        "coaching (Adaptive Coach) must not import the Brain — it is read-only downstream"


# ── 4 · Recommendation stays downstream ──────────────────────────────────────
def test_recommend_imports_no_brain():
    assert "brain" not in _module_imports("recommend"), \
        "recommend must not import the Brain"


# ── 5 · The cascade has exactly one non-test consumer (app.py) ───────────────
def test_cascade_has_single_non_test_consumer():
    consumers = set()
    for py in _ROOT.rglob("*.py"):
        rel = py.relative_to(_ROOT).as_posix()
        if rel.startswith("brain/") or rel.startswith("tests/") or "test_" in py.name:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            hit = (isinstance(node, ast.Import) and any(a.name == "brain.cascade" for a in node.names)) or \
                  (isinstance(node, ast.ImportFrom) and node.module == "brain" and
                   any(a.name == "cascade" for a in node.names)) or \
                  (isinstance(node, ast.ImportFrom) and node.module == "brain.cascade")
            if hit:
                consumers.add(rel)
    assert consumers == {"app.py"}, \
        f"cascade must be composed only by app.py, found consumers: {consumers}"


# ── 6 · No import cycles among the four layers ───────────────────────────────
def test_no_cycles_among_layers():
    layers = ["brain", "human_state", "coaching", "recommend"]
    graph = {l: _module_imports(l) & set(layers) for l in layers}
    for a in layers:                     # a→b and b→a would be a cycle (ignore intra-layer self-imports)
        for b in graph[a]:
            if b == a:
                continue
            assert a not in graph[b], f"import cycle between {a} and {b}"
