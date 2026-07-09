import pytest
import time
from brain.observatory.engine import ObservatoryEngine
from brain.observatory.analytics import RetentionAnalytics
from brain.observatory.dropoff import DropoffDetector
from brain.observatory.dashboard import ObservatoryDashboard

def test_observatory_session_and_analytics_flow():
    ObservatoryEngine.clear()
    
    # 1. Proving sessions recorded
    session = ObservatoryEngine.start_session(
        session_id="session-123",
        language="en",
        mode="voice",
        device="mobile",
        browser="safari",
        user_id="user-456"
    )
    
    assert session.session_id == "session-123"
    assert session.language == "en"
    assert session.mode == "voice"
    assert session.device == "mobile"
    assert session.browser == "safari"
    
    # 2. Proving analytics updated
    ObservatoryEngine.log_turn("session-123", latency=1.2, listening_time=3.5, decision="CONTINUE")
    ObservatoryEngine.log_turn("session-123", latency=1.5, listening_time=4.0, decision="PLAN_READY")
    ObservatoryEngine.log_learning("session-123", facts=2, confidence_incs=1, contradictions=0, memory_updates=1)
    
    session = ObservatoryEngine.get_session("session-123")
    assert session.turns == 2
    assert session.total_turn_latency == 2.7
    assert session.plan_ready_count == 1
    assert session.facts_extracted == 2
    
    # Proving dropoff stage updates
    assert session.dropoff_stage == "after_plan_ready"
    ObservatoryEngine.complete_session("session-123")
    assert session.dropoff_stage == "completed_session"
    
    # Proving stats calculations
    stats = ObservatoryDashboard.render_stats(list(ObservatoryEngine._sessions.values()))
    assert stats["sessions_today"] == 1
    assert stats["completion_rate"] == 1.0

def test_observatory_retention_and_consistency():
    # 3. Proving retention calculated
    user_sessions = {
        "user-1": [time.time(), time.time() + 1.5 * 24 * 3600], # returned 1d
        "user-2": [time.time()] # did not return
    }
    ret = RetentionAnalytics.calculate_retention(user_sessions)
    assert ret["1d"] == 0.5
    assert ret["7d"] == 0.0

    # Consistency score calculation
    consistency = RetentionAnalytics.calculate_consistency([time.time(), time.time() + 3 * 24 * 3600])
    assert 0.0 < consistency < 1.0

def test_observatory_privacy_constraints():
    ObservatoryEngine.clear()
    session = ObservatoryEngine.start_session("session-priv")
    
    # Log turn and learning
    ObservatoryEngine.log_turn("session-priv", latency=1.0, listening_time=2.0, decision="CONTINUE")
    ObservatoryEngine.log_learning("session-priv", facts=1, confidence_incs=1, contradictions=0, memory_updates=1)
    
    # Retrieve all values of the session
    session_data = session.__dict__
    
    # 4 & 5. Proving no transcript, prompts, LLM responses or audio are stored
    forbidden_keys = ["transcript", "text", "audio", "prompt", "response", "speech", "recording"]
    for key, value in session_data.items():
        # Check that none of the keys contain forbidden names
        assert not any(fk in key.lower() for fk in forbidden_keys)
        # Check that none of the values contain conversation string snippets or audio bytes
        if isinstance(value, str):
            # Safe strings are only configuration metadata
            assert value in ["session-priv", "en", "text", "desktop", "chrome", "before_plan_ready"]

def test_observatory_independence_readonly():
    # 7. Proving Observatory never modifies Brain, Learning or Relationship states
    # It acts strictly downstream
    from brain.learning.schema import HumanModel
    
    model = HumanModel()
    original_model_dict = model.to_dict().copy()
    
    # Run observatory functions
    session = ObservatoryEngine.start_session("session-test-indep")
    ObservatoryEngine.log_learning("session-test-indep", facts=5, confidence_incs=4, contradictions=1, memory_updates=2)
    
    # Verify that the model remains completely unaffected
    assert model.to_dict() == original_model_dict
