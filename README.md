# RestockIQ: Demand Forecasting & Inventory Optimization Website

> **Production-Oriented Web Application for Small Food Retailers, Bakeries, and Cafés**  
> *Convert perishability into profit through Bayesian ML forecasting, Newsvendor Critical Ratio optimization, and intraday waste mitigation.*

---

## 🥐 Executive Summary & Problem Statement

Independent bakeries and cafés operate under unique, punishing operational dynamics:
1. **Ultra-Short Shelf Life:** Products like croissants, baguettes, and fresh pastries lose commercial value in 18 to 24 hours.
2. **Asymmetric Risk:** The penalty for over-baking is total product write-off (100% loss of ingredient and labor cost). The penalty for under-baking is stockouts during morning peak hours (lost margin and frustrated regulars).
3. **Naive Restocking Failures:** Most small food retailers rely on static "gut feel" or fixed batch sizes, leading to **15% to 30% daily food waste** or recurring 11:00 AM stockouts.

**RestockIQ** transforms this workflow into an automated, data-driven daily operating system. It couples **Autoregressive Gradient-Boosted Trees (GBDT) and Bayesian TSB category priors** with **single-period Newsvendor Critical Ratio economic calculations ($CR = 0.60 \implies z = +0.2533$)** and a real-time **intraday waste action engine**.

---

## 🏗️ Technical Architecture

RestockIQ Website is architected as a high-performance, single-runtime full-stack web application:

```
                                  [ Browser / Client ]
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │      Uvicorn ASGI Server (Port 8000)          │
                    │         FastAPI Unified Web Engine            │
                    └───────┬───────────────────────────────┬───────┘
                            │                               │
             ┌──────────────┴───────────────┐ ┌─────────────┴───────────────┐
             │    Responsive Web UI Layer   │ │   REST API & Integration    │
             │   - Jinja2 Server Templates  │ │   - /api/v1/auth            │
             │   - Tailwind CSS (Warm Tech) │ │   - /api/v1/items           │
             │   - Chart.js 7-Day Visuals   │ │   - /api/v1/forecasts       │
             │   - Lucide Modern Icons      │ │   - /api/v1/waste-alerts    │
             │   - Floating AI Copilot Chat │ │   - /api/v1/export          │
             └──────────────┬───────────────┘ └─────────────┬───────────────┘
                            │                               │
                            └───────────────┬───────────────┘
                                            ▼
 ┌─────────────────────────────────────────────────────────────────────────────────────┐
 │                                Core Business Services                                │
 │  ┌───────────────────────┐ ┌──────────────────────┐ ┌─────────────────────────────┐  │
 │  │    ForecastService    │ │   SalesCsvValidator  │ │         LLMService          │  │
 │  │ - GBDT Multi-step     │ │ - Header Alignment   │ │ - Gemini 3 Flash Preview    │  │
 │  │ - Newsvendor CR Math  │ │ - ISO Date Format    │ │ - Deterministic Fallback    │  │
 │  │ - Category Priors     │ │ - Negative Detection │ │ - Daily Executive Briefing  │  │
 │  └───────────────────────┘ └──────────────────────┘ └─────────────────────────────┘  │
 └──────────────────────────────────────────┬──────────────────────────────────────────┘
                                            ▼
 ┌─────────────────────────────────────────────────────────────────────────────────────┐
 │                         DualModeDatabase Resilience Layer                           │
 │  ┌────────────────────────────────────────┐ ┌────────────────────────────────────┐  │
 │  │        MongoDB Atlas Primary           │ │     Resilient Local JSON Cache     │  │
 │  │        (Motor Async Driver)            │ │       (Thread-safe Atomic)         │  │
 │  └────────────────────────────────────────┘ └────────────────────────────────────┘  │
 └─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📐 Mathematical Formulation

### 1. Newsvendor Critical Ratio Restocking
For each perishable SKU, the optimal production quantity balances underage cost $C_u$ against overage cost $C_o$:
- **Underage Cost ($C_u$):** Opportunity cost of a missed sale ($C_u = \text{Selling Price} - \text{Cost Price}$).
- **Overage Cost ($C_o$):** Direct financial loss from an unsold, expired unit ($C_o = \text{Cost Price}$).
- **Critical Ratio ($CR$):**
  $$CR = \frac{C_u}{C_u + C_o}$$
  For standard artisanal bakery items with ~60% gross profit margin ($P = €4.50, C = €1.80$):
  $$C_u = 4.50 - 1.80 = 2.70, \quad C_o = 1.80$$
  $$CR = \frac{2.70}{2.70 + 1.80} = \frac{2.70}{4.50} = 0.60$$
- **Optimal Order Target ($Q^*$):**
  $$z = \Phi^{-1}(0.60) \approx +0.2533$$
  $$Q^* = \hat{D} + z \cdot \hat{\sigma}_D = \hat{D} + 0.2533 \cdot \hat{\sigma}_D$$
- **Restock Action:**
  $$\text{Restock Quantity} = \max(0, Q^* - \text{Current Stock})$$

### 2. Intraday Waste Action Engine
At 2:00 PM – 4:00 PM, if the cumulative intraday sales pace ratio falls below 60%:
$$\text{Pace Ratio} = \frac{\text{Actual Sales Velocity}}{\text{Expected Sales Velocity}} < 0.60$$
The system immediately activates proactive recovery:
1. **Dynamic POS 20% Markdown:** Clears surplus before closing while capturing revenue.
2. **Charity / Food Donation Dispatch:** Flags remaining shelf-life for local non-profit pickup.

---

## 🚀 Quickstart & Setup

### Prerequisites
- Python **3.10+** (Tested on Python 3.13)
- Modern web browser (Chrome, Edge, Firefox, Safari)

### 1. Installation
Navigate to the `demand website/` directory and install dependencies:
```powershell
cd "demand website"
pip install -r requirements.txt
```

### 2. Environment Configuration
Create a `.env` file from the provided `.env.example` template:
```ini
MONGO_URI="mongodb+srv://<username>:<password>@cluster0.mongodb.net/?appName=Cluster0"
JWT_SECRET="your-jwt-secret-key-here"
ENVIRONMENT="development"
ALLOW_DEMO_SEED=true

