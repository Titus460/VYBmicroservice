"""
Groq-powered explanations for the manager match demo (docs/match-demo.html).

Uses the same GROQ_API_KEY / vibr_config.json as llm_explain.py.
Warm, elaborative copy for manager demos — still plain English.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from Model.recsys.llm_explain import _call_groq, is_ai_explain_enabled

logger = logging.getLogger(__name__)

_DEMO_SYSTEM = (
    "You explain dating-app recommendations warmly and thoroughly for a live product demo. "
    "Write in plain English for non-technical managers. Be specific and descriptive — "
    "walk through why someone was ranked, using the data provided. "
    "No ML jargon, formulas, or weights. Return valid JSON only."
)


def _parse_demo_response(content: str) -> List[dict]:
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


def _top_spots(personality: dict, limit: int = 3) -> List[str]:
    venues = personality.get("top_venues") or []
    return [v.get("venue") for v in venues if v.get("venue")][:limit]


def _compact_user(user: dict, learned: Optional[dict] = None) -> dict:
    personality = user.get("personality") or {}
    ctx = {
        "interests": user.get("interests") or [],
        "intent": user.get("answer3") or "",
        "communication": user.get("commType") or "",
        "prompt_perfect_day": user.get("prompt1") or "",
        "prompt_relax": user.get("prompt2") or "",
        "checkins": user.get("checkins") or {},
        "check_in_vibe": personality.get("archetype") or personality.get("headline") or "",
        "personality_traits": personality.get("traits") or [],
        "top_spots": _top_spots(personality),
        "observation": personality.get("observation") or "",
    }
    if learned:
        ctx["from_your_likes"] = learned
    return ctx


def _compact_match(match: dict) -> dict:
    personality = match.get("personality") or {}
    breakdown = match.get("score_breakdown") or {}
    return {
        "id": match.get("id"),
        "name": match.get("name"),
        "age": match.get("age"),
        "interests": match.get("interests") or [],
        "intent": match.get("answer3") or "",
        "communication": match.get("commType") or "",
        "prompt_perfect_day": match.get("prompt1_response") or "",
        "prompt_relax": match.get("prompt2_response") or "",
        "distance_km": match.get("distance_km"),
        "checkins": match.get("checkins") or {},
        "check_in_vibe": personality.get("archetype") or personality.get("headline") or "",
        "personality_traits": personality.get("traits") or [],
        "top_spots": _top_spots(personality),
        "total_score": breakdown.get("total_score") or match.get("similarity_score"),
        "tier": breakdown.get("tier") or match.get("matchLabel") or "",
        "score_breakdown": breakdown,
        "rule_based_reasons": match.get("matchReasons") or [],
        "learned_boost_reasons": match.get("learned_reasons") or [],
    }


def enrich_demo_matches(
    user: dict,
    matches: List[dict],
    learned: Optional[dict] = None,
    for_you_only: bool = True,
) -> Dict[str, Any]:
    """
    Return Groq explanations for demo candidates (For you tab).
    On failure returns {"ok": False, "matches": [], "error": "..."}.
    """
    if not matches:
        return {"ok": True, "matches": [], "groq": False, "elapsed_ms": 0}

    if not is_ai_explain_enabled():
        return {
            "ok": True,
            "matches": [],
            "groq": False,
            "elapsed_ms": 0,
            "error": "Groq not configured. Set GROQ_API_KEY or groq_api_key in vibr_config.json.",
        }

    t0 = time.perf_counter()
    requester = _compact_user(user, learned)
    candidates = [_compact_match(m) for m in matches]

    prompt = f"""Explain why this person appears in the viewer's personalized For you feed.

VIEWER:
{json.dumps(requester, ensure_ascii=False)}

MATCHES (each includes score_breakdown — the exact factors and points used to rank them):
{json.dumps(candidates, ensure_ascii=False)}

The app scores each match on: shared interests, proximity (distance), dating intent, communication style, check-ins (lifestyle rhythm + shared venue types), reciprocal likelihood, and boosts from the viewer's recent likes.

