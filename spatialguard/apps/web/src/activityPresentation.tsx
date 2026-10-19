import {
  BellRing, Car, CircleDashed, CircleHelp, DoorOpen, Footprints, Package, PawPrint,
  PersonStanding, Route, ScanFace, ShieldAlert, Truck, type LucideIcon,
} from "lucide-react";
import { type ActivityKind } from "@twinforge/spatial-view/TopDownPerson";
import type { Marker } from "@twinforge/spatial-view/Map2D";
import type { components } from "./generated";

type Classification = components["schemas"]["IncidentClassification"];
type Presentation = { kind: ActivityKind; label: string; review: "routine" | "review" | "urgent"; person: boolean };
export const activities: Record<Classification["label"], Presentation> = {
  delivery_activity: { kind: "delivery", label: "Delivery worker", review: "routine", person: true },
  unidentified_person: { kind: "person", label: "Unidentified person", review: "review", person: true },
  face_covering_visible: { kind: "face_covering", label: "Face covering visible", review: "review", person: true },
  possible_weapon_visible: { kind: "weapon", label: "Possible weapon", review: "urgent", person: true },
  possible_unauthorized_entry: { kind: "intrusion", label: "Possible intrusion", review: "urgent", person: true },
  package_visible: { kind: "package", label: "Package visible", review: "routine", person: false },
  animal_visible: { kind: "animal", label: "Animal detected", review: "routine", person: false },
  vehicle_visible: { kind: "vehicle", label: "Vehicle detected", review: "routine", person: false },
  unclear: { kind: "unknown", label: "Activity unclear", review: "review", person: false },
  no_relevant_activity: { kind: "none", label: "No relevant activity", review: "review", person: false },
};

export type ActorPresentation = Pick<Marker, "actorKind" | "actorLabel" | "reviewLevel">;
export const DEFAULT_ACTOR: ActorPresentation = {
  actorKind: "person", actorLabel: "Person · not classified", reviewLevel: "review",
};
export function actorFromClassification(classification: Classification | null): ActorPresentation {
  if (!classification) return DEFAULT_ACTOR;
  const activity = activities[classification.label];
  // The current detector supplies person coordinates only. An event-level animal,
  // package or vehicle result cannot locate that object at the person's feet.
  if (!activity.person) return DEFAULT_ACTOR;
  return { actorKind: activity.kind, actorLabel: activity.label, reviewLevel: activity.review };
}

// List and card icons: one line-icon style on a tint that says how much
// attention the visit needs. Map markers keep their top-down figures.
const ICONS: Record<ActivityKind, LucideIcon> = {
  person: PersonStanding, delivery: Truck, face_covering: ScanFace, weapon: ShieldAlert, possible_threat: ShieldAlert,
  intrusion: DoorOpen, package: Package, animal: PawPrint, vehicle: Car, unknown: CircleHelp, none: CircleDashed,
};
type Tone = "routine" | "review" | "urgent" | "quiet";

function tone(classification: Classification | null): Tone {
  if (!classification) return "review";
  const activity = activities[classification.label];
  if (activity.kind === "none" || activity.kind === "unknown") return "quiet";
  return activity.review;
}

/**
 * The icon for one visit. A visit seen by several cameras shows a path with
 * the camera count, since following someone across cameras is the point.
 */
export function VisitIcon({ classification, cameras = 1, doorbell = false, size = 40 }: {
  classification: Classification | null; cameras?: number; doorbell?: boolean; size?: number;
}) {
  const activity = classification ? activities[classification.label] : null;
  const vague = !activity || activity.kind === "unknown" || activity.kind === "none" || activity.kind === "person";
  const Icon = cameras > 1 && vague ? Route
    : activity ? ICONS[activity.kind]
      : doorbell ? BellRing : Footprints;
  const label = [activity?.label ?? (doorbell ? "Doorbell pressed" : "Motion reported"),
    cameras > 1 ? `seen by ${cameras} cameras` : ""].filter(Boolean).join(", ");
  return (
    <span className={`visit-icon tone-${cameras > 1 && vague ? "review" : tone(classification)}`}
      style={{ width: size, height: size }} role="img" aria-label={label} title={label}>
      <Icon size={Math.round(size * 0.5)} strokeWidth={1.9} aria-hidden="true" />
      {cameras > 1 && <span className="visit-icon-count" aria-hidden="true">{cameras}</span>}
    </span>
  );
}

export function ActivityIcon({ classification, size = 38 }: { classification: Classification; size?: number }) {
  return <VisitIcon classification={classification} size={size} />;
}
