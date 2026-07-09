import json

class HumanModel:
    """The permanent Human Model for a specific user, representing confirmed physical coaching data."""
    def __init__(self, data_dict=None):
        data = data_dict or {}
        self.preferences = data.get("preferences", {})
        self.habits = data.get("habits", {})
        self.constraints = data.get("constraints", {})
        self.patterns = data.get("patterns", {})
        self.confidence = data.get("confidence", {})
        self.timeline = data.get("timeline", [])
        self.clarifications = data.get("clarifications", {})  # Flags keys requiring clarification on contradiction

    def to_dict(self):
        return {
            "preferences": self.preferences,
            "habits": self.habits,
            "constraints": self.constraints,
            "patterns": self.patterns,
            "confidence": self.confidence,
            "timeline": self.timeline,
            "clarifications": self.clarifications
        }

    def serialize(self):
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def deserialize(cls, serialized_str):
        try:
            return cls(json.loads(serialized_str))
        except Exception:
            return cls()
