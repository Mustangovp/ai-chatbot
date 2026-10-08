# Canonical Movement Studies Expansion

Baseline: `7a96d7ecdbfdccb7b5334efdaad71c4462e529d2`.
Generation uses the built-in image generation tool, with existing approved
protocol artwork as style references. No existing artwork is replaced.

## Reference Rules

All ten existing thumb/protocol pairs were inspected before generation.
Use realistic athletic proportions, black performance clothing, a charcoal gym,
soft directional light, graphite equipment, and restrained red equipment/shoe
accents. Keep the athlete and working equipment clearly separated from the
background. Use eye/torso-height three-quarter or side views appropriate to the
movement, not dramatic wide-angle distortion. The body position must remain
recognizable at 160 x 120. Keep hands, feet, working joints, and equipment inside
the safe 4:3 frame; preserve the same pose between the two output sizes.
No text, logos, watermarks, diagrams, ghost limbs, or decorative overlays.

Outputs: `<exercise_id>--thumb.webp` (320 x 240) and
`<exercise_id>--protocol.webp` (960 x 720). A single reviewed source photograph
per exercise is mechanically resized to both variants, never repurposed for a
different canonical exercise. The existing ten pairs stay byte-for-byte intact.

## Biomechanical Specs / Prompt Set

These are visual specifications from the registry and canonical instruction
catalog, not new prescriptions or training authority.

| Canonical ID | Equipment / Pattern | Required Visible Distinction |
| --- | --- | --- |
| bodyweight.incline_push_up | Bodyweight + bench / horizontal push | Palms on a stable elevated bench, rigid diagonal body, chest approaching bench; not a wall or floor push-up. |
| dumbbell.goblet_squat | One dumbbell / squat | One vertical dumbbell cupped at chest, heels grounded, knees tracking toes; not two front-racked dumbbells. |
| bodyweight.reverse_lunge | Bodyweight / lunge | Rear foot stepped back, rear knee lowered, front heel grounded; no external weights. |
| bodyweight.hip_hinge | Bodyweight / hinge | Hips pushed back, slight knee bend, hands on thighs, neutral back; not a deep squat. |
| dumbbell.row | One dumbbell / horizontal pull | One hand supported on stable bench, one dumbbell pulled toward hip, neutral non-rotating torso; not bilateral bent-over row. |
| band.row | Resistance band / horizontal pull | Secure chest-height anchor ahead, band under tension, standing athlete pulling elbows toward ribs. |
| dumbbell.overhead_press | Two dumbbells / vertical push | Standing strict press with stable straight legs and weights overhead, ribs controlled. |
| dumbbell.seated_press | Two dumbbells + bench / vertical push | Seated on supported backrest, feet grounded, weights overhead; not standing. |
| bodyweight.pull_up | Pull-up bar / vertical pull | Pronated secure bar grip, controlled near-top pull, no kipping or step support. |
| barbell.back_squat | Barbell / squat | Bar supported across upper back, not neck; controlled squat inside rack with safety arms. |
| dumbbell.floor_press | Two dumbbells / horizontal push | Supine on floor, knees bent, feet grounded, upper arms touching floor, forearms vertical. |
| band.chest_press | Resistance band / horizontal push | Secure chest-height anchor behind athlete, staggered stance, hands pressing forward. |
| cable.chest_press | Cable / horizontal push | Two chest-height pulleys behind, two handles pressing forward, stable staggered stance. |
| dumbbell.chest_supported_row | Two dumbbells + bench / horizontal pull | Chest supported on incline bench, feet grounded, elbows pulled beside ribs; no unsupported hinge. |
| cable.seated_row | Cable / horizontal pull | Seated at low cable row, feet on supports, knees soft, handle at lower ribs, upright neutral back. |
| band.lat_pulldown | Resistance band / vertical pull | Secure overhead band anchor, kneeling athlete, elbows pulling down toward ribs. |
| cable.lat_pulldown | Cable / vertical pull | Seated with thigh support, wide bar pulled toward upper chest, no behind-neck pull. |
| dumbbell.split_squat | Two dumbbells / lunge | Stationary split stance, rear forefoot on floor, vertical controlled lowering; no rear-foot elevation. |
| dumbbell.step_up | Two dumbbells + bench / lunge | Full lead foot on stable moderate-height platform, rising through lead leg, no jump. |
| cable.pull_through | Cable / hinge | Athlete faces away from low pulley, rope passes between legs, hinged hips and neutral back. |
| barbell.romanian_deadlift | Barbell / hinge | Soft knees, hips back, bar close below knees but above floor; distinguish from floor-start deadlift. |
| bodyweight.dead_bug | Bodyweight / core anti-extension | Supine opposite arm/leg extended, other hip/knee at 90 degrees, lower back controlled. |
| band.pallof_press | Resistance band / core anti-extension | Chest-height anchor lateral to athlete, both hands pressed forward, torso resists rotation. |
| bodyweight.march_in_place | Bodyweight / monostructural | Upright relaxed stance, one comfortable knee lift, opposite arm forward, no weights or jump. |
| dumbbell.bench_press | Two dumbbells + bench / horizontal push | Supine on flat bench, feet grounded, dumbbells separately above chest. |
| barbell.bench_press | Barbell + bench / horizontal push | Supine beneath rack, bar above chest, safety arms visibly set, feet grounded. |
| bodyweight.negative_pull_up | Pull-up bar / vertical pull | Controlled partially lowered eccentric position, stable reset step beneath feet; distinct from top concentric pull-up. A still image illustrates position, not proof of motion direction. |
| dumbbell.reverse_lunge | Two dumbbells / lunge | Backward step/lowered rear knee, two weights at sides, front heel grounded. |
| barbell.deadlift | Barbell / hinge | Floor-start position with standard plates at floor, bar over midfoot, knees bent more than RDL, neutral back. |
| dumbbell.push_press | Two dumbbells / vertical push | Shallow knee dip with upright torso and two shoulder-racked dumbbells before leg drive; distinguish from strict locked-knee overhead press. |

