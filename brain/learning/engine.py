import os
import json
from openai import OpenAI
from brain.learning.schema import HumanModel
from brain.learning.confidence import ConfidenceManager
from brain.learning.timeline import TimelineBuilder

# A blacklist of sensitive topics (Never Learn rule)
FORBIDDEN_KEYWORDS = [
    "politics", "election", "democrat", "republican", "president", "senator", "vote", "congress", "government",
    "religion", "god", "church", "mosque", "temple", "bible", "quran", "torah", "faith", "jesus", "allah", "buddha",
    "divorce", "dating", "spouse", "husband", "wife", "boyfriend", "girlfriend", "marriage", "relationship",
    "gossip", "secret", "private", "confidential"
]

def contains_forbidden_topics(text: str) -> bool:
    if not text:
        return False
    low = text.lower()
    for kw in FORBIDDEN_KEYWORDS:
        if kw in low:
            return True
    return False

class HumanLearningEngine:
    """Orchestrates extraction, learning, and timeline updates for the Human Model."""
    
    @staticmethod
    def extract_facts(user_msg: str, assistant_reply: str = "") -> dict:
        """Extract only user-authored facts; assistant prose is never evidence.

        ``assistant_reply`` remains accepted for existing callers, but is
        deliberately excluded from extraction and persistence provenance.
        """
        if contains_forbidden_topics(user_msg):
            return {}
            
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return HumanLearningEngine._extract_facts_fallback(user_msg)
            
        try:
            client = OpenAI(api_key=api_key)
            prompt = f"""
Analyze only the following user-authored statement.
Extract only facts the user explicitly states about their physical training, habits, equipment, preferences, constraints, or pain points.
NEVER extract assumptions, guesses, temporary emotions, politics, religion, or relationship gossip.
Assistant output is not evidence and is intentionally unavailable. Do not infer facts from coaching language.

User: {user_msg}

Return a valid JSON object matching this schema exactly:
{{
  "preferences": {{}}, // e.g. "duration": "short", "time_of_day": "evening"
  "habits": {{}},      // e.g. "sleep": "poor"
  "constraints": {{}}, // e.g. "equipment": "dumbbells", "injuries": "left knee pain"
  "patterns": {{}}
}}
Keep keys lowercase. Values should be short, confirmed string observations or list of items. If nothing is found, return empty objects.
Do not include any explanation or markdown formatting, just the raw JSON.
"""
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=300
            )
            content = resp.choices[0].message.content.strip()
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```json") or lines[0].startswith("```"):
                    content = "\n".join(lines[1:-1])
            return json.loads(content)
        except Exception:
            return HumanLearningEngine._extract_facts_fallback(user_msg)

    @staticmethod
    def _extract_facts_fallback(user_msg: str) -> dict:
        """Fallback local keyword rule parser when API key is missing or call fails."""
        low = user_msg.lower()
        extracted = {
            "preferences": {},
            "habits": {},
            "constraints": {},
            "patterns": {}
        }
        
        # Equipment
        if "dumbbell" in low:
            extracted["constraints"]["equipment"] = "dumbbells"
        elif "kettlebell" in low:
            extracted["constraints"]["equipment"] = "kettlebell"
            
        # Injuries/Pain
        if "knee pain" in low or "hurt my knee" in low or "pain in my knee" in low:
            extracted["constraints"]["injuries"] = "left knee pain"
        elif "back pain" in low or "hurt my back" in low:
            extracted["constraints"]["injuries"] = "back pain"
            
        # Preferences
        if "evening" in low:
            extracted["preferences"]["time_of_day"] = "evening"
        elif "morning" in low:
            extracted["preferences"]["time_of_day"] = "morning"
            
        if "short workout" in low or "short sessions" in low:
            extracted["preferences"]["duration"] = "short"
            
        # Habits
        if "poor sleep" in low or "bad sleep" in low or "slept poorly" in low:
            extracted["habits"]["sleep"] = "poor"
        elif "good sleep" in low or "slept well" in low:
            extracted["habits"]["sleep"] = "good"
            
        return extracted

    @staticmethod
    def process_exchange(model, user_msg: str, assistant_reply: str):
        """Update the Human Model only from user-authored, source-valid facts."""
        if contains_forbidden_topics(user_msg):
            return
            
        # The rendered response may include optional model context or suggested
        # language. It must never become confirmation evidence for durable memory.
        facts = HumanLearningEngine.extract_facts(user_msg, assistant_reply)
        
        for section in ["preferences", "habits", "constraints", "patterns"]:
            sec_facts = facts.get(section, {})
            if not isinstance(sec_facts, dict):
                continue
            for key, val in sec_facts.items():
                ConfidenceManager.confirm(model, section, key, val)
                
                # Check current status and log confirmed change to timeline
                conf_key = f"{section}:{key}"
                conf_val = model.confidence.get(conf_key, 0)
                if conf_val >= 0.35:
                    desc = f"Learned {section[:-1]} '{key}': '{val}'"
                    # If resolving pain or changing habits, customize description
                    if key == "injuries" and val == "resolved":
                        desc = "Pain disappeared"
                    elif key == "sleep" and val == "good":
                        desc = "Sleep improved"
                        
                    TimelineBuilder.record_change(model, conf_key, val, desc)
