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
    re.compile(r"\b(?:meal\s+plan(?:\s+for\s+(?:today|fat\s+loss))?|daily\s+(?:meal|nutrition)\s+plan|full[- ]day\s+(?:meal|nutrition)\s+plan|meal\s+menu\s+for\s+today|nutrition\s+plan\s+for\s+today|alternative\s+meal\s+plan|alternative\s+daily\s+menu|complete\s+daily\s+meal\s+plan|give\s+me\s+(?:a\s+)?diet|make\s+me\s+(?:a\s+)?menu|what\s+should\s+i\s+eat\s+today|give\s+me\s+another\s+diet|make\s+(?:a\s+)?plan\s+for\s+my\s+day)\b", re.I),
    re.compile(r"(?:\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+\u043f\u043b\u0430\u043d(?:\s+\u0437\u0430\s+\u0434\u0435\u043d\u044f|\s+\u0437\u0430\s+\u043c\u0435\u043d)?|\u0434\u043d\u0435\u0432\u0435\u043d\s+\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+(?:\u043f\u043b\u0430\u043d|\u0440\u0435\u0436\u0438\u043c)|\u043c\u0435\u043d\u044e\s+\u0437\u0430\s+(?:\u0434\u043d\u0435\u0441|\u0441\u0432\u0430\u043b\u044f\u043d\u0435\s+\u043d\u0430\s+\u043c\u0430\u0437\u043d\u0438\u043d\u0438)|(?:\u0438\u0441\u043a\u0430\u043c\s+)?\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+\u0440\u0435\u0436\u0438\u043c|\u0434\u0440\u0443\u0433\s+\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+\u0440\u0435\u0436\u0438\u043c|\u0430\u043b\u0442\u0435\u0440\u043d\u0430\u0442\u0438\u0432\u0435\u043d\s+\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+\u043f\u043b\u0430\u043d|\u0430\u043b\u0442\u0435\u0440\u043d\u0430\u0442\u0438\u0432\u043d\u043e\s+\u0434\u043d\u0435\u0432\u043d\u043e\s+\u043c\u0435\u043d\u044e|\u043f\u044a\u043b\u0435\u043d\s+\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+\u043f\u043b\u0430\u043d|\u0438\u0441\u043a\u0430\u043c\s+\u0440\u0435\u0436\u0438\u043c\s+\u0437\u0430\s+\u043e\u0442\u0441\u043b\u0430\u0431\u0432\u0430\u043d\u0435|\u043a\u0430\u043a\u0432\u043e\s+\u0434\u0430\s+\u044f\u043c\s+\u043f\u0440\u0435\u0437\s+\u0434\u0435\u043d\u044f|(?:\u0434\u0430\u0439|\u043d\u0430\u043f\u0440\u0430\u0432\u0438)\s+\u043c\u0438\s+(?:\u0434\u043d\u0435\u0432\u043d\u043e\s+)?\u043c\u0435\u043d\u044e|\u0438\u0441\u043a\u0430\u043c\s+\u0434\u0440\u0443\u0433\u043e\s+\u043c\u0435\u043d\u044e|\u043d\u0430\u043f\u0440\u0430\u0432\u0438\s+\u043c\u0438\s+\u0434\u0440\u0443\u0433\s+\u0440\u0435\u0436\u0438\u043c)", re.I),
)
_CONTEXTUAL_FULL_DAY = re.compile(r"\b(?:another\s+meal\s+plan)\b|\u0438\u0441\u043a\u0430\u043c\s+\u0434\u0440\u0443\u0433\s+\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b\u0435\u043d\s+\u0440\u0435\u0436\u0438\u043c", re.I)
_NUTRITION_CONTEXT = re.compile(r"\b(?:nutrition|meal\s+plan|daily\s+menu|kcal|calorie|protein)\b|\u0445\u0440\u0430\u043d\u0438\u0442\u0435\u043b|\u043c\u0435\u043d\u044e|\u043a\u0430\u043b\u043e\u0440|\u043f\u0440\u043e\u0442\u0435\u0438\u043d", re.I)
_QUANTITY_ONLY = re.compile(
    r"^\s*\d+(?:[.,]\d+)?\s*(?:g|\u0433|\u0433\u0440|kg|\u043a\u0433|ml|\u043c\u043b|"
    r"pcs?\.?|\u0431\u0440\.?|\u0431\u0440\u043e\u0439|servings?|portions?|\u043f\u043e\u0440\u0446\u0438\u044f|\u043f\u043e\u0440\u0446\u0438\u0438|"
    r"medium|large|small|\u0441\u0440\u0435\u0434\u0435\u043d|\u0433\u043e\u043b\u044f\u043c|\u043c\u0430\u043b\u044a\u043a)\s*$",
    re.I,
)
_SUPPORTED_QUANTITY = _QUANTITY_ONLY
_PREPARATION_ONLY = frozenset({
    "boiled", "cooked", "grilled", "fried", "baked", "roasted",
    "\u0441\u0432\u0430\u0440\u0435\u043d", "\u0441\u0432\u0430\u0440\u0435\u043d\u043e", "\u043f\u0435\u0447\u0435\u043d", "\u043f\u0435\u0447\u0435\u043d\u043e", "\u0432\u0430\u0440\u0435\u043d", "\u043f\u044a\u0440\u0436\u0435\u043d", "\u043d\u0430 \u0441\u043a\u0430\u0440\u0430",
})
_VAGUE_FOOD_NAMES = frozenset({
    "protein", "carbs", "vegetables", "meat", "fruit", "snack", "optional",
    "one serving", "one bowl", "any fruit", "food of choice", "something light",
    "\u0435\u0434\u043d\u0430 \u043f\u043e\u0440\u0446\u0438\u044f", "\u0435\u0434\u043d\u0430 \u043a\u0443\u043f\u0438\u0447\u043a\u0430", "\u043f\u043e \u0438\u0437\u0431\u043e\u0440", "\u043d\u044f\u043a\u0430\u043a\u044a\u0432 \u043f\u043b\u043e\u0434", "\u043f\u0440\u043e\u0442\u0435\u0438\u043d", "\u0437\u0435\u043b\u0435\u043d\u0447\u0443\u0446\u0438",
})


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
    computed_totals: tuple[tuple[str, Decimal], ...] = ()
    validation_metadata: tuple[str, ...] = ()


