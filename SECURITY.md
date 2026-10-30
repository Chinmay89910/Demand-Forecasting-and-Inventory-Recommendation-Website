# RestockIQ Security Architecture & Threat Model

This document outlines the security controls, authentication mechanisms, data protection practices, and threat mitigation strategies implemented in the RestockIQ website.

---

## 1. Authentication & Session Management

### 1.1 Dual-Token Delivery (Web & REST API)
- **Web UI:** Authenticated sessions use HTTP-only, secure, `SameSite=Lax` cookies (`access_token`). This mitigates client-side Cross-Site Scripting (XSS) token theft.
- **REST API:** Supports standard `Authorization: Bearer <token>` headers as well as cookie-based auth for seamless single-page widget integration.
- **Token Signing:** JWT tokens are cryptographically signed using HMAC-SHA256 (`HS256`) with a configurable secret key (`JWT_SECRET`).
- **Session Duration:** Standard session duration is 24 hours; extended to 7 days when "Remember me" is checked.

### 1.2 Password Hashing
- Passwords are salted and hashed using **bcrypt** via the `passlib` crypt context. Plaintext passwords are never stored, logged, or serialized.

---

## 2. Rate Limiting & Denial-of-Service Defense

To prevent credential stuffing, brute-force attacks, and Gemini API quota exhaustion, RestockIQ implements an in-memory sliding-window rate limiter (`InMemoryRateLimiter`):

| Endpoint | Window | Threshold | Exceeded Action |
|---|---|---|---|
| `/login` & `/api/v1/auth/login` | 60 seconds | 15 requests / IP | HTTP 429 Too Many Requests (`Retry-After`) |
| `/api/v1/assistant/chat` | 60 seconds | 25 requests / IP | HTTP 429 Too Many Requests |

Client IP addresses are extracted safely from proxy headers (`X-Forwarded-For`) with validation to avoid spoofing.

---

## 3. Data Isolation & Multi-Tenancy

- **Owner-Scoped Queries:** All inventory items, waste alerts, and sales logs are scoped by `owner_id`. A user can only read, update, or delete items belonging to their authenticated tenant.
- **Walkthrough Sandboxing:** Demo accounts (`admin@test.com`, `manager@cafe.com`, `demo@restockiq.com`) share a pre-seeded tenant sandbox (`demo_walkthrough_owner`) for evaluation, preventing cross-tenant leakage to newly registered bakery accounts.

---

## 4. Input Validation & Data Ingestion Security

- **Pydantic Validation:** All API inputs (`LoginRequest`, `ItemCreateRequest`, `BulkCheckInRequest`, `CsvValidateRequest`) enforce strict typing, length constraints, and value sanitization.
- **CSV Sanitization:** Uploaded sales CSV files are parsed in-memory without invoking shell commands or dangerous eval functions. The validator verifies:
  - Header normalization and alias mapping.
  - Strict ISO 8601 date format (`YYYY-MM-DD`).
  - Integer sales quantity verification ($\text{quantity} \ge 0$).
  - Stripping of leading formula trigger characters (`=`, `+`, `-`, `@`) to prevent CSV Injection / Formula Injection in spreadsheet software.

---

## 5. Fail-Fast LLM Circuit Breaker

The Google GenAI integration includes automatic circuit breaking:
- If the Gemini API returns a rate limit (`429`), quota exhaustion (`RESOURCE_EXHAUSTED`), or network timeout, the application immediately switches to the local deterministic rule-based generator.
- This guarantees that operational pages (e.g. morning dashboard) will **never crash or stall** due to third-party AI outages.

---

## 6. Security Checklist for Production Administrators

1. Set `ALLOW_DEMO_SEED=false` in production `.env` to prevent automatic creation of public walkthrough credentials.
2. Generate a dedicated 32+ character random string for `JWT_SECRET`.
3. Enable HTTPS on your reverse proxy (Nginx / Caddy / Cloudflare).
4. Restrict MongoDB Atlas Network Access IP whitelist to application server egress addresses.

