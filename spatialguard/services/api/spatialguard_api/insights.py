"""Weekly AI insight for Site Analytics, written by Amazon Bedrock.

The model receives only the aggregate numbers shown on the dashboard: visit
counts, hours, zone and camera names, dwell times and layout-change dates. It
never receives images, recordings, tracks or anything about individual people.
It must use only those numbers, and its answer is checked before it is shown:
every figure must come from the data, a block list catches anything about
people's identity or appearance, and a failed note is replaced by a plain one
built from the numbers (see ``check`` and ``fallback``).

Configuration (server-side only): ``AWS_BEARER_TOKEN_BEDROCK`` (a Bedrock API
key), ``AWS_REGION`` (default us-west-2) and optionally
``PATHLIGHT_INSIGHT_MODEL`` (default Amazon Nova Pro). Values from the root
``.env`` are used when the environment does not set them.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from .models import Model

DEFAULT_MODEL = "us.amazon.nova-pro-v1:0"
KEYS = ("AWS_BEARER_TOKEN_BEDROCK", "AWS_REGION", "PATHLIGHT_INSIGHT_MODEL")


class InsightUnavailable(RuntimeError):
    pass


# Guardrails (Ring Computer Vision Guidelines: never treat model output as ground
# truth; deterministic, externally updatable block lists; a defined fallback).
# The model only ever sees aggregate counts, so any of these words means it
# invented something about people. PATHLIGHT_INSIGHT_BLOCKLIST adds more terms
# (comma-separated) without a code change.
BLOCKED_TERMS = (
    "race", "racial", "ethnic", "ethnicity", "skin", "gender", "male", "female", "men", "women", "man", "woman",
    "boy", "girl", "child", "children", "kid", "kids", "teen", "teenager", "elderly", "age", "aged",
    "face", "faces", "facial", "identity", "identified", "identify", "recognize", "recognise", "recognition",
    "suspicious", "suspect", "criminal", "crime", "thief", "theft", "steal", "stealing", "shoplift", "shoplifting",
    "loiter", "loiterer", "loiterers", "loitering", "homeless", "disabled", "disability", "wheelchair", "religion", "religious",
    "weapon", "gun", "license plate", "plate number", "stalk", "stalking",
)
# Numbers a note may use without coming from the data: hours, days of the week, "one action".
FREE_NUMBERS = set(range(0, 13)) | {14, 24}


def _blocked_terms() -> list[str]:
    extra = os.environ.get("PATHLIGHT_INSIGHT_BLOCKLIST", "")
    return [*BLOCKED_TERMS, *(term.strip().lower() for term in extra.split(",") if term.strip())]


def _texts(insight: dict) -> list[str]:
    return [insight["headline"], insight["summary"], insight["recommendation"],
            *(part for h in insight["highlights"] for part in (h["title"], h["detail"]))]


def _fact_numbers(value, found: set[float]) -> set[float]:
    if isinstance(value, bool):
        return found
    if isinstance(value, (int, float)):
        found.add(float(value))
    elif isinstance(value, dict):
        for item in value.values():
            _fact_numbers(item, found)
    elif isinstance(value, list):
        for item in value:
            _fact_numbers(item, found)
    elif isinstance(value, str):
        # "5 PM" and dates are facts too.
        for match in re.findall(r"\d+(?:\.\d+)?", value):
            found.add(float(match))
    return found


def _pairs(value, found: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """(this period, previous period) pairs, so a note can quote a percentage change."""
    if isinstance(value, dict):
        for now_key, before_key in (("visits", "previous"), ("visits", "same_day_previous_week"),
                                    ("visits", "visits_previous"), ("total", "previous"),
                                    ("average_dwell_seconds", "average_dwell_seconds_previous"),
                                    ("average_visit_seconds", "average_visit_seconds_previous"),
                                    ("visits_per_day_after", "visits_per_day_before"),
                                    ("share_of_visits_after_pct", "share_of_visits_before_pct"),
                                    ("average_dwell_seconds_after", "average_dwell_seconds_before")):
            a, b = value.get(now_key), value.get(before_key)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
                found.append((float(a), float(b)))
        for item in value.values():
            _pairs(item, found)
    elif isinstance(value, list):
        for item in value:
            _pairs(item, found)
    return found


def _grounded(number: float, facts: set[float], pairs: list[tuple[float, float]],
              totals: tuple[float, ...] = ()) -> bool:
    if number in FREE_NUMBERS or any(abs(number - fact) <= max(0.6, abs(fact) * 0.01) for fact in facts):
        return True
    for total in totals:  # "the counter saw 64% of visits"
        if total and any(abs(number - fact / total * 100) <= 1.5 for fact in facts if 0 <= fact <= total):
            return True
    for fact in facts:  # seconds quoted as minutes
        if fact >= 60 and abs(number - fact / 60) <= 0.6:
            return True
    for now, before in pairs:
        if before and abs(abs(number) - abs((now - before) / before * 100)) <= 1.5:
            return True
        if abs(abs(number) - abs(now - before)) <= 0.6:
            return True
        if before and abs(number - now / before) <= 0.15:  # "1.4x"
            return True
    return False


def check(insight: dict, facts: dict) -> list[str]:
    """Why a generated note cannot be shown as written; empty when it passes."""
    problems = []
    text = " ".join(_texts(insight)).lower()
    for term in _blocked_terms():
        if re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", text):
            problems.append(f"mentions '{term}'")
    known, pairs = _fact_numbers(facts, set()), _pairs(facts, [])
    # Ignore dates and clock times; check every other figure against the data.
    cleaned = re.sub(r"\d{4}-\d{2}-\d{2}|\b\d{1,2}(:\d{2})?\s?(am|pm)\b", " ", text)
    for match in re.findall(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?", cleaned):
        number = float(match.replace(",", ""))
        totals = tuple(float(facts.get(key) or 0) for key in ("visits", "visits_previous"))
        if not _grounded(number, known, pairs, totals):
            problems.append(f"uses {match}, which is not in the data")
    if facts.get("simulated_visits") and "simulat" not in text:
        problems.append("does not say which visits are simulated")
    return problems


def fallback(facts: dict) -> dict:
    """A plain note built only from the numbers, shown when the model's note fails a check."""
    visits, previous, change = facts["visits"], facts["visits_previous"], facts["change_pct"]
    if change is None:
        headline = f"{visits} visits in the last 7 days"
    else:
        headline = f"Visits {'up' if change >= 0 else 'down'} {abs(round(change))}% on the week before"
    busiest = max(facts["zones"], key=lambda z: z["visits"], default=None)
    parts = [f"You had {visits} visits in the last 7 days, against {previous} the week before."]
    if facts["peak_hour"]:
        parts.append(f"The busiest hour was {facts['peak_hour']}.")
    if busiest and busiest["visits"]:
        parts.append(f"{busiest['zone']} was the busiest area.")
    if facts.get("simulated_visits"):
        parts.append(f"{facts['simulated_visits']} of these visits are simulated (demo mode).")
    highlights = []
    if facts["peak_hour"]:
        highlights.append({"title": "Peak hour", "detail": f"Most visits arrived around {facts['peak_hour']}.", "trend": "info"})
    if busiest and busiest["visits"]:
        highlights.append({"title": "Busiest area", "detail": f"{busiest['zone']}: {busiest['visits']} visits.", "trend": "info"})
    action = (f"Have an extra person ready around {facts['peak_hour']}, your busiest hour."
              if facts["peak_hour"] else "Keep the cameras on for a full week so there is a pattern to act on.")
    return {"headline": headline[:160], "summary": " ".join(parts)[:600], "highlights": highlights,
            "recommendation": action}


