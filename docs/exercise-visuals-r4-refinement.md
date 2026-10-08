# Movement Studies r4 Refinement

Baseline: `3c343bdf41b7c48cc904545693e8358be611f92b`.
Mode: built-in image generation, reference-guided edits of the existing artwork.
Only these five canonical pairs are replaced; the other 70 WebP files remain
byte-for-byte unchanged. No exercise identity, instruction, prescription,
renderer, Core, training policy, database or global static-cache change.

## Final Assets and Prompt Set

Final directory: `static/exercise/visuals/v1/`.
Filenames remain `<exercise_id>--thumb.webp` and
`<exercise_id>--protocol.webp`. Each pair is derived from one reviewed source,
with Lanczos resizing, WebP quality 86 / method 6, and no pose-changing crop.
Thumbs are 320 x 240; protocols are 960 x 720.

Shared visual invariants: photographic realism, charcoal gym, black performance
clothing, restrained red accents, consistent directional lighting, no text,
logos, watermark, extra limbs or decorative overlays.

| Canonical ID | Reference / Edit Specification | Selected Source Filename |
| --- | --- | --- |
| `barbell.bench_press` | Existing target plus approved dumbbell bench press style reference. Rebuild from a slightly elevated foot-end three-quarter camera: transverse bar above mid-chest, symmetric grip, complete shoulder/upper-arm/elbow/forearm/wrist connections, grounded feet and normal bench/rack setup. Follow-up removes all plate lettering, retaining plain matte graphite plates and all corrected anatomy. | `exec-f5afe555-aed5-4fd4-a632-df857f59c811.png` |
| `cable.pull_through` | Existing target. Tighten the frame while keeping the low pulley, taut cable route between the legs, textured rope and both hands gripping its end stoppers visible. Preserve neutral hip-hinge anatomy. Follow-up replaces footwear with plain black lace-up training shoes and restrained red soles, without branding. | `exec-a8b800ca-1673-491d-b22f-c0e47c3264eb.png` |
| `bodyweight.wall_push_up` | Existing target. Change footwear only: remove swooshes, emblems, lettering and labels from both shoes; use plain black/red footwear. Preserve athlete, wall push-up pose, hands, alignment, floor contact, camera and lighting. | `exec-b349e531-fab2-426a-85ae-a564e4d00c5d.png` |
| `bodyweight.push_up` | Existing target. Same footwear-only correction; preserve push-up anatomy, hand placement, aligned torso, feet, camera and environment. | `exec-9a5ff180-ea78-49c5-9963-326bd9285836.png` |
| `bodyweight.glute_bridge` | Existing target. Same footwear-only correction; preserve hip height, bent knees, grounded feet, hands beside torso, head on floor, camera and environment. | `exec-4fdff264-bb3d-4217-9b6f-6f75aa632318.png` |

## Cache Authority

The app template defines `canonical_workout_revision` once as
`canonical-workout-r4`. Both mutable script URLs use that value.
The manifest reads its own `document.currentScript.src` revision and appends
the same query to both image variants for every ID. It has no separately
hardcoded release token. Static cache configuration remains unchanged.

## QA and Validation

- All ten exported assets visually inspected at full protocol resolution and
  actual 80 x 60 / 160 x 120 UI sizes; matching thumb/protocol poses.
- Bench press: transverse chest-height bar, symmetric grip, connected arms,
  grounded feet and recognizable bench setup; no plate lettering.
- Pull-through: visible low pulley, cable, between-leg rope and grip; tighter
  framing distinguishes it from an unloaded hinge.
- Wall push-up, push-up and glute bridge: original movement retained, visible
  third-party footwear branding removed.
- Narrow Python visual coverage / app cache / canonical delivery: 18 passed.
- Chromium visual coverage / canonical delivery: 49 passed, zero failures.
- Live registry: 40/40 canonical visual entries; 80/80 WebP responses HTTP 200
  with exact dimensions and successful Chromium decoding.
- Five corrected cards and protocols: no fallback in BG and EN at 390 and
  360 pixels; no horizontal overflow; completion metadata unchanged.
- Bench press and pull-through screenshot evidence captured at actual card
  and active-protocol sizes in all four language/viewport combinations and
  visually inspected. Neutral unknown-ID / missing-asset fallback remains safe.
- Changed JavaScript syntax, changed Python compilation and `git diff --check`
  passed. Full repository suites were not run.
