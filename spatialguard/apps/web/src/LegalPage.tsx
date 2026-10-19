import { ArrowLeft } from "lucide-react";
import SpatialGuardMark, { PathlightWordmark } from "./SpatialGuardMark";
import type { ReactNode } from "react";
import { native } from "./platform";

type LegalKind = "privacy" | "terms" | "data-deletion";

const content: Record<LegalKind, { title: string; intro: string; sections: { title: string; body: ReactNode }[] }> = {
  privacy: {
    title: "Privacy notice",
    intro: "This notice describes what Pathlight collects, why, who processes it, how long it is kept, and how to delete it or withdraw consent.",
    sections: [
      { title: "Data the service keeps", body: <p>Pathlight stores your account email and salted password verifier, your places (maps, uploaded floor plans, camera placements and business areas), camera mappings, signed Ring event metadata, visits, visitor paths, analytics, queue and crowding alerts, weekly insights, security audit records, and your saved settings. If you create a time-lapse, its still images are stored until the project or account is deleted.</p> },
      { title: "Ring data", body: <p>Ring access is optional and needs your permission in Settings. After you authorize Pathlight in Ring, server-held credentials are encrypted at rest. Inventory, device status, event metadata, snapshots, event recordings and bounded live-view sessions are used only for the features you turn on. Pathlight does not record live video.</p> },
      { title: "Foot-traffic analysis", body: <p>Only if you turn on Foot-traffic analysis, Pathlight downloads each Ring event recording to its own server, detects people in it, and stores only the anonymous points where a person stood on your floor plan. The recording is deleted as soon as the analysis finishes. Pathlight never recognises faces, never identifies people, never infers sensitive traits, and never links a person across visits, places or accounts. These points power your heatmap, Site Analytics and queue alerts. As the business owner you are responsible for telling visitors that cameras are in use, for example with a sign at the entrance, and for complying with local law.</p> },
      { title: "Optional activity labels", body: <p>If you separately allow activity labels, up to three authorized event snapshots may be sent to an Amazon Bedrock model in the configured AWS region. The saved result is a cautious category for review; the snapshots are not kept by Pathlight. Pathlight does not perform face identification or infer gender.</p> },
      { title: "Weekly insight", body: <p>The weekly AI summary is written by Amazon Bedrock from aggregate numbers only, such as visits per hour and per zone. No images, video, or personal details are sent.</p> },
      { title: "AI training", body: <p>Pathlight does not use your Ring data, recordings, snapshots or analytics to train any AI model, and does not sell or share your data for advertising or marketing.</p> },
      { title: "Retention and deletion", body: <p>Visits, and the visitor paths derived from them, are kept for 90 days by default (30 days or 1 year in Settings). Audit records are kept for 365 days by default. Deleting a place removes its maps, floor plan, visits, paths, analytics, alerts and insights. Deleting the account disconnects Ring and removes all owner-scoped data. Turning off a permission stops that processing immediately.</p> },
      { title: "Service providers", body: <p>The service runs on Railway infrastructure in the United States. Ring processes authorized camera data under your Ring account. Amazon Bedrock (Amazon Web Services) receives a snapshot only when activity labels are on, a floor-plan drawing only when you choose label reading during import, and aggregate visit counts for the weekly insight.</p> },
      { title: "Your choices", body: <p>You can turn each permission on or off in Settings → Privacy, export your data, delete a place, or delete the account at any time. Contact support through the Pathlight website for any privacy request.</p> },
    ],
  },
  terms: {
    title: "Terms of service",
    intro: "Pathlight turns the Ring cameras a business already owns into foot-traffic analytics on its floor plan.",
    sections: [
      { title: "Authorized use", body: <p>Use Pathlight only with cameras, accounts, and floor plans you own or have permission to use. Tell visitors that cameras are in use where the law or good practice requires it. Keep your account password private and revoke sessions you no longer recognize.</p> },
      { title: "Estimates, not measurements", body: <p>Visitor positions, paths, counts and alerts are estimates from camera views and can be wrong. Activity labels can be wrong and always require human review. Pathlight does not establish anyone's identity.</p> },
      { title: "No emergency service", body: <p>Pathlight is a business analytics tool. It is not a security, emergency, medical, or life-safety service and should not be used as the only basis for an emergency decision.</p> },
      { title: "Service availability", body: <p>Features may change or be unavailable during maintenance. Ring integration depends on the owner’s authorization, applicable subscription state, and provider availability.</p> },
    ],
  },
  "data-deletion": {
    title: "Delete your data",
    intro: "You can remove individual places or permanently delete the entire Pathlight account.",
    sections: [
      { title: "Delete a place", body: <p>Open Settings → Places and choose Remove. This deletes that map, uploaded drawing, camera placement, visits, visitor paths, analytics, alerts, insights and replay history from Pathlight and TwinForge.</p> },
      { title: "Delete the account", body: <p>Open Settings → Delete account. Enter your current password and type DELETE. Pathlight first disconnects the Ring integration, then removes the account and its owner-scoped data. If Ring is unavailable, the account stays intact so you can retry or remove Pathlight from Ring first.</p> },
      { title: "Stop processing", body: <p>Settings → Privacy lets you turn off Ring access, foot-traffic analysis or activity labels at any time; processing stops immediately. You can also disconnect Ring separately, or revoke a browser or phone session without deleting other data.</p> },
      { title: "Retention", body: <p>Settings → Privacy and retention lets you reduce visit retention to 30 days and audit retention to 90 days. Cleanup runs in the background; choosing a shorter period does not replace the immediate account-deletion control.</p> },
    ],
  },
};

export default function LegalPage({ kind }: { kind: LegalKind }) {
  const page = content[kind];
  const back = native ? "/" : "/landing";
  return (
    <main className="legal-page">
      <header>
        <a className="legal-brand" href={back}><span><SpatialGuardMark size={20} /></span><PathlightWordmark /></a>
        <a href={back}><ArrowLeft size={15} />Back</a>
      </header>
      <article>
        <p className="eyebrow">Effective October 1, 2026</p>
        <h1>{page.title}</h1>
        <p className="legal-intro">{page.intro}</p>
        {page.sections.map(section => <section key={section.title}><h2>{section.title}</h2>{section.body}</section>)}
      </article>
      <nav aria-label="Legal pages"><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/data-deletion">Data deletion</a></nav>
    </main>
  );
}
