import os
import re
import json
import time
import logging
from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

try:
    from services.forecast_service import forecast_engine
except ImportError:
    from website.services.forecast_service import forecast_engine

load_dotenv()

logger = logging.getLogger("restockiq.llm")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [LLM] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        _client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Initialized Google GenAI client with model: %s", GEMINI_MODEL)
    except Exception as e:
        logger.warning("Could not initialize google-genai Client: %s", e)


def is_llm_configured() -> bool:
    return bool(GEMINI_API_KEY and _client)


def get_llm_info() -> Dict[str, Any]:
    return {
        "configured": is_llm_configured(),
        "provider": "google-gemini" if is_llm_configured() else "deterministic-fallback",
        "model": GEMINI_MODEL if is_llm_configured() else "rule-based",
    }


def _call_gemini_with_retry(prompt: str, max_retries: int = 2, initial_delay: float = 0.5) -> Optional[str]:
    """Executes generate_content with backoff across model candidates."""
    global _client
    if not _client:
        return None

    model_candidates = [
        GEMINI_MODEL,
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-flash-latest",
        "gemini-3-flash-preview",
    ]
    models_to_try = []
    for m in model_candidates:
        if m and m not in models_to_try:
            models_to_try.append(m)

    for active_model in models_to_try:
        delay = initial_delay
        for attempt in range(1, max_retries + 1):
            try:
                response = _client.models.generate_content(
                    model=active_model,
                    contents=prompt,
                )
                if response and response.text:
                    return response.text.strip()
                break
            except Exception as e:
                err_str = str(e).lower()
                if any(k in err_str for k in ["resource_exhausted", "quota", "daily limit", "429"]):
                    logger.info("Gemini model %s daily quota limit reached (%s). Trying next available model candidate...", active_model, e)
                    break
                is_retryable = any(k in err_str for k in ["500", "502", "503", "504", "timeout"])
                logger.warning("Gemini API (model %s) attempt %d/%d failed: %s", active_model, attempt, max_retries, e)
                if attempt < max_retries and is_retryable:
                    time.sleep(delay)
                    delay *= 1.5
                else:
                    break
    return None