class Highlight(Model):
    title: str = Field(min_length=1, max_length=80)
    detail: str = Field(min_length=1, max_length=260)
    trend: Literal["up", "down", "flat", "info"] = "info"


class Insight(Model):
    headline: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=600)
    highlights: list[Highlight] = Field(default_factory=list, max_length=4)
    recommendation: str = Field(min_length=1, max_length=320)


def _settings() -> dict[str, str]:
    values = {key: os.environ.get(key, "") for key in KEYS}
    env = Path(__file__).resolve().parents[4] / ".env"
    if env.is_file() and not all(values[key] for key in KEYS[:2]):
        for line in env.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            key = key.strip()
            if separator and key in KEYS and not values[key]:
                values[key] = value.strip().strip('"').strip("'")
    values["AWS_REGION"] = values["AWS_REGION"] or "us-west-2"
    values["PATHLIGHT_INSIGHT_MODEL"] = values["PATHLIGHT_INSIGHT_MODEL"] or DEFAULT_MODEL
    return values


def status() -> dict:
    settings = _settings()
    return {"available": bool(settings["AWS_BEARER_TOKEN_BEDROCK"]), "model": settings["PATHLIGHT_INSIGHT_MODEL"],
            "provider": "Amazon Bedrock"}


SYSTEM = (
    "You are a retail and workplace foot-traffic analyst writing a short weekly note for a small-business owner. "
    "Use ONLY the numbers in the data you are given. Never invent causes, events, people, or numbers. "
    "You may connect a change to a layout change only if its date is listed in layout_changes or layout_change, "
    "and then say it "
    "coincided rather than caused. Percentages must be computed from the given counts. "
    "Positions are estimates from camera views, so talk about zones and times, not exact spots. "
    "If there is little data, say so plainly and suggest what would help. "
    "simulated_visits counts demo-mode visitors that no camera saw; when it is above zero, the summary must say "
    "how many of the visits are simulated, and must never describe them as real customers. "
    "Write plainly, in the second person, with no hype, and use the times exactly as given (like 5 PM). "
    "The headline leads with the single most important change in under 80 characters. "
    "The recommendation is ONE specific, low-cost action tied to a named zone, hour or entrance from the data "
    "(for example staffing at the peak hour, signage at a quiet zone, or moving a display toward the busiest zone); "
    "never generic advice such as 'analyze the factors'. Reply with JSON only, matching this shape: "
    '{"headline": str, "summary": str (2-3 sentences), '
    '"highlights": [{"title": str (2-4 words), "detail": str, "trend": "up"|"down"|"flat"|"info"}] (2-4 items), '
    '"recommendation": str}.'
)


