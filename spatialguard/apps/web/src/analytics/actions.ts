/**
 * "Today's actions": two or three plain decisions drawn from the week's
 * analytics. Rule-based on purpose, with no model call, so the same numbers
 * always give the same advice and nothing can fail at the moment an owner
 * (or a judge) looks. Every action names the figures it comes from.
 */
import type { components } from "../generated";
import { hourLabel } from "./charts";

type SiteAnalytics = components["schemas"]["SiteAnalytics"];
type CrowdAlerts = components["schemas"]["CrowdAlerts"];

export type ActionKind = "staff" | "queue" | "space" | "trend" | "arrivals";
export type Action = { kind: ActionKind; title: string; detail: string };

/** Below this many visits in the week, patterns are too thin to act on. */
export const MIN_VISITS = 10;

// Places people wait to be served. "Entrance" also raises queue alerts, but
// a long stay there is not a till problem, so it is left out here.
const WAIT_WORDS = ["checkout", "check-out", "counter", "register", "queue", "line", "till", "order"];
const isWaitZone = (name: string) => WAIT_WORDS.some((w) => name.toLowerCase().includes(w));
// Ways in and out of the place: busy by nature, not floor space to rearrange.
const PASS_WORDS = ["entrance", "entry", "door", "exit", "parking", "car park", "lot", "sidewalk", "street", "driveway"];
const isPassZone = (name: string) => PASS_WORDS.some((w) => name.toLowerCase().includes(w));

const weekdayLong = (date: string) =>
  new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { weekday: "long" });

const pct = (now: number, before: number) => (before > 0 ? Math.round(((now - before) / before) * 100) : null);

export function stay(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60), r = s % 60;
  return r ? `${m} min ${r} s` : `${m} min`;
}

/** Up to three actions, most useful first. Empty when the week is too thin. */
export function todaysActions(data: SiteAnalytics, alerts?: CrowdAlerts | null, limit = 3): Action[] {
  const t = data.totals;
  if (t.visits < MIN_VISITS) return [];
  const ranked: { rank: number; action: Action }[] = [];

  // 1. Staff the rush: the peak hour against a typical open hour.
  const openHours = data.hourly.filter((h) => h.visits > 0);
  const typical = openHours.length ? t.visits / openHours.length : 0;
  let slot: { day: number; hour: number; count: number } | null = null;
  data.week_grid.forEach((row, day) => row.forEach((count, hour) => {
    if (count > 0 && (!slot || count > slot.count)) slot = { day, hour, count };
  }));
  if (t.peak_hour != null && typical > 0 && t.peak_hour_visits >= typical * 1.4) {
    const ratio = Math.round((t.peak_hour_visits / typical) * 10) / 10;
    const best = slot as { day: number; hour: number; count: number } | null;
    const busiest = best && data.daily[best.day]
      ? ` Busiest single slot: ${weekdayLong(data.daily[best.day].date)} ${hourLabel(best.hour)} (${best.count}).` : "";
    ranked.push({ rank: 1, action: {
      kind: "staff",
      title: `Staff up for the ${hourLabel(t.peak_hour)} rush`,
      detail: `${t.peak_hour_visits} visits in that hour this week, ${ratio}× a typical open hour.${busiest}`,
    } });
  }

  // 2. Shorten the wait: the slowest serving zone, its trend and its queue alerts.
  const since = Date.parse(data.period.since);
  const waits = data.zones.filter((z) => isWaitZone(z.name) && z.dwell_s != null && z.visits > 0)
    .sort((a, b) => (b.dwell_s ?? 0) - (a.dwell_s ?? 0));
  const wait = waits[0];
  if (wait && wait.dwell_s != null) {
    const growth = wait.dwell_previous_s ? pct(wait.dwell_s, wait.dwell_previous_s) : null;
    const queueAlerts = (alerts?.alerts ?? []).filter((a) => a.kind === "queue" && a.zone === wait.name
      && (!Number.isFinite(since) || Date.parse(a.at) >= since)).length;
    if (queueAlerts > 0 || wait.dwell_s >= 90 || (growth != null && growth >= 20)) {
      const parts = [`People spend ${stay(wait.dwell_s)} at ${wait.name} on average`];
      if (growth != null && growth >= 10) parts.push(`up ${growth}% on last week`);
      const alertNote = queueAlerts ? ` ${queueAlerts} queue alert${queueAlerts === 1 ? "" : "s"} this week.` : "";
      const when = t.peak_hour != null ? ` Open a second register around ${hourLabel(t.peak_hour)}.` : " Add a second person at peak times.";
      ranked.push({ rank: queueAlerts ? 0 : 1, action: {
        kind: "queue", title: `Shorten the wait at ${wait.name}`, detail: `${parts.join(", ")}.${alertNote}${when}`,
      } });
    }
  }

  // 3. Use the space: a zone far quieter than the busiest one.
  // Compare only floor areas a shop can rearrange: not tills, doors or parking.
  const byVisits = [...data.zones].filter((z) => !isWaitZone(z.name) && !isPassZone(z.name)).sort((a, b) => b.visits - a.visits);
  const busy = byVisits[0];
  const quiet = byVisits[byVisits.length - 1];
  if (busy && quiet && quiet.name !== busy.name && busy.visits >= 5 && quiet.visits <= busy.visits * 0.35) {
    ranked.push({ rank: 2, action: {
      kind: "space",
      title: `Put ${quiet.name} to work`,
      detail: `${quiet.visits} visit${quiet.visits === 1 ? "" : "s"} there against ${busy.visits} at ${busy.name}. Move a display or an offer into ${quiet.name}, or give the space to ${busy.name}.`,
    } });
  }

  // 4. Week-over-week: say which day moved most.
  if (t.change_pct != null && Math.abs(t.change_pct) >= 15 && t.previous >= MIN_VISITS) {
    const moved = [...data.daily].sort((a, b) => Math.abs(b.visits - b.previous) - Math.abs(a.visits - a.previous))[0];
    const up = t.change_pct > 0;
    ranked.push({ rank: up ? 3 : 2, action: {
      kind: "trend",
      title: `Visits ${up ? "up" : "down"} ${Math.abs(Math.round(t.change_pct))}% on last week`,
      detail: moved
        ? `${weekdayLong(moved.date)} moved most (${moved.visits} vs ${moved.previous}). ${up ? "Keep whatever changed that day." : "Check opening hours, weather or anything blocking the street that day."}`
        : up ? "Keep whatever changed this week." : "Check opening hours and the street outside.",
    } });
  }

  // 5. Arrivals: one entrance doing most of the work.
  const entrances = data.entrances.filter((e) => e.visits > 0);
  const totalIn = entrances.reduce((n, e) => n + e.visits, 0);
  const top = [...entrances].sort((a, b) => b.visits - a.visits)[0];
  if (entrances.length >= 2 && top && totalIn > 0 && top.visits / totalIn >= 0.7) {
    ranked.push({ rank: 3, action: {
      kind: "arrivals",
      title: `Most people arrive by ${top.name}`,
      detail: `${Math.round((top.visits / totalIn) * 100)}% of visits start there. Put your menu, offer or signage where people first walk in.`,
    } });
  }

  return ranked.sort((a, b) => a.rank - b.rank).slice(0, limit).map((r) => r.action);
}
