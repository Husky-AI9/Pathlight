/**
 * Layout change impact: the week before the latest floor-plan change against
 * the days since, per day. Only possible because Pathlight keeps a versioned
 * twin of the space: a door counter cannot say which area got busier.
 * It shows what coincided with the change, never what it caused.
 */
import { LayoutDashboard } from "lucide-react";
import type { components } from "../generated";

type SiteAnalytics = components["schemas"]["SiteAnalytics"];
type Impact = NonNullable<SiteAnalytics["layout_impact"]>;

const stay = (seconds: number | null | undefined) => {
  if (seconds == null) return "—";
  const s = Math.round(seconds);
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60), r = s % 60;
  return r ? `${m} min ${r} s` : `${m} min`;
};
const day = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });

type Row = { label: string; before: string; after: string; delta: string; good: boolean | null;
  ratio: [number, number] };

function rows(impact: Impact): Row[] {
  const result: Row[] = [];
  const pct = (now: number, was: number) => (was ? Math.round(((now - was) / was) * 100) : null);
  const visits = pct(impact.visits_per_day_after, impact.visits_per_day_before);
  const top = Math.max(impact.visits_per_day_after, impact.visits_per_day_before, 1);
  result.push({
    label: "Visits per day", before: impact.visits_per_day_before.toFixed(1), after: impact.visits_per_day_after.toFixed(1),
    delta: visits == null ? "" : `${visits > 0 ? "+" : ""}${visits}%`, good: visits == null || visits === 0 ? null : visits > 0,
    ratio: [impact.visits_per_day_before / top, impact.visits_per_day_after / top],
  });
  // The areas that moved most: share of visits for places people choose, time spent for queues.
  // Areas nearly every visit passes through (entrance, queue) are compared by
  // time spent; the others by how many visits chose them.
  const passing = (z: Impact["zones"][number]) => z.share_before >= 80 && z.share_after >= 80;
  const zones = (impact.zones ?? []).filter((z) => !passing(z));
  const shares = zones.map((z) => ({ z, change: z.share_after - z.share_before }))
    .filter((x) => Math.abs(x.change) >= 2).sort((a, b) => Math.abs(b.change) - Math.abs(a.change)).slice(0, 2);
  for (const { z, change } of shares) {
    result.push({
      label: `${z.name} · share of visits`, before: `${Math.round(z.share_before)}%`, after: `${Math.round(z.share_after)}%`,
      // A busier area is not better or worse by itself, so shares stay neutral.
      delta: `${change > 0 ? "+" : ""}${Math.round(change)} pts`, good: null,
      ratio: [z.share_before / 100, z.share_after / 100],
    });
  }
  const waits = (impact.zones ?? []).filter((z) => z.dwell_before_s && z.dwell_after_s && passing(z))
    .map((z) => ({ z, change: pct(z.dwell_after_s!, z.dwell_before_s!) ?? 0, seconds: z.dwell_after_s! - z.dwell_before_s! }))
    .filter((x) => Math.abs(x.change) >= 5 && Math.abs(x.seconds) >= 10)
    .sort((a, b) => Math.abs(b.seconds) - Math.abs(a.seconds)).slice(0, 1);
  for (const { z, change } of waits) {
    const longest = Math.max(z.dwell_before_s!, z.dwell_after_s!);
    result.push({
      label: `${z.name} · average time`, before: stay(z.dwell_before_s), after: stay(z.dwell_after_s),
      delta: `${change > 0 ? "+" : ""}${change}%`, good: change < 0,
      ratio: [z.dwell_before_s! / longest, z.dwell_after_s! / longest],
    });
  }
  return result;
}

export default function LayoutImpactCard({ data, className = "an-card" }: { data: SiteAnalytics; className?: string }) {
  const impact = data.layout_impact;
  if (!impact) return null;
  const list = rows(impact);
  return (
    <section className={`${className} an-impact`} aria-labelledby="an-impact-title">
      <header className="an-impact-head">
        <span className="an-impact-icon" aria-hidden="true"><LayoutDashboard size={17} /></span>
        <div>
          <h3 id="an-impact-title">Since the layout change on {day(impact.changed_at)}</h3>
          <p>{impact.note ?? "Floor plan edited"}{impact.simulated ? " · Simulated" : ""}</p>
        </div>
      </header>
      <div className="an-impact-grid" role="table" aria-label="Before and after the layout change">
        <div className="an-impact-row an-impact-labels" role="row">
          <span role="columnheader">Per day</span>
          <span role="columnheader">{impact.days_before} days before</span>
          <span role="columnheader">{impact.days_after < 7 ? `${Math.round(impact.days_after)} days since` : "7 days after"}</span>
          <span role="columnheader" className="an-impact-sr">Change</span>
        </div>
        {list.map((row) => (
          <div className="an-impact-row" role="row" key={row.label}>
            <span role="rowheader">{row.label}</span>
            <span role="cell"><b>{row.before}</b><i style={{ width: `${Math.max(4, row.ratio[0] * 100)}%` }} className="was" /></span>
            <span role="cell"><b>{row.after}</b><i style={{ width: `${Math.max(4, row.ratio[1] * 100)}%` }} className="now" /></span>
            <span role="cell" className={`an-impact-delta${row.good == null ? "" : row.good ? " good" : " bad"}`}>{row.delta}</span>
          </div>
        ))}
      </div>
      <p className="an-impact-foot">
        These changes happened alongside the layout change; other things may have changed too. Positions are estimates.
      </p>
    </section>
  );
}
