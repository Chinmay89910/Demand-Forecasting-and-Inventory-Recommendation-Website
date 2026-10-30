# RestockIQ: Complete Project File Inventory

This inventory documents every file in the source repository, its architectural purpose, logic classification, dependencies, and disposition for the website conversion.

---

## 1. Directory Structure Overview

```
demand website/
├── PROJECT_INVENTORY.md              # File-by-file classification and disposition
├── ARCHITECTURE_ANALYSIS.md          # Architectural comparison and selection rationale
├── FEATURE_PARITY_MATRIX.md          # Parity audit across all 20+ features
├── DATA_FLOW.md                      # End-to-end data pipeline traces
├── IMPLEMENTATION_PLAN.md            # Phased implementation roadmap
├── RISK_AND_ASSUMPTIONS.md           # Operational assumptions, risks, and mitigations
└── CAPSTONE_PROJECT/                 # Preserved independent source copy
    ├── APP/                          # Original Flutter mobile client (Dart)
    ├── Backend/                      # FastAPI asynchronous microservice
    │   ├── services/                 # LLM and business logic services
    │   ├── main.py                   # REST API routes and security controls
    │   ├── test_backend_unit.py      # Security and BVA test suite
    │   └── requirements.txt          # Python microservice dependencies
    ├── ML/                           # Demand forecasting engine
    │   ├── data/                     # Raw and processed historical sales datasets
    │   ├── models/                   # GBDT, Prophet, and residual models
    │   ├── experiments/              # Benchmark studies and weather placebo tests
    │   └── batch_forecast.py         # Batch forecast execution pipeline
    ├── docs/                         # Empirical reports and testing presentations
    ├── Documentation/                # Academic capstone thesis, literature, and log book
    ├── figures/                      # Forecast charts, frontiers, and diagrams
    ├── scripts/                      # Operational automation tools
    └── tables/                       # LaTeX empirical benchmark tables
```

---

## 2. File-by-File Technical Audit

### A. Backend Core (`CAPSTONE_PROJECT/Backend/`)

| File Path | Purpose | Key Classes & Functions | Logic Classification | Dependencies | Disposition & Reason |
|---|---|---|---|---|---|
| `Backend/main.py` | Primary FastAPI backend entry point; defines REST routes, JWT auth, rate limiters, database connections, and business calculations. | `app`, `InMemoryRateLimiter`, `get_current_user`, `evaluate_waste_alert_tier`, `register`, `login`, `get_items`, `create_item`, `update_item`, `get_today_forecasts`, `submit_intraday_sales`, `apply_waste_discount`, `flag_waste_donation`, `dismiss_waste_alert`, `assistant_chat` | Business, Database, Security, API | `motor`, `pymongo`, `passlib`, `jose`, `pydantic`, `services.llm_service` | **Adapt & Expand**: Serves as the primary web backend; extended to serve the responsive web frontend and web routes. |
| `Backend/services/llm_service.py` | Google Gemini 3 Flash LLM integration with deterministic fallback generator. | `generate_daily_briefing`, `answer_assistant_chat`, `get_llm_info`, `_build_deterministic_fallback`, `_call_gemini_with_retry` | Business, AI / ML Integration | `google.genai`, `dotenv`, `logging` | **Reuse Unchanged**: Provides zero-math grounded daily briefing and assistant chat with graceful fallbacks. |
| `Backend/requirements.txt` | Backend dependency specifications. | `fastapi`, `uvicorn`, `motor`, `pymongo`, `pydantic`, `passlib`, `bcrypt`, `python-jose`, `google-genai`, `httpx` | Configuration | Python Package Index | **Adapt**: Include web template dependencies (`jinja2`, `python-multipart`, `aiofiles`) to support web serving and file uploads. |
| `Backend/.env.example` | Sanitized environment variable template. | `MONGODB_URI`, `JWT_SECRET`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `ALLOWED_ORIGINS` | Configuration | None | **Preserve & Sanitize**: Kept as reference template. |
| `Backend/Dockerfile` | Render/Docker container build file. | Multi-stage slim python container, uvicorn entry point. | Deployment | Docker / Linux | **Adapt**: Update to expose website port and package web static assets. |
| `Backend/test_backend_unit.py` | Offline security, BVA, and basis path testing suite. | `TestBackendOfflineSuite`, `test_ep_bva_assistant_query_length`, `test_decision_table_waste_action_engine`, `test_get_client_ip_whitebox` | Testing | `unittest`, `main` | **Preserve & Run**: Critical regression test suite to ensure backend logic remains intact. |
| `Backend/test_rate_limiter.py` | Multi-IP sliding-window rate limiting unit tests. | `test_multi_ip_rate_limiting` | Testing | `main.InMemoryRateLimiter` | **Preserve & Run**: Verifies security defenses against denial of service and credential stuffing. |
| `Backend/test_tenant_isolation.py` | Multi-tenant tenant scoping and owner security audit. | `test_tenant_isolation` | Testing | `main.app`, `httpx` | **Preserve & Run**: Verifies multi-business data isolation. |

---

### B. Machine Learning Engine (`CAPSTONE_PROJECT/ML/`)