def _facts(metrics: dict) -> dict:
    """The aggregate numbers the model may use; nothing else leaves the server."""
    hour = lambda h: None if h is None else ("12 AM" if h == 0 else f"{h} AM" if h < 12 else "12 PM" if h == 12 else f"{h - 12} PM")
    return {
        "site": metrics["site_name"],
        "period": "last 7 days vs the 7 days before",
        "time_zone": metrics["time_zone"],
        "visits": metrics["totals"]["visits"],
        "simulated_visits": metrics.get("simulated_visits", 0),
        "visits_previous": metrics["totals"]["previous"],
        "change_pct": metrics["totals"]["change_pct"],
        "average_visit_seconds": metrics["totals"]["avg_visit_s"],
        "average_visit_seconds_previous": metrics["totals"]["avg_visit_previous_s"],
        "peak_hour": hour(metrics["totals"]["peak_hour"]),
        "peak_hour_previous": hour(max(range(24), key=lambda h: metrics["hourly"][h]["previous"]))
        if any(h["previous"] for h in metrics["hourly"]) else None,
        "daily": [{"date": d["date"], "visits": d["visits"], "same_day_previous_week": d["previous"]}
                  for d in metrics["daily"]],
        "busiest_hours": sorted(({"hour": hour(h["hour"]), "visits": h["visits"], "previous": h["previous"]}
                                 for h in metrics["hourly"] if h["visits"] or h["previous"]),
                                key=lambda item: -item["visits"])[:6],
        "zones": [{"zone": z["name"], "visits": z["visits"], "previous": z["previous"],
                   "average_dwell_seconds": z["dwell_s"], "average_dwell_seconds_previous": z["dwell_previous_s"]}
                  for z in metrics["zones"][:12]],
        "entrances": [{"camera": e["name"], "visits": e["visits"], "previous": e["previous"]}
                      for e in metrics["entrances"][:8]],
        "data_quality": metrics["quality"],
        "layout_changes": metrics["layout_changes"],
        **({"vehicles": {"total": v["total"], "previous": v["previous"], "peak_hour": hour(v["peak_hour"]),
                         "cameras": [{"camera": c["name"], "count": c["count"], "previous": c["previous"]}
                                     for c in v["cameras"][:4]]}}
           if (v := metrics.get("vehicles") or {}).get("total") or v.get("previous") else {}),
        **({"layout_change": {
            "date": li["changed_at"][:10], "what_changed": li.get("note"), "simulated": li["simulated"],
            "visits_per_day_before": li["visits_per_day_before"], "visits_per_day_after": li["visits_per_day_after"],
            "zones": [{"zone": z["name"], "share_of_visits_before_pct": z["share_before"],
                       "share_of_visits_after_pct": z["share_after"],
                       "average_dwell_seconds_before": z["dwell_before_s"], "average_dwell_seconds_after": z["dwell_after_s"]}
                      for z in li["zones"][:8]],
        }} if (li := metrics.get("layout_impact")) else {}),
    }


