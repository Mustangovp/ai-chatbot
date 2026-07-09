import time
from datetime import datetime

class TimelineBuilder:
    """Builds and manages the chronological memory of the user's evolution (Timeline)."""
    
    @staticmethod
    def record_change(model, change_type, value, description):
        """Records a chronological milestone/change in the user's physical history."""
        # Clean existing identical state transitions in the same month to prevent duplicates
        now = time.time()
        current_month = datetime.fromtimestamp(now).strftime("%B")
        
        # Check if identical change already exists this month
        for entry in model.timeline:
            if entry.get("month") == current_month and entry.get("type") == change_type and entry.get("value") == value:
                return  # Skip duplicate recording
        
        entry = {
            "timestamp": now,
            "month": current_month,
            "type": change_type,
            "value": value,
            "description": description
        }
        model.timeline.append(entry)
        
        # Keep timeline sorted chronologically
        model.timeline.sort(key=lambda x: x.get("timestamp", 0))

    @staticmethod
    def get_evolution(model):
        """Returns a formatted list of transitions showing user evolution."""
        evolution = []
        for entry in model.timeline:
            evolution.append(f"{entry.get('month', 'Unknown')}: {entry.get('description', '')}")
        return evolution
