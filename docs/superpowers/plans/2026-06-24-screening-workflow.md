# Screening Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-pass post-close stock screening workflow that joins existing data health, sector, ETF, mean-reversion, pair, and risk checks into one user-facing result.

**Architecture:** Keep the workflow as a thin orchestration layer over existing APIs and helper functions. Do not train deep learning models or make LLM calls in the default workflow; instead surface LLM/deep-learning readiness as evidence so the user can decide when to run heavier checks.

**Tech Stack:** FastAPI, Pydantic, existing Qlib-backed API modules, React, TanStack Query, Vite.

---

### Task 1: Backend Screening Workflow API

**Files:**
- Create: `backend/api/screening.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_screening_workflow.py`

- [ ] Write failing tests for candidate action classification and workflow response shape.
- [ ] Run the targeted test and verify it fails because `backend.api.screening` does not exist.
- [ ] Implement a minimal screening router with `POST /api/screening/run`.
- [ ] Include data health, hot sectors, ETF signals, candidate mean-reversion checks, pair signals, risk summary, and final buckets.
- [ ] Run targeted backend tests until passing.

### Task 2: Frontend Screening Page

**Files:**
- Create: `frontend/src/pages/screening-workflow/index.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/sidebar.tsx`
- Modify: `frontend/src/lib/api.ts`

- [ ] Add API client types and `api.screening.run`.
- [ ] Add route `/screening-workflow`.
- [ ] Add sidebar entry named `盘后选股`.
- [ ] Build a compact workflow page with one run button and result buckets.
- [ ] Run frontend build to verify TypeScript and Vite pass.
