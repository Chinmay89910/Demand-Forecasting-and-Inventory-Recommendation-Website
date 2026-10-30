# RestockIQ Production Deployment Guide

This document provides complete instructions for containerizing, configuring, and deploying the RestockIQ Demand Forecasting & Inventory Optimization website to cloud environments (Render, AWS, DigitalOcean, GCP Cloud Run, or Docker VPS).

---

## 1. Production Architecture Overview

In production, RestockIQ operates as an asynchronous ASGI service running behind a high-performance reverse proxy (Nginx or Caddy) with SSL termination and Gzip/Brotli compression:

```
                      [ HTTPS Traffic :443 ]
                                │
                                ▼
                    ┌───────────────────────┐
                    │     Nginx / Caddy     │ (SSL Termination, Rate Limit,
                    │     Reverse Proxy     │  Static Caching, Gzip)
                    └───────────┬───────────┘
                                │ HTTP :8000
                                ▼
                    ┌───────────────────────┐
                    │      Gunicorn /       │ (Multi-worker ASGI)
                    │     Uvicorn Worker    │
                    └───────────┬───────────┘
                                │
                 ┌──────────────┴──────────────┐
                 ▼                             ▼
        ┌──────────────────┐          ┌──────────────────┐
        │  MongoDB Atlas   │          │  Google Gemini   │
        │  Cluster Primary │          │     GenAI API    │
        └──────────────────┘          └──────────────────┘
```

---

## 2. Docker Containerization

### 2.1 Dockerfile
Create a `Dockerfile` in the root of the project:

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set working directory to website module
WORKDIR /app/website

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Run with multi-worker Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### 2.2 Docker Compose (`docker-compose.yml`)
```yaml
version: '3.8'

services:
  web:
    build: .
    container_name: restockiq-web
    restart: always
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=production
      - MONGO_URI=${MONGO_URI}
      - JWT_SECRET=${JWT_SECRET}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - GEMINI_MODEL=${GEMINI_MODEL:-gemini-3-flash-preview}
      - ALLOW_DEMO_SEED=false
    volumes:
      - ./website/data:/app/website/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## 3. Reverse Proxy Configuration (Nginx)

Below is the hardened Nginx configuration template (`/etc/nginx/sites-available/restockiq.conf`):

```nginx
server {
    listen 80;
    server_name bakery.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name bakery.yourdomain.com;

    # SSL Certificates (managed via Certbot Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/bakery.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bakery.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Static Assets Caching
    location /static/ {
        alias /app/website/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    # Proxy Application
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_connect_timeout 60s;
    }
}
```

---

## 4. Production Checklist

1. [x] **Environment Isolation:** Ensure `.env` is never committed to public repositories.
2. [x] **Secret Key Strength:** Replace default `JWT_SECRET` with a 256-bit cryptographically random hex token (`openssl rand -hex 32`).
3. [x] **Atlas Network Whitelist:** In MongoDB Atlas Security -> Network Access, add server outbound IP addresses or allow `0.0.0.0/0` with strong password auth.
4. [x] **Database Fallback:** RestockIQ provides automatic fallback to local JSON persistence (`website/data/local_db.json`), ensuring zero-downtime during transient database outages.
5. [x] **Rate Limiting:** Authentication and AI chat routes feature sliding-window rate limiters to prevent brute-force attacks and API budget exhaustion.
6. [x] **Health Probing:** Use `/health` for automated container orchestrator probes.

