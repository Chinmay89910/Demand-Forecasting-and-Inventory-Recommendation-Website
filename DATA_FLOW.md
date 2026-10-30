# RestockIQ: Complete Data Flow & Pipeline Analysis

This document traces the data movement through every layer of the RestockIQ website system.

---

## 1. Authentication & Session Data Flow

```
[User Browser]
      │
      │ 1. POST /api/v1/auth/login (email, password)
      ▼
[FastAPI Router: login()]
      │
      │ 2. InMemoryRateLimiter check (max 10 req/60s per client IP)
      │ 3. Fetch user by email from MongoDB / Local Persistence
      │ 4. verify_password(plain_password, password_hash) via passlib bcrypt
      │ 5. Generate signed JWT token with sub=user_id and 7-day expiration
      ▼
[Response to Browser]
      │
      │ 6. Set HTTP-only session cookie 'access_token' + Return JSON TokenResponse
      ▼
[Browser Client]
      │ 7. Stores session; subsequent requests automatically send cookie or Bearer header
```

---

## 2. Daily Morning Forecast & Inventory Decision Flow

```
[Store Manager Browser] ──── (Opens /dashboard or /forecast) ────► [FastAPI Router]
                                                                          │
                                                                          ▼
                                                            [Dependencies: get_current_user]
                                                            (Validates JWT token, extracts owner_id)
                                                                          │
                                                                          ▼
                                                            [Core Forecast & Inventory Service]
                                                                          │
     ┌────────────────────────────────────────────────────────────────────┴───────────────────────────────────┐
     ▼                                                                                                        ▼
[Primary SKUs (>10 units/day)]                                                                   [Sparse SKUs (<10 units/day)]
- Fetch historical sales series (`primary_items.csv` or DB)                                     - Look up category prior in `category_priors.json`
- Apply day-ahead rolling lag features (lag_1, lag_7, rolling_7)                                 - Apply Bayesian TSB formula: W = n / (n + k)
- GBDT regression model (`HistGradientBoostingRegressor`)                                        - Blend item history with 90th percentile prior
- Compute point prediction: \hat{D}                                                             - Compute point prediction: \hat{D}
     │                                                                                                        │
     └────────────────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                                      │
                                                      ▼
                                       [Newsvendor Critical Ratio Engine]
                                       - Given Underage Cost (Cu = 0.60) and Overage Cost (Co = 0.40)
                                       - Critical Ratio CR = Cu / (Cu + Co) = 0.60
                                       - Calculate safety stock multiplier: z = Phi^{-1}(0.60) = +0.2533
                                       - Safety stock: SS = z * \hat{\sigma}_{demand}
                                       - Target order quantity: Q* = \hat{D} + SS
                                       - Net restock recommendation: Restock = max(0, Q* - CurrentStock)
                                                      │
                                                      ▼
                                       [Google Gemini LLM Briefing Service]
                                       - Formulate sanitized inventory JSON payload (top 15 items, alerts)
                                       - Send prompt with zero-math constraint to `gemini-3-flash-preview`
                                       - If API key absent or quota hit &rarr; activate deterministic fallback
                                                      │
                                                      ▼
                                       [Render /dashboard Web View]
                                       - Summary KPI badges (Total SKUs, Restock Needed, Urgent Alerts)
                                       - Executive Briefing card with plain-language bullet points
                                       - SKU restock table with interactive detail buttons
```

---

## 3. Real-Time Intraday Telemetry & Waste Mitigation Flow

```
[POS / Store Register] ──── (Records afternoon sales: actual_units_sold) ────► [POST /api/v1/sales/intraday]
                                                                                        │
                                                                                        ▼
                                                                        [Waste Action Engine]
                                                                        - Lookup today's forecast \hat{D}
                                                                        - Compute elapsed day fraction (e.g. 0.60 at 3:00 PM)
                                                                        - Expected sales so far: \hat{D}_{expected} = \hat{D} * fraction
                                                                        - Sales Pace Ratio: r = actual_units_sold / \hat{D}_{expected}
                                                                                        │
                                                                                        ▼
                                                                        [Decision Table Evaluation]
                                                                        - If r < 0.40 & isPerishable:
                                                                          &rarr; Risk: "critical", Action: "Apply 20% Discount Immediately"
                                                                        - Else If r < 0.60 & isPerishable:
                                                                          &rarr; Risk: "high", Action: "Prepare 20% Markdown / Bundle Offer"
                                                                        - Else If r >= 0.60:
                                                                          &rarr; Risk: "normal", Action: "Pace on Track - No Action Needed"
                                                                                        │
                                                                                        ▼
                                                                        [Database / Store Update]
                                                                        - Persist alert state in `waste_alerts` collection
                                                                        - Trigger real-time alert badge on web navigation bar
```

---

## 4. End-of-Day Physical Check-In & Reset Flow

```
[Store Manager Browser] ──── (Opens /checkin at closing time) ────► [FastAPI Router: /checkin]
                                                                           │
                                                                           ▼
                                                             [Displays Current SKU List]
                                                             - Displays recorded book stock vs physical count inputs
                                                             - User adjusts physical counts (+ / - steppers)
                                                                           │
                                                                           ▼
                                                             [POST /api/v1/items/bulk-checkin]
                                                             - Validates all counts >= 0
                                                             - For Perishable items:
                                                               * Confirms unsold units are logged to waste history
                                                               * Automatically locks closing stock to 0 for next day
                                                             - For Non-Perishable items:
                                                               * Updates currentStock = verified physical count
                                                             - Persists closing audit timestamp and variance report
```

---

## 5. Sales CSV Dataset Import & Validation Flow

```
[User Browser] ──── (Uploads CSV file via /import-sales) ────► [FastAPI Router: /api/v1/data/import]
                                                                        │
                                                                        ▼
                                                         [Stream Validation & Security Guard]
                                                         - Enforce file size limit (max 15 MB)
                                                         - Verify MIME type (`text/csv`, `application/vnd.ms-excel`)
                                                         - Sanitize filename to prevent directory traversal
                                                                        │
                                                                        ▼
                                                         [Structural & Schema Verification]
                                                         - Detect required columns: [`date`, `article` (or `product`), `quantity`]
                                                         - Validate date format (`YYYY-MM-DD` or parseable ISO/US dates)
                                                         - Validate numeric quantities (`quantity >= 0`)
                                                         - Detect duplicate records and calculate summary statistics
                                                                        │
                                                                        ▼
                                                         [Import Summary Generation]
                                                         - Return JSON:
                                                           {
                                                             "status": "success",
                                                             "total_rows": 1250,
                                                             "accepted_rows": 1248,
                                                             "rejected_rows": 2,
                                                             "errors": ["Row 42: Negative quantity -5", "Row 89: Invalid date"],
                                                             "date_range": {"min": "2026-01-01", "max": "2026-10-28"},
                                                             "unique_articles": 24
                                                           }
                                                         - Persist accepted records into user's historical sales series
```

