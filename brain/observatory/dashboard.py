class ObservatoryDashboard:
    @staticmethod
    def render_stats(sessions):
        total_sessions = len(sessions)
        if total_sessions == 0:
            return {
                "sessions_today": 0,
                "active_users": 0,
                "average_session_duration": 0.0,
                "average_conversation_turns": 0.0,
                "completion_rate": 0.0,
                "plan_generation_rate": 0.0,
                "safety_interventions": 0,
                "return_users": 0,
                "retention_1d": 0.0
            }
        
        sessions_today = total_sessions
        active_users = len(set(s.session_id for s in sessions))
        avg_duration = sum(s.duration for s in sessions) / total_sessions
        avg_turns = sum(s.turns for s in sessions) / total_sessions
        completion_rate = sum(1 for s in sessions if s.completed) / total_sessions
        plan_generation_rate = sum(1 for s in sessions if s.plan_ready_count > 0) / total_sessions
        safety_interventions = sum(s.safety_stop_count for s in sessions)
        
        return {
            "sessions_today": sessions_today,
            "active_users": active_users,
            "average_session_duration": avg_duration,
            "average_conversation_turns": avg_turns,
            "completion_rate": completion_rate,
            "plan_generation_rate": plan_generation_rate,
            "safety_interventions": safety_interventions,
            "return_users": 0,
            "retention_1d": 0.0
        }