def _build_deterministic_fallback(items: List[Dict[str, Any]], alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Robust rule-based generator when LLM API is unreachable or not configured."""
    restock_needed = [
        it for it in items
        if it.get("currentStock", 0) <= it.get("safetyStock", 0)
        or it.get("currentStock", 0) < it.get("predictedDemand", 0)
    ]
    urgent_alerts = [a for a in alerts if a.get("riskLevel") in ["high", "critical"]]

    summary = (
        f"Operational status: {len(items)} products tracked. "
        f"{len(restock_needed)} items require restocking attention today, and "
        f"{len(urgent_alerts)} intraday waste mitigation alerts are currently active."
    )

    actions = []
    if restock_needed:
        names = ", ".join([it.get("name", "Item") for it in restock_needed[:3]])
        actions.append(f"Restock priority items: {names}.")
    if urgent_alerts:
        alert_names = ", ".join([a.get("name", "Item") for a in urgent_alerts[:2]])
        actions.append(f"Review waste alerts for {alert_names} to apply scheduled discount or donation.")
    else:
        actions.append("Inventory levels stable with standard turnover pace.")

    return {
        "source": "fallback",
        "provider": "deterministic-fallback",
        "model": "rule-based",
        "executive_summary": summary,
        "actions": actions,
        "raw_text": f"### Daily Executive Brief\n\n{summary}\n\n**Key Actions Today:**\n" + "\n".join([f"- {a}" for a in actions]),
    }


def generate_daily_briefing(items: List[Dict[str, Any]], alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generates natural language executive briefing for store managers."""
    global _client
    if not _client:
        return _build_deterministic_fallback(items, alerts)

    inventory_summary = []
    for it in items[:15]:
        inventory_summary.append({
            "name": it.get("name"),
            "category": it.get("category"),
            "current_stock": it.get("currentStock"),
            "predicted_demand": it.get("predictedDemand"),
            "safety_stock": it.get("safetyStock"),
            "price": it.get("price"),
            "risk_level": it.get("riskLevel"),
        })

    alerts_summary = []
    for a in alerts[:10]:
        alerts_summary.append({
            "name": a.get("name"),
            "risk_level": a.get("riskLevel"),
            "sales_pace_ratio": a.get("sales_pace_ratio"),
            "current_stock": a.get("currentStock"),
            "recommended_action": a.get("recommendedAction"),
        })

    prompt = f"""You are the senior inventory manager for RestockIQ, an AI inventory platform for bakeries and food retail.
Review today's inventory status and active alerts:

INVENTORY ITEMS:
{json.dumps(inventory_summary, indent=2)}

ACTIVE WASTE ALERTS:
{json.dumps(alerts_summary, indent=2)}

Generate a concise, professional operational briefing with:
1. "executive_summary": A 2-3 sentence overview of store operational health.
2. "actions": A list of 2-4 concrete, prioritized bullet-point action items for the morning shift.

Return ONLY a valid JSON object matching:
{{
  "executive_summary": "...",
  "actions": ["...", "..."]
}}
"""
    raw_response = _call_gemini_with_retry(prompt)
    if not raw_response:
        return _build_deterministic_fallback(items, alerts)

    try:
        cleaned = raw_response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        parsed = json.loads(cleaned.strip())
        return {
            "source": "google-gemini",
            "provider": "google-gemini",
            "model": GEMINI_MODEL,
            "executive_summary": parsed.get("executive_summary", ""),
            "actions": parsed.get("actions", []),
            "raw_text": raw_response,
        }
    except Exception as e:
        logger.warning("Could not parse Gemini JSON response (%s); falling back to rule-based briefing.", e)
        return _build_deterministic_fallback(items, alerts)


MONTH_MAP: Dict[str, int] = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
    'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
    'aug': 8, 'august': 8, 'sep': 9, 'september': 9, 'oct': 10, 'october': 10,
    'nov': 11, 'november': 11, 'dec': 12, 'december': 12
}

WEEKDAY_MAP: Dict[str, int] = {
    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
    'friday': 4, 'saturday': 5, 'sunday': 6
}


def _resolve_target_date(query: str, reference_date: Optional[date] = None) -> Tuple[Optional[date], Optional[str]]:
    """
    Extracts explicit or relative future dates from natural language questions:
    - 'tomorrow' -> ref + 1 day
    - 'day after tomorrow' -> ref + 2 days
    - 'after 9 days' / 'after the 9 days' / 'in 5 days' -> ref + N days
    - '8 november' / '8th nov' / 'nov 8' -> date(ref.year, 11, 8)
    - 'next monday' / 'this sunday' -> upcoming weekday
    """
    ref = reference_date or date.today()
    q_low = query.lower()

    if 'day after tomorrow' in q_low:
        return ref + timedelta(days=2), 'day after tomorrow'
    if 'tomorrow' in q_low:
        return ref + timedelta(days=1), 'tomorrow'
    if 'today' in q_low or 'tonight' in q_low:
        return ref, 'today'

    # Relative days: 'after 9 days', 'after the 9 days', 'in 5 days'
    m_days = re.search(r'(?:after|in)\s+(?:the\s+)?(\d+)\s+days?', q_low)
    if m_days:
        n = int(m_days.group(1))
        return ref + timedelta(days=n), f'after {n} days'

    # Day of week: 'next monday', 'this sunday', 'on friday'
    m_weekday = re.search(r'(?:next|this|on)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)', q_low)
    if m_weekday:
        target_dow = WEEKDAY_MAP[m_weekday.group(1)]
        current_dow = ref.weekday()
        days_ahead = (target_dow - current_dow) % 7
        if days_ahead == 0:
            days_ahead = 7
        return ref + timedelta(days=days_ahead), m_weekday.group(1).capitalize()

    # Formats: '8 november 2026', '8th nov'
    m_date1 = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)(?:\s+(\d{4}))?', q_low)
    if m_date1 and m_date1.group(2) in MONTH_MAP:
        d = int(m_date1.group(1))
        m = MONTH_MAP[m_date1.group(2)]
        y = int(m_date1.group(3)) if m_date1.group(3) else ref.year
        try:
            return date(y, m, d), f'{d} {m_date1.group(2).capitalize()} {y}'
        except ValueError:
            pass

    # Formats: 'november 8 2026', 'nov 8'
    m_date2 = re.search(r'([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?', q_low)
    if m_date2 and m_date2.group(1) in MONTH_MAP:
        m = MONTH_MAP[m_date2.group(1)]
        d = int(m_date2.group(2))
        y = int(m_date2.group(3)) if m_date2.group(3) else ref.year
        try:
            return date(y, m, d), f'{d} {m_date2.group(1).capitalize()} {y}'
        except ValueError:
            pass

    # ISO date: '2026-11-08'
    m_iso = re.search(r'(\d{4})-(\d{2})-(\d{2})', q_low)
    if m_iso:
        try:
            return date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))), m_iso.group(0)
        except ValueError:
            pass

    return None, None


