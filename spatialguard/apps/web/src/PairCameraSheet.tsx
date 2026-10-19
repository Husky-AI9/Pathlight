import { useEffect, useState } from "react";
import { Check, Link2, RefreshCw, X } from "lucide-react";
import type { components } from "./generated";
import { request } from "./platform";
import { useDialogFocus } from "./useDialogFocus";
import CameraMark from "./CameraMark";

type Device = components["schemas"]["RingDevice"];
type RingStatus = components["schemas"]["RingStatus"];
type Hardware = NonNullable<components["schemas"]["RingMapping"]["hardware_model"]>;

// Ring's device inventory has no device-type field, so the owner says what is
// mounted here. The choice sets the 3D model on the map.
export const RING_HARDWARE: { value: Hardware; label: string; hint: string }[] = [
  { value: "video_doorbell", label: "Video doorbell", hint: "At a door, with a doorbell button" },
  { value: "stick_up_cam", label: "Stick Up Cam", hint: "A small camera on a wall, shelf or ceiling" },
  { value: "other", label: "Another Ring camera", hint: "Floodlight, Spotlight, Indoor and others · shown as a generic camera" },
];

/**
 * Pair one floor-plan camera with a Ring camera without leaving the page.
 * Ring data consent and an unlinked account are handled in place; only the
 * first-time Ring authorization still needs the full connection page.
 */
export default function PairCameraSheet({
  siteId,
  camera,
  consent,
  onAllowRing,
  onConnectRing,
  onPaired,
  onClose,
}: {
  siteId: string;
  camera: { id: string; name: string };
  consent: boolean;
  onAllowRing: () => Promise<void>;
  onConnectRing: () => void;
  onPaired: () => void;
  onClose: () => void;
}) {
  const [status, setStatus] = useState<RingStatus | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [chosen, setChosen] = useState<Device | null>(null);
  const [hardware, setHardware] = useState<Hardware | null>(null);
  const dialog = useDialogFocus(true, onClose, !busy);

  const load = async (refresh = false) => {
    const next = await request<RingStatus>("/v1/ring");
    setStatus(next);
    setDevices(next.state === "connected"
      ? await request<Device[]>(refresh ? "/v1/ring/devices/refresh" : "/v1/ring/devices", refresh ? "POST" : "GET")
      : []);
  };
  const act = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (consent) void act(() => load());
  }, [consent]);

  const choose = (device: Device) => {
    setChosen(device);
    setHardware(device.hardware_model ?? null);
    setError("");
  };
  const pair = () => {
    if (!chosen || !hardware) return;
    void act(async () => {
      await request(`/v1/ring/devices/${encodeURIComponent(chosen.id)}/mapping`, "PUT",
        { site_id: siteId, camera_id: camera.id, hardware_model: hardware });
      onPaired();
      onClose();
    });
  };

  const pairedHere = (d: Device) => d.site_id === siteId && d.camera_id === camera.id;
  const usable = (d: Device) => d.support?.motion_events !== false;

  return (
    <div className="modal-backdrop sheet-backdrop" onClick={(e) => e.target === e.currentTarget && !busy && onClose()}>
      <section {...dialog} className="modal pair-sheet" role="dialog" aria-modal="true" aria-labelledby="pair-title">
        <div className="panel-heading">
          <div>
            <h2 id="pair-title">Pair {camera.name}</h2>
            <span>{chosen ? `${chosen.name} · what is mounted here?` : "Choose the Ring camera at this spot"}</span>
          </div>
          <button aria-label="Close" disabled={busy} onClick={onClose}><X size={18} /></button>
        </div>
        <div className="pair-sheet-body">
          {!consent ? (
            <div className="pair-sheet-state">
              <Link2 size={22} />
              <strong>Allow Ring camera access</strong>
              <span>Pathlight needs your permission to use your Ring cameras.</span>
              <button className="primary" disabled={busy} onClick={() => void act(onAllowRing)}>Allow and continue</button>
            </div>
          ) : !status ? (
            <p className="pair-sheet-loading" role="status">Loading your Ring cameras…</p>
          ) : status.state !== "connected" ? (
            <div className="pair-sheet-state">
              <Link2 size={22} />
              <strong>Link your Ring account</strong>
              <span>Authorize Pathlight in Ring once, then pair cameras here.</span>
              <button className="primary" onClick={onConnectRing}>Link Ring account</button>
            </div>
          ) : !devices.length ? (
            <div className="pair-sheet-state">
              <CameraMark size={22} />
              <strong>No Ring cameras found</strong>
              <span>Authorize cameras for Pathlight in the Ring app, then refresh.</span>
              <button disabled={busy} onClick={() => void act(() => load(true))}><RefreshCw size={16} /> Refresh</button>
            </div>
          ) : chosen ? (
            <fieldset className="pair-model" disabled={busy}>
              <legend>What kind of Ring camera is at {camera.name}?</legend>
              {RING_HARDWARE.map((option) => (
                <label key={option.value} className="pair-device pair-model-option" data-checked={hardware === option.value}>
                  <input
                    type="radio"
                    name="pair-hardware"
                    value={option.value}
                    checked={hardware === option.value}
                    onChange={() => setHardware(option.value)}
                  />
                  <span className="pair-device-text">
                    <strong>{option.label}</strong>
                    <small>{option.hint}</small>
                  </span>
                </label>
              ))}
              <div className="pair-model-actions">
                <button type="button" onClick={() => setChosen(null)}>Back</button>
                <button type="button" className="primary" disabled={!hardware} onClick={pair}>
                  {pairedHere(chosen) ? "Save camera type" : "Pair camera"}
                </button>
              </div>
            </fieldset>
          ) : (
            <ul className="pair-device-list">
              {devices.map((device) => {
                const here = pairedHere(device);
                const elsewhere = !here && !!device.camera_id;
                return (
                  <li key={device.id}>
                    <button
                      className="pair-device"
                      disabled={busy || !usable(device)}
                      aria-pressed={here}
                      onClick={() => choose(device)}
                    >
                      <span className="pair-device-icon"><CameraMark size={20} /></span>
                      <span className="pair-device-text">
                        <strong>{device.name}</strong>
                        <small>
                          {here ? "Paired with this camera · tap to change its type"
                            : !usable(device) ? "Not compatible"
                              : elsewhere ? "Paired elsewhere · tap to move here"
                                : "Available"}
                        </small>
                      </span>
                      {here && <Check size={18} />}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {error && <p className="pair-sheet-error" role="alert">{error}</p>}
          {status?.state === "connected" && !!devices.length && !chosen && (
            <button className="pair-sheet-refresh" disabled={busy} onClick={() => void act(() => load(true))}>
              <RefreshCw size={15} /> Refresh list
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
