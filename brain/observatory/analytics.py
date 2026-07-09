class RetentionAnalytics:
    @staticmethod
    def calculate_retention(user_sessions):
        """
        user_sessions is a dict mapping user_id to list of session start times (timestamps)
        """
        returned_1d = 0
        returned_7d = 0
        returned_30d = 0
        total_users = len(user_sessions)
        if total_users == 0:
            return {"1d": 0.0, "7d": 0.0, "30d": 0.0}

        for user_id, timestamps in user_sessions.items():
            if len(timestamps) < 2:
                continue
            first_session = min(timestamps)
            other_sessions = [t for t in timestamps if t != first_session]
            
            has_1d = any(1 * 24 * 3600 <= (t - first_session) < 2 * 24 * 3600 for t in other_sessions)
            has_7d = any(7 * 24 * 3600 <= (t - first_session) < 8 * 24 * 3600 for t in other_sessions)
            has_30d = any(30 * 24 * 3600 <= (t - first_session) < 31 * 24 * 3600 for t in other_sessions)
            
            if has_1d: returned_1d += 1
            if has_7d: returned_7d += 1
            if has_30d: returned_30d += 1

        return {
            "1d": returned_1d / total_users,
            "7d": returned_7d / total_users,
            "30d": returned_30d / total_users
        }

    @staticmethod
    def calculate_consistency(timestamps):
        """
        Consistency score based on weekly workout gaps.
        Returns a score between 0.0 and 1.0.
        """
        if len(timestamps) < 2:
            return 0.0
        sorted_times = sorted(timestamps)
        gaps = [sorted_times[i] - sorted_times[i-1] for i in range(1, len(sorted_times))]
        avg_gap = sum(gaps) / len(gaps)
        one_week = 7 * 24 * 3600
        if avg_gap >= one_week:
            return 0.1
        return max(0.1, 1.0 - (avg_gap / one_week))
