# M2.1 local release candidate

Base: `af8cf0b57204321e4420e791ad583f590491db6c`.
Status: **BLOCKED** pending a separately scoped canonical-delivery correction.
No commit, push, deployment, production access or production configuration
change is authorized by this preparation task.

## Exact release scope

- `.gitignore`: track the new focused Python test only.
- `app.py`: progress intent and deterministic account-owned SSE branch only.
- `coaching/progress_analysis.py`: bounded verified evidence projection.
- `static/progress_analysis.js`: closed contract and safe DOM/SVG presentation.
- `static/progress_analysis.css`: styles scoped to the analysis only.
- `templates/apex.html`: two asset imports and M2.1 ChatLifecycle/SSE glue only.
- `tests/test_progress_analysis.py`.
- `tests/test_chat_enforcement.py`: replace the intentionally obsolete generic
  `show my progress` model-call expectation with the deterministic contract.
- `tests/playwright/progress-analysis.spec.js`.
- `docs/PROGRESS_CHAT_M2_1.md` and this release preparation record.

Exclude all pre-existing Premium UI CSS hunks in `templates/apex.html`, both
untracked Live Voice preview scripts, temporary SQLite databases, runtime
scripts, screenshots, test reports and credentials. Preserve these local changes
in the original worktree; do not reset or delete them.

No dependency, migration, schema, environment-variable, model, payment, Core,
Training Engine, Nutrition Engine, Next Move or Voice change belongs in this scope.

## Baseline classification

All following failures were reproduced on the exact base, not attributed to M2.1.

| Baseline assertion | Evidence / release impact |
| --- | --- |
| Progress private-field substring | `reason` matches the existing closed `reason_code`; not account leakage. M2.1 does not project either field. |
| Chat traceable completion revision | Fixture omits typed duration evidence for current duration prescriptions; validation rejects it before a model call. No validation relaxation is proposed. |
| Chat persisted comparable completion | Same stale rep-only fixture; existing dose-type validation rejects it. |
| Three Goblet Squat assertions | Expected old exercise selection; delivered current valid intermediate exercise is Dumbbell Front Squat. |
| Two nutrition precedence-copy assertions | Expect older explanatory wording; no nutrient or validation failure is reported by those assertions. |
| Browser CL-3 | User-history expectation races account hydration; interrupted assistant content still stays hidden. Flaky on base too. |
| Browser CL-8 | Counts every fetch, including existing post-turn projection refresh, as a chat request. |
| Browser CL-9 | Expects obsolete Bulgarian quota wording; terminal quota state is still FAILED. |
| Browser malformed workout metadata | **RELEASE BLOCKER**, as independently confirmed below. |

The first eleven assertions do not establish a new M2.1 security/authentication
or valid-workout-delivery regression. The twelfth cannot be declared harmless.

### Active SSE reproduction (base and M2.1)

Using the same synthetic canonical Plank fixture and the actual `send()` path,
deliver text, a completion metadata event, then `done`:

| Metadata | Workout cards | Rejection | Success prose |
| --- | --- | --- | --- |
| `null` | 1 | absent | visible |
| `{}` | 0 | present | absent |
| `{"sessions": []}` | 0 | present | absent |

The existing `else if (o.training_completion || ...)` ignores null metadata.
The older baseline test also incorrectly used a non-current exchange object;
that test flaw does not negate this independently reproduced active-path defect.
No claim is made that arbitrary users can forge a trusted server response.
The confirmed issue is failure of canonical rendering to fail closed on malformed
trusted transport metadata. Do not silently waive it or fold a runtime fix into
this release-preparation task.

## Validation and approval gate

Re-run focused M2.1 Python and browser tests against the isolated base-plus-M2.1
tree, not the original template containing Premium UI experiments. Cover BG/EN,
persisted synthetic evidence, no evidence, account isolation, invalid metadata,
SSE `done`, interruption, 390px and 1440px. All provider calls must be mocked or
prohibited. Preserve the existing baseline assertions unchanged.

### 2026-10-24 isolated-candidate results

- 85 focused Python tests passed (42 M2.1/chat-contract gates plus existing
  My Training and Next Move checks).
- 87 browser tests passed: 24 BG/EN M2.1 cases, 13 existing Workout/Nutrition/
  ChatLifecycle cases, and 50 Next Move/account-continuity cases.
- BG/EN real synthetic persisted evidence, empty/single history, exact UTC values,
  `done`, interrupted SSE, 390px/1440px and safe HTML handling passed.
- Full baseline UI CSS, Core engines/renderer and pointer blocks are byte-identical
  in the isolated candidate; the unrelated Premium UI experiments are excluded.
- Compile, JavaScript syntax and isolated diff checks passed. No migrations,
  dependency additions, paid API calls or production access occurred.
- The independent active-SSE null-completion probe FAILED on both base and M2.1,
  as documented above. Passing focused suites do not override this release blocker.

The candidate is isolated locally at `C:/tmp/apex-m21-rc-af8`; the scoped review
patch is `C:/tmp/apex-m21-rc.patch`. A separate temporary Git index was used to
export it; the real worktree index is unchanged. These are review artifacts, not
approval to commit or deploy.

Before owner approval, review the M2.1-only patch and exact file list. A blanket
`git add templates/apex.html` from the original worktree is not safe because it
would include unrelated Premium UI changes.

## Rollback procedure (not executed)

1. Record and verify the exact production SHA before any future approved rollout.
2. If M2.1 fails post-release health, ownership, contract, safety or card rendering
   checks, use the existing Railway deployment rollback to that recorded SHA.
   Do not move branch source or edit variables as a substitute for exact rollback.
3. If production still equals the stated base, the rollback target is exactly
   `af8cf0b57204321e4420e791ad583f590491db6c`. Do not assume it has not advanced.
4. No database rollback is needed: M2.1 adds no schema or training-fact writes.
   Existing completed workouts and constraints must be retained. Readable chat
   fallback text may remain as ordinary conversation history.
5. Verify `/`, `/en`, `/app` health, `/app` no-store, existing workout/nutrition
   rendering and unchanged account isolation after any separately authorized rollback.

Rolling back M2.1 would not repair the baseline null-metadata defect. That issue
needs its own verified correction before certifying this release safe.
