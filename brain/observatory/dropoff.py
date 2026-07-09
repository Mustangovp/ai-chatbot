class DropoffDetector:
    @staticmethod
    def detect_stage(session):
        if session.turns == 0:
            return "before_first_reply"
        if session.safety_stop_count > 0:
            return "safety_stop_interrupted"
        if session.completed:
            return "completed_session"
        if session.plan_ready_count > 0:
            return "after_plan_ready"
        return "before_plan_ready"