def _json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise InsightUnavailable("The AI summary could not be read. Try again.")
    return json.loads(match.group(0))


def generate(metrics: dict, timeout: float = 45) -> dict:
    settings = _settings()
    token = settings["AWS_BEARER_TOKEN_BEDROCK"]
    if not token:
        raise InsightUnavailable("AI insights are not configured on this server.")
    model = settings["PATHLIGHT_INSIGHT_MODEL"]
    facts = _facts(metrics)
    body = {
        "system": [{"text": SYSTEM}],
        "messages": [{"role": "user", "content": [{"text": "Data:\n" + json.dumps(facts)}]}],
        "inferenceConfig": {"maxTokens": 700, "temperature": 0.2},
    }
    region = settings["AWS_REGION"]
    # The region becomes part of the host name, so only accept a real region code.
    if not re.fullmatch(r"[a-z]{2}(-[a-z]+)+-\d", region):
        raise InsightUnavailable("AI insights are not configured on this server.")
    url = (f"https://bedrock-runtime.{region}.amazonaws.com/model/"
           f"{urllib.parse.quote(model, safe='')}/converse")
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        # nosec B310: fixed https Bedrock endpoint; the region is validated above.
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
            reply = json.load(response)
    except urllib.error.HTTPError as error:
        # Never surface provider bodies; they can echo request details.
        raise InsightUnavailable(f"Amazon Bedrock is unavailable (HTTP {error.code}). Try again later.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise InsightUnavailable("Amazon Bedrock could not be reached. Try again later.") from None
    try:
        text = "".join(part.get("text", "") for part in reply["output"]["message"]["content"])
        raw = _json(text)
        # Keep only the fields the dashboard shows; models sometimes add extras.
        raw = {key: raw.get(key) for key in ("headline", "summary", "highlights", "recommendation") if key in raw}
        raw["highlights"] = [{k: h.get(k) for k in ("title", "detail", "trend") if k in h}
                             for h in (raw.get("highlights") or [])[:4] if isinstance(h, dict)]
        insight = Insight.model_validate(raw)
    except (KeyError, TypeError, ValueError, ValidationError):
        raise InsightUnavailable("The AI summary was incomplete. Try again.") from None
    result = insight.model_dump()
    problems = check(result, facts)
    checks = {"passed": not problems, "fallback": bool(problems), "reasons": problems[:5]}
    if problems:
        # Show a plain, deterministic note instead of the model's text.
        result = Insight.model_validate(fallback(facts)).model_dump()
    return {**result, "model": model, "provider": "Amazon Bedrock", "checks": checks,
            "usage": {k: reply.get("usage", {}).get(k) for k in ("inputTokens", "outputTokens")}}
