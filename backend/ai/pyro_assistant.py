import os
import time
import re
import hashlib
import google.generativeai as genai
from pydantic import BaseModel
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    source: str
    history: Optional[List[ChatMessage]] = []


# ── In-memory response cache (avoids duplicate API calls) ────────────────────
_RESPONSE_CACHE: dict = {}
_CACHE_TTL_SECONDS = 120  # Cache entries expire after 2 minutes

def _cache_key(message: str, source: str) -> str:
    return hashlib.md5(f"{source}:{message.lower().strip()}".encode()).hexdigest()

def _get_cached(key: str):
    entry = _RESPONSE_CACHE.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL_SECONDS:
        return entry["response"]
    return None

def _set_cached(key: str, response: str):
    _RESPONSE_CACHE[key] = {"response": response, "ts": time.time()}


# ── Rule-based engine (instant, no API call) ─────────────────────────────────
# Pre-routing keywords: if matched, skip Gemini entirely for speed
_INSTANT_KEYWORDS = {
    "risk": ["risk", "dangerous", "top event", "worst", "highest"],
    "persistent": ["persistent", "burning", "days"],
    "industrial": ["industrial", "facility", "refinery", "plant"],
    "stats": ["stat", "summary", "overview", "total", "count", "how many", "data"],
    "gas": ["gas flare", "flare"],
    "wildfire": ["wildfire", "forest fire"],
    "help": ["help", "what can", "what do", "what are you", "hello", "hi ", "hey"],
}

def _is_factual_query(message: str) -> bool:
    """Returns True if the query can be answered instantly from local data."""
    msg_lower = message.lower()
    for kws in _INSTANT_KEYWORDS.values():
        if any(kw in msg_lower for kw in kws):
            return True
    return False


def get_rule_based_response(message: str, stats: dict, top_events: list) -> str:
    """Instant response generated directly from backend data — no API call needed."""
    msg_lower = message.lower()

    if any(k in msg_lower for k in ["help", "what can", "hello", "hi ", "hey", "what are you", "what do you"]):
        return (
            "Hey! I'm **Pyro** 🔥, your fire investigation assistant.\n\n"
            "I can tell you about:\n"
            "- **Top risk events** — highest-risk detections right now\n"
            "- **Persistent sources** — locations burning for 3+ days\n"
            "- **Industrial fires & gas flares** — facility-linked anomalies\n"
            "- **Dataset summary** — total counts and stats\n\n"
            "Just ask!"
        )

    if any(k in msg_lower for k in ["risk", "dangerous", "top event", "worst", "highest"]):
        if not top_events:
            return "No high-risk events found in the current dataset."
        response = "**Top 5 Highest-Risk Events:**\n\n"
        for i, ev in enumerate(top_events, 1):
            fac = f"near _{ev['nearest_facility_name']}_" if ev['nearest_facility_name'] else "no known facility nearby"
            response += f"{i}. **{ev['classification']}** — Risk Score: `{ev['risk_score']}` | {fac} | FRP: {ev['frp']} MW\n"
        return response

    if any(k in msg_lower for k in ["persistent", "burning", "days"]):
        return (
            f"There are currently **{stats['persistent_sources']} persistent thermal sources** in the dataset. "
            f"These locations have been burning for 3 or more consecutive days."
        )

    if any(k in msg_lower for k in ["gas flare", "flare"]):
        return f"There are **{stats['gas_flares']} gas flares** detected — these are typically associated with oil & gas processing facilities."

    if any(k in msg_lower for k in ["wildfire", "forest fire"]):
        total = stats.get('total_hotspots', 0)
        return f"Wildfire detections are present in the dataset. Total anomalies: {total}. Use the map filter to isolate wildfire events."

    if any(k in msg_lower for k in ["industrial", "facility", "refinery", "plant"]):
        return (
            f"We've detected **{stats['industrial_fires']} industrial fires** and **{stats['gas_flares']} gas flares** "
            f"out of {stats['total_hotspots']} total thermal anomalies."
        )

    if any(k in msg_lower for k in ["stat", "summary", "overview", "total", "count", "how many", "data"]):
        return (
            f"**📊 Dataset Summary:**\n"
            f"- Total Anomalies: **{stats['total_hotspots']}**\n"
            f"- High Risk: **{stats['high_risk_events']}**\n"
            f"- Industrial Fires: **{stats['industrial_fires']}**\n"
            f"- Gas Flares: **{stats['gas_flares']}**\n"
            f"- Persistent Sources: **{stats['persistent_sources']}**"
        )

    # Generic fallback
    return (
        f"The current dataset has **{stats['total_hotspots']} thermal anomalies**, "
        f"including **{stats['high_risk_events']} high-risk events**.\n\n"
        f"Ask me about: `top risk events`, `persistent sources`, `industrial stats`, or `gas flares`."
    )