@dataclass(frozen=True)
class NutritionValidationResult:
    valid: bool
    failures: tuple[str, ...]
    day: NutritionDay | None = None
    delivery: str | None = None


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
    return normalized in _TOTALS or normalized.startswith(("dnev", "\u0434\u043d\u0435\u0432"))


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
        if not quantity and re.search(
                r"\d\s*(?:g|\u0433|\u0433\u0440|kg|\u043a\u0433|ml|\u043c\u043b|pcs?\.?|\u0431\u0440\.?|"
                r"serving|portion|\u043f\u043e\u0440\u0446\u0438\u044f|\u043f\u043e\u0440\u0446\u0438\u0438|medium|large|small)", value, re.I):
            quantity = value
        values.append(parsed)
    return quantity, values


def _is_quantity_only(value: str) -> bool:
    return bool(_QUANTITY_ONLY.fullmatch(_clean(value)))


def _food_name_failure(name: str) -> str | None:
    clean = _clean(name).strip("| -–—,:;")
    normalized = clean.lower()
    if not clean:
        return "food without a name"
    if _is_quantity_only(clean) or (not _NORMALIZER.sub("", clean)):
        return "food name is a quantity"
    if normalized in _PREPARATION_ONLY:
        return "food name is preparation only"
    if normalized in _VAGUE_FOOD_NAMES:
        return "food name is too vague"
    if normalized.startswith(("vegetables", "\u0437\u0435\u043b\u0435\u043d\u0447\u0443\u0446\u0438")) and ":" not in clean:
        return "food name is too vague"
    return None


