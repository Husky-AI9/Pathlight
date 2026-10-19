import { useCallback, useEffect, useState, type ComponentProps } from "react";
import Scene3D, { type CameraModelFactory } from "@twinforge/spatial-view/Scene3D";
import { ringCameraModel } from "./ringCameraModels";
import { request } from "./platform";
import type { components } from "./generated";

type Device = components["schemas"]["RingDevice"];

// Provider-specific presentation stays in Pathlight, outside TwinForge's
// layout contract and the reusable map renderer. This module loads with 3D.
export default function RingScene3D({ siteId, ...props }: ComponentProps<typeof Scene3D> & { siteId: string }) {
  const [devices, setDevices] = useState<Device[]>([]);
  useEffect(() => {
    let active = true;
    setDevices([]);
    void request<Device[]>("/v1/ring/devices")
      .then(inventory => { if (active) setDevices(inventory); })
      .catch(() => { if (active) setDevices([]); });
    return () => { active = false; };
  }, [siteId]);
  const factory = useCallback<CameraModelFactory>((id, active, heading, mount) => {
    const device = devices.find(d => d.site_id === siteId && d.camera_id === id);
    // The owner says what is mounted while pairing; anything else draws the generic camera body.
    const kind = device?.hardware_model === "video_doorbell" ? "video_doorbell" : "stick_up_cam";
    return ringCameraModel(kind, id, active, heading, mount);
  }, [devices, siteId]);
  return <Scene3D {...props} cameraModelFactory={factory} />;
}
