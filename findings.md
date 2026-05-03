# Findings

## Handover Summary

- The project is an A-share quantitative trading platform migrated from Streamlit to FastAPI + React.
- Cloud URL documented in handover: `http://49.235.215.39:9090`.
- Backend runs in Docker behind system Nginx; frontend is deployed as static files under `/var/www/quant`.
- The handover identifies the highest-priority issue as an unhealthy backend container, likely related to slow initial stock-name loading or external data calls.
- Search dropdown failure may be a downstream symptom of slow `/api/stocks/search`, an API URL mismatch, browser cache, or CSS layering.

## Priority Issues From `PROJECT_HANDOVER.md`

1. Fix backend `unhealthy` status and ensure `/api/stocks/search?q=茅台` responds quickly.
2. Verify frontend search dropdown behavior in header and quote page.
3. Replace dashboard mock data with existing real APIs.
4. Remove mock data from ETF, mean reversion, pair trading, and data management pages.
5. Replace `stock_names.py` yfinance fallback with local or baostock-backed cache.
6. Plan periodic Qlib data updates beyond `2024-12-31`.

## Important Files

- `backend/main.py`: FastAPI entrypoint, Qlib init, ParallelExt patch.
- `backend/api/stocks.py`: stock search API and baostock-backed cache.
- `backend/api/quote.py`: Qlib quote data endpoint.
- `frontend/src/components/layout/header.tsx`: global search UI.
- `frontend/src/pages/quote/index.tsx`: quote page search UI.
- `frontend/src/lib/api.ts`: frontend API client.
- `docker-compose.yml`: backend container and health configuration.
- `stock_names.py`: legacy stock name mapping with possible yfinance fallback.

## Environment Notes

- The Windows host cannot directly resolve `/home/jason/...` via PowerShell path APIs.
- WSL can access `/home/jason/projects/qlib-workspace`.
- Windows UNC path `\\wsl.localhost\Ubuntu\home\jason\projects\qlib-workspace` is available.
- No repository-level `AGENTS.md`, `CLAUDE.md`, or `GEMINI.md` was found under this project path during initial scan.

## Baseline Inspection

- `backend/main.py` defines `/health` as a lightweight endpoint returning `healthy` only when Qlib initialization succeeded, otherwise `degraded`.
- App startup calls `init_qlib()` before route registration. If Qlib initialization is slow or blocked, Uvicorn startup may delay healthcheck readiness even though `/health` itself is lightweight.
- `backend/api/stocks.py` lazily loads stock names on first `/api/stocks/search` or `/api/stocks/list` call.
- Stock loading first calls `baostock.login()` and `query_hs300_stocks()`, then supplements from `~/.qlib/qlib_data/cn_data/instruments/csi300.txt`.
- Frontend search fetches `${import.meta.env.DEV ? "http://localhost:8000" : ""}/api/stocks/search?...`, so production should use the Nginx relative `/api` proxy.
- Header dropdown uses `z-50`; quote page dropdown also uses `z-50`. A CSS stacking issue is still possible but not yet proven.

## Cloud Reproduction

- `http://49.235.215.39:9090/health` returned HTTP 200 with `{"status":"healthy","qlib":"initialized"}` in about 0.10s.
- `http://49.235.215.39:9090/api/stocks/search?q=茅台` returned HTTP 200 in about 0.08s.
- The cloud search response exposed a confirmed bug: `SH600519` was returned with `"market":"SZ"`.

## Fixes Applied Locally

- Added backend unit tests for stock search and stock info market metadata.
- Added backend unit tests proving unknown stock names use local fallback and do not call yfinance.
- Fixed `backend/api/stocks.py` market detection for Qlib-style `SH...` / `SZ...` codes.
- Removed dynamic yfinance lookup from `stock_names.py:get_stock_name()` and fixed prefixed-code market fallback.

## Remaining Risks

- The cloud server has not been updated with these local changes yet.
- Some business endpoints still intentionally use yfinance, especially ETF, sectors, and quote info endpoints.
- Frontend dropdown CSS has not been browser-verified in this session.

## User-Reported Issues 2026-05-01

- Cards keep loading in hot sector details, quote stock query, mean reversion overbought/oversold, pair list/spread chart, ETF rotation recommendation, and ETF screener list.
- Factor analysis data period cannot be selected.
- Model backtest results are slow.
- Dashboard market trend is stale at 2024-12 and K-lines are not real.

## Initial UI Pattern

- Many affected pages rely on React Query with backend calls and only fall back to mock data after an error or successful empty response.
- If a backend endpoint hangs instead of failing quickly, the UI remains in loading state and the existing mock fallback is not reached.
- `FactorAnalysisPage` has `enabled: false` on the analysis query and hard-coded `start_date: "2024-01-01"` / `end_date: "2024-12-31"`, so period selection is not implemented beyond prediction period.

## Cloud API Reproduction 2026-05-01

- `/health`: HTTP 200 but took about 7.95s.
- `/api/quote/SH600519?indicators=true`: HTTP 200 but took about 6.37s.
- `/api/sectors/performance?days=10`: timed out after 12s with no response.
- `/api/sectors/stocks?sector=半导体`: timed out after 12s with no response.
- `/api/pair/list`: timed out after 12s with no response.
- `/api/etf/signals?days=20`: timed out after 12s with no response.

Conclusion: the loading cards are backed by slow/hanging backend endpoints. Frontend fallback only handles fast failures/empty responses, not long-running requests.

## Code Changes 2026-05-01

- Added an 8s timeout wrapper in `frontend/src/lib/api.ts`; existing API calls now fail fast with `ApiError(408)` instead of waiting indefinitely.
- Added factor analysis data-cycle controls in `frontend/src/pages/factors/index.tsx`: preset range, custom start/end dates, and manual "运行分析" trigger.
- Updated dashboard market trend in `frontend/src/pages/dashboard/index.tsx` to use `/api/index/performance?index=hs300` and calculate MA60/MA200 from returned close prices.

## Backend Slow Path Findings

- `backend/api/sectors.py` loops over many yfinance tickers per request for performance and stock details.
- `backend/api/etf.py` loops over all ETF tickers and calls yfinance for both price and signal calculation.
- `backend/api/pair.py` recalculates Qlib correlations for every default pair on `/api/pair/list`.
- These should be converted to cached/background-updated endpoints; otherwise the 2C/2GB cloud instance can block even `/health`.
