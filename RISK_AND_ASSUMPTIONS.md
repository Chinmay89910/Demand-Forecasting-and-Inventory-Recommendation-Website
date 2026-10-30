# RestockIQ: Risk Assessment & Technical Assumptions

This document identifies operational assumptions, environmental dependencies, potential failure modes, and mitigation strategies for the RestockIQ website.

---

## 1. Technical Assumptions

1. **Python Runtime Environment**:
   - The system assumes Python 3.10+ (tested and verified on Python 3.13.7 on Windows 11).
   - Core packages (`fastapi`, `uvicorn`, `scikit-learn`, `pydantic`, `pandas`, `google-genai`, `motor`, `pymongo`) are available or installable via standard pip.

2. **Database Connectivity Posture**:
   - **Primary**: MongoDB Atlas cloud cluster (`cluster0.ixtelck.mongodb.net`) accessed via standard SRV connection string.
   - **Network Reality**: Due to common institutional/ISP firewall rules blocking TCP port 27017, the application MUST assume that direct cloud database connections may fail during local evaluations.
   - **Mitigation**: The system implements an automatic, transparent local JSON/in-memory persistence fallback layer to guarantee uninterrupted functionality regardless of firewall restrictions.

3. **Generative AI Availability**:
   - Google Gemini 3 Flash (`gemini-3-flash-preview`) is assumed as the primary natural language briefing provider when a valid `GEMINI_API_KEY` is present.
   - The system assumes API rate limits or network dropouts can occur; it MUST therefore provide a deterministic rule-based executive briefing generator with zero external network dependency.

4. **Multi-Tenant Scoping**:
   - Every database record (item, forecast, alert, checkin) includes an `owner_id`. All read/write operations strictly filter by this identifier extracted from the validated JWT token.

---

## 2. Risk Matrix & Mitigations

| Risk ID | Risk Description | Severity | Probability | Mitigation Strategy in Website |
|:---:|---|:---:|:---:|---|
| **R-01** | **Atlas Port 27017 Blocked by Local Wi-Fi / ISP** | HIGH | HIGH | Implement dual-mode storage engine. The application pings Atlas with a short 3-second non-blocking timeout. If unreachable, it activates a persistent local JSON store (`data/local_db.json`), allowing 100% of features (CRUD, forecasts, check-ins) to work locally. |
| **R-02** | **Gemini API Key Missing or Quota Exhausted** | MEDIUM | MEDIUM | The `llm_service.py` module wraps API calls in retry blocks and automatically switches to `_build_deterministic_fallback()` if the key is missing or quota is exhausted. The UI displays the briefing seamlessly with a "Rule-Based" badge. |
| **R-03** | **Large CSV Upload Memory Exhaustion / DOS** | HIGH | LOW | Enforce strict 15 MB streaming upload size limit, validate header row before reading entire body, and process records in chunks. |
| **R-04** | **Credential Stuffing & Brute Force on Auth** | HIGH | MEDIUM | `InMemoryRateLimiter` enforces a strict 10 requests / 60 seconds limit on `/auth/login` and `/api/v1/auth/login`, extracting the client IP via the nearest trusted reverse proxy header. |
| **R-05** | **Cross-Site Scripting (XSS) via User Product Names** | MEDIUM | LOW | Jinja2 auto-escaping is strictly enabled across all template expressions; DOM updates in JavaScript use `textContent` rather than `innerHTML`. |
| **R-06** | **Long-Running ML Training Blocking HTTP Requests** | HIGH | LOW | The website operates on pre-computed daily model forecasts and rapid day-ahead GBDT / Newsvendor inference (<50ms execution time). Heavy re-training is decoupled into standalone scripts. |
| **R-07** | **Accidental Modification of Original `cap/` Source** | CRITICAL | LOW | Strict operational boundary: the website resides entirely in `demand website/`. All commands, edits, and file writes are executed exclusively within `demand website/`. Original `cap/` is verified unchanged after every phase. |

---

## 3. Unresolved Blockers & Disclosures

1. **MongoDB Atlas IP Whitelisting**:
   - Connecting directly to the live Atlas cluster from this local machine requires either adding the current public IP (`117.240.212.195`) or `0.0.0.0/0` in the Atlas Network Access panel, or using a mobile network/VPN that permits outbound TCP on port 27017.
   - *Status*: Gracefully handled by the local persistence fallback layer.
2. **Prophet Python Package**:
   - The optional `prophet` package is not installed in the local Python environment.
   - *Status*: The production model architecture utilizes `HistGradientBoostingRegressor` (from `scikit-learn`, which is installed), and pre-computed Prophet baseline curves are preserved in `ML/data/processed/`, so live forecasting functions cleanly without needing Prophet.

