# RestockIQ: Architecture Analysis & Technical Selection

This document provides a comparative analysis of the existing mobile architecture versus the new website architecture, detailing technology selections, tradeoffs, and design decisions.

---

## 1. Existing System Architecture (Mobile + Microservice)

The original project implements a client-server architecture:
```
[Flutter Mobile App (iOS / Android)]
               │
               ▼ HTTPS / REST (JWT Bearer)
[FastAPI Asynchronous Microservice (Python 3.10+)]
       │                      │                  │
       ▼                      ▼                  ▼
[MongoDB Atlas Cloud]   [Google Gemini LLM]   [Pre-computed ML Batch Store]
(Users, Items, Audits)  (Briefing, Chat RAG)  (GBDT + TSB Forecasts)
```

### Key Architectural Characteristics of the Existing System:
1. **Frontend**: Native Flutter/Dart compiled mobile application. State managed via `Provider`. Interacts with FastAPI through `api_service.dart`. Contains rich offline fallback datasets for resilience.
2. **Backend**: Asynchronous FastAPI service (`Backend/main.py`) running on Render with `motor` (async MongoDB driver) and Pydantic v2 data models.
3. **ML Pipeline**: Batch-driven. Heavy Prophet and Scikit-Learn `HistGradientBoostingRegressor` models precompute 7-day rolling horizons. The API acts as a high-speed read-layer rather than training on every HTTP request.
4. **Resilience Strategy**: Dual-mode operations. If database or cloud services are temporarily unavailable, deterministic fallbacks and local catalogs allow complete application walkthroughs.

---

## 2. Technical Evaluation of Website Architecture Options

We evaluated three potential architectural approaches to build the website version:

### Option A: Flutter Web Build (`flutter build web`)
* **How it works**: Compiling the existing `APP/` Flutter project to web using Dart2JS/Wasm.
* **Evaluation**:
  * *Pros*: Reuses Dart UI code directly.
  * *Cons*: Heavy bundle size (15–25 MB initial download), slow initial canvas rendering (3–8s first paint), canvas-based text rendering causes poor accessibility, awkward desktop browser resizing, non-standard HTML DOM, difficult integration with standard web analytics and browser features.
  * *Verdict*: **Rejected**. Does not deliver a production-grade, responsive website experience as expected by professional web users.

### Option B: Decoupled Single-Page App (React / Vue / Next.js + FastAPI)
* **How it works**: Introducing a separate Node.js/React frontend repository communicating with FastAPI over HTTP.
* **Evaluation**:
  * *Pros*: Rich component ecosystem.
  * *Cons*: Introduces Node.js runtime, npm dependencies, separate port management, complex CORS negotiation, duplicate data modeling (TypeScript interfaces vs Pydantic models), and requires managing two separate servers during development and production hosting.
  * *Verdict*: **Rejected**. Violates the core architectural directive: *"Prefer the smallest reliable architectural change... Do not automatically introduce React, Node.js, Java, Spring Boot, or an entirely new technology stack unless the inspected project and its requirements justify the choice."*

### Option C: Unified Python-Native Web Application (FastAPI + Modern Responsive UI + Chart.js)
* **How it works**: Extending the existing FastAPI microservice with web route controllers, Jinja2 server-side page templates, a clean modern HTML5/Tailwind "Warm Tech" presentation layer, and vanilla asynchronous JavaScript client modules with Chart.js for data visualization.
* **Evaluation**:
  * *Pros*:
    1. **Single Unified Server**: Both the full REST API (`/api/v1/...`) and the web application interface (`/`, `/dashboard`, `/forecast`, etc.) run from a single Python process on one port (`http://localhost:8000`).
    2. **Zero Additional Infrastructure**: Runs natively on the existing Python environment with zero Node.js or build-step dependencies.
    3. **Zero CORS Friction**: Browser pages and backend APIs are co-located on the same origin.
    4. **Direct Python Logic Reuse**: Python forecasting models, Newsvendor inventory calculations, CSV parsing, and Gemini LLM services can be invoked directly with zero inter-process overhead.
    5. **100% Backward Compatibility**: Existing mobile API contracts (`/api/v1/items`, `/api/v1/forecasts/today`, `/api/v1/auth/login`) remain completely untouched and fully functional.
    6. **Universal Responsiveness**: Modern semantic HTML5 + Tailwind CSS delivers native, responsive rendering across desktop displays, laptops, tablets, and mobile web browsers.
  * *Verdict*: **SELECTED (Optimal Architecture)**.

