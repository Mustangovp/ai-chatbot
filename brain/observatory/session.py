import uuid
import time

class ObservatorySession:
    def __init__(self, session_id=None, language="en", mode="text", device="desktop", browser="chrome"):
        self.session_id = session_id or str(uuid.uuid4())
        self.start_time = time.time()
        self.end_time = None
        self.duration = 0.0
        self.language = language
        self.mode = mode
        self.device = device
        self.browser = browser
        
        # Turn metrics
        self.turns = 0
        self.total_turn_latency = 0.0
        self.total_listening_time = 0.0
        self.plan_ready_count = 0
        self.safety_stop_count = 0
        self.clarification_count = 0
        self.completed = False
        
        # Learning metrics (strictly count values, never store text or audio)
        self.facts_extracted = 0
        self.confidence_increases = 0
        self.contradictions = 0
        self.memory_updates = 0
        self.unresolved_clarifications = 0
        
        # Drop-off stage
        self.dropoff_stage = "before_first_reply"

    def end(self):
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
