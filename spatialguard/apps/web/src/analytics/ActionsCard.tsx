/**
 * Today's actions: the week's analytics turned into two or three decisions.
 * Presentational only, so the web page and the phone layout share it.
 */
import { ArrowUpRight, LayoutGrid, LogIn, TrendingUp, Users } from "lucide-react";
import type { components } from "../generated";
import { MIN_VISITS, todaysActions, type ActionKind } from "./actions";

type SiteAnalytics = components["schemas"]["SiteAnalytics"];
type CrowdAlerts = components["schemas"]["CrowdAlerts"];

const ICONS: Record<ActionKind, typeof Users> = {
  staff: Users, queue: ArrowUpRight, space: LayoutGrid, trend: TrendingUp, arrivals: LogIn,
};

export default function ActionsCard({ data, alerts, className = "an-card" }: {
  data: SiteAnalytics; alerts?: CrowdAlerts | null; className?: string;
}) {
  const actions = todaysActions(data, alerts);
  return (
    <section className={`${className} an-actions`} aria-labelledby="an-actions-title">
      <header className="an-actions-head">
        <h3 id="an-actions-title">Today&rsquo;s actions</h3>
        <span>From this week&rsquo;s numbers</span>
      </header>
      {actions.length ? (
        <ol className="an-actions-list">
          {actions.map((a) => {
            const Icon = ICONS[a.kind];
            return (
              <li key={a.kind}>
                <span className="an-actions-icon" aria-hidden="true"><Icon size={16} /></span>
                <span className="an-actions-text"><strong>{a.title}</strong><small>{a.detail}</small></span>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="an-actions-empty">
          {data.totals.visits < MIN_VISITS
            ? `Suggestions appear once the week has at least ${MIN_VISITS} visits.`
            : "Nothing stands out this week. Traffic is spread evenly."}
        </p>
      )}
      <p className="an-actions-foot">Rule-based from visit counts, peak hours and time spent. Positions are estimates.</p>
    </section>
  );
}
