import os
import google.generativeai as genai
from pydantic import BaseModel
from typing import List, Optional

# Configure Gemini — loaded fresh on each request so reloads pick up .env changes
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    source: str
    history: Optional[List[ChatMessage]] = []

def get_rule_based_response(message: str, stats: dict, top_events: list) -> str:
    """Generates a rule-based response directly from backend data when LLM is unavailable."""
    msg_lower = message.lower()
    
    if "risk" in msg_lower or "dangerous" in msg_lower or "top" in msg_lower:
        response = "**Top 5 Highest-Risk Events:**\n\n"
        for i, ev in enumerate(top_events, 1):
            fac = f"near {ev['nearest_facility_name']}" if ev['nearest_facility_name'] else "no known facility nearby"
            response += f"{i}. **{ev['classification']}** (Risk Score: {ev['risk_score']}) — {fac}. FRP: {ev['frp']} MW.\n"
        return response
        
    elif "persistent" in msg_lower:
        return f"There are currently **{stats['persistent_sources']} persistent thermal sources** detected in the {stats.get('source', 'current')} dataset. These are locations that have been actively burning for 3 or more consecutive days."
        
    elif "industrial" in msg_lower or "facility" in msg_lower:
        return f"We have detected **{stats['industrial_fires']} industrial fires** and **{stats['gas_flares']} gas flares** out of {stats['total_hotspots']} total anomalies."
        
    elif "stat" in msg_lower or "summary" in msg_lower or "overview" in msg_lower or "data" in msg_lower:
        return f"**Dataset Summary:**\n- Total Anomalies: {stats['total_hotspots']}\n- High Risk Events: {stats['high_risk_events']}\n- Industrial Fires: {stats['industrial_fires']}\n- Gas Flares: {stats['gas_flares']}\n- Persistent Sources: {stats['persistent_sources']}"
        
    else:
        return f"Based on the current data, we have {stats['total_hotspots']} active thermal anomalies, including {stats['high_risk_events']} high-risk events. Try asking me about 'highest risk events', 'persistent sources', or 'industrial stats'!"

def generate_pyro_response(request: ChatRequest, stats: dict, top_events: list) -> str:
    """Uses Gemini API to answer questions, falling back to rule-based logic on failure."""
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("GEMINI_API_KEY")
    
    # If no API key, use rule-based immediately
    if not api_key:
        fallback = get_rule_based_response(request.message, stats, top_events)
        return fallback + "\n\n*(AI explanation unavailable: GEMINI_API_KEY not set)*"

    genai.configure(api_key=api_key)

    # Format the dataset context
    context = "You are Pyro, an AI Fire Investigation Assistant. You help operators understand thermal anomalies.\n\n"
    context += f"CURRENT DATASET ({request.source.upper()}):\n"
    context += f"- Total Anomalies: {stats['total_hotspots']}\n"
    context += f"- Industrial Fires: {stats['industrial_fires']}\n"
    context += f"- Gas Flares: {stats['gas_flares']}\n"
    context += f"- Persistent Sources: {stats['persistent_sources']}\n"
    context += f"- High Risk Events: {stats['high_risk_events']}\n\n"
    
    context += "TOP 5 HIGHEST RISK EVENTS:\n"
    for ev in top_events:
        fac = f"{ev['nearest_facility_name']} ({ev['nearest_facility_dist_km']:.1f}km)" if ev['nearest_facility_name'] else "None"
        context += f"- {ev['classification']} | Risk: {ev['risk_score']} | FRP: {ev['frp']} MW | Persistent: {bool(ev['is_persistent'])} | Near: {fac}\n"
        
    context += "\nKeep your answers concise, professional, and directly reference the data provided above if relevant. Do not invent data."

    # Format history
    messages = []
    for msg in request.history:
        role = "user" if msg.role == "user" else "model"
        messages.append({"role": role, "parts": [msg.content]})
        
    # Use gemini-flash-latest (fast, available on this key)
    model = genai.GenerativeModel('gemini-flash-latest', system_instruction=context)
    
    try:
        chat = model.start_chat(history=messages)
        response = chat.send_message(request.message)
        return response.text
    except Exception as e:
        print(f"[Pyro] Gemini error/quota exceeded: {e}. Falling back to rule-based.")
        
        # Fallback to rule-based
        fallback = get_rule_based_response(request.message, stats, top_events)
        return fallback + "\n\n*(AI explanation temporarily unavailable due to API limits. Response generated directly from local data)*"
