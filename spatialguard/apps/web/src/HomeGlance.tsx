/**
 * Today at a glance, for the desktop Home bar: the few numbers an owner looks
 * for first, from the same Site Analytics the Analytics page uses. Hidden on
 * phones, where Home stays a compact map-first layout.
 */
import { useEffect, useState } from "react";
import type { components } from "./generated";
import { request } from "./platform";
import { timeZone } from "./SiteAnalytics";
import { hourLabel } from "./analytics/charts";

type Analytics = components["schemas"]["SiteAnalytics"];

const weekday = (date: string) => new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { weekday: "short" });

function change(now: number, before: number | null | undefined) {
  if (!before) return { text: now ? "New this week" : "No visits yet", tone: "" };
  const pct = Math.round(((now - before) / before) * 100);
  if (pct === 0) return { text: "Same as", tone: "flat" };
  return { text: `${pct > 0 ? "+" : ""}${pct}%`, tone: pct > 0 ? "up" : "down" };
}

export default function HomeGlance({ siteId, refreshKey }: { siteId?: string; refreshKey?: unknown }) {
  const [data, setData] = useState<Analytics | null>(null);

  useEffect(() => {
    if (!siteId) return;
    let live = true;
    void request<Analytics>(`/v1/sites/${encodeURIComponent(siteId)}/analytics?tz=${encodeURIComponent(timeZone())}`)
      .then((value) => { if (live) setData(value); })
      .catch(() => { if (live) setData(null); });
    return () => { live = false; };
  }, [siteId, refreshKey]);

  if (!data) return null;
  const today = data.daily[data.daily.length - 1];
  const t = data.totals;
  const day = today ? change(today.visits, today.previous) : null;
  const week = change(t.visits, t.previous);
  const items = [
    { label: "Visits today", value: today ? today.visits.toLocaleString() : "0",
      tone: day?.tone ?? "", note: day ? `${day.text}${day.tone === "flat" ? " " : day.tone ? " vs " : ""}${day.tone ? `last ${weekday(today!.date)}` : ""}` : "" },
    { label: "Last 7 days", value: t.visits.toLocaleString(), tone: week.tone,
      note: `${week.text}${week.tone === "flat" ? " the week before" : week.tone ? " vs the week before" : ""}` },
    { label: "Peak hour", value: t.peak_hour != null ? hourLabel(t.peak_hour) : "—", tone: "",
      note: t.peak_hour != null ? `${t.peak_hour_visits} visits in that hour` : "No visits yet" },
    { label: "Busiest area", value: t.busiest_zone ?? "—", tone: "",
      note: t.quietest_zone ? `Quietest: ${t.quietest_zone}` : "From your floor plan" },
  ];
  return (
    <dl className="home-glance" aria-label="Today at a glance">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>
            <strong title={item.value}>{item.value}</strong>
            <small className={item.tone && item.tone !== "flat" ? `is-${item.tone}` : undefined}>{item.note}</small>
          </dd>
        </div>
      ))}
    </dl>
  );
}
