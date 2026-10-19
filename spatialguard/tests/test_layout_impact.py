"""Layout change impact: the week before a floor-plan change against the days since."""
from datetime import datetime, timedelta, timezone

from spatialguard_api import analytics, demo, insights

ZONES = [("Parking", [[0, -10], [8, -10], [8, -3], [0, -3]]), ("Entrance", [[0, -3], [8, -3], [8, 4], [0, 4]]),
         ("Counter", [[2, 4], [4, 4], [4, 11], [2, 11]]), ("Window bar", [[0, 4], [2, 4], [2, 11], [0, 11]]),
         ("Seating", [[4, 4], [8, 4], [8, 24], [4, 24]])]
SITE = {"id": "s", "name": "Café", "revision_id": "r", "layout": {
    "floors": [{"id": "f"}], "rooms": [],
    "cameras": [{"id": "door", "name": "Front door", "position_m": [4, -2], "heading_degrees": 90, "fov_degrees": 110, "range_m": 12}],
    "zones": [{"name": n, "purpose": analytics.ANALYTICS_PURPOSE, "polygon_xy_m": p} for n, p in ZONES]}}
TZ = analytics.zone_info("America/Phoenix")
NOW = datetime(2026, 10, 19, 22, 0, tzinfo=timezone.utc)


def build(**extra):
    incidents = demo.history(SITE, NOW, TZ, seed=9)
    change = {"at": demo.layout_change_at(NOW, TZ).isoformat(), "note": demo.LAYOUT_CHANGE_NOTE, "simulated": True}
    return analytics.build(SITE, incidents, {}, "America/Phoenix", now=NOW, layout_change=change, **extra)


def test_demo_layout_change_shows_its_simulated_effect():
    impact = build()["layout_impact"]
    assert impact["simulated"] and impact["note"] == demo.LAYOUT_CHANGE_NOTE
    assert impact["days_before"] == 7 and 3 < impact["days_after"] < 5
    zones = {z["name"]: z for z in impact["zones"]}
    # The pastry display moved out of the queue and next to the window bar.
    assert zones["Window bar"]["share_after"] > zones["Window bar"]["share_before"] * 1.3
    assert zones["Counter"]["dwell_after_s"] < zones["Counter"]["dwell_before_s"]
    assert "Outside" not in zones


def test_live_only_leaves_out_the_simulated_change_and_needs_a_day_after():
    assert build(mode="live")["layout_impact"] is None
    today = {"at": (NOW - timedelta(hours=3)).isoformat(), "simulated": False}
    incidents = demo.history(SITE, NOW, TZ, seed=9)
    assert analytics.build(SITE, incidents, {}, "UTC", now=NOW, layout_change=today)["layout_impact"] is None
    assert analytics.build(SITE, incidents, {}, "UTC", now=NOW)["layout_impact"] is None


def test_demo_change_is_before_opening_a_few_days_ago():
    at = demo.layout_change_at(NOW, TZ)
    local = at.astimezone(TZ)
    assert (NOW.astimezone(TZ).date() - local.date()).days == demo.LAYOUT_CHANGE_DAYS_BACK
    assert local.hour < 7


def test_the_weekly_note_may_quote_the_impact_figures():
    metrics = build()
    facts = insights._facts(metrics)
    change = facts["layout_change"]
    assert change["simulated"] and change["what_changed"] == demo.LAYOUT_CHANGE_NOTE
    window = next(z for z in change["zones"] if z["zone"] == "Window bar")
    note = {"headline": "Window bar busier since the layout change",
            "summary": (f"Since the simulated layout change, the window bar's share of visits went from "
                        f"{round(window['share_of_visits_before_pct'])}% to {round(window['share_of_visits_after_pct'])}%. "
                        f"{facts['simulated_visits']} visits are simulated."),
            "highlights": [], "recommendation": "Keep the pastry display by the window bar."}
    assert insights.check(note, facts) == []
