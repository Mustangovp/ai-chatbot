"""Deterministic validation for complete daily nutrition delivery."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re


_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")
_NORMALIZER = re.compile(r"[^a-z\u0400-\u04ff]+")
_MEALS = {
    "breakfast": {"breakfast", "\u0437\u0430\u043a\u0443\u0441\u043a\u0430"},
    "snack": {"snack", "snacks", "morningsnack", "afternoonsnack", "eveningsnack",
              "\u043c\u0435\u0436\u0434\u0438\u043d\u043d\u0430", "\u0441\u043b\u0435\u0434\u043e\u0431\u0435\u0434\u043d\u0430", "\u043c\u0435\u0436\u0434\u0438\u043d\u043d\u043e", "\u0441\u043d\u0430\u043a"},
    "lunch": {"lunch", "\u043e\u0431\u044f\u0434"},
    "dinner": {"dinner", "\u0432\u0435\u0447\u0435\u0440\u044f"},
}
_TOTALS = {"total", "dailytotal", "totalfortheday", "\u043e\u0431\u0449\u043e", "\u043e\u0431\u0449\u043e\u0437\u0430\u0434\u0435\u043d\u044f", "\u0441\u0443\u043c\u0430\u0440\u043d\u043e", "\u0441\u0443\u043c\u0430"}
_COLUMN_NAMES = {
    "meal": {"meal", "\u0445\u0440\u0430\u043d\u0435\u043d\u0435"},
    "food": {"food", "foods", "item", "product", "\u0445\u0440\u0430\u043d\u0430", "\u043f\u0440\u043e\u0434\u0443\u043a\u0442"},
    "quantity": {"quantity", "amount", "qty", "portion", "\u043a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e", "\u043f\u043e\u0440\u0446\u0438\u044f"},
    "protein": {"protein", "proteins", "\u043f\u0440\u043e\u0442\u0435\u0438\u043d", "\u0431\u0435\u043b\u0442\u044a\u0447\u0438\u043d\u0438"},
    "carbs": {"carbs", "carbohydrate", "carbohydrates", "\u0432\u044a\u0433\u043b\u0435\u0445\u0438\u0434\u0440\u0430\u0442\u0438"},
    "fat": {"fat", "fats", "\u043c\u0430\u0437\u043d\u0438\u043d\u0438"},
    "kcal": {"kcal", "calorie", "calories", "cal", "\u043a\u043a\u0430\u043b", "\u043a\u0430\u043b\u043e\u0440\u0438\u0438"},
}
_PROHIBITED_COMPLETION_GUIDANCE = (
    re.compile(r"\b(?:you\s+can|you\s+may|feel\s+free\s+to)\s+(?:add|increase|adjust)\b.*\b(?:food|portion|meal|calorie)", re.I),
    re.compile(r"\bthis\s+is\s+a\s+base\s+plan\b", re.I),
    re.compile(r"\b(?:add|increase|adjust)\b.*\b(?:food|portion|meal|calorie)s?\b", re.I),
    re.compile(r"(?:\u043c\u043e\u0436\u0435\u0448|\u043c\u043e\u0436\u0435\u0442\u0435)\s+\u0434\u0430\s+(?:\u0434\u043e\u0431\u0430\u0432\u0438\u0448|\u0434\u043e\u0431\u0430\u0432\u0438\u0442\u0435|\u0443\u0432\u0435\u043b\u0438\u0447\u0438\u0448|\u0443\u0432\u0435\u043b\u0438\u0447\u0438\u0442\u0435).*?(?:\u0445\u0440\u0430\u043d|\u043f\u043e\u0440\u0446\u0438|\u043a\u0430\u043b\u043e\u0440|\u044f\u0434\u0435\u043d\u0435)", re.I),
    re.compile(r"\b\u0442\u043e\u0432\u0430\s+\u0435\s+\u0431\u0430\u0437\u043e\u0432\s+\u043f\u043b\u0430\u043d\b", re.I),
)
_DIRECT_FULL_DAY = (
    re.compile(r"\b(?:meal\s+plan\s+for\s+today|daily\s+(?:meal|nutrition)\s+plan|full[- ]day\s+(?:meal|nutrition)\s+plan|meal\s+menu\s+for\s+today|nutrition\s+plan\s+for\s+today|alternative\s+meal\s+plan|alternative\s+daily\s+menu|complete\s+daily\s+meal\s+plan)\b", re.I),
    re.compile(r"(?:\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+\u043f\u043b\u0430\u043d\s+\u0437\u0430\s+\u0434\u0435\u043d\u044f|\u0434\u043d\u0435\u0432\u0435\u043d\s+\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+(?:\u043f\u043b\u0430\u043d|\u0440\u0435\u0436\u0438\u043c)|\u043c\u0435\u043d\u044e\s+\u0437\u0430\s+\u0434\u043d\u0435\u0441|(?:\u0438\u0441\u043a\u0430\u043c\s+)?\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+\u0440\u0435\u0436\u0438\u043c|\u0434\u0440\u0443\u0433\s+\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+\u0440\u0435\u0436\u0438\u043c|\u0430\u043b\u0442\u0435\u0440\u043d\u0430\u0442\u0438\u0432\u0435\u043d\s+\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+\u043f\u043b\u0430\u043d|\u0430\u043b\u0442\u0435\u0440\u043d\u0430\u0442\u0438\u0432\u043d\u043e\s+\u0434\u043d\u0435\u0432\u043d\u043e\s+\u043c\u0435\u043d\u044e|\u043f\u044a\u043b\u0435\u043d\s+\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+\u043f\u043b\u0430\u043d)", re.I),
)
_CONTEXTUAL_FULL_DAY = re.compile(r"\b(?:another\s+meal\s+plan)\b|\u0438\u0441\u043a\u0430\u043c\s+\u0434\u0440\u0443\u0433\s+\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+\u0440\u0435\u0436\u0438\u043c", re.I)
_NUTRITION_CONTEXT = re.compile(r"\b(?:nutrition|meal\s+plan|daily\s+menu|kcal|calorie|protein)\b|\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b|\u043c\u0435\u043d\u044e|\u043a\u0430\u043b\u043e\u0440|\u043f\u0440\u043e\u0442\u0435\u0438\u043d", re.I)


@dataclass(frozen=True)
class NutritionTargets:
    kcal: Decimal
    protein: Decimal | None = None
    carbs: Decimal | None = None
    fat: Decimal | None = None


@dataclass(frozen=True)
class NutritionFood:
    name: str
    quantity: str
    protein: Decimal | None
    carbs: Decimal | None
    fat: Decimal | None
    kcal: Decimal | None


@dataclass(frozen=True)
class NutritionMeal:
    key: str
    label: str
    foods: tuple[NutritionFood, ...]


@dataclass(frozen=True)
class NutritionDay:
    meals: tuple[NutritionMeal, ...]
    declared_totals: tuple[dict[str, Decimal | None], ...]


@dataclass(frozen=True)
class NutritionValidationResult:
    valid: bool
    failures: tuple[str, ...]


def _decimal(value: str | Decimal | None) -> Decimal | None:
    match = _NUMBER.search(str(value or ""))
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", "."))
    except InvalidOperation:
        return None


def _clean(value: str) -> str:
    return str(value or "").replace("**", "").replace("__", "").replace("`", "").strip()


def _normalized(value: str) -> str:
    return _NORMALIZER.sub("", _clean(value).lower())


def _meal_key(value: str) -> str | None:
    normalized = _normalized(value).rstrip(":")
    for key, labels in _MEALS.items():
        if normalized in labels:
            return key
    return None


def _is_total(value: str) -> bool:
    normalized = _normalized(value)
    return normalized in _TOTALS or normalized.startswith("dnev")


def _cells(line: str) -> list[str]:
    return [_clean(cell) for cell in line.strip().strip("|").split("|")]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(not cell or set(cell) <= {"-", ":", " "} for cell in cells)


def _column_key(value: str) -> str | None:
    normalized = _normalized(value)
    for key, aliases in _COLUMN_NAMES.items():
        if normalized in aliases or normalized.startswith(key):
            return key
    return None


def _header_mapping(cells: list[str]) -> dict[str, int] | None:
    mapping = {key: index for index, value in enumerate(cells) if (key := _column_key(value))}
    if not {"protein", "carbs", "fat", "kcal"}.issubset(mapping):
        return None
    if "food" not in mapping:
        candidates = [index for index in range(len(cells)) if index not in mapping.values()]
        if candidates:
            mapping["food"] = candidates[0]
    return mapping if "food" in mapping else None


def _numbers_after(cells: list[str], start: int) -> tuple[str, list[Decimal]]:
    quantity = ""
    values: list[Decimal] = []
    for value in cells[start:]:
        if not _clean(value):
            continue
        parsed = _decimal(value)
        if parsed is None:
            break
        if not quantity and re.search(r"\d\s*(?:g|\u0433|\u0433\u0440|kg|\u043a\u0433|ml|\u043c\u043b|serving|portion|\u043f\u043e\u0440\u0446)", value, re.I):
            quantity = value
        values.append(parsed)
    return quantity, values


def parse_nutrition_day(text: str) -> NutritionDay:
    """Parse renderer-compatible nutrition input into a pure canonical model."""
    mutable_meals: list[dict[str, object]] = []
    totals: list[dict[str, Decimal | None]] = []
    current: dict[str, object] | None = None
    header: dict[str, int] | None = None

    def set_meal(label: str) -> None:
        nonlocal current
        key = _meal_key(label)
        if key is None:
            return
        if current is not None and current["key"] == key:
            return
        current = {"key": key, "label": _clean(label).rstrip(":"), "foods": []}
        mutable_meals.append(current)

    def add_food(name: str, quantity: str, protein: Decimal | None, carbs: Decimal | None,
                 fat: Decimal | None, kcal: Decimal | None) -> None:
        if current is None:
            return
        current["foods"].append(NutritionFood(_clean(name), _clean(quantity), protein, carbs, fat, kcal))  # type: ignore[index]

    def add_total(values: list[Decimal]) -> None:
        if len(values) < 4:
            return
        protein, carbs, fat, kcal = values[-4:]
        totals.append({"protein": protein, "carbs": carbs, "fat": fat, "kcal": kcal})

    def consume_generic(cells: list[str]) -> None:
        index = 0
        while index < len(cells):
            name = _clean(cells[index])
            if not name or _decimal(name) is not None:
                index += 1
                continue
            key = _meal_key(name.rstrip(":"))
            if key is not None:
                set_meal(name)
                index += 1
                continue
            if _is_total(name):
                _, values = _numbers_after(cells, index + 1)
                add_total(values)
                return
            quantity, values = _numbers_after(cells, index + 1)
            if len(values) >= 4:
                protein, carbs, fat, kcal = values[-4:]
                add_food(name, quantity, protein, carbs, fat, kcal)
                index += 1
                while index < len(cells) and (_decimal(cells[index]) is not None or not _clean(cells[index])):
                    index += 1
                continue
            index += 1

    def consume_mapped(cells: list[str], mapping: dict[str, int]) -> None:
        def value(key: str) -> str:
            index = mapping.get(key)
            return cells[index] if index is not None and index < len(cells) else ""

        meal = value("meal")
        food = value("food")
        if _is_total(meal) or _is_total(food):
            add_total([value for value in (_decimal(value(key)) for key in ("protein", "carbs", "fat", "kcal")) if value is not None])
            return
        if meal and _meal_key(meal):
            set_meal(meal)
        if _meal_key(food):
            return
        quantity = value("quantity")
        if not quantity:
            quantity_match = re.search(r"\d+(?:[.,]\d+)?\s*(?:g|\u0433|\u0433\u0440|kg|\u043a\u0433|ml|\u043c\u043b)", food, re.I)
            quantity = quantity_match.group(0) if quantity_match else ""
        add_food(food, quantity, _decimal(value("protein")), _decimal(value("carbs")),
                 _decimal(value("fat")), _decimal(value("kcal")))

    for raw_line in str(text or "").replace("\r", "").splitlines():
        line = _clean(raw_line)
        if not line:
            continue
        if "|" in line:
            cells = _cells(line)
            if _is_separator(cells):
                continue
            mapping = _header_mapping(cells)
            if mapping is not None:
                header = mapping
                continue
            if header is not None and len(cells) >= max(header.values()) + 1:
                consume_mapped(cells, header)
            else:
                consume_generic(cells)
            continue
        if _meal_key(line.rstrip(":")):
            set_meal(line)
            continue
        if _is_total(line):
            add_total([Decimal(number.replace(",", ".")) for number in _NUMBER.findall(line)])
            continue
        numbers = [Decimal(number.replace(",", ".")) for number in _NUMBER.findall(line)]
        if current is not None and len(numbers) >= 4 and re.search(r"(?:g|\u0433|kcal|\u043a\u043a\u0430\u043b|protein|\u043f\u0440\u043e\u0442\u0435\u0438\u043d)", line, re.I):
            first_number = re.search(r"\d", line)
            if first_number:
                name = line[:first_number.start()].rstrip(" -–—,:;")
                quantity_match = re.search(r"\d+(?:[.,]\d+)?\s*(?:g|\u0433|\u0433\u0440|kg|\u043a\u0433|ml|\u043c\u043b)", line, re.I)
                protein, carbs, fat, kcal = numbers[-4:]
                add_food(name, quantity_match.group(0) if quantity_match else "", protein, carbs, fat, kcal)

    meals = tuple(NutritionMeal(meal["key"], meal["label"], tuple(meal["foods"])) for meal in mutable_meals)  # type: ignore[arg-type]
    return NutritionDay(meals, tuple(totals))


def targets_from_profile_block(profile_block: str) -> NutritionTargets | None:
    """Read only explicitly emitted production targets; never derive macro targets."""
    text = str(profile_block or "")

    def target(pattern: str) -> Decimal | None:
        match = re.search(pattern, text, re.I)
        return _decimal(match.group(1)) if match else None

    kcal = target(r"(?:calorie\s+target|\u043a\u0430\u043b\u043e\u0440\u0438\u0435\u043d\s+\u0442\u0430\u0440\u0433\u0435\u0442)\s*:\s*([\d\s,]+)\s*(?:kcal|\u043a\u043a\u0430\u043b)")
    if kcal is None or kcal <= 0:
        return None
    protein = target(r"(?:protein\s+target|\u043f\u0440\u043e\u0442\u0435\u0438\u043d\s+\u0442\u0430\u0440\u0433\u0435\u0442)\s*:\s*(?:minimum\s+)?([\d\s,]+)\s*(?:g|\u0433)")
    carbs = target(r"(?:carb(?:ohydrate)?s?\s+target|\u0432\u044a\u0433\u043b\u0435\u0445\u0438\u0434\u0440\u0430\u0442\u0435\u043d\s+\u0442\u0430\u0440\u0433\u0435\u0442)\s*:\s*([\d\s,]+)\s*(?:g|\u0433)")
    fat = target(r"(?:fat\s+target|\u043c\u0430\u0437\u043d\u0438\u043d\u0435\u043d\s+\u0442\u0430\u0440\u0433\u0435\u0442)\s*:\s*([\d\s,]+)\s*(?:g|\u0433)")
    return NutritionTargets(kcal, protein, carbs, fat)


def is_full_day_request(message: str, history: object = None) -> bool:
    text = str(message or "")
    if any(pattern.search(text) for pattern in _DIRECT_FULL_DAY):
        return True
    if not _CONTEXTUAL_FULL_DAY.search(text):
        return False
    turns = history[-2:] if isinstance(history, list) else []
    return any(_NUTRITION_CONTEXT.search(str(turn.get("content", "")))
               for turn in turns if isinstance(turn, dict))


def generation_contract(targets: NutritionTargets) -> str:
    """Return the strict delivery contract using only authoritative targets."""
    required = [f"{targets.kcal} kcal"]
    if targets.protein is not None:
        required.append(f"{targets.protein}g protein")
    if targets.carbs is not None:
        required.append(f"{targets.carbs}g carbs")
    if targets.fat is not None:
        required.append(f"{targets.fat}g fat")
    return (
        "[DAILY NUTRITION DELIVERY CONTRACT]\n"
        "Return one complete pipe-delimited daily plan. Include Breakfast, optional Snack, Lunch, optional Snack, Dinner in chronological order. "
        "Each food needs a name, quantity, protein, carbs, fat, and kcal. Include exactly one Daily Total row. "
        "Do not add instructions to increase food, portions, or calories.\n"
        f"Required daily totals: {'; '.join(required)}."
    )


def failure_message(lang: str) -> str:
    if str(lang).lower() == "bg":
        return "\u041d\u0435 \u0443\u0441\u043f\u044f\u0445 \u0434\u0430 \u0441\u044a\u0437\u0434\u0430\u043c \u043f\u044a\u043b\u0435\u043d \u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d \u043f\u043b\u0430\u043d, \u043a\u043e\u0439\u0442\u043e \u043e\u0442\u0433\u043e\u0432\u0430\u0440\u044f \u043d\u0430 \u0442\u0435\u043a\u0443\u0449\u0438\u0442\u0435 \u0442\u0438 \u0446\u0435\u043b\u0438. \u041c\u043e\u043b\u044f, \u043e\u043f\u0438\u0442\u0430\u0439 \u043e\u0442\u043d\u043e\u0432\u043e."
    return "Unable to generate a nutritionally complete plan.\nPlease try again."


def _reconciliation_tolerance(field: str, declared: Decimal) -> Decimal:
    return max(Decimal("10"), abs(declared) * Decimal("0.01")) if field == "kcal" else Decimal("1.0")


def validate_daily_nutrition(text: str, targets: NutritionTargets) -> NutritionValidationResult:
    """Validate a complete daily nutrition plan without side effects or model access."""
    failures: list[str] = []
    if any(pattern.search(str(text or "")) for pattern in _PROHIBITED_COMPLETION_GUIDANCE):
        failures.append("Plan includes prohibited completion guidance.")

    day = parse_nutrition_day(text)
    foods_by_meal = {key: [] for key in _MEALS}
    meal_sequence: list[str] = []
    for meal in day.meals:
        foods_by_meal[meal.key].extend(meal.foods)
        if meal.foods:
            meal_sequence.append(meal.key)

    for key in ("breakfast", "lunch", "dinner"):
        if not foods_by_meal[key]:
            failures.append(f"Missing {key}.")

    phase = 0
    seen_primary: set[str] = set()
    snack_phase: set[int] = set()
    for key in meal_sequence:
        if key == "breakfast":
            if phase != 0:
                failures.append("Meals are not in chronological order.")
            if key in seen_primary:
                failures.append("Duplicate meal: breakfast.")
            seen_primary.add(key)
            phase = 1
        elif key == "snack":
            if phase not in (1, 3) or phase in snack_phase:
                failures.append("Meals are not in chronological order.")
            snack_phase.add(phase)
        elif key == "lunch":
            if phase not in (1, 3):
                failures.append("Meals are not in chronological order.")
            if key in seen_primary:
                failures.append("Duplicate meal: lunch.")
            seen_primary.add(key)
            phase = 3
        elif key == "dinner":
            if phase not in (3, 5):
                failures.append("Meals are not in chronological order.")
            if key in seen_primary:
                failures.append("Duplicate meal: dinner.")
            seen_primary.add(key)
            phase = 5

    sums = {"protein": Decimal("0"), "carbs": Decimal("0"), "fat": Decimal("0"), "kcal": Decimal("0")}
    for key, foods in foods_by_meal.items():
        for food in foods:
            if not food.name:
                failures.append(f"{key.title()} has a food without a name.")
            if not food.quantity or _decimal(food.quantity) is None:
                failures.append(f"{key.title()} has a food without quantity.")
            values = {"protein": food.protein, "carbs": food.carbs, "fat": food.fat, "kcal": food.kcal}
            for field, value in values.items():
                if value is None or (field == "kcal" and value <= 0) or (field != "kcal" and value < 0):
                    failures.append(f"{key.title()} has a food without {field}.")
                else:
                    sums[field] += value

    if not day.declared_totals:
        failures.append("Missing daily totals.")
    elif len(day.declared_totals) != 1:
        failures.append("Duplicate daily totals.")
    else:
        totals = day.declared_totals[0]
        for field, total in totals.items():
            if total is None:
                failures.append("Daily totals are incomplete.")
                continue
            if abs(sums[field] - total) > _reconciliation_tolerance(field, total):
                failures.append(f"Daily {field} total does not equal meal totals.")
        target_values = {"kcal": targets.kcal, "protein": targets.protein, "carbs": targets.carbs, "fat": targets.fat}
        names = {"kcal": "Calories", "protein": "Protein", "carbs": "Carbs", "fat": "Fat"}
        for field, target in target_values.items():
            total = totals.get(field)
            if target is not None and total is not None and abs(total - target) > target * Decimal("0.05"):
                failures.append(f"{names[field]} outside 5% of target.")

    return NutritionValidationResult(not failures, tuple(dict.fromkeys(failures)))
