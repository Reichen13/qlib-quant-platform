# Qlib Workspace Handover Plan

## Goal
Take over the FastAPI + React quantitative platform and continue optimization from the current cloud deployment state.

## Current Constraints
- Project path: `/home/jason/projects/qlib-workspace`.
- Local access is through WSL from the Windows host.
- The project directory is not currently a Git repository, so changes must be tracked explicitly in these planning files.

## Phases

### Phase 1: Handover Intake
Status: complete

- Read `PROJECT_HANDOVER.md`.
- Identify top-priority issues and key files.
- Confirm project is accessible through WSL.

### Phase 2: Baseline Inspection
Status: complete

- Inspect backend health check implementation and container configuration.
- Inspect stock search loading path and frontend search components.
- Determine whether failures are caused by backend latency, API URL mismatch, or UI rendering.

### Phase 3: Backend Health and Search Fix
Status: in_progress

- Make `/health` independent from slow external data loading.
- Preload or cache stock names at startup without blocking health checks.
- Remove slow yfinance fallback paths that can affect hot endpoints.
- Fix stock search market metadata for Qlib-prefixed codes.

### Phase 4: Frontend Search Verification
Status: pending

- Confirm search API URL selection in development and production.
- Check dropdown positioning/z-index and empty/error states.
- Build frontend after changes.

### Phase 5: Follow-up Optimization
Status: pending

- Replace dashboard mock data with real API data.
- Progressively remove mock data from strategy pages.
- Add operational notes for Qlib data refresh.

### Phase 6: User-Reported Production Issues
Status: in_progress

- Reproduce slow/hanging cards by measuring cloud API endpoints.
- Add frontend request timeouts/fallback behavior so cards do not spin indefinitely.
- Replace slow yfinance-backed sector/ETF endpoints with bounded local/mock-safe responses where needed.
- Add factor analysis date range controls.
- Investigate backtest runtime and dashboard stale data separately after loading blockers.

Current status:
- Cloud endpoint reproduction complete.
- Frontend timeout and factor period controls implemented.
- Dashboard now requests index performance data, but cloud index endpoint still timed out during reproduction and needs backend optimization.

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| PowerShell could not resolve `/home/jason/...` | Direct `Test-Path` from Windows | Use WSL and UNC path access. |
| Project path is not a Git repository | `git status --short` in project root | Track changes in planning files and inspect manually. |
| Sandbox setup failed on direct PowerShell file reads | Reading local skill file without escalation | Re-ran required reads with escalation. |
| Cloud reproduction command failed | Embedded Python command had shell quoting conflict | Retried with `curl` timing output. |
| Similar-code scan failed | WSL lacks `rg`; regex pipe was parsed by shell | Switched to `grep` with simpler patterns. |