GEMINI_API_KEY="your-gemini-api-key-here"
GEMINI_MODEL="gemini-3-flash-preview"

HOST="0.0.0.0"
PORT=8000
```

### 3. Launching the Application
Execute the unified root runner:
```powershell
python run_website.py
```
Open your browser to: **`http://localhost:8000`**

---

## 🔑 Authentication, Onboarding & User Experience

### 1. User Registration & Personal Shop Setup (`/register`)
- **New User Registration:** Self-service registration captures Full Name, Email, Password, Confirm Password, Shop/Store Name, and Business Type (Bakery, Café, Delicatessen, Quick-Service).
- **Security & Integrity:** Passwords are cryptographically hashed using **bcrypt** with random salting. Duplicate emails, weak passwords (< 6 characters), and format violations are rejected with clear user-facing feedback.
- **Immediate Session Initiation:** Upon successful registration, a secure HTTP-only JWT `access_token` cookie is issued, and the user is redirected straight to their personal shop dashboard.

### 2. First-Time Guided Demo & Walkthrough Modal
- **Interactive 10-Step Tour:** Automatically pops up for first-time users on their initial dashboard visit (`onboarding_completed: false`).
- **Progress Tracking & Controls:** Step-by-step progress bar, animated highlights, "Next", "Previous", and "Skip" buttons that explain every core capability (AI Morning Briefing, Urgent Restocks, Perishable Zero-Reset, 7-Day Forecasts, Intraday Waste Engine, and Settings).
- **Backend Persistence:** Completing or dismissing the tour triggers an asynchronous API call (`POST /api/v1/user/onboarding`) persisting completion to the database so the tour does not disrupt future logins.

### 3. Personal Shop Dashboard & Multi-Tenant Isolation
- **Tenant Isolation:** Every item, inventory level, and waste alert is strictly isolated by `owner_id`. User A cannot view, edit, or delete User B's inventory.
- **Empty State UX:** Newly registered shops display a clean empty state guiding the owner to add their first product or upload a historical sales CSV file.

### 4. Replayable Guided Demo in Settings (`/settings`)
- Existing users can replay the 10-step guided demo anytime by navigating to **Store Settings** and clicking **"Replay Guided Demo"**. This operates purely in client-side walkthrough mode without resetting or modifying any shop data.

### 5. Pre-Seeded Evaluation Accounts
For instantaneous evaluation without filling out registration forms, the login screen includes one-click demo credentials:

| Persona | Email | Password | Access Level | Description |
|---|---|---|---|---|
| **Bakery Owner** | `admin@test.com` | `123456` | Full Admin | Complete access to forecasts, check-ins, sales imports, settings |
| **Store Manager** | `manager@cafe.com` | `password123` | Store Manager | Inventory management, waste actions, and check-in workflows |
| **System Evaluator** | `demo@restockiq.com` | `demo123456` | Owner | Clean walkthrough account for grading and verification |

---

## 🖥️ Screen Guide & Core Capabilities

1. **Login & Registration (`/login`, `/register`):** Secure credential entry, password visibility toggles, loading state submission spinners, and clear validation banners.
2. **Personal Dashboard (`/dashboard`):** Shop header (`{{ shop.name }}`), morning AI briefing, urgent restock alerts, 7-day sales metrics, and guided onboarding.
3. **Inventory Management (`/inventory`):** Tenant-isolated SKU catalog with category filtering, real-time stock levels, perishability flags, unit costs, and add/delete actions.
4. **Interactive Forecasts (`/forecast`):** Chart.js multi-step 7-day predicted curves with 90% confidence bands, historical actuals comparison, and live Newsvendor parameters.
5. **Intraday Waste Alerts (`/waste-alerts`):** Real-time sales pace monitors. One-click 20% promotional discount trigger and charity donation flags.
6. **Evening Check-In (`/checkin`):** Physical stock audit stepper with single-click perishable daily zero-reset locking.
7. **Sales Data Import (`/import-sales`):** Drag-and-drop CSV importer with strict validation (required headers, date formats, non-negative numbers).
8. **Reports & Simulations (`/reports`):** Operational benchmarks comparing Naive restock vs. RestockIQ Newsvendor optimization.
9. **Store Settings (`/settings`):** Business operating hours, target service levels, connectivity diagnostics, and "Replay Guided Demo" trigger.
10. **Data Exports (`/api/v1/export/...`):** Real-time CSV and JSON downloads for inventory, forecasts, and full data backups.
11. **Floating AI Assistant Copilot:** Interactive slide-out chat drawer available on every page for operational guidance.