## QA Gate

Integration is withheld until each source and both resized variants have been
visually inspected for equipment, pose, anatomy, crop safety, readability, and
style. Image-file checks additionally cover format, dimensions, unique contents,
and HTTP availability. Automated coverage is against the current registry, not
a manually frozen list of forty IDs.

## Generation and Review Record

Mode: built-in reference-guided image edits, saved non-destructively. Each
exercise has its own generated source; no source is aliased to another ID.
The shared prompt retains the reference's charcoal gym, directional lighting,
black unbranded clothing and restrained red accents. Each row's specification
above supplies the movement-specific pose and equipment. The shared negative
prompt excludes text, logos, watermarks, extra people, diagrams, motion ghosts,
clipped working joints and brand-shaped footwear marks.

Sources and both exported variants were visually reviewed. Contact sheets also
checked the protocol artwork at its actual 160 x 120 display size. WebP exports
use Lanczos resizing, quality 86 and method 6, with no pose-changing crop.
All 30 sources and 60 exports passed the visual gate. Rejected intermediate
outputs were not integrated: footwear branding was removed from Goblet Squat,
Floor Press, March and Incline Push-Up; Band Row and Overhead Press were
reframed; Dead Bug limb coordination and Pallof anchor geometry were corrected.

| Canonical ID | Approved Style Reference | Source / Thumb / Protocol QA |
| --- | --- | --- |
| `dumbbell.goblet_squat` | `dumbbell.front_squat--protocol.webp` | PASS |
| `dumbbell.floor_press` | `bodyweight.glute_bridge--protocol.webp` | PASS |
| `bodyweight.march_in_place` | `bodyweight.wall_push_up--protocol.webp` | PASS |
| `bodyweight.incline_push_up` | `bodyweight.wall_push_up--protocol.webp` | PASS |
| `bodyweight.reverse_lunge` | `bodyweight.squat--protocol.webp` | PASS |
| `bodyweight.hip_hinge` | `dumbbell.romanian_deadlift--protocol.webp` | PASS |
| `dumbbell.row` | `dumbbell.bent_over_row--protocol.webp` | PASS |
| `band.row` | `dumbbell.bent_over_row--protocol.webp` | PASS |
| `dumbbell.overhead_press` | `dumbbell.front_squat--protocol.webp` | PASS |
| `dumbbell.seated_press` | `bodyweight.glute_bridge--protocol.webp` | PASS |
| `bodyweight.pull_up` | `bodyweight.table_row--protocol.webp` | PASS |
| `barbell.back_squat` | `bodyweight.squat--protocol.webp` | PASS |
| `band.chest_press` | `bodyweight.wall_push_up--protocol.webp` | PASS |
| `cable.chest_press` | `bodyweight.wall_push_up--protocol.webp` | PASS |
| `dumbbell.chest_supported_row` | `dumbbell.bent_over_row--protocol.webp` | PASS |
| `cable.seated_row` | `bodyweight.table_row--protocol.webp` | PASS |
| `band.lat_pulldown` | `bodyweight.wall_push_up--protocol.webp` | PASS |
| `cable.lat_pulldown` | `dumbbell.bent_over_row--protocol.webp` | PASS |
| `dumbbell.split_squat` | `dumbbell.front_squat--protocol.webp` | PASS |
| `dumbbell.step_up` | `bodyweight.squat--protocol.webp` | PASS |
| `cable.pull_through` | `dumbbell.romanian_deadlift--protocol.webp` | PASS |
| `barbell.romanian_deadlift` | `dumbbell.romanian_deadlift--protocol.webp` | PASS |
| `bodyweight.dead_bug` | `bodyweight.glute_bridge--protocol.webp` | PASS |
| `band.pallof_press` | `bodyweight.wall_push_up--protocol.webp` | PASS |
| `dumbbell.bench_press` | `bodyweight.glute_bridge--protocol.webp` | PASS |
| `barbell.bench_press` | `bodyweight.table_row--protocol.webp` | PASS |
| `bodyweight.negative_pull_up` | `bodyweight.table_row--protocol.webp` | PASS |
| `dumbbell.reverse_lunge` | `bodyweight.wall_push_up--protocol.webp` | PASS |
| `barbell.deadlift` | `dumbbell.bent_over_row--protocol.webp` | PASS |
| `dumbbell.push_press` | `dumbbell.front_squat--protocol.webp` | PASS |

The automated gate resolves every ID from the live registry, verifies exact
canonical filenames, bilingual alt text, distinct artwork, WebP headers and
dimensions, HTTP 200 and unchanged static caching. Chromium independently
decodes all 80 files. The real six-exercise workout is exercised in BG and EN
at 1440, 390 and 360 pixels, preserving its completion metadata. Unknown IDs
still use the neutral fallback in cards and active protocol.

Only the two mutable script URL tokens change in the app template, from
`canonical-workout-r2` to `canonical-workout-r3`. No renderer, training policy,
exercise-library definition, completion contract, Core or database code changes.

## Validation Results

- Narrow Python coverage/cache/canonical-delivery tests: 17 passed.
- Exercise visuals and canonical-delivery browser tests: 45 passed.
- Real six-exercise screenshot verification rerun: 6 passed.
- Manifest/test JavaScript syntax and changed Python compilation: passed.
- Existing 20 approved WebP files: unchanged.
- Current registry and visual coverage: 40/40, no missing IDs.
- New artwork: 30 unique sources, 60 valid WebP exports at exact dimensions.
- Full repository suites were not run; validation stayed within this task's scope.
