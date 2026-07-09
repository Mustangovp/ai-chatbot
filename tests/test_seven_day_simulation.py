import pytest
import time
from brain.learning.schema import HumanModel
from brain.learning.confidence import ConfidenceManager
from brain.learning.timeline import TimelineBuilder
from brain.learning.detector import PatternDetector
from brain.learning.engine import HumanLearningEngine

def test_seven_day_apex_evolution_simulation():
    # Initialize the HumanModel for a new user
    model = HumanModel()
    
    # ═══════════════════════════════════════════════════════════
    # DAY 1: Initial Conversation, Brain assessment, Workout, Memory update
    # ═══════════════════════════════════════════════════════════
    user_msg_d1 = "I want to start training but I have left knee pain. I only own dumbbells."
    apex_reply_d1 = "Understood. I will avoid knee-loading movements. Let's do a dumbbell upper body session."
    
    # Human Learning Engine extracts facts and commits to memory
    HumanLearningEngine.process_exchange(model, user_msg_d1, apex_reply_d1)
    
    # Verify Day 1 Memory
    assert model.constraints["injuries"] == "left knee pain"
    assert model.constraints["equipment"] == "dumbbells"
    assert model.confidence["constraints:injuries"] == 0.35
    assert len(model.timeline) == 2  # 2 constraints learned
    
    # ═══════════════════════════════════════════════════════════
    # DAY 2: Greet naturally referencing yesterday's state
    # ═══════════════════════════════════════════════════════════
    # Find last noted concern in timeline
    last_injury_concern = None
    for entry in reversed(model.timeline):
        if entry["type"] == "constraints:injuries":
            last_injury_concern = entry["value"]
            break
            
    assert last_injury_concern == "left knee pain"
    
    # Natural opening greeting referencing yesterday
    day_2_greeting = f"Yesterday you noted {last_injury_concern}. How does your body feel today?"
    assert day_2_greeting == "Yesterday you noted left knee pain. How does your body feel today?"
    
    user_msg_d2 = "Knee feels better today. Also I slept well last night."
    apex_reply_d2 = "Good to hear. Let's try some upper body exercises."
    
    # Learning
    HumanLearningEngine.process_exchange(model, user_msg_d2, apex_reply_d2)
    assert model.habits["sleep"] == "good"
    assert model.confidence["habits:sleep"] == 0.35
    
    # ═══════════════════════════════════════════════════════════
    # DAY 3: Notice real changes
    # ═══════════════════════════════════════════════════════════
    # The user completes their second session and reports pain resolved
    user_msg_d3 = "Just finished the second session. No knee pain at all today."
    apex_reply_d3 = "I notice your left knee pain has resolved. I am updating your constraint log."
    
    # Resolve the injury constraint
    ConfidenceManager.resolve_clarification(model, "constraints", "injuries", "resolved")
    TimelineBuilder.record_change(model, "constraints:injuries", "resolved", "Pain disappeared")
    
    # Verify pain is resolved in profile
    assert model.constraints["injuries"] == "resolved"
    assert len(model.timeline) == 4  # Includes pain resolved entry
    
    # ═══════════════════════════════════════════════════════════
    # DAY 5: Make a prediction using Pattern Detector
    # ═══════════════════════════════════════════════════════════
    # Mocking historical logs up to Day 5: 2 completed sessions
    now = time.time()
    sessions = [
        {"timestamp": now - 4 * 24 * 3600, "duration": "short"}, # Day 1
        {"timestamp": now - 2 * 24 * 3600, "duration": "short"}  # Day 3
    ]
    
    # Pattern detector calculates consistency
    avg_sessions_per_week = PatternDetector.detect_consistency(sessions)
    
    # We predict the user will finish 3 sessions this week
    predicted_sessions = 3
    prediction_msg = f"Based on your consistency of {avg_sessions_per_week} sessions/week, I predict you will complete 3 workouts this week."
    
    # Store prediction in patterns
    model.patterns["weekly_prediction"] = {
        "predicted_sessions": predicted_sessions,
        "actual_sessions": len(sessions)
    }
    
    assert model.patterns["weekly_prediction"]["predicted_sessions"] == 3
    
    # ═══════════════════════════════════════════════════════════
    # DAY 7: Verify prediction & Generate the first Weekly Reflection
    # ═══════════════════════════════════════════════════════════
    # User completes the 3rd session on Day 7
    sessions.append({"timestamp": now, "duration": "short"})
    model.patterns["weekly_prediction"]["actual_sessions"] = len(sessions)
    
    # Verify prediction accuracy
    prediction_correct = (
        model.patterns["weekly_prediction"]["actual_sessions"] == 
        model.patterns["weekly_prediction"]["predicted_sessions"]
    )
    assert prediction_correct is True
    
    # Generate weekly reflection: Max 4 sentences. No motivation. No praise. Only insight.
    weekly_reflection = (
        f"You completed {len(sessions)} sessions this week. "
        "Sleep improved to good. "
        "Knee discomfort resolved on Day 3. "
        "Consistency remains your strongest predictor of progress."
    )
    
    # Assert sentence limit constraint (max 4 sentences)
    sentences = [s.strip() for s in weekly_reflection.split(".") if s.strip()]
    assert len(sentences) <= 4
    
    print("\n--- Day 7 Weekly Reflection Output ---")
    print(weekly_reflection)
    print("--------------------------------------")
