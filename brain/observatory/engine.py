from brain.observatory.session import ObservatorySession
from brain.observatory.dropoff import DropoffDetector

class ObservatoryEngine:
    _sessions = {}
    _user_session_map = {} # Maps user_id -> list of session timestamps

    @classmethod
    def start_session(cls, session_id, language="en", mode="text", device="desktop", browser="chrome", user_id=None):
        session = ObservatorySession(session_id, language, mode, device, browser)
        cls._sessions[session.session_id] = session
        if user_id:
            if user_id not in cls._user_session_map:
                cls._user_session_map[user_id] = []
            cls._user_session_map[user_id].append(session.start_time)
        return session

    @classmethod
    def get_session(cls, session_id):
        return cls._sessions.get(session_id)

    @classmethod
    def log_turn(cls, session_id, latency, listening_time, decision):
        session = cls.get_session(session_id)
        if session:
            session.turns += 1
            session.total_turn_latency += latency
            session.total_listening_time += listening_time
            if decision == "PLAN_READY":
                session.plan_ready_count += 1
            elif decision == "SAFETY_STOP":
                session.safety_stop_count += 1
            session.dropoff_stage = DropoffDetector.detect_stage(session)

    @classmethod
    def log_learning(cls, session_id, facts, confidence_incs, contradictions, memory_updates):
        session = cls.get_session(session_id)
        if session:
            session.facts_extracted += facts
            session.confidence_increases += confidence_incs
            session.contradictions += contradictions
            session.memory_updates += memory_updates

    @classmethod
    def complete_session(cls, session_id):
        session = cls.get_session(session_id)
        if session:
            session.completed = True
            session.dropoff_stage = DropoffDetector.detect_stage(session)

    @classmethod
    def clear(cls):
        cls._sessions.clear()
        cls._user_session_map.clear()
