from collections import Counter
from datetime import datetime

class PatternDetector:
    """Analyzes historical feedback and logs to detect physical training habits and tendencies."""
    
    @staticmethod
    def detect_duration_preference(sessions):
        """Analyzes a list of session dicts to find preferred duration (e.g. 'short' < 30m, 'medium' 30-50m, 'long' > 50m)."""
        if not sessions:
            return None
        durations = []
        for s in sessions:
            dur = s.get("duration")
            if dur is not None:
                durations.append(dur)
        if not durations:
            return None
        
        counter = Counter(durations)
        most_common, count = counter.most_common(1)[0]
        # Only lock preference if it has been observed at least twice
        if count >= 2:
            return most_common
        return None

    @staticmethod
    def detect_time_preference(sessions):
        """Analyzes timestamps of sessions to detect preferred time of day ('morning', 'afternoon', 'evening')."""
        if not sessions:
            return None
        times_of_day = []
        for s in sessions:
            ts = s.get("timestamp")
            if ts:
                try:
                    dt = datetime.fromtimestamp(ts)
                    hour = dt.hour
                    if 5 <= hour < 12:
                        times_of_day.append("morning")
                    elif 12 <= hour < 17:
                        times_of_day.append("afternoon")
                    else:
                        times_of_day.append("evening")
                except Exception:
                    pass
        if not times_of_day:
            return None
            
        counter = Counter(times_of_day)
        most_common, count = counter.most_common(1)[0]
        if count >= 2:
            return most_common
        return None

    @staticmethod
    def detect_consistency(sessions):
        """Calculates average sessions per week over the logged period."""
        if not sessions:
            return 0.0
        timestamps = [s.get("timestamp") for s in sessions if s.get("timestamp")]
        if not timestamps:
            return 0.0
        
        min_ts = min(timestamps)
        max_ts = max(timestamps)
        
        # Calculate time span in weeks (minimum 1 week to avoid division by zero)
        span_weeks = max(1.0, (max_ts - min_ts) / (7 * 24 * 3600))
        total_sessions = len(sessions)
        return round(total_sessions / span_weeks, 2)

    @staticmethod
    def detect_sleep_recovery_trends(history):
        """Scans recovery trends from raw sleep and fatigue logs."""
        if not history:
            return "stable"
        sleeps = [h.get("sleep") for h in history if h.get("sleep")]
        if len(sleeps) < 3:
            return "stable"
            
        # If last 3 entries are "poor", it's a downward trend
        if all(s == "poor" for s in sleeps[-3:]):
            return "declining"
        # If last 3 entries are "good", it's an upward trend
        if all(s == "good" for s in sleeps[-3:]):
            return "improving"
        return "stable"

    @staticmethod
    def detect_recurring_injuries(history):
        """Detects recurring pain reports in history logs."""
        if not history:
            return []
        pains = []
        for h in history:
            body = h.get("body")
            if body and body != "ok":
                pains.append(body)
        if not pains:
            return []
            
        counter = Counter(pains)
        recurring = [item for item, count in counter.items() if count >= 2]
        return recurring
