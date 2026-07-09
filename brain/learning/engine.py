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
    def extract_facts(user_msg: str, assistant_reply: str) -> dict:
        """Calls OpenAI to extract confirmed physical training facts from the exchange.
        Returns a dict matching the schema. Fallback to keyword-based parsing if offline."""
        if contains_forbidden_topics(user_msg) or contains_forbidden_topics(assistant_reply):
            return {}
            
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return HumanLearningEngine._extract_facts_fallback(user_msg)
            
        try:
            client = OpenAI(api_key=api_key)
            prompt = f"""
Analyze the following conversation segment between a fitness user and APEX (the AI coach).
Extract only CONFIRMED physical training facts, habits, equipment, preferences, constraints, or pain points.
NEVER extract assumptions, guesses, temporary emotions, politics, religion, or relationship gossip.

User: {user_msg}
APEX: {assistant_reply}

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
        """Processes a conversational exchange to update the Human Model with confirmed facts."""
        if contains_forbidden_topics(user_msg) or contains_forbidden_topics(assistant_reply):
            return
            
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
