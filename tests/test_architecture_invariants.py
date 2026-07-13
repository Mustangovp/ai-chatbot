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

from dataclasses import replace

import pytest

from brain.corpus import load_fixtures
from brain.runtime_assets.expert_rules import (
    EXPERT_RULE_PACK_VERSION,
    load_expert_rule_packs,
    validate_expert_rule_packs,
)
from brain.runtime_assets.personas import (
    load_runtime_personas,
    validate_runtime_personas,
)

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


def test_runtime_persona_assets_preserve_the_complete_fixture_corpus():
    fixtures = load_fixtures()
    first = load_runtime_personas()
    second = load_runtime_personas()

    assert [fixture["id"] for fixture in fixtures] == [f"P-{number:03d}" for number in range(1, 141)]
    assert first == second
    assert len(first) == 140
    assert all(persona.id == persona.source_fixture_id for persona in first)
    assert all(persona.prohibited_assumptions == () for persona in first)


def test_runtime_persona_validation_fails_closed_for_duplicate_invalid_or_inferred_records():
    records = load_runtime_personas()
    duplicated = (records[0], records[0], *records[2:])
    with pytest.raises(ValueError, match="complete P-001"):
        validate_runtime_personas(duplicated, load_fixtures())

    invalid_enum = (replace(records[0], experience_level="unsupported"), *records[1:])
    with pytest.raises(ValueError, match="invalid context enum"):
        validate_runtime_personas(invalid_enum, load_fixtures())

    inferred = (replace(records[0], problem_tags=("invented_fact",)), *records[1:])
    with pytest.raises(ValueError, match="unsupported inferred facts"):
        validate_runtime_personas(inferred, load_fixtures())


def test_expert_rule_packs_are_complete_source_traceable_and_deterministic():
    first = load_expert_rule_packs()
    second = load_expert_rule_packs()

    assert first == second
    assert [pack.lineage for pack in first] == [
        "Galpin", "Helms", "McGill", "Aragon", "Clear", "Gervais", "Winkelman",
    ]
    assert all(rule.source_document and rule.source_section and rule.evidence_reference
               for pack in first for rule in pack.rules)


def test_expert_rule_validation_fails_closed_for_duplicate_missing_or_unresolved_sources():
    packs = load_expert_rule_packs()
    duplicate = replace(packs[0], rules=(packs[0].rules[0], packs[0].rules[0]))
    with pytest.raises(ValueError, match="duplicate rule ID"):
        validate_expert_rule_packs((duplicate, *packs[1:]))

    missing = replace(packs[0].rules[0], source_document="docs/research/missing.md")
    with pytest.raises(ValueError, match="missing source reference"):
        validate_expert_rule_packs((replace(packs[0], rules=(missing, *packs[0].rules[1:])), *packs[1:]))

    unresolved = replace(packs[0].rules[0], runtime_ready=True)
    with pytest.raises(ValueError, match="unresolved rule"):
        validate_expert_rule_packs((replace(packs[0], rules=(unresolved, *packs[0].rules[1:])), *packs[1:]))


def test_runtime_assets_remain_detached_from_production_execution_modules():
    for filename in ("app.py", "decision_engine.py"):
        source = (_ROOT / filename).read_text(encoding="utf-8")
        assert "runtime_assets" not in source
    assert EXPERT_RULE_PACK_VERSION == "expert-rule-packs-v1"