def _food_quantity_failure(quantity: str) -> bool:
    return not _SUPPORTED_QUANTITY.fullmatch(_clean(quantity))


def _source_fragment_failures(text: str) -> list[str]:
    """Find standalone quantity/preparation cards that the permissive parser may skip."""
    failures: list[str] = []
    pending_named_food = False
    for raw_line in str(text or "").replace("\r", "").splitlines():
        line = _clean(raw_line)
        if not line:
            continue
        cells = _cells(line) if "|" in line else [line]
        if _is_separator(cells) or _header_mapping(cells) is not None:
            continue
        candidates = [cell for cell in cells if _clean(cell)]
        if not candidates:
            continue
        meal_row = _meal_key(candidates[0].rstrip(":")) is not None
        if meal_row:
            if "|" in line and len(cells) > 1 and not _clean(cells[1]):
                continue
            candidates = candidates[1:]
        if not candidates or _is_total(candidates[0]):
            continue
        candidate = _clean(candidates[0])
        if _is_quantity_only(candidate):
            if pending_named_food:
                pending_named_food = False
            else:
                failures.append("Dangling quantity without a food name.")
        elif candidate.lower() in _PREPARATION_ONLY:
            if not pending_named_food:
                failures.append("Dangling preparation without a food name.")
        elif "|" not in line:
            pending_named_food = True
        else:
            pending_named_food = False
    return failures


_NUTRITION_VALUE_HEADINGS = {"хранителнастойност", "nutritionvalue", "nutritionvalues", "nutritionfacts"}


def _totals_from_meals(meals: tuple[NutritionMeal, ...]) -> tuple[tuple[str, Decimal], ...]:
    totals = {"protein": Decimal("0"), "carbs": Decimal("0"), "fat": Decimal("0"), "kcal": Decimal("0")}
    for meal in meals:
        for food in meal.foods:
            for key, value in (("protein", food.protein), ("carbs", food.carbs),
                               ("fat", food.fat), ("kcal", food.kcal)):
                if value is not None:
                    totals[key] += value
    return tuple((key, totals[key]) for key in ("protein", "carbs", "fat", "kcal"))


def _parse_multiline_label_value(text: str) -> NutritionDay:
    """Parse the label/value format as one strict state machine.

    A malformed block is retained as a food or meal plus metadata.  Validation can
    therefore reject the whole plan without silently dropping the evidence that
    made it malformed.
    """
    lines = [_clean(line) for line in str(text or "").replace("\r", "").splitlines()]
    lines = [line for line in lines if line]
    meals: list[dict[str, object]] = []
    declared: list[dict[str, Decimal | None]] = []
    metadata: list[str] = []
    current: dict[str, object] | None = None
    index = 0

    def next_line(offset: int) -> str:
        return lines[offset] if offset < len(lines) else ""

    def add_meal(label: str) -> None:
        nonlocal current
        key = _meal_key(label.rstrip(":"))
        current = {"key": key, "label": label.rstrip(":"), "foods": []}
        meals.append(current)

    def add_food(name: str, quantity: str, values: dict[str, Decimal | None]) -> None:
        if current is None:
            metadata.append("Food block appears before a meal heading.")
            return
        current["foods"].append(NutritionFood(
            name, quantity, values.get("protein"), values.get("carbs"),
            values.get("fat"), values.get("kcal")))

    while index < len(lines):
        line = lines[index]
        if _meal_key(line.rstrip(":")):
            add_meal(line)
            index += 1
            continue
        if _is_total(line):
            values: dict[str, Decimal | None] = {}
            index += 1
            for expected in ("protein", "carbs", "fat", "kcal"):
                label = next_line(index)
                if _column_key(label) != expected:
                    metadata.append(f"Malformed daily totals: expected {expected} label before value.")
                    break
                value = next_line(index + 1)
                parsed = _decimal(value)
                if parsed is None:
                    metadata.append(f"Malformed daily totals: missing {expected} value.")
                    break
                values[expected] = parsed
                index += 2
            if len(values) == 4:
                declared.append(values)
            else:
                while index < len(lines) and not _meal_key(lines[index].rstrip(":")):
                    index += 1
            continue
        if current is None:
            index += 1
            continue

        name = line
        quantity = next_line(index + 1)
        values: dict[str, Decimal | None] = {}
        if not quantity or _meal_key(quantity.rstrip(":")) or _is_total(quantity):
            metadata.append(f"Malformed food block for {name}: missing quantity.")
            add_food(name, "", values)
            index += 1
            continue
        marker = next_line(index + 2)
        if _normalized(marker) not in _NUTRITION_VALUE_HEADINGS:
            metadata.append(f"Malformed food block for {name}: missing nutrition-value heading.")
            add_food(name, quantity, values)
            index += 2
            continue
        cursor = index + 3
        complete = True
        for expected in ("protein", "carbs", "fat", "kcal"):
            label = next_line(cursor)
            if _column_key(label) != expected:
                metadata.append(f"Malformed food block for {name}: expected {expected} label before value.")
                complete = False
                break
            value = next_line(cursor + 1)
            parsed = _decimal(value)
            if parsed is None:
                metadata.append(f"Malformed food block for {name}: missing {expected} value.")
                complete = False
                break
            values[expected] = parsed
            cursor += 2
        add_food(name, quantity, values)
        index = cursor if complete else max(cursor, index + 3)

    parsed_meals = tuple(NutritionMeal(
        str(meal["key"]), str(meal["label"]), tuple(meal["foods"])) for meal in meals)
    return NutritionDay(parsed_meals, tuple(declared), _totals_from_meals(parsed_meals), tuple(metadata))