def _call_gemini(model, messages, user_message: str) -> str:
    """Blocking Gemini call — run in a thread so we can apply a hard timeout."""
    chat = model.start_chat(history=messages)
    response = chat.send_message(user_message)
    return response.text


def generate_pyro_response(request: ChatRequest, stats: dict, top_events: list) -> str:
    """
    Fast response strategy:
      1. Check in-memory cache (instant)
      2. Pre-route factual queries to rule-based engine (instant, no API)
      3. Try Gemini with a hard 8s timeout
      4. If Gemini times out or hits quota, fall back to rule-based silently
    """
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")
    cache_key = _cache_key(request.message, request.source)

    # ── Step 1: Cache hit ────────────────────────────────────────────────────
    cached = _get_cached(cache_key)
    if cached:
        print(f"[Pyro] Cache hit for: {request.message[:40]}")
        return cached

    # ── Step 2: Factual pre-routing (instant) ────────────────────────────────
    if _is_factual_query(request.message):
        result = get_rule_based_response(request.message, stats, top_events)
        _set_cached(cache_key, result)
        return result

    # ── Step 3: No API key ───────────────────────────────────────────────────
    if not api_key:
        return get_rule_based_response(request.message, stats, top_events)

    genai.configure(api_key=api_key)

    # Build minimal context (shorter = faster API response)
    context = (
        "You are Pyro, a concise AI fire investigation assistant. "
        "Answer in 2-4 sentences maximum using the data below.\n\n"
        f"Dataset ({request.source}): {stats['total_hotspots']} anomalies, "
        f"{stats['high_risk_events']} high-risk, "
        f"{stats['industrial_fires']} industrial fires, "
        f"{stats['gas_flares']} gas flares, "
        f"{stats['persistent_sources']} persistent sources.\n"
    )
    if top_events:
        top = top_events[0]
        fac = top['nearest_facility_name'] or 'unknown'
        context += f"Top risk: {top['classification']} (score {top['risk_score']}, FRP {top['frp']} MW) near {fac}.\n"
    context += "Be brief and professional. Do not invent data."

    messages = []
    for msg in request.history[-4:]:  # Only last 4 messages to reduce tokens
        role = "user" if msg.role == "user" else "model"
        messages.append({"role": role, "parts": [msg.content]})

    model = genai.GenerativeModel('gemini-flash-latest', system_instruction=context)

    # ── Step 4: Gemini with 8s hard timeout ─────────────────────────────────
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_call_gemini, model, messages, request.message)
        result = future.result(timeout=8)
        _set_cached(cache_key, result)
        return result
    except FuturesTimeoutError:
        print("[Pyro] Gemini timed out after 8s. Using instant rule-based fallback.")
        future.cancel()
    except Exception as e:
        err = str(e)
        is_rate_limit = "429" in err or "quota" in err.lower()
        if is_rate_limit:
            print(f"[Pyro] Rate limited. Using instant rule-based fallback.")
        else:
            print(f"[Pyro] Gemini error: {err[:80]}. Using rule-based fallback.")
    finally:
        executor.shutdown(wait=False)

    result = get_rule_based_response(request.message, stats, top_events)
    _set_cached(cache_key, result)
    return result
