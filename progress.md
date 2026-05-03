# Progress Log

## 2026-05-01

- Read the full `PROJECT_HANDOVER.md` handover document.
- Confirmed the project is accessible through WSL at `/home/jason/projects/qlib-workspace`.
- Confirmed Windows UNC access exists at `\\wsl.localhost\Ubuntu\home\jason\projects\qlib-workspace`.
- Started takeover plan focused on backend health, stock search, and frontend dropdown verification.
- Inspected `backend/main.py`, `backend/api/stocks.py`, `Dockerfile.backend`, `docker-compose.yml`, `frontend/src/lib/api.ts`, header search, and quote page search.
- Reproduced cloud `/health` and `/api/stocks/search?q=茅台`; both currently respond quickly, but search returned incorrect market metadata.
- Added tests in `backend/tests/test_stocks.py` and `backend/tests/test_stock_names.py`.
- Fixed market detection in `backend/api/stocks.py`.
- Removed dynamic yfinance name lookup from `stock_names.py:get_stock_name()`.
- Verified with `./venv/bin/python -m unittest discover -s backend/tests -v`.
- Verified syntax with `./venv/bin/python -m py_compile backend/api/stocks.py stock_names.py`.
- Started investigation of user-reported loading issues across hot sectors, quote, mean reversion, pair trading, ETF rotation/screener, factor analysis, backtest speed, and dashboard freshness.
- Measured cloud endpoint latency: several sector/ETF/pair endpoints timed out at 12s; quote and health were slow but returned.
- Added frontend API timeout handling to prevent indefinite loading cards.
- Added factor analysis date range controls and manual analysis trigger.
- Switched dashboard market trend data source from quote/mock style to index performance API with MA60/MA200 calculation.
- Verified frontend with `npm run build`.
- Verified backend tests with `./venv/bin/python -m unittest discover -s backend/tests -v`.