def parse_nutrition_day(text: str) -> NutritionDay:
    """Parse renderer-compatible nutrition input into a pure canonical model."""
    if any(_normalized(line) in _NUTRITION_VALUE_HEADINGS
           for line in str(text or "").replace("\r", "").splitlines()):
        return _parse_multiline_label_value(text)
    mutable_meals: list[dict[str, object]] = []
    totals: list[dict[str, Decimal | None]] = []
    current: dict[str, object] | None = None
    header: dict[str, int] | None = None
    pending_name = ""
    pending_preparation = ""

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
            if pending_name:
                first = next((index for index, cell in enumerate(cells) if _clean(cell)), None)
                if first is not None and _is_quantity_only(cells[first]):
                    cells[first] = pending_name + (", " + pending_preparation if pending_preparation else "")
                    cells.insert(first + 1, _clean(raw_line).strip().strip("|").split("|")[first].strip())
                pending_name = ""
                pending_preparation = ""
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
                pending_name = ""
                pending_preparation = ""
                continue
        if current is not None and not _is_total(line):
            if line.lower() in _PREPARATION_ONLY and pending_name:
                pending_preparation = line
            elif not _is_quantity_only(line):
                pending_name = line
                pending_preparation = ""

    meals = tuple(NutritionMeal(meal["key"], meal["label"], tuple(meal["foods"])) for meal in mutable_meals)  # type: ignore[arg-type]
    return NutritionDay(meals, tuple(totals), _totals_from_meals(meals))


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
    if _CONTEXTUAL_FULL_DAY.search(text):
        turns = history[-2:] if isinstance(history, list) else []
        return any(_NUTRITION_CONTEXT.search(str(turn.get("content", "")))
                   for turn in turns if isinstance(turn, dict))
    if any(pattern.search(text) for pattern in _DIRECT_FULL_DAY):
        return True
    return False


def appears_complete_daily_plan(text: str) -> bool:
    """Return true only for responses that carry strong daily-plan evidence."""
    lines = [_clean(line) for line in str(text or "").replace("\r", "").splitlines() if _clean(line)]
    cells_by_line = [_cells(line) if "|" in line else [line] for line in lines]
    meal_count = sum(1 for cells in cells_by_line
                     if any(_meal_key(cell.rstrip(":")) for cell in cells))
    macro_count = sum(1 for cells in cells_by_line for cell in cells
                      if _column_key(cell) in {"protein", "carbs", "fat", "kcal"})
    total_present = any(_is_total(cell) for cells in cells_by_line for cell in cells)
    quantity_count = sum(1 for cells in cells_by_line for cell in cells
                         if _SUPPORTED_QUANTITY.fullmatch(cell))
    return meal_count >= 2 and (macro_count >= 3 or total_present or quantity_count >= 2)


