# Food Catalog V1 Provenance

## Scope

`food_catalog_v1.json` is an isolated development catalog for Nutrition Engine
V2. It is not a production catalog, clinical policy, or runtime dependency.
Every record has `NUTRIENTS_REVIEWED` status: nutrient values and preparation
states were transcribed from the identified source record; portion bounds remain
`TEST_POLICY_ONLY` and prevent a `PRODUCTION_READY` designation.

## Primary sources and reuse

* USDA FoodData Central, [downloadable datasets](https://fdc.nal.usda.gov/download-datasets/)
  * FNDDS 2021-2023 JSON release, 2024-10-31.
  * Foundation Foods JSON release, 2026-04-30.
* FoodData Central states that the data are public domain / CC0 and requests
  source attribution: [API guide](https://fdc.nal.usda.gov/api-guide/) and
  [FoodData Central](https://fdc.nal.usda.gov/).

The dataset type, FDC ID, and release date are retained in each record. FDC
records provide nutrient values per 100 g edible portion. The catalog preserves
the source Energy (nutrient 208), protein (203), carbohydrate (205), and total
fat (204) values without recalculation.

## Review and calorie-consistency policy

The development catalog accepts a maximum absolute difference of **15 kcal per
100 g** between the source Energy value and `4 * protein + 4 * carbohydrate +
9 * fat`. This permits source rounding and FDC food-data conversion conventions;
it never rewrites source Energy. A larger difference is rejected as an
unexplained material deviation. This is catalog data-quality policy only, not a
nutrition target or medical rule.

## Record mapping

| Catalog record | Dataset | FDC record | Preparation/data basis |
| --- | --- | --- | --- |
| `dev_chicken_breast_cooked` | FNDDS 2021-2023 | 2705956 | baked/broiled/roasted, skin not eaten |
| `dev_lean_beef_cooked` | Foundation 04/2026 | 746758 | cooked roasted, trimmed lean only |
| `dev_white_fish_cooked` | FNDDS 2021-2023 | 2706325 | baked or broiled |
| `dev_whole_egg_boiled` | FNDDS 2021-2023 | 2707154 | boiled or poached; FDC portion is 50 g/egg |
| `dev_egg_whites` | Foundation 04/2026 | 323697 | raw frozen pasteurized |
| `dev_greek_yogurt_2pct` | FNDDS 2021-2023 | 2705423 | plain low-fat milk category |
| `dev_cottage_cheese` | FNDDS 2021-2023 | 2705749 | farmer's cottage cheese |
| `dev_oats_dry` | FNDDS 2021-2023 | 2708489 | raw oats |
| `dev_rice_cooked` | FNDDS 2021-2023 | 2708402 | cooked rice, NFS |
| `dev_potatoes_boiled` | FNDDS 2021-2023 | 2709385 | boiled potato, NFS |
| `dev_wholegrain_bread` | FNDDS 2021-2023 | 2707709 | whole-wheat bread |
| `dev_banana` | FNDDS 2021-2023 | 2709224 | raw banana |
| `dev_apple` | FNDDS 2021-2023 | 2709215 | raw apple |
| `dev_broccoli_cooked` | FNDDS 2021-2023 | 2709644 | restaurant-cooked broccoli |
| `dev_tomatoes` | FNDDS 2021-2023 | 2709719 | raw tomatoes |
| `dev_cucumber` | FNDDS 2021-2023 | 2709784 | raw cucumber with peel |
| `dev_mixed_salad` | FNDDS 2021-2023 | 2709719 + 2709784 + 2709789 | deterministic equal-weight raw mix |
| `dev_olive_oil` | FNDDS 2021-2023 | 2710186 | plain olive oil, gram-only catalog unit |
| `dev_avocado` | FNDDS 2021-2023 | 2709223 | raw avocado |
| `dev_almonds` | FNDDS 2021-2023 | 2707486 | unroasted almonds |

The mixed-salad record is explicitly a fixed mathematical composite of three
cited source records, not an inferred recipe. It remains development-only.

## Unit and portion governance

Nutrition values are keyed to grams. A `pcs` display unit is permitted only for
a record with a reviewed `grams_per_piece`; the boiled egg uses the FDC 50 g
portion. No record uses milliliters in this catalog, so the engine does not
infer food density. All min/max/default/increment values are caller-test inputs
labeled `TEST_POLICY_ONLY`, pending product and clinical policy approval.

## Phase 3 expansion

Phase 3 extends the development catalog to 45 `NUTRIENTS_REVIEWED` records.
New records use FNDDS 2021-2023 (2024-10-31), Foundation Foods (2026-04-30),
or SR Legacy (2018-04) FDC identifiers retained in each JSON record. The
expansion includes turkey, lean pork, salmon, tuna, nonfat Greek yogurt, milk,
legumes, firm tofu, cooked grains, sweet potato, berries, orange, walnuts, and
additional vegetables. Firm tofu (172448) and cooked zucchini (169292) are
SR Legacy records because no exact newer-download record was available.

Pumpkin seeds (2707581) and peanut butter (2707537) were deliberately excluded:
their source Energy values exceeded the catalog's documented macro-consistency
tolerance. Source kcal values were not changed to force admission.

## Known limitations — why this blocks runtime integration

These results are recorded here so the foundation is not mistaken for a
shippable capability.

**Coverage.** Across the 100-scenario development matrix (60-120 kg, fat-loss
and maintenance shapes, with periodic no-chicken / no-dairy constraints), the
optimizer solves **41 of 100 scenarios (41%)**. The 59 infeasible results are
`CALORIE_TARGET_UNREACHABLE` (51) and `MEAL_STRUCTURE_INFEASIBLE` (8). A 41%
coverage rate is **not acceptable for runtime integration**: most real requests
would return no plan. The cause is the deliberately small 20-record catalog plus
the `TEST_POLICY_ONLY` portion bounds, not a defect in the solver arithmetic.

**The 99 kg case is technical feasibility only.** It demonstrates that the
solver can satisfy 1914 kcal with a 198 g protein floor deterministically. It is
not a plan a coach should hand to a person: it repeats chicken and rice across
both lunch and dinner and drives portions to the development boundary values.
Menu variety, culinary sanity, and portion realism are explicitly out of scope
for this phase.

**Nothing here is production-ready.** No record is `PRODUCTION_READY`; all
records are `NUTRIENTS_REVIEWED` with `TEST_POLICY_ONLY` portion bounds, and
`production_ready=True` loading rejects every current record by design.

### Phase 3 update to these limitations

The 45-record catalog and the candidate builder raise coverage on the supported
matrix to 150/150 (100%), which supersedes the Phase 2 41% figure above for
*supported* requests. It does **not** make the engine runtime-eligible:

* **Technical feasibility is not nutritional approval.** A `feasible` result and
  an `acceptable` quality score mean the solver found portions that hit the
  arithmetic targets without a hard practicality violation. They do not mean the
  plan is nutritionally, medically, or culturally appropriate for a person. That
  judgement is out of scope for this library.
* **The 99 kg result is only a technical solver result** — deterministic,
  1913.5 kcal with protein above the 198 g floor, distinct lunch/dinner protein
  and starch — not a coach-approved menu.
* **Unsupported diets fail closed.** `vegan` requests and requests that exclude
  the entire `protein` category return no candidate plan (the builder yields
  `None` before optimization); the caller must surface a controlled refusal.
  This is intended, not a coverage gap to paper over.
* **Latency is not yet within a runtime budget.** The recorded 200-scenario
  benchmark passed its P95 threshold but the **worst single solve exceeded
  250 ms** (development machine). A user-facing path needs a hard per-request
  time bound before this could be considered.
* **No record is `PRODUCTION_READY`; portion bounds remain `TEST_POLICY_ONLY`;
  the engine is not connected to runtime.**
