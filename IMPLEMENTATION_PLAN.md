# RestockIQ: Phased Website Implementation Plan

This implementation plan details the sequential milestones to build, verify, and deliver the production-oriented website version of RestockIQ inside `demand website/`.

---

## 1. Milestones Overview

```
Phase 1: Project Discovery & Independent Copy [COMPLETED]
   │
Phase 2: Project Structure & Backend Foundation Setup
   │
Phase 3: Web Presentation Layer & "Warm Tech" Design System
   │
Phase 4: ML & Forecasting Engine Integration
   │
Phase 5: Intraday Waste Action & Check-In Workflows
   │
Phase 6: Data Import, Validation & Export Workflows
   │
Phase 7: Comprehensive Automated Testing & Verification
   │
Phase 8: Production Deployment Configuration & Final Evidence Report
```

---

## 2. Milestone Details

### Milestone 1: Project Discovery & Independent Copy (COMPLETED)
- [x] Verified original folder `cap` exists and inspected all modules.
- [x] Verified `demand website` does not conflict with existing folders.
- [x] Created independent copy in `demand website` excluding reproducible caches and incomplete venvs.
- [x] Verified original folder `cap` remains 100% untouched.
- [x] Authored foundational audit documents: `PROJECT_INVENTORY.md`, `ARCHITECTURE_ANALYSIS.md`, `FEATURE_PARITY_MATRIX.md`, `DATA_FLOW.md`.

### Milestone 2: Project Structure & Backend Foundation Setup
- [ ] Create clean unified project entrypoint in `demand website/`:
  - `demand website/run_server.py` or enhanced `Backend/main.py`.
  - Pinned `requirements.txt` containing FastAPI, Uvicorn, Jinja2, python-multipart, motor, pymongo, scikit-learn, and google-genai.
  - Sanitized `.env.example` with clear placeholders.
- [ ] Configure FastAPI to mount:
  - Static assets directory (`/static/` for CSS, JavaScript, icons, and diagrams).
  - Jinja2 template directory (`/templates/` for responsive web views).
  - Existing REST API endpoints (`/api/v1/...`).
- [ ] Implement dual-mode persistence manager:
  - Primary: MongoDB Atlas async client.
  - Resilient Fallback: Thread-safe local JSON persistence layer ensuring zero server crashes if Atlas port 27017 is blocked.

### Milestone 3: Web Presentation Layer & "Warm Tech" Design System
- [ ] Base layout template (`templates/base.html`):
  - Responsive header with live system health pill (DB, LLM, Cloud status).
  - Navigation bar (Dashboard, Inventory, Forecasts, Alerts, Check-In, Import, Reports, Settings).
  - Floating AI Assistant chat drawer.
  - Warm Tech visual styling (Cream background, Forest green accents, soft cards, responsive mobile hamburger drawer).
- [ ] Core Views:
  - `login.html` & `register.html`: Clean auth with one-click demo credentials for quick walkthrough.
  - `dashboard.html`: Morning executive overview, KPI cards, Gemini daily briefing, priority restock table.
  - `inventory.html`: Comprehensive SKU management table with search, category filtering, stock adjustments, and "Add Product" modal.
  - `forecast_detail.html`: 7-day historical bar chart, 7-day forward prediction line, Newsvendor CR restock reasoning.

### Milestone 4: ML & Forecasting Engine Integration
- [ ] Bind web forecasting endpoints directly to:
  - Scikit-Learn `HistGradientBoostingRegressor` with rolling lags.
  - Ground truth historical series from `ML/data/processed/primary_items.csv`.
  - Bayesian TSB sparse item priors from `ML/data/processed/category_priors.json`.
  - Newsvendor Critical Ratio formulation ($Q^* = \hat{D} + 0.2533 \cdot \hat{\sigma}$).
- [ ] Implement dynamic forecast generation endpoint allowing users to trigger predictions across SKUs and horizons.

### Milestone 5: Intraday Waste Action & Check-In Workflows
- [ ] Implement `/waste-alerts` view:
  - Visual pace indicators (actual vs predicted pace).
  - Interactive "Apply 20% Discount" and "Flag for Donation" buttons with state persistence.
  - Real-time alert dismissal and audit logging.
- [ ] Implement `/checkin` view:
  - End-of-day stock audit table with stepper controls (`+` / `-`).
  - Automatic perishable zero-locking logic.
  - Closing variance calculations and historical audit save.

### Milestone 6: Data Import, Validation & Export Workflows
- [ ] Implement `/import-sales` workflow:
  - Drag-and-drop CSV file uploader.
  - Server-side format and schema validator (date format, positive quantities, required columns).
  - Interactive preview table highlighting valid rows and specific validation errors.
  - Commit to database with import summary.
- [ ] Implement `/reports` and export endpoints:
  - Download current inventory as CSV/JSON.
  - Download 7-day forecast schedule as CSV.
  - Printable/PDF daily executive report.

### Milestone 7: Automated Testing & Verification
- [ ] Backend unit test suite (`test_website_backend.py`):
  - Authentication and token lifecycle.
  - Multi-tenant tenant scoping and security.
  - Rate limiting behavior.
  - Newsvendor calculation precision.
  - CSV validation edge cases.
- [ ] Integration test suite (`test_website_integration.py`):
  - Web page HTTP 200 responses.
  - API endpoint payload validation.
  - Fallback mechanisms under disconnected networks.
- [ ] End-to-end browser verification via Playwright / Python test client.

### Milestone 8: Deployment Configuration & Final Evidence Report
- [ ] Containerization: Production `Dockerfile` and `docker-compose.yml`.
- [ ] Comprehensive documentation: `README.md`, `DEPLOYMENT.md`, `SECURITY.md`, `TESTING_REPORT.md`.
- [ ] Final evidence-based report verifying:
  - Original `cap` directory integrity.
  - Test pass counts and execution logs.
  - Live server startup confirmation.

