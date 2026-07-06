"""
M1 Commit 3 — Brain Inspector (pure). Verifies every observability requirement:
stable Decision ID, per-station timing, confidence evolution, evidence→state,
why a constraint was / was not added, skipped stations, flags, versions.
"""
from brain import inspector


def test_full_trace_shape_and_versions():
    tr = inspector.inspect({"age": 69, "level": "beginner", "activityLevel": "sedentary",
                            "healthNotes": "prior stroke, high blood pressure"},
                           model="gpt-4o-mini")
    # Stable Decision ID + deterministic fingerprint.
    assert tr["decision_id"]
    assert tr["evidence_fingerprint"]
    # Versions: library, model, trace + athlete schema.
    v = tr["versions"]
    assert v["constraint_library"] and v["model"] == "gpt-4o-mini"
    assert v["trace_schema"] == "brain-trace-v2" and v["athlete_model_schema"]
    # Feature-flag state recorded.
    assert set(tr["flags"]) == {"BRAIN_SHADOW", "BRAIN_ENFORCE"}
    # Per-station execution + timing.
    s1 = tr["stations"]["S1"]
    assert s1["executed"] is True and isinstance(s1["duration_ms"], float)
    # Confidence evolution through the cascade.
    assert tr["cascade"]["confidence_evolution"][0]["station"] == "S1"
    # The full shadow cascade S1→S5 now executes; only S6 (generation) is skipped.
    for st in ("S1", "S2", "S3", "S4", "S5"):
        assert tr["stations"][st]["executed"] is True
    assert tr["cascade"]["stations_executed"] == ["S1", "S2", "S3", "S4", "S5"]
    skipped = [s["station"] for s in tr["cascade"]["stations_skipped"]]
    assert skipped == ["S6"]
    # Decision surfaced at cascade level.
    assert tr["cascade"]["verdict"] in ("GO", "MODIFY", "NOT_YET", "NO_TRAIN")
    assert tr["stations"]["S4"]["verdict"] == tr["cascade"]["verdict"]
    assert tr["stations"]["S5"]["intervention"]["kind"]
    assert isinstance(tr["cascade"]["generate_training"], bool)


def test_s2_red_flag_in_trace():
    tr = inspector.inspect({}, message="my chest feels tight and heavy going uphill")
    s2 = tr["stations"]["S2"]
    assert s2["executed"] is True and s2["halt"] is True
    assert any(f["class_key"] == "exertional_chest" and f["urgency"] == "URGENT_soon"
               for f in s2["red_flags"])
    assert tr["cascade"]["halt"] is True


def test_why_constraint_added_has_provenance():
    tr = inspector.inspect({"healthNotes": "high blood pressure"})
    s1 = tr["stations"]["S1"]
    valsalva = next(c for c in s1["constraints_added"] if c["movement"] == "valsalva")
    assert "hypertension" in valsalva["source_conditions"]
    assert "hypertension" in valsalva["why"]
    assert s1["evidence_changed_state"]["detected_conditions"] == sorted(
        s1["evidence_changed_state"]["detected_conditions"])


def test_why_no_constraint_empty_health():
    tr = inspector.inspect({"age": 30, "level": "advanced", "activityLevel": "active"})
    s1 = tr["stations"]["S1"]
    assert s1["constraints_added"] == []
    assert s1["no_constraint_reason"] and "empty" in s1["no_constraint_reason"]


def test_why_no_constraint_unmatched_health():
    tr = inspector.inspect({"healthNotes": "generally healthy, no issues"})
    s1 = tr["stations"]["S1"]
    assert s1["constraints_added"] == []
    assert "no known condition token matched" in s1["no_constraint_reason"]


def test_stable_id_and_deterministic_fingerprint():
    p = {"age": 40, "healthNotes": "osteoporosis"}
    a = inspector.inspect(p, decision_id="11111111-1111-1111-1111-111111111111")
    b = inspector.inspect(p, decision_id="22222222-2222-2222-2222-222222222222")
    assert a["decision_id"] != b["decision_id"]          # explicit id honored
    assert a["evidence_fingerprint"] == b["evidence_fingerprint"]  # same evidence → same fingerprint