Write warmly for a manager demo. Use score_breakdown.factors and profile details — explain what actually drove the score. Do not invent facts.

For EACH match return:
- aiMatchSummary: one friendly sentence for the profile card (max 28 words)
- aiReasoning: 3–4 sentences that walk through the match — cover interests, proximity, check-ins, intent, communication, reciprocal signal, and any like-pattern boost when they contributed. Connect the dots like a thoughtful friend explaining the ranking.
- aiReasonBullets: 4–6 bullet strings for "Why this match?" — one fuller bullet per factor that mattered (interests, proximity, check-ins, intent, communication, reciprocal, from_your_likes). Each bullet can be up to 22 words. Mention specific shared interests, distance, venue overlap, or intent alignment when present.

Return JSON only:
{{"matches": [{{"id": <id>, "aiMatchSummary": "...", "aiReasoning": "...", "aiReasonBullets": ["...", "..."]}}]}}"""

    max_tokens = 1200 if len(matches) == 1 else min(3200, 900 * len(matches))
    raw = _call_groq(prompt, max_tokens=max_tokens, system=_DEMO_SYSTEM)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if not raw:
        return {
            "ok": False,
            "matches": [],
            "groq": True,
            "elapsed_ms": elapsed_ms,
            "error": "Groq request failed (often rate limit — wait ~20s and retry)",
        }

    try:
        parsed = _parse_demo_response(raw)
        by_id = {int(p["id"]): p for p in parsed if p.get("id") is not None}
    except Exception as e:
        logger.warning("Failed to parse Groq demo explain JSON: %s", e)
        return {
            "ok": False,
            "matches": [],
            "groq": True,
            "elapsed_ms": elapsed_ms,
            "error": "Invalid Groq JSON response",
        }

    out = []
    for m in matches:
        mid = int(m.get("id", 0))
        ai = by_id.get(mid)
        if not ai:
            continue
        bullets = ai.get("aiReasonBullets") or []
        if isinstance(bullets, str):
            bullets = [bullets]
        out.append(
            {
                "id": mid,
                "aiMatchSummary": ai.get("aiMatchSummary") or m.get("matchSummary", ""),
                "aiReasoning": ai.get("aiReasoning") or "",
                "aiReasonBullets": [str(b) for b in bullets if b][:6],
            }
        )

    return {
        "ok": True,
        "matches": out,
        "groq": True,
        "elapsed_ms": elapsed_ms,
        "match_count": len(matches),
        "explained_count": len(out),
    }


def _parse_learning_response(content: str) -> List[dict]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    data = json.loads(content)
    if isinstance(data, dict) and "dimensions" in data:
        return data["dimensions"]
    if isinstance(data, list):
        return data
    return []


def enrich_demo_learning(
    user: dict,
    sections: List[dict],
    stats: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Groq explanations for the demo “What the AI is learning about you” panel.
    Elaborative paragraph per dimension.
    """
    if not sections:
        return {"ok": True, "dimensions": [], "groq": False, "elapsed_ms": 0}

    if not is_ai_explain_enabled():
        return {
            "ok": True,
            "dimensions": [],
            "groq": False,
            "elapsed_ms": 0,
            "error": "Groq not configured. Set GROQ_API_KEY or groq_api_key in vibr_config.json.",
        }

    t0 = time.perf_counter()
    compact_sections = []
    for section in sections:
        items = section.get("items") or []
        nonzero = [
            {"name": i.get("name"), "likes": i.get("likes", 0), "hides": i.get("hides", 0)}
            for i in items
            if (i.get("likes") or 0) > 0 or (i.get("hides") or 0) > 0
        ]
        compact_sections.append(
            {
                "title": section.get("dimension") or section.get("title"),
                "signals": nonzero[:5],
                "summary": section.get("rule_based_conclusion") or section.get("conclusion") or "",
            }
        )

    prompt = f"""Explain what the recommendation system is learning from this user's likes and hides.

USER: {json.dumps(_compact_user(user), ensure_ascii=False)}

DIMENSIONS (like/hide counts per area; summary is the app's template):
{json.dumps(compact_sections, ensure_ascii=False)}

For EACH dimension with the same title:
- explanation: 2–3 sentences in warm, plain language — what the AI is inferring from the counts
- Mention specific items when likes or hides are nonzero (e.g. "you've liked 3 profiles into Coffee")
- If mostly hides, explain what they seem to avoid; if mostly likes, what they gravitate toward
- Do not copy the summary verbatim — expand on it
- If no signal yet, say the AI is still gathering data for that area

Return JSON only:
{{"dimensions": [{{"title": "Interests", "explanation": "..."}}]}}"""

    raw = _call_groq(prompt, max_tokens=1600, system=_DEMO_SYSTEM)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if not raw:
        return {
            "ok": False,
            "dimensions": [],
            "groq": True,
            "elapsed_ms": elapsed_ms,
            "error": "Groq request failed (often rate limit — wait ~20s and retry)",
        }

    try:
        parsed = _parse_learning_response(raw)
        allowed = {s.get("dimension") or s.get("title") for s in sections}
        out = []
        for row in parsed:
            title = row.get("title") or row.get("dimension")
            expl = (row.get("explanation") or row.get("groqExplanation") or "").strip()
            if title and expl and title in allowed:
                out.append({"title": title, "explanation": expl})
    except Exception as e:
        logger.warning("Failed to parse Groq learning JSON: %s", e)
        return {
            "ok": False,
            "dimensions": [],
            "groq": True,
            "elapsed_ms": elapsed_ms,
            "error": "Invalid Groq JSON response",
        }

    return {
        "ok": True,
        "dimensions": out,
        "groq": True,
        "elapsed_ms": elapsed_ms,
        "dimension_count": len(sections),
        "explained_count": len(out),
    }


