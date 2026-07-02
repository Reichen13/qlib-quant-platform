# Turtle Trade Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-version Turtle-style trade planning layer that converts existing selected symbols into risk-sized, stop-aware, explainable trade plans.

**Architecture:** Add a focused backend module and API router for deterministic Turtle money-management calculations. Connect it to the frontend as a small trade-plan page and API client, then allow existing workflows to navigate candidates into it. Keep this as a planning/risk feature, not order execution.

**Tech Stack:** FastAPI, Pydantic, pandas-free deterministic Python calculations where possible, React + TanStack Query, existing Qlib quote API patterns.

---

### Task 1: Backend Turtle Plan Core

**Files:**
- Create: `backend/core/turtle_trade.py`
- Test: `backend/tests/test_turtle_trade_plan.py`

- [ ] Write tests for ATR, unit sizing, stop distance, add-on levels, and reward/risk gating.
- [ ] Verify the tests fail because `backend.core.turtle_trade` does not exist.
- [ ] Implement `build_turtle_plan` with inputs for account equity, risk percent, entry price, ATR, max units, and optional target price.
- [ ] Verify tests pass.

### Task 2: Backend API Router

**Files:**
- Create: `backend/api/trade_plan.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_trade_plan_api.py`

- [ ] Write API tests for `POST /api/trade-plan/turtle` using mocked quote history.
- [ ] Verify tests fail because the router is not registered.
- [ ] Implement request/response models and route registration.
- [ ] Derive entry price and ATR from recent quote data when caller does not provide them.
- [ ] Verify API tests pass.

### Task 3: Frontend API and Page

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/sidebar.tsx`
- Create: `frontend/src/pages/trade-plan/index.tsx`

- [ ] Add `api.tradePlan.turtle` client method.
- [ ] Add `/trade-plan` route and sidebar entry.
- [ ] Build a simple page with account equity, risk percent, candidate symbols, and generated plan cards.
- [ ] Keep wording clear: this is a plan and risk estimate, not investment advice or order placement.

### Task 4: Screening Workflow Link

**Files:**
- Modify: `frontend/src/pages/screening-workflow/index.tsx`

- [ ] Add a link/button that opens `/trade-plan` with selected candidate codes in query params.
- [ ] Do not change the screening algorithm.
- [ ] Verify the existing screening page still builds.

### Task 5: Verification

**Files:**
- No new files.

- [ ] Run targeted backend tests.
- [ ] Run `python -m py_compile` for changed backend modules.
- [ ] Run `npm run build`.
- [ ] Start local backend/frontend if needed and smoke test `/api/trade-plan/turtle` plus `/trade-plan`.
