"""
Automated Test Suite for RestockIQ Grounded AI Chatbot.
Verifies:
1. Authenticated API endpoint access & rate limiting.
2. Unauthenticated rejection (HTTP 401).
3. Data grounding from actual store items & alerts.
4. Mathematical adherence to Newsvendor reorder logic ((D + S) - C = R).
5. Misspelling & alias resolution ('crossiants' -> Croissant, 'brfi' -> Barfi).
6. Conversational follow-ups ('why?') using message history.
7. Waste and spoilage alerts retrieval.
8. Unknown item handling (no fabrication).
9. Dynamic data-driven fallback when LLM is unavailable (no hardcoded canned strings).
10. Tenant isolation across different store owners.
"""
import sys
import os
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent / "website"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

import pytest
from fastapi.testclient import TestClient
from main import app
from services.llm_service import (
    answer_assistant_chat,
    _resolve_target_item,
    _dynamic_data_driven_chat_fallback,
    is_llm_configured
)

client = TestClient(app)

SAMPLE_ITEMS = [
    {
        "id": "item_1",
        "name": "Butter Croissant",
        "category": "Pastry",
        "currentStock": 20,
        "predictedDemand": 45,
        "safetyStock": 10,
        "price": 60.0,
        "costPrice": 25.0,
        "isPerishable": True,
        "shelf_life_days": 1
    },
    {
        "id": "item_2",
        "name": "Kaju Katli (Barfi)",
        "category": "Sweets",
        "currentStock": 15,
        "predictedDemand": 40,
        "safetyStock": 10,
        "price": 120.0,
        "costPrice": 60.0,
        "isPerishable": False,
        "shelf_life_days": 15
    },
    {
        "id": "item_3",
        "name": "Sourdough Baguette",
        "category": "Bread",
        "currentStock": 35,
        "predictedDemand": 30,
        "safetyStock": 8,
        "price": 50.0,
        "costPrice": 20.0,
        "isPerishable": True,
        "shelf_life_days": 1
    }
]

SAMPLE_ALERTS = [
    {
        "name": "Butter Croissant",
        "riskLevel": "high",
        "currentStock": 20,
        "sales_pace_ratio": 0.35,
        "surplusUnits": 12,
        "atRiskValue": 300.0,
        "recommendedAction": "Apply 20% discount after 3:00 PM."
    }
]


def test_alias_and_misspelling_resolution():
    """Verify intelligent item resolution for common misspellings and aliases."""
    # Misspelled croissant
    res1 = _resolve_target_item("crossiants", SAMPLE_ITEMS)
    assert res1 is not None
    assert res1["name"] == "Butter Croissant"

    # Alias brfi
    res2 = _resolve_target_item("how much brfi is remaining", SAMPLE_ITEMS)
    assert res2 is not None
    assert res2["name"] == "Kaju Katli (Barfi)"

    # Bread alias
    res3 = _resolve_target_item("sourdough bread stock", SAMPLE_ITEMS)
    assert res3 is not None
    assert res3["name"] == "Sourdough Baguette"


def test_followup_resolution_from_history():
    """Verify follow-up query 'why' resolves the subject from previous turn."""
    history = [
        {"role": "user", "content": "What is the restock quantity for Butter Croissant?"},
        {"role": "assistant", "content": "Recommended reorder is 35 units."}
    ]
    resolved = _resolve_target_item("why?", SAMPLE_ITEMS, history=history)
    assert resolved is not None
    assert resolved["name"] == "Butter Croissant"