def enrich_demo_my_checkins(user: dict) -> Dict[str, Any]:
    """Groq explanation of the requesting user's check-ins only."""
    if not is_ai_explain_enabled():
        return {
            "ok": True,
            "explanation": "",
            "groq": False,
            "elapsed_ms": 0,
            "error": "Groq not configured. Set GROQ_API_KEY or groq_api_key in vibr_config.json.",
        }

    checkins = user.get("checkins") or {}
    personality = user.get("personality") or {}
    vibe = personality.get("archetype") or personality.get("headline") or ""
    top_spots = _top_spots(personality, limit=5)

    t0 = time.perf_counter()
    prompt = f"""Explain this user's monthly check-in pattern for a dating app demo.

CHECK-INS (visits per month by venue type):
{json.dumps(checkins, indent=2)}

INFERRED LIFESTYLE:
{json.dumps({
    "vibe": vibe,
    "traits": personality.get("traits") or [],
    "top_spots": top_spots,
    "observation": personality.get("observation") or "",
}, indent=2)}

Write 3–4 sentences in warm, plain language:
- What their check-in rhythm suggests about how they live (gym, cafes, culture, nights out, etc.)
- How the app uses their check-ins together with other people's patterns to score matches
- Mention specific venue types from the data when helpful

No ML jargon. Do not invent venues or habits not in the JSON.

Return JSON only: {{"explanation": "..."}}"""

    raw = _call_groq(prompt, max_tokens=450, system=_DEMO_SYSTEM)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if not raw:
        return {
            "ok": False,
            "explanation": "",
            "groq": True,
            "elapsed_ms": elapsed_ms,
            "error": "Groq request failed (often rate limit — wait ~20s and retry)",
        }

    try:
        content = raw.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        data = json.loads(content)
        explanation = (data.get("explanation") or "").strip()
        if not explanation:
            raise ValueError("empty explanation")
    except Exception as e:
        logger.warning("Failed to parse Groq my-checkins JSON: %s", e)
        return {
            "ok": False,
            "explanation": "",
            "groq": True,
            "elapsed_ms": elapsed_ms,
            "error": "Invalid Groq JSON response",
        }

    return {
        "ok": True,
        "explanation": explanation,
        "groq": True,
        "elapsed_ms": elapsed_ms,
    }
