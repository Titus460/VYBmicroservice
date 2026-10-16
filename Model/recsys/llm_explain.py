"""
Natural-language match explanations via Groq (Llama models).

Set environment variables:
    GROQ_API_KEY=gsk_...          # from https://console.groq.com
    GROQ_MODEL=llama-3.3-70b-versatile   # optional
    VYB_AI_EXPLAIN=1              # set 0 to disable

Note: LLAMA_CLOUD_API_KEY is for LlamaIndex Cloud (parsing/indexing), not Groq chat.
"""

import json
import logging
import os
import re
import time
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def _vibr_config_paths():
    """Same config file as netwirk_profile (cwd) plus repo-root fallback."""
    candidates = [
        os.path.join(os.getcwd(), "vibr_config.json"),
        os.path.join(os.path.dirname(__file__), "..", "..", "vibr_config.json"),
    ]
    seen = set()
    for path in candidates:
        abs_path = os.path.abspath(path)
        if abs_path not in seen and os.path.isfile(abs_path):
            seen.add(abs_path)
            yield abs_path


def _load_vibr_config() -> dict:
    for config_path in _vibr_config_paths():
        try:
            with open(config_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            continue
    return {}


def _get_groq_api_key() -> Optional[str]:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if key:
        return key
    cfg = _load_vibr_config()
    return (
        (cfg.get("groq_api_key") or cfg.get("GROQ_API_KEY") or "")
        .strip()
        or None
    )


def is_ai_explain_enabled() -> bool:
    return os.getenv("VYB_AI_EXPLAIN", "1") == "1" and bool(_get_groq_api_key())


def _build_requester_context(my_data: dict, my_row: dict = None) -> dict:
    ctx = {
        "vibes": ", ".join(sorted(my_data.get("vibes_set") or [])),
        "communication_style": my_data.get("ans3", ""),
        "dating_goals": my_data.get("ans4", ""),
        "city": "",
        "state": "",
    }
    if my_row:
        ctx["city"] = my_row.get("city", "")
        ctx["state"] = my_row.get("state", "")
    return ctx


def _match_to_context(match: dict) -> dict:
    return {
        "userId": match.get("userId"),
        "name": match.get("fullName", ""),
        "vibes": match.get("vibes", ""),
        "city": match.get("city", ""),
        "state": match.get("state", ""),
        "communication_style": match.get("Describe_your_communication_style", ""),
        "dating_goals": match.get("What_brings_you_to_Vyb", ""),
        "prompt1": match.get("prompt1answer", ""),
        "prompt2": match.get("prompt2answer", ""),
        "wave_status": match.get("wave_status", "no_wave"),
        "similarity_score": match.get("similarity_score"),
        "rule_based_reasons": match.get("matchReasons", []),
    }


def _parse_groq_json(content: str) -> List[dict]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    data = json.loads(content)
    if isinstance(data, dict) and "matches" in data:
        return data["matches"]
    if isinstance(data, list):
        return data
    return []


def _call_groq(
    prompt: str,
    max_tokens: int = 1200,
    system: Optional[str] = None,
) -> Optional[str]:
    api_key = _get_groq_api_key()
    if not api_key:
        return None

    payload = {
        "model": DEFAULT_MODEL,
        "temperature": 0.4,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "system",
                "content": system
                or (
                    "You explain dating app matches clearly and warmly. "
                    "Return valid JSON only, no markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt, delay in enumerate((0, 2, 5, 10)):
        if delay:
            time.sleep(delay)
        try:
            resp = requests.post(
                GROQ_API_URL,
                headers=headers,
                json=payload,
                timeout=45,
            )
            if resp.status_code == 429:
                logger.warning("Groq rate limited (attempt %s)", attempt + 1)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                logger.warning("Groq rate limited (attempt %s)", attempt + 1)
                continue
            logger.warning("Groq match explain failed: %s", e)
            return None
        except Exception as e:
            logger.warning("Groq match explain failed: %s", e)
            return None

    logger.warning("Groq match explain failed: rate limit persisted after retries")
    return None


def enrich_matches_with_groq(
    matches: List[dict],
    my_data: dict,
    my_row: dict = None,
) -> List[dict]:
    """
    Add aiMatchSummary and aiReasoning to each match using Groq.
    Falls back to existing matchSummary if Groq unavailable.
    """
    if not matches or not is_ai_explain_enabled():
        return matches

    requester = _build_requester_context(my_data, my_row)
    candidates = [_match_to_context(m) for m in matches]

    prompt = f"""You are explaining why dating app profiles appear in a user's feed.

REQUESTING USER:
{json.dumps(requester, indent=2)}

CANDIDATES (each needs an explanation):
{json.dumps(candidates, indent=2)}

For EACH candidate, write:
- aiMatchSummary: one friendly sentence (max 20 words) for the profile card
- aiReasoning: 2-3 sentences explaining WHY this person was recommended. Mention specific overlaps (vibes, goals, prompts, location, wave status). Reference the ML signals when useful.

Return JSON:
{{
  "matches": [
    {{"userId": <id>, "aiMatchSummary": "...", "aiReasoning": "..."}}
  ]
}}"""

    raw = _call_groq(prompt)
    if not raw:
        return matches

    try:
        parsed = _parse_groq_json(raw)
        by_id = {int(p["userId"]): p for p in parsed if p.get("userId") is not None}
    except Exception as e:
        logger.warning("Failed to parse Groq explain JSON: %s", e)
        return matches

    enriched = []
    for m in matches:
        copy = dict(m)
        ai = by_id.get(int(m.get("userId", 0)))
        if ai:
            copy["aiMatchSummary"] = ai.get("aiMatchSummary", copy.get("matchSummary", ""))
            copy["aiReasoning"] = ai.get("aiReasoning", "")
        else:
            copy["aiMatchSummary"] = copy.get("matchSummary", "")
            copy["aiReasoning"] = ". ".join(copy.get("matchReasons", []))
        enriched.append(copy)
    return enriched