def _format_decimal(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def serialize_nutrition_day(day: NutritionDay) -> str:
    """Deliver only the same canonical model that passed deterministic validation."""
    computed = dict(day.computed_totals)
    lines = [
        "| Meal | Food | Quantity | Protein (g) | Carbs (g) | Fat (g) | Kcal |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for meal in day.meals:
        for position, food in enumerate(meal.foods):
            lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(
                meal.label if position == 0 else "", food.name, food.quantity,
                _format_decimal(food.protein or Decimal("0")),
                _format_decimal(food.carbs or Decimal("0")),
                _format_decimal(food.fat or Decimal("0")),
                _format_decimal(food.kcal or Decimal("0")),
            ))
    lines.append("| Daily Total | | | {} | {} | {} | {} |".format(
        _format_decimal(computed.get("protein", Decimal("0"))),
        _format_decimal(computed.get("carbs", Decimal("0"))),
        _format_decimal(computed.get("fat", Decimal("0"))),
        _format_decimal(computed.get("kcal", Decimal("0"))),
    ))
    return "\n".join(lines)


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
        "Each food needs an explicit food name, numeric quantity with a supported unit/count, protein, carbs, fat, and kcal. "
        "Never output a quantity or preparation as a separate food: write 'Whole eggs | 2 pcs' and 'Rice, cooked | 200 g'. "
        "Never use placeholders such as protein, vegetables, food of choice, or any fruit. Include exactly one Daily Total row. "
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
    failures.extend(day.validation_metadata)
    failures.extend(_source_fragment_failures(text))
    foods_by_meal = {key: [] for key in _MEALS}
    meal_sequence: list[str] = []
    for meal in day.meals:
        foods_by_meal[meal.key].extend(meal.foods)
        meal_sequence.append(meal.key)
        if not meal.foods:
            failures.append(f"Empty meal: {meal.key}.")

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

    sums = dict(day.computed_totals)
    for key, foods in foods_by_meal.items():
        for food in foods:
            name_failure = _food_name_failure(food.name)
            if name_failure:
                failures.append(f"{key.title()} has a {name_failure}.")
            if not food.quantity or _decimal(food.quantity) is None:
                failures.append(f"{key.title()} has a food without quantity.")
            elif _food_quantity_failure(food.quantity):
                failures.append(f"{key.title()} has a food with an unsupported quantity unit.")
            values = {"protein": food.protein, "carbs": food.carbs, "fat": food.fat, "kcal": food.kcal}
            for field, value in values.items():
                if value is None or (field == "kcal" and value <= 0) or (field != "kcal" and value < 0):
                    failures.append(f"{key.title()} has a food without {field}.")
                else:
                    pass

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
            target = getattr(targets, field)
            if target is not None and abs(total - target) > target * Decimal("0.05"):
                failures.append(f"{ {'kcal': 'Calories', 'protein': 'Protein', 'carbs': 'Carbs', 'fat': 'Fat'}[field] } outside 5% of target.")
    target_values = {"kcal": targets.kcal, "protein": targets.protein, "carbs": targets.carbs, "fat": targets.fat}
    names = {"kcal": "Calories", "protein": "Protein", "carbs": "Carbs", "fat": "Fat"}
    for field, target in target_values.items():
        if target is not None and abs(sums.get(field, Decimal("0")) - target) > target * Decimal("0.05"):
            failures.append(f"{names[field]} outside 5% of target.")

    unique_failures = tuple(dict.fromkeys(failures))
    return NutritionValidationResult(
        not unique_failures, unique_failures, day,
        serialize_nutrition_day(day) if not unique_failures else None,
    )