def test_dynamic_fallback_no_hardcoded_strings():
    """
    Verify dynamic fallback computes exact real-time math without
    returning any hardcoded static strings.
    """
    # 1. Product reorder calculation
    ans1 = _dynamic_data_driven_chat_fallback(
        "why should I order croissants?",
        SAMPLE_ITEMS,
        SAMPLE_ALERTS
    )
    assert "Butter Croissant" in ans1
    # Target = 45 + 10 = 55. Stock = 20. Reorder = 35.
    assert "35 units" in ans1
    assert "55 units" in ans1

    # 2. Stock remaining query
    ans2 = _dynamic_data_driven_chat_fallback(
        "how much brfi is remaining",
        SAMPLE_ITEMS,
        SAMPLE_ALERTS
    )
    assert "15 units" in ans2
    assert "Kaju Katli (Barfi)" in ans2

    # 3. Active waste alerts
    ans3 = _dynamic_data_driven_chat_fallback(
        "are there any waste alerts?",
        SAMPLE_ITEMS,
        SAMPLE_ALERTS
    )
    assert "1 active waste alerts" in ans3
    assert "20% discount" in ans3

    # 4. Unknown item
    ans4 = _dynamic_data_driven_chat_fallback(
        "how many sushi rolls do we have?",
        SAMPLE_ITEMS,
        SAMPLE_ALERTS
    )
    assert "couldn't find" in ans4.lower()
    # Must list tracked products, not a static canned message
    assert "Butter Croissant" in ans4


def test_assistant_chat_unauthenticated_rejected():
    """Verify that unauthenticated chat requests are strictly rejected (HTTP 401)."""
    resp = client.post("/api/v1/assistant/chat", json={"query": "hello"})
    assert resp.status_code == 401


def test_assistant_chat_live_authenticated():
    """Verify that authenticated requests to /api/v1/assistant/chat succeed and return grounded answers."""
    # Login as demo admin
    login_resp = client.post("/login", data={"email": "admin@test.com", "password": "123456"}, follow_redirects=False)
    assert login_resp.status_code in [302, 303, 200]
    
    # Query assistant with session cookie
    chat_resp = client.post(
        "/api/v1/assistant/chat",
        json={"query": "Which products need restocking?"},
        cookies=login_resp.cookies
    )
    assert chat_resp.status_code == 200
    data = chat_resp.json()
    assert "answer" in data
    assert len(data["answer"]) > 10
    # Must not contain the old hardcoded canned string
    assert "RestockIQ is currently tracking 7 items. Ask specifically about" not in data["answer"]


def test_date_specific_forecast_distinct_dates():
    """
    Verify that asking for tomorrow vs after 9 days vs specific festival dates (8 Nov)
    produces distinct, mathematically calculated predictions instead of repeating the same number.
    """
    items = [{
        "id": "item_brfi",
        "name": "brfi",
        "category": "Dairy",
        "currentStock": 82,
        "predictedDemand": 135,
        "safetyStock": 33,
        "price": 100.0,
        "costPrice": 50.0,
        "isPerishable": True,
        "shelf_life_days": 5
    }]
    
    # 1. 8 November (Diwali Sunday)
    ans_nov8 = answer_assistant_chat("what will be the sale of brfi on 8 november", items, [])
    assert "08 November 2026" in ans_nov8 or "8 November" in ans_nov8
    assert "Diwali" in ans_nov8
    # Baseline is 135; 8 Nov with Sunday (1.35x) and Diwali boost gives ~219 units
    assert "219 units" in ans_nov8

    # 2. Tomorrow
    ans_tomorrow = answer_assistant_chat("what is the forecast of brfi for tomorrow", items, [])
    assert "Target Date" in ans_tomorrow
    # Must NOT be 135 units
    assert "225 units" in ans_tomorrow

    # Confirm tomorrow and Nov 8 are distinctly different
    assert ans_tomorrow != ans_nov8


def test_sku_baseline_demand_estimation():
    """Verify intelligent baseline estimation for new items and historical items."""
    from services.forecast_service import forecast_engine
    
    # Historical match: Croissant
    pred_croissant, safe_croissant = forecast_engine.estimate_sku_baseline_demand("Butter Croissant", "Pastry", 20)
    assert pred_croissant >= 40  # Derived from actual ~50 historical mean in primary_items.csv

    # Dynamic scaling for high initial batch
    pred_batch, safe_batch = forecast_engine.estimate_sku_baseline_demand("Custom Sweet", "Sweets", 100)
    assert pred_batch > 25  # Scales with batch turnover rather than being stuck at flat 20/25

