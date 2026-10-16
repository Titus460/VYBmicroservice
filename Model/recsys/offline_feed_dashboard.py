"""In-memory ring buffer + local HTML dashboard for offline feed ranking."""

from __future__ import annotations

import html
import os
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

_MAX_EVENTS = int(os.getenv("OFFLINE_FEED_DASHBOARD_MAX_EVENTS", "200"))
_lock = threading.Lock()
_events: Deque[Dict[str, Any]] = deque(maxlen=_MAX_EVENTS)


def record_offline_feed_event(event: Dict[str, Any]) -> None:
    payload = dict(event)
    payload.setdefault("ts", datetime.now(timezone.utc).isoformat())
    with _lock:
        _events.appendleft(payload)


def list_offline_feed_events(limit: int = 100) -> List[Dict[str, Any]]:
    with _lock:
        return list(_events)[: max(1, min(limit, _MAX_EVENTS))]


def dashboard_summary(events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    rows = events if events is not None else list_offline_feed_events(limit=_MAX_EVENTS)
    total = len(rows)
    if not total:
        return {
            "total": 0,
            "cache_hit_rate": 0.0,
            "fallback_rate": 0.0,
            "avg_latency_ms": 0.0,
            "avg_personalize_returned": 0.0,
        }

    cache_hits = sum(1 for e in rows if e.get("cache_hit") is True)
    fallbacks = sum(1 for e in rows if e.get("ranker") == "sql_fallback")
    latencies = [float(e["latency_ms"]) for e in rows if e.get("latency_ms") is not None]
    returned = [
        float(e["personalize_returned"])
        for e in rows
        if e.get("personalize_returned") is not None and e.get("cache_hit") is False
    ]

    return {
        "total": total,
        "cache_hit_rate": round(100.0 * cache_hits / total, 1),
        "fallback_rate": round(100.0 * fallbacks / total, 1),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        "avg_personalize_returned": (
            round(sum(returned) / len(returned), 1) if returned else 0.0
        ),
    }


def _format_suggested(suggested: Any) -> str:
    if not suggested:
        return "—"
    parts = []
    for item in suggested:
        if not isinstance(item, dict):
            continue
        uid = item.get("user_id", "")
        name = (item.get("full_name") or "").strip()
        score = item.get("score", "")
        label = f"{uid}"
        if name:
            label += f" {name}"
        if score != "" and score is not None:
            label += f" ({score})"
        parts.append(html.escape(label))
    return "<br>".join(parts) if parts else "—"


def render_dashboard_html(limit: int = 100) -> str:
    events = list_offline_feed_events(limit=limit)
    summary = dashboard_summary(events)

    rows_html = []
    for e in events:
        viewer_id = e.get("user_id", "")
        viewer_name = (e.get("viewer_name") or "").strip()
        viewer_label = f"{viewer_id}"
        if viewer_name:
            viewer_label = f"{viewer_id} {viewer_name}"
        rows_html.append(
            "<tr>"
            f"<td>{html.escape(str(e.get('ts', '')))}</td>"
            f"<td>{html.escape(viewer_label)}</td>"
            f"<td>{html.escape(str(e.get('ranker', '')))}</td>"
            f"<td>{'true' if e.get('cache_hit') else 'false'}</td>"
            f"<td>{html.escape(str(e.get('latency_ms', '')))}</td>"
            f"<td>{html.escape(str(e.get('personalize_returned', '')))}</td>"
            f"<td>{html.escape(str(e.get('candidates', '')))}</td>"
            f"<td>{html.escape(str(e.get('matches', '')))}</td>"
            f"<td class='suggested'>{_format_suggested(e.get('suggested'))}</td>"
            "</tr>"
        )

    body_rows = "\n".join(rows_html) or (
        "<tr><td colspan='9'>No feed events yet. Call get_user_list_offline.</td></tr>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Offline Feed Dashboard</title>
  <style>
    :root {{
      --bg: #0f1419;
      --panel: #1a2332;
      --text: #e7ecf3;
      --muted: #8b9bb4;
      --accent: #3d8bfd;
      --ok: #3dd68c;
      --warn: #f5a524;
      --border: #2a3548;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: radial-gradient(1200px 600px at 10% -10%, #1b2a44, var(--bg));
      color: var(--text);
      min-height: 100vh;
      padding: 24px;
    }}
    h1 {{ margin: 0 0 8px; font-size: 1.6rem; }}
    .sub {{ color: var(--muted); margin-bottom: 20px; }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin-bottom: 20px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 14px 16px;
    }}
    .card .label {{ color: var(--muted); font-size: 0.8rem; }}
    .card .value {{ font-size: 1.4rem; margin-top: 6px; font-weight: 600; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: auto;
      max-height: 70vh;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
    }}
    th, td {{
      padding: 10px 12px;
      text-align: left;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
      position: sticky;
      top: 0;
      background: #162033;
      white-space: nowrap;
    }}
    td:not(.suggested) {{ white-space: nowrap; }}
    td.suggested {{
      white-space: normal;
      min-width: 220px;
      max-width: 420px;
      font-size: 0.85rem;
      line-height: 1.45;
      color: #c5d4ea;
    }}
    tr:hover td {{ background: rgba(61, 139, 253, 0.08); }}
    a {{ color: var(--accent); }}
  </style>
</head>
<body>
  <h1>Offline Feed Dashboard</h1>
  <p class="sub">
    Local in-memory events (last {html.escape(str(len(events)))} shown).
    Refresh the page to update. Top suggested users shown with id, name, score.
    JSON: <a href="/offline-feed-dashboard.json">/offline-feed-dashboard.json</a>
    · <a href="/offline-feed-dashboard">Refresh</a>
  </p>
  <div class="cards">
    <div class="card"><div class="label">Requests</div><div class="value">{summary['total']}</div></div>
    <div class="card"><div class="label">Cache-hit rate</div><div class="value">{summary['cache_hit_rate']}%</div></div>
    <div class="card"><div class="label">Fallback rate</div><div class="value">{summary['fallback_rate']}%</div></div>
    <div class="card"><div class="label">Avg latency (ms)</div><div class="value">{summary['avg_latency_ms']}</div></div>
    <div class="card"><div class="label">Avg Personalize returned</div><div class="value">{summary['avg_personalize_returned']}</div></div>
  </div>
  <div class="panel">
    <table>
      <thead>
        <tr>
          <th>Time (UTC)</th>
          <th>Viewer</th>
          <th>Ranker</th>
          <th>Cache hit</th>
          <th>Latency ms</th>
          <th>Personalize returned</th>
          <th>Candidates</th>
          <th>Matches</th>
          <th>Suggested users (top)</th>
        </tr>
      </thead>
      <tbody>
        {body_rows}
      </tbody>
    </table>
  </div>
</body>
</html>
"""