| File Path | Purpose | Key Classes & Functions | Logic Classification | Dependencies | Disposition & Reason |
|---|---|---|---|---|---|
| `ML/batch_forecast.py` | Batch forecast generation pipeline; computes 7-day rolling origin predictions and Newsvendor restock levels. | `run_batch_forecast`, Newsvendor Critical Ratio calculation, rolling lag generation. | ML Engine, Business Logic | `numpy`, `pandas`, `scikit-learn`, `pymongo` | **Reuse & Integrate**: Powers the web forecast calculation engine. |
| `ML/models/bakery_model.py` | Prophet generalized additive baseline model. | `create_prophet_model`, `train_prophet` | ML Model | `prophet` | **Reuse**: Available when Prophet is installed in the Python runtime. |
| `ML/models/xgboost_model.py` | Gradient boosting baseline model. | `train_xgb` | ML Model | `xgboost` / `scikit-learn` | **Preserve for Reference**: Historical baseline comparison. |
| `ML/data/processed/primary_items.csv` | Preprocessed historical daily sales series (35 SKUs across 637 calendar days). | 646 KB tabular dataset with `ds`, `article`, `y`, `unit_price`. | Data Asset | None | **Preserve & Mount**: Serves as the ground truth training and demonstration dataset for web forecasts. |
| `ML/data/processed/category_priors.json` | Empirical category distribution priors for cold-start and sparse SKUs. | Category priors across Bakery, Viennoiserie, Pastry, Savory, and Beverage. | Data Asset | None | **Reuse**: Used by the Bayesian TSB cold-start engine. |
| `ML/data/raw/Bakery sales.csv` | 234,005 raw transaction records from Guérande, France. | Transaction level tickets, quantities, timestamps. | Data Asset | None | **Preserve**: Used for full backtesting, simulation, and dataset audit. |
| `ML/requirements.txt` | ML engine dependencies. | `numpy`, `pandas`, `pymongo`, `scikit-learn`, `joblib` | Configuration | Python Package Index | **Preserve**: Pinned packages for ML workloads. |

---

### C. Operational Scripts (`CAPSTONE_PROJECT/scripts/`)

| File Path | Purpose | Key Classes & Functions | Logic Classification | Disposition & Reason |
|---|---|---|---|---|
| `scripts/run_waste_simulation.py` | 90-day inventory simulation comparing Newsvendor CR policy against baseline heuristics. | `run_simulation`, `evaluate_policy` | Business / Simulation | **Preserve**: Generates verifiable waste and profit metrics. |
| `scripts/run_backtest.py` | 38-fold weekly rolling origin temporal backtest. | `run_backtest` | ML Evaluation | **Preserve**: Produces empirical WAPE results. |
| `scripts/audit_datasets.py` | Automated dataset health check and date span verification. | `audit_directory` | QA / Audit | **Preserve**: Validates raw datasets. |
| `scripts/validate_latex.py` | Automated check of LaTeX environments, citations, tables, and figures. | `validate_document` | QA / Audit | **Preserve**: Capstone documentation audit tool. |

---

### D. Original Mobile Frontend (`CAPSTONE_PROJECT/APP/`)

| File Path | Purpose | Key Classes & Functions | Logic Classification | Disposition & Reason |
|---|---|---|---|---|
| `APP/lib/main.dart` | Flutter application entry point and provider registration. | `RestockIQApp`, `MultiProvider` | Mobile UI | **Preserve as Reference**: The complete UI behavior and state structure is mapped 1:1 to the web frontend. |
| `APP/lib/providers/*.dart` | State management for inventory, stock checks, and waste alerts. | `InventoryProvider`, `StockCheckProvider`, `WasteAlertsProvider` | State Management | **Map to Web Logic**: State models and mutation logic are translated into responsive client-side and server-side state in the website. |
| `APP/lib/screens/*.dart` | 8 operational mobile screens (Login, Dashboard, Check-In, Alerts, Detail, Setup, Settings, Forgot Password). | UI views and event handlers. | Mobile UI | **Convert to Web Views**: Transformed into fully responsive HTML5/Tailwind web views suitable for desktop and mobile browsers. |
| `APP/lib/services/api_service.dart` | REST API client with cold-start detection, retry backoff, and demo walkthrough fallback. | `ApiService`, `login`, `fetchTodayDashboard`, `submitIntradaySales` | Frontend Service | **Re-implement in Web Client**: Translated into `api-client.js` for asynchronous browser interactions. |
| `APP/test/*.dart` | 44 unit, widget, and integration tests. | 21 unit, 18 widget, 5 integration tests. | Testing | **Preserve & Replicate**: Mobile tests preserved; web-specific equivalent tests created. |

---

## 3. Explicit Exclusion List (Reproducible Artifacts Only)

The following items were safely excluded during the copy from `cap` to `demand website`:
1. `cap/venv/` — Incomplete virtual environment (missing pip). Excluded to prevent broken environment inheritance.
2. `cap/CAPSTONE_PROJECT/Backend/venv/` — Virtual environment containing only pip. Excluded to ensure a clean, reproducible environment.
3. `cap/CAPSTONE_PROJECT/APP/build/` — Reproducible Flutter compilation cache (100+ MB of intermediate `.dill`, `.obj`, and `.dex` files).
4. `cap/CAPSTONE_PROJECT/APP/.dart_tool/` — Dart package cache, recreated automatically by Flutter.
5. `__pycache__/` and `*.pyc` — Python bytecode files, automatically re-generated on execution.
6. `.pytest_cache/` — Temporary test run cache.

**Zero source code files, zero datasets, zero models, zero configuration files, and zero documentation files were excluded.**