COMMON_ALIASES: Dict[str, List[str]] = {
    "croissant": ["croissant", "croissants", "crossiant", "crossiants", "butter croissant"],
    "baguette": ["baguette", "baguettes", "sourdough", "bread", "sourdough baguette"],
    "danish": ["danish", "almond danish", "pastry"],
    "muffin": ["muffin", "muffins", "chocolate muffin", "rich chocolate muffin", "choco"],
    "milk": ["milk", "whole milk", "dairy", "fresh milk"],
    "coffee": ["coffee", "coffee beans", "espresso", "beans", "latte", "cappuccino"],
    "cheesecake": ["cheesecake", "cheesecake slice", "cake", "classic cheesecake"],
    "sandwich": ["sandwich", "sandwiches", "veg sandwich", "fresh vegetable sandwich"],
    "barfi": ["barfi", "brfi", "burfi", "kaju katli", "kaju", "mithai", "sweet"],
    "strawberry": ["strawberry", "strawberries"],
}


def _resolve_target_item(
    query: str,
    items: List[Dict[str, Any]],
    history: Optional[List[Dict[str, str]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Intelligently resolves which item is in focus based on:
    1. Direct item name matching (case-insensitive)
    2. Common retail food aliases and misspellings (e.g. 'crossiants', 'brfi')
    3. Conversational context from previous user and assistant turns
    """
    if not items:
        return None

    q = query.lower().strip()

    # 1. Exact or substring match in item name
    for it in items:
        name = it.get("name", "").lower()
        if name and (name in q or q in name):
            return it

    # 2. Alias dictionary lookup
    for canonical, aliases in COMMON_ALIASES.items():
        if any(alias in q for alias in aliases):
            for it in items:
                name = it.get("name", "").lower()
                cat = it.get("category", "").lower()
                if canonical in name or any(a in name for a in aliases) or canonical in cat:
                    return it

    # 3. Fuzzy token matching against item names
    q_tokens = set(re.findall(r"\w+", q))
    for it in items:
        name_tokens = set(re.findall(r"\w+", it.get("name", "").lower()))
        if q_tokens & name_tokens:
            return it

    # 4. Contextual resolution from conversation history (e.g. for "why?", "how much is remaining?")
    if history:
        for msg in reversed(history[-4:]):
            content = msg.get("content", "").lower()
            for it in items:
                name = it.get("name", "").lower()
                if name and name in content:
                    return it
            for canonical, aliases in COMMON_ALIASES.items():
                if any(alias in content for alias in aliases):
                    for it in items:
                        name = it.get("name", "").lower()
                        if canonical in name or any(a in name for a in aliases):
                            return it

    return None


def _sanitize_response(answer: str, query: str, target_item: Optional[Dict[str, Any]]) -> str:
    """
    Ensures that focused questions (e.g. single product forecasts or stock checks)
    receive only the specific, human-like necessary answer without unsolicited
    store-wide inventory dumps or full restock lists.
    """
    if not answer:
        return ""
    q_low = query.lower()
    is_general_restock_query = any(k in q_low for k in ["which products", "what products", "what should i order", "restock list", "items need restocking", "what to reorder", "low on stock"])
    is_overview_query = any(k in q_low for k in ["overview", "summary", "status", "situation"])

    # If the user asked about a specific item or specific date forecast:
    if target_item or (not is_general_restock_query and not is_overview_query):
        # Truncate any unsolicited appended sections
        m = re.search(
            r'(\n\s*---\s*\n|\n\s*Here is your (current\s+)?(real-time\s+)?verified inventory|\n\s*(\*\*)?Critical Restock Needed|\n\s*(\*\*)?Restock Recommended|\n\s*(\*\*)?Healthy Stock Levels)',
            answer,
            re.IGNORECASE
        )
        if m:
            answer = answer[:m.start()].strip()

    return answer.strip()


def answer_assistant_chat(
    query: str,
    items: List[Dict[str, Any]],
    alerts: List[Dict[str, Any]],
    shop_info: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    weather_info: Optional[Dict[str, Any]] = None,
    upcoming_events: Optional[List[Dict[str, Any]]] = None,
    weather_7d: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Real-time, data-aware intelligent assistant for RestockIQ store managers.
    Understands natural language questions, maps aliases/misspellings, retrieves live
    inventory, alerts, weather, calendar, and date-specific demand forecasts.
    """
    global _client

    # 1. Enrich items with Newsvendor restock calculations
    enriched_items = []
    restock_needed_items = []
    currency = (shop_info.get("currency") if shop_info else None) or "₹"
    shop_name = (shop_info.get("name") if shop_info else None) or "RestockIQ Store"
    shop_location = (shop_info.get("location") if shop_info else None) or "Shirpur, Maharashtra"

    for it in items:
        curr = int(it.get("currentStock", 0))
        pred = int(it.get("predictedDemand", 0))
        safety = int(it.get("safetyStock", 0))
        price = float(it.get("price", 0.0) or 0.0)
        cost = float(it.get("costPrice", 0.0) or round(price * 0.5, 2))
        is_perish = bool(it.get("isPerishable", True))
        shelf_days = int(it.get("shelf_life_days") or (1 if is_perish else 180))

        target_inv = pred + safety
        reorder_qty = max(0, target_inv - curr)
        surplus_qty = max(0, curr - pred)

        if curr <= safety:
            status_desc = "CRITICAL: Stock at/below safety buffer. Urgent restock required."
            restock_needed_items.append(it.get("name"))
        elif curr < target_inv:
            status_desc = "RESTOCK RECOMMENDED: Stock below target inventory."
            restock_needed_items.append(it.get("name"))
        else:
            status_desc = "HEALTHY: Current stock covers predicted demand and safety buffer."

        enriched_items.append({
            "name": it.get("name"),
            "category": it.get("category"),
            "current_stock": curr,
            "predicted_demand": pred,
            "safety_stock": safety,
            "target_inventory": target_inv,
            "recommended_reorder": reorder_qty,
            "surplus_units": surplus_qty,
            "unit_price": f"{currency}{price:.2f}",
            "unit_cost": f"{currency}{cost:.2f}",
            "is_perishable": is_perish,
            "shelf_life": f"{shelf_days} days",
            "status": status_desc,
        })

    # 2. Enrich alerts
    enriched_alerts = []
    for a in alerts:
        a_curr = int(a.get("currentStock", 0))
        a_surplus = int(a.get("surplusUnits", 0))
        a_loss = float(a.get("atRiskValue", 0.0))
        a_pace = int(round(float(a.get("sales_pace_ratio", 0.0)) * 100))
        enriched_alerts.append({
            "product": a.get("name"),
            "risk_level": a.get("riskLevel", "Medium").upper(),
            "current_stock": a_curr,
            "sales_pace": f"{a_pace}% of expected velocity",
            "potential_surplus": f"{a_surplus} units",
            "estimated_loss": f"{currency}{a_loss:.2f}",
            "action": a.get("recommendedAction", "Monitor turnover rate."),
        })

    # 3. Check for specific product in focus and requested date
    target_item = _resolve_target_item(query, items, history)
    target_date, target_date_label = _resolve_target_date(query, reference_date=date.today())

    date_forecast_data = None
    multi_item_date_forecasts = []

    if target_date:
        if target_item:
            date_forecast_data = forecast_engine.get_sku_date_forecast(
                target_item,
                target_date,
                shop_location=shop_location,
                weather_7d=weather_7d
            )
        elif items:
            for it in items[:6]:
                multi_item_date_forecasts.append(
                    forecast_engine.get_sku_date_forecast(
                        it,
                        target_date,
                        shop_location=shop_location,
                        weather_7d=weather_7d
                    )
                )

    focused_item_data = None
    if target_item:
        t_curr = int(target_item.get("currentStock", 0))
        t_pred = int(target_item.get("predictedDemand", 0))
        t_safe = int(target_item.get("safetyStock", 0))
        t_target = t_pred + t_safe
        t_reorder = max(0, t_target - t_curr)
        focused_item_data = {
            "name": target_item.get("name"),
            "current_stock": t_curr,
            "predicted_demand": t_pred,
            "safety_stock": t_safe,
            "target_inventory": t_target,
            "recommended_reorder": t_reorder,
            "formula_explanation": (
                f"Target Inventory = Predicted Demand ({t_pred}) + Safety Stock ({t_safe}) = {t_target} units. "
                f"Recommended Order = Target ({t_target}) - Current Stock ({t_curr}) = {t_reorder} units."
            )
        }

    # 4. Construct conversation history block
    history_lines = []
    if history:
        for msg in history[-6:]:
            role = "Store Manager" if msg.get("role") in ["user", "human"] else "RestockIQ Copilot"
            content = msg.get("content", "").strip()
            if content:
                history_lines.append(f"{role}: {content}")
    history_block = "\n".join(history_lines) if history_lines else "None (New conversation)"

    # 5. Build full grounded prompt
    weather_desc = f"{weather_info.get('condition', 'Clear')}, {weather_info.get('temperature', 26)}°C" if weather_info else "Clear, 26°C"
    events_desc = ", ".join([f"{e.get('name')} on {e.get('date')}" for e in (upcoming_events or [])[:6]]) or "Standard operating schedule."

    date_forecast_prompt_block = ""
    if date_forecast_data:
        df = date_forecast_data
        date_forecast_prompt_block = f"""
### SPECIFIC DATE FORECAST FOR REQUESTED DATE ({df['formatted_date']} - {df['day_name']})
The manager is specifically inquiring about the forecast on {df['formatted_date']} ({target_date_label}) for {df['item_name']}:
- Target Date: {df['formatted_date']} ({df['day_name']})
- Product Name: {df['item_name']}
- Baseline Daily Average Demand: {df['base_demand']} units
- Day-of-Week Seasonality: {df['day_name']} (Multiplier: {df['dow_multiplier']}x)
- Calendar Holiday / Festival Occasion: {df['event_badge']}
- Event / Festival / Weekend Lift: {df['event_boost_pct']}
- Weather Context: {df['weather_condition']}
- PREDICTED DEMAND FOR THIS TARGET DATE: {df['predicted_demand']} units ({df['variance_from_baseline']} vs average)
- Current Stock: {df['current_stock']} units
- Safety Stock Buffer: {df['safety_stock']} units
- Target Inventory: {df['target_inventory']} units
- Recommended Reorder: {df['recommended_reorder']} units (Formula: {df['reorder_formula']})

CRITICAL MANDATORY INSTRUCTIONS FOR THIS QUERY:
1. The manager is asking ONLY about {df['item_name']} for {df['formatted_date']}.
2. You MUST state that the predicted demand for {df['item_name']} on {df['formatted_date']} is **{df['predicted_demand']} units**.
3. Do NOT report the generic baseline ({df['base_demand']} units) as the forecast for {df['formatted_date']}.
4. STRICT PROHIBITION: DO NOT mention or list other store products (sweet, paaaav, kajukatli, periperi, etc.). DO NOT append an inventory status report or a restock list.
5. End your response immediately after explaining the demand for {df['item_name']}.

Follow this exact clean structure:
Hello! Here is the demand forecast for **{df['item_name']}** for **{df['formatted_date']} ({df['day_name']})**:

* **Target Date:** {df['formatted_date']} ({df['day_name']})
* **Occasion / Seasonality:** {df['event_badge']}
* **Baseline Demand:** {df['base_demand']} units
* **Predicted Demand for {target_date_label}:** **{df['predicted_demand']} units** ({df['variance_from_baseline']} vs average)
* **Current Stock:** {df['current_stock']} units
* **Safety Buffer:** {df['safety_stock']} units
* **Recommended Reorder:** **{df['recommended_reorder']} units** (Formula: {df['reorder_formula']})

Explain in 1-2 concise sentences how {df['day_name']} footfall and {df['event_badge']} drive this demand of {df['predicted_demand']} units. Do NOT output anything else after this explanation.
"""
    elif multi_item_date_forecasts:
        d0 = multi_item_date_forecasts[0]
        date_forecast_prompt_block = f"""
### SPECIFIC DATE FORECAST FOR ALL PRODUCTS ({d0['formatted_date']} - {d0['day_name']})
The manager is asking about the forecast for {d0['formatted_date']} ({target_date_label}).
Occasion: {d0['event_badge']} ({d0['event_boost_pct']} lift).
Product forecast calculations for this date:
{json.dumps(multi_item_date_forecasts, indent=2)}

CRITICAL MANDATORY INSTRUCTION:
List each product on its own bullet point with its date-specific predicted demand and restock recommendation for {d0['formatted_date']}.
"""

    prompt = f"""You are the RestockIQ Intelligent Store Copilot, a data-aware inventory and demand forecasting AI assistant for food retailers and bakeries.

### STORE CONTEXT
- Store Name: {shop_name}
- Location: {shop_location}
- Current Weather: {weather_desc}
- Upcoming Calendar Events: {events_desc}

### REAL-TIME VERIFIED INVENTORY ({len(enriched_items)} SKUs tracked)
{json.dumps(enriched_items, indent=2)}

### ACTIVE INTRADAY SPOILAGE & WASTE MITIGATION ALERTS ({len(enriched_alerts)} active)
{json.dumps(enriched_alerts, indent=2)}

{date_forecast_prompt_block}

{f"### FOCUS ITEM DETAILS AND NEWVENDOR FORMULA\n{json.dumps(focused_item_data, indent=2)}" if focused_item_data else ""}

### RECENT CONVERSATION HISTORY
{history_block}

### MANAGER'S NEW QUESTION
"{query}"

### STRICT OPERATIONAL GUIDELINES & STRUCTURING:
1. RELEVANCE & CONCISENESS (CRITICAL):
   - Answer ONLY what the manager explicitly asked.
   - If the manager asks about a single product or forecast (e.g. 'how much brfi will sell tomorrow', 'what is sweet stock?'):
     Provide ONLY the answer for that product.
     DO NOT mention other products (such as sweet, paaaav, kajukatli, periperi, etc.).
     DO NOT append an inventory status report or a restock list.
     End your response immediately after explaining that specific product.
   - ONLY provide the full restock list (Critical Restock Needed / Restock Recommended) if the manager EXPLICITLY asks 'which products need restocking?', 'what should I reorder?', or 'show me the restock list'.
2. PRESENTATION & READABILITY:
   - Provide clean, human-readable markdown with clear bullet points.
   - Always put clean blank lines between paragraphs, headers, and bullet sections.
   - Keep the introductory sentence short (at most 1 sentence).
   - If answering about a specific future date, state the computed predicted demand for that date and explain the day-of-week and event factors concisely in natural human language.
3. Ground your answer ENTIRELY in verified store data. Never fabricate numbers.
"""

    # 6. Execute with LLM (with cascade retry)
    answer = _call_gemini_with_retry(prompt)
    if answer and len(answer.strip()) > 5:
        sanitized = _sanitize_response(answer.strip(), query, target_item)
        if len(sanitized) > 5:
            return sanitized
        return answer.strip()

    # 7. Fallback to dynamic data-driven engine if LLM API is completely unreachable
    logger.warning("LLM API call did not return a response. Utilizing dynamic data-driven fallback.")
    return _dynamic_data_driven_chat_fallback(
        query=query,
        items=items,
        alerts=alerts,
        history=history,
        target_item=target_item,
        target_date=target_date,
        target_date_label=target_date_label,
        date_forecast_data=date_forecast_data,
        multi_item_date_forecasts=multi_item_date_forecasts,
    )


def _dynamic_data_driven_chat_fallback(
    query: str,
    items: List[Dict[str, Any]],
    alerts: List[Dict[str, Any]],
    history: Optional[List[Dict[str, str]]] = None,
    target_item: Optional[Dict[str, Any]] = None,
    target_date: Optional[date] = None,
    target_date_label: Optional[str] = None,
    date_forecast_data: Optional[Dict[str, Any]] = None,
    multi_item_date_forecasts: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Dynamic, non-hardcoded data-driven fallback.
    Inspects live items, computes Newsvendor math, and summarizes actual store state.
    Supports date-specific forecasting for relative or explicit future dates.
    """
    # 0. Date-specific forecast fallback
    if date_forecast_data:
        df = date_forecast_data
        reorder_text = f"Recommended reorder is **{df['recommended_reorder']} units** (Formula: {df['reorder_formula']})." if df['recommended_reorder'] > 0 else "Current stock is sufficient to meet forecasted demand."
        return (
            f"Hello! Here is the demand forecast for **{df['item_name']}** for **{df['formatted_date']} ({df['day_name']})**:\n\n"
            f"* **Target Date:** {df['formatted_date']} ({df['day_name']})\n"
            f"* **Occasion / Seasonality:** {df['event_badge']}\n"
            f"* **Baseline Demand:** {df['base_demand']} units\n"
            f"* **Predicted Demand for {target_date_label or 'this date'}:** **{df['predicted_demand']} units** ({df['variance_from_baseline']} vs average)\n"
            f"* **Current Stock:** {df['current_stock']} units\n"
            f"* **Safety Buffer:** {df['safety_stock']} units\n"
            f"* **Recommended Reorder:** **{df['recommended_reorder']} units** (Formula: {df['reorder_formula']})\n\n"
            f"Demand for **{df['item_name']}** is projected at **{df['predicted_demand']} units** on {df['day_name']} "
            f"factoring in {df['day_name']} footfall patterns ({df['dow_multiplier']}x) and {df['event_badge']}. {reorder_text}"
        )

    if multi_item_date_forecasts:
        d0 = multi_item_date_forecasts[0]
        items_lines = []
        for df in multi_item_date_forecasts:
            items_lines.append(
                f"* **{df['item_name']}**: Predicted Demand: **{df['predicted_demand']} units** "
                f"(Current Stock: {df['current_stock']}, Reorder: **{df['recommended_reorder']} units**)."
            )
        return (
            f"Hello! Here is the demand forecast across products for **{d0['formatted_date']} ({d0['day_name']})**:\n\n"
            f"**Seasonality / Events:** {d0['event_badge']} ({d0['event_boost_pct']} lift)\n\n"
            + "\n".join(items_lines)
        )

    if target_item is None:
        target_item = _resolve_target_item(query, items, history)

    q = query.lower()

    # 1. Product-specific questions
    if target_item:
        name = target_item.get("name", "Product")
        curr = int(target_item.get("currentStock", 0))
        pred = int(target_item.get("predictedDemand", 0))
        safety = int(target_item.get("safetyStock", 0))
        price = float(target_item.get("price", 0.0))
        target_inv = pred + safety
        reorder = max(0, target_inv - curr)

        if "why" in q or "reason" in q or "calculate" in q or "explain" in q:
            return (
                f"For **{name}**, RestockIQ calculates a target inventory of **{target_inv} units** "
                f"({pred} predicted demand + {safety} safety buffer). Because your current stock is **{curr} units**, "
                f"the recommended order is **{reorder} units** ({target_inv} - {curr} = {reorder})."
            )

        if "how much" in q or "remain" in q or "stock" in q or "left" in q:
            return (
                f"You currently have **{curr} units** of **{name}** in stock against a predicted demand of **{pred} units**. "
                f"{'Stock is currently sufficient.' if curr >= target_inv else f'Recommended restock quantity is **{reorder} units**.'}"
            )

        if "demand" in q or "forecast" in q or "tomorrow" in q:
            return (
                f"The forecasted demand for **{name}** is **{pred} units**. Current stock is **{curr} units**, "
                f"with a recommended restock quantity of **{reorder} units**."
            )

        return (
            f"**{name}**: Current stock is **{curr} units**, predicted demand is **{pred} units**, "
            f"and safety buffer is **{safety} units**. Recommended restock order is **{reorder} units** (Price: ₹{price:.2f})."
        )

    # 2. Waste, spoilage, or discount alerts
    if any(w in q for w in ["alert", "waste", "spoil", "discount", "loss", "risk"]):
        if alerts:
            alert_items = [
                f"* **{a.get('name')}**: {a.get('riskLevel', 'High').capitalize()} Risk ({int(float(a.get('sales_pace_ratio', 0))*100)}% pace). Action: {a.get('recommendedAction')}"
                for a in alerts[:4]
            ]
            return f"There are currently **{len(alerts)} active waste alerts**:\n\n" + "\n".join(alert_items)
        return "All items are currently selling at healthy velocity with no high-risk waste alerts active."

    # 3. Restock recommendations query
    if any(w in q for w in ["restock", "order", "need", "reorder", "shortage", "buy"]):
        critical = []
        recommended = []
        for it in items:
            c = int(it.get("currentStock", 0))
            p = int(it.get("predictedDemand", 0))
            s = int(it.get("safetyStock", 0))
            t = p + s
            diff = max(0, t - c)
            if diff > 0:
                cat = it.get("category", "Item")
                if c <= s:
                    critical.append(f"* **{it.get('name')}** ({cat}): Current stock is {c} units (Demand: {p}, Safety: {s}). Recommended reorder: **{diff} units**.")
                else:
                    recommended.append(f"* **{it.get('name')}** ({cat}): Current stock is {c} units. Recommended reorder: **{diff} units** (Demand {p} + Safety {s} - Stock {c}).")

        sections = []
        if critical:
            sections.append("**Critical Restock Needed (At or Below Safety Buffer):**\n" + "\n".join(critical))
        if recommended:
            sections.append("**Restock Recommended (Stock Below Target Inventory):**\n" + "\n".join(recommended))

        if sections:
            return "Here are the products currently requiring attention and restocking:\n\n" + "\n\n".join(sections)
        return "All inventory levels currently satisfy demand and safety buffer thresholds. No restocks required today."

    # 4. Overview or store summary
    if any(w in q for w in ["overview", "summary", "status", "health", "how are we", "situation"]):
        total_skus = len(items)
        urgent = sum(1 for it in items if int(it.get("currentStock", 0)) <= int(it.get("safetyStock", 0)))
        return (
            f"RestockIQ Store Overview: Tracking **{total_skus} SKUs**.\n\n"
            f"* **{urgent} items** are at or below safety buffer.\n"
            f"* **{len(alerts)} items** have active waste mitigation alerts."
        )

    # 5. Fallback with honest acknowledgment of tracked catalog
    tracked_names = ", ".join([f"**{it.get('name')}**" for it in items[:6]])
    return (
        f"I couldn't find an item or metric matching your request in the live store database.\n\n"
        f"Currently tracked products include: {tracked_names}. You can ask about current stock, forecasts, restock reasons, or waste alerts."
    )