---

## 3. Selected Website Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                   BROWSER (Desktop / Tablet / Mobile)                  │
│                                                                        │
│   ┌───────────────────────────┐      ┌─────────────────────────────┐   │
│   │   Responsive Web Views    │      │    Interactive Visuals      │   │
│   │   (HTML5, Tailwind CSS,   │      │    (Chart.js 4, Lucide,     │   │
│   │    Warm Tech Design Sys)  │      │     Dynamic Modals/Toasts)  │   │
│   └─────────────┬─────────────┘      └──────────────┬──────────────┘   │
└─────────────────┼───────────────────────────────────┼──────────────────┘
                  │ Form Posts / Page Requests        │ Asynchronous Fetch (AJAX)
                  ▼                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   FASTAPI UNIFIED APPLICATION SERVER                   │
│                                                                        │
│   ┌───────────────────────────┐      ┌─────────────────────────────┐   │
│   │     Web Route Routers     │      │       REST API v1           │   │
│   │  - /login, /register      │      │  - /api/v1/auth/*           │   │
│   │  - /dashboard, /inventory │      │  - /api/v1/items/*          │   │
│   │  - /forecast, /alerts     │      │  - /api/v1/forecasts/*      │   │
│   │  - /checkin, /import-sales│      │  - /api/v1/waste-alerts/*   │   │
│   │  - /reports, /settings    │      │  - /api/v1/assistant/*      │   │
│   └─────────────┬─────────────┘      └──────────────┬──────────────┘   │
│                 │                                   │                  │
│                 └─────────────────┬─────────────────┘                  │
│                                   ▼                                    │
│                 ┌───────────────────────────────────┐                  │
│                 │      Core Business Logic Layer    │                  │
│                 │  - Newsvendor Critical Ratio      │                  │
│                 │  - Intraday Waste Action Engine   │                  │
│                 │  - Rate Limiting & Auth Scoping   │                  │
│                 │  - CSV Import Validator Engine    │                  │
│                 └─────────┬───────────────┬─────────┘                  │
└───────────────────────────┼───────────────┼────────────────────────────┘
                            │               │
                            ▼               ▼
         ┌────────────────────────┐   ┌──────────────────────────────┐
         │     Database Layer     │   │     ML & LLM Engine Layer    │
         │ - MongoDB Atlas Cloud  │   │ - HistGradientBoosting (GBDT)│
         │ - Dual-Mode Fallback   │   │ - Bayesian TSB Priors        │
         │   (Local Cache / Sync) │   │ - Google Gemini 3 Flash      │
         └────────────────────────┘   │ - Rule-Based Fallback        │
                                      └──────────────────────────────┘
```

---

## 4. Key Design Decisions

### 4.1 "Warm Tech" Design System Preservation
The website preserves the original mobile application's signature visual identity:
* **Background Canvas**: Cream white (`#FCF9F4` / `#F8F6F0`).
* **Primary Tonal Brand**: Deep Forest Green (`#1B4332` / `#2D6A4F`).
* **Accent & Alerts**: Warm Amber (`#FFB702`), Coral Red (`#B91C1C`), and Olive Green (`#52796F`).
* **Typography**: Clean Montserrat headings with Inter body copy for high readability.
* **Card Radii**: Soft `rounded-2xl` surfaces with subtle border dividers (`#E5E0D8`).

### 4.2 Dual-Mode Persistence (Atlas Cloud + Offline/Local Fallback)
To ensure the website remains 100% functional even when MongoDB port 27017 is blocked by local firewalls or Wi-Fi routers, the backend implements a resilient dual-mode data manager:
1. When Atlas is reachable, all user records, items, forecasts, and audits persist to MongoDB Atlas.
2. If Atlas is unreachable or whitelisting is pending, the service falls back gracefully to a thread-safe local JSON persistence layer, preventing server crashes and enabling full operational demonstrations.

### 4.3 Direct Model Execution & Historical Replay
The website connects directly to:
* `ML/data/processed/primary_items.csv` for authentic historical sales telemetry across 35 SKUs.
* `ML/data/processed/category_priors.json` for Bayesian TSB sparse item priors.
* The Newsvendor Critical Ratio formulation ($CR = \frac{C_u}{C_u + C_o} = 0.60 \implies z = +0.2533$) to compute mathematically rigorous reorder quantities rather than arbitrary numbers.

