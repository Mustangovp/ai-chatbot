CONFIDENCE_STEPS = [0.35, 0.58, 0.82, 0.97]

class ConfidenceManager:
    """Manages confidence levels and contradictions for learned facts in the Human Model."""
    
    @staticmethod
    def confirm(model, section_name, key, value):
        """Confirms a fact. Elevates confidence or flags contradiction if values mismatch."""
        section = getattr(model, section_name, None)
        if section is None or not isinstance(section, dict):
            return
        
        conf_key = f"{section_name}:{key}"
        current_val = section.get(key)
        
        if current_val is None:
            # First observation
            section[key] = value
            model.confidence[conf_key] = CONFIDENCE_STEPS[0]
            # Clean any pending contradiction clarification
            if conf_key in model.clarifications:
                del model.clarifications[conf_key]
        elif current_val == value:
            # Repeated confirmation: advance confidence step
            curr_conf = model.confidence.get(conf_key, CONFIDENCE_STEPS[0])
            next_conf = CONFIDENCE_STEPS[-1]
            for step in CONFIDENCE_STEPS:
                if step > curr_conf:
                    next_conf = step
                    break
            model.confidence[conf_key] = next_conf
            # Clean any pending contradiction clarification
            if conf_key in model.clarifications:
                del model.clarifications[conf_key]
        else:
            # Contradiction observed!
            ConfidenceManager.contradict(model, section_name, key, value)

    @staticmethod
    def contradict(model, section_name, key, new_value):
        """Handles a contradiction: lowers confidence and flags the conflict for natural clarification."""
        conf_key = f"{section_name}:{key}"
        curr_conf = model.confidence.get(conf_key, CONFIDENCE_STEPS[0])
        
        # Lower confidence by one step or drop by a fixed amount (capped at 0.10)
        new_conf = curr_conf - 0.25
        # Also clamp to nearest step if possible, but keep it >= 0.10
        if new_conf < 0.10:
            new_conf = 0.10
        model.confidence[conf_key] = round(new_conf, 2)
        
        # Flag conflict: do NOT overwrite yet, store in clarifications for dialogue resolving
        model.clarifications[conf_key] = new_value

    @staticmethod
    def resolve_clarification(model, section_name, key, confirmed_value):
        """Resolves a pending contradiction with the user's explicit confirmation."""
        section = getattr(model, section_name, None)
        if section is None or not isinstance(section, dict):
            return
            
        conf_key = f"{section_name}:{key}"
        section[key] = confirmed_value
        model.confidence[conf_key] = CONFIDENCE_STEPS[0]  # Reset to initial verified level
        if conf_key in model.clarifications:
            del model.clarifications[conf_key]
