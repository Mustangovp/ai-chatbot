# CONTINUOUS INTEGRATION & QUALITY GATE PROTOCOL (CI)
## Automated Testing & Release Management Specifications

**Version:** 1.0  
**Status:** Approved Architecture Draft  
**Owner:** APEX Pulse Pro  

---

## 1. Pipeline Stages & Execution Order

The CI pipeline runs automatically on every pull request (PR) or push commit to protected target branches (`main`, `master`). The process strictly operates in the following sequential order:

```
[ Checkout Codebase ]
         │
         ▼
[ Environment Prep ] ──> Set up Python 3.13 & Node.js (LTS)
         │
         ▼
[ Dependency Install ] ──> pip install + npm packages + Playwright browsers
         │
         ▼
[ Server Bootstrap ] ──> Launch local Flask server with mock keys in background
         │
         ▼
[ Health Gate ] ──> Wait for HTTP response on http://localhost:5000/app
         │
         ▼
[ E2E Verification ] ──> Execute Playwright test suite (workers=1 to avoid race states)
         │
         ▼
[ Artifact Upload ] ──> Upload reports, screenshots on failure, and trace logs
```

---

## 2. Failure & Success Policies

### 2.1 Failure Policy
*   **Hard Termination:** If any step in the pipeline fails (e.g. dependency installation timeout, health check gate failure, or a single test assertion crash), the entire build is marked as **FAILED**.
*   **Diagnostic Artifacts:** Upon a test failure, Playwright automatically generates screenshots, session videos, and E2E trace logs. These are uploaded to GitHub Actions artifacts as `test-failures` with a 14-day retention limit for immediate inspection.
*   **PR Blockage:** A failed CI pipeline automatically locks the pull request, preventing merge actions.

### 2.2 Success Policy
*   **All Checks Green:** The pipeline is marked as **PASSED** if and only if every single test case in `tests/playwright/` reports a successful execution status, and the HTML report compiles cleanly.

---

## 3. Merge Requirements (Protected Branches)

To maintain absolute project stability, branches merging into protected targets must satisfy these gates:
1.  **Required Status Check:** The `APEX E2E Playwright Tests` workflow must have a successful ("Green") status check.
2.  **No Uncommitted Local Changes:** The merging branch must have all modified code committed.
3.  **Governance Sign-off:** The developer must confirm that the **Engineering Governance** checklists (UI, UX, AI, Performance, Security) have been run locally.

---

## 4. Deployment Requirements (PaaS Release Gate)

Once a PR merges successfully:
*   The PaaS platform (Railway) will trigger an automatic production build based on the newly pushed commit.
*   The PaaS environment must read its secure production environment variables (`APEX_SECRET`, `STRIPE_SECRET_KEY`, `OPENAI_API_KEY`) to authorize payment polling and chat queries.
*   The PaaS platform's release manager verifies that Gunicorn starts the worker threads cleanly without crashing.
