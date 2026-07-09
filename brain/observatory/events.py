class ObservatoryEvent:
    def __init__(self, session_id, event_type, payload=None):
        self.session_id = session_id
        self.event_type = event_type
        self.payload = payload or {}