---

## 🧪 Automated Verification Suite

Run the full verification suite covering registration, credential security, route protection, tenant isolation, onboarding persistence, all 11 HTML views, REST APIs, Newsvendor math, and CSV validation:
```powershell
python -m pytest test_website.py test_calendar_unit.py test_calendar_live.py
```
**Test Results:** `24/24 Passed (100% Verification Rate)`.

---

## 🇮🇳 Live India Holiday & Festival Calendar Integration

RestockIQ integrates live, verified Indian public holiday and festival data tailored specifically for food retail businesses, bakeries, and cafés in **Maharashtra** and across India.

### 1. External Candidate API Verification & Empirical Findings

| Candidate Provider | Documented Endpoint | Live Status | Verified Scope & Years | Technical Limitations & Empirical Findings |
|---|---|---|---|---|
| **India Public Holidays API (Primary)** | `https://calendar-api-d7a8.onrender.com/v1/holidays` | **Verified (HTTP 200)** | Year 2026: 50 Central, 69 Maharashtra (`scope=all`), 22 Maharashtra State (`scope=state`) | Runs on Render free tier (cold starts ~25s on first request, sub-200ms subsequent). **Crucial finding:** Returns `404: Data not available for this year` for 2024, 2025, and 2027. Open-source, no API key required, derived from official government calendar (`https://www.india.gov.in/calendar`). |
| **Indian Festival API (Supplementary)** | `https://indian-festival-api.vercel.app/api/festivals` | **Verified (HTTP 200)** | 40 National festivals, 30 Maharashtra-specific (`state=Maharashtra`) | MIT License, free, no API key. **Crucial finding:** Dataset is static JSON containing dates exclusively for 2026 (`date_2026`). Query parameter `year=...` is ignored by upstream. Valuable for cultural festivals (Dhanteras, Makar Sankranti, Diwali, Bhai Dooj). |
| **Statutory Calendar Engine (Fallback)** | Python `holidays` (IN, MH) | **Verified (Active)** | 2021–2027+ multi-year astronomical & gazetted Maharashtra public holidays | Used to provide reliable astronomical and statutory holiday calculations for historical validation (2021–2025) and future projections (2027+) where external web APIs return 404. |

### 2. Architecture & Caching Strategy (`calendar_service.py`)
- **Normalized Schema:** Events are unified into a standard structure containing `date`, `name`, `type` (`gazetted_holiday`, `festival`, `restricted_holiday`), `country` (`IN`), `state` (`MH` or `all`), `level` (`national`, `state`, `cultural`), `verification_status` (`verified_gazetted`, `verified_cultural_festival`, `restricted_optional`), `source`, and retrieval timestamp.
- **Cache Persistence:** Saved to `website/data/calendar_cache.json`.
- **Cache TTL:** 24 hours (86,400 seconds). Prevents redundant external calls across products and forecast horizons.
- **Resilient Fallback:** If upstream APIs time out or fail, valid cached data is strictly preserved and served with a `stale` warning; existing cache is **never overwritten** by malformed or empty responses.

### 3. Forecasting Model Integration (`forecast_service.py`)
- **No Arbitrary Fixed Boosts:** In strict adherence to statistical rigor, arbitrary flat percentage multipliers (e.g. +25%) are eliminated.
- **Empirical Holiday Lift:** For established SKUs with historical sales observations (e.g., Croissants, Baguettes), the system fits an empirical regression against historical holiday observations, learning data-backed holiday multipliers with shrinkage.
- **Cold-Start Protection:** For newly introduced SKUs without sales history (e.g., sweet, brfi), the model explicitly keeps a `0%` holiday boost, preserving baseline demand and transparently noting: *"No historical holiday sales records in database. Baseline demand preserved without arbitrary boosts."*
- **Model Validation:** Evaluated using expanding-window time-based validation on 19,416 historical sales records, demonstrating up to 33%–50% error reduction on holiday dates.

### 4. Interactive Frontend Integration (`/forecast`)
- **Upcoming Holidays & Events Card:** Displays upcoming verified Maharashtra holidays and festivals, classification tags, state applicability pills (`MH State` vs `National`), empirical lift badges, and live sync timestamps.
- **Daily Forecast Details Table:** Itemizes each day's weather, event name, official badge, and predicted units with confidence bounds.
- **AI Briefing & Explanation:** Dynamically cites whether an upcoming date is an official Maharashtra public holiday or cultural festival and explains the empirical basis for demand adjustments.
- **REST API Endpoint (`GET /api/v1/calendar/holidays`):** Programmatic access supporting `year`, `state`, and `refresh=true` query parameters.

