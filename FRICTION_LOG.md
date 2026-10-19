# Pathlight — Ring developer friction log

**Build, Ship, Shape: Amazon Developer Hackathon · Primary track: Ring**
**Last updated:** October 7, 2026 · **First recorded:** September 19, 2026

This log records friction we hit while building Pathlight (repository: SpatialGuard) against the Ring Partner API with a real Ring account and a physical **Video Doorbell (2nd Gen)**. Each entry lists the task, steps, expected and actual results, severity, our workaround, and a suggestion. It contains no credentials, account IDs, device IDs, private media, or addresses.

**Environment:**
- **Ring app:** private app on a US Ring account with an active plan.
- **Hosting:** local Windows development behind an HTTPS quick tunnel (Sept 19–20), then a stable Railway HTTPS deployment (from Sept 21).
- **Backend:** Python 3.11 standard-library `urllib` client.
- **Live view:** WebRTC WHEP in Chrome and in the Android app (Capacitor).
- **Docs:** we used the Ring developer documentation as published on September 18, 2026.

**Severity scale:**
- **Critical:** blocked a core flow.
- **Important:** cost significant time, or forced a workaround that users or reviewers would notice.
- **Minor:** a papercut or documentation gap.

## Summary

| # | Area | What happened | Severity | Status |
|---|---|---|---|---|
| 1 | OAuth | Token request blocked at Ring's edge (Cloudflare 1010) because of the default Python user agent | Critical | Worked around (Sept 19) |
| 2 | Live video (WHEP) | The real session `Location` carried a `location` query parameter the docs don't show | Critical | Worked around (Sept 19) |
| 3 | Snapshots | A `latest_in_range` window that started before app consent was rejected | Important | Worked around (Sept 19–20) |
| 4 | Dev setup | Four callback URLs had to be re-entered after every quick-tunnel restart | Important | Resolved by stable hosting (Sept 21) |
| 5 | Webhooks | No delivery log or "send test event" for a private app linked to real hardware | Critical → Important | Partly resolved (real deliveries since Sept 19) |
| 6 | Recorded clips | Clip download returned 403 until the app's download permission was enabled; the scope-to-endpoint mapping isn't documented | Important | Resolved (Sept 24) |
| 7 | Recorded clips | No signal for when a motion event's recording becomes downloadable | Important | Worked around (retry on 425) |
| 8 | Device inventory | No device type field; the docs say not to infer it from `image_url` | Minor | Workaround limited to cosmetics |
| 9 | Media security | The host set for pre-signed snapshot and clip redirects isn't documented | Minor | Worked around (allowlist) |
| 10 | Account linking | Keeping the nonce out of referrers broke our hosted link form | Minor | Resolved (Sept 21) |

---

## 1. OAuth token request rejected at Ring's edge

- **Date / status:** Sept 19, 2026 · worked around
- **Task attempted:** Exchange the one-time Ring authorization grant for tokens from a Python backend.
- **Steps taken:**
  1. Created a private app and configured its URLs.
  2. Completed authorization through the Ring Appstore flow.
  3. POSTed the documented token request to `https://oauth.ring.com/oauth/token` with Python's standard `urllib`.
- **Expected:** Ring evaluates the grant and returns tokens or a structured OAuth error.
- **Actual:** Ring's edge returned **Cloudflare Error 1010** before evaluating the OAuth request. The same request succeeded once we replaced urllib's default `User-Agent` with an explicit application user agent.
- **Severity:** Critical. Account linking could not complete.
- **Workaround:** Every Ring request now sends `User-Agent: SpatialGuard-Ring-Partner/1.0`.
- **Evidence:** `spatialguard/services/api/spatialguard_api/ring_provider.py` (`Provider.send`), `spatialguard/docs/verification.md` (Sept 19).
- **Suggestion:** State the required or blocked HTTP headers for server-side clients. Return a JSON error that separates an edge-policy rejection from an invalid grant.

## 2. WHEP session `Location` shape differs from the docs

- **Date / status:** Sept 19, 2026 · worked around
- **Task attempted:** Open a bounded, receive-only live view and keep the session URL so we can close it safely.
- **Steps taken:**
  1. POSTed a video-only SDP offer to `/v1/devices/{id}/media/streaming/whep/sessions`.
  2. Parsed the `Location` header.
  3. Validated that the close URL stayed on `api.amazonvision.com`, directly below this camera's session collection.
- **Expected:** `Location` would be `…/whep/sessions/{session_id}`, as shown in the Live Video docs.
- **Actual:** The physical doorbell returned a valid session `Location` that also carried a `location` query parameter. Our strict validator rejected it, so the stream opened at Ring but could not be managed or closed by us.
- **Severity:** Critical. Live view could not be safely closed.
- **Workaround:**
  - Resolve relative, root-relative or absolute references against the collection URL.
  - Accept only the single observed `location` query field, capped at 512 characters.
  - Keep the host, path, single-segment and no-fragment checks.
  - Record only the URL shape (never IDs) when a response is rejected.
- **Evidence:** `ring_provider.py` (`Provider.stream`); test `test_ring_whep_location_accepts_safe_relative_session_reference`; first real 1280×720 live view on Sept 19 (`verification.md`).
- **Suggestion:** Document the full `Location` grammar, including the permitted query parameters, with an example of the matching `DELETE`.

## 3. Snapshot range that starts before app consent is rejected

- **Date / status:** Sept 19–20, 2026 · worked around
- **Task attempted:** Download the latest still for a camera right after the account was linked.
- **Steps taken:**
  1. POSTed `/v1/devices/{id}/media/image/download` with `type: latest_in_range`.
  2. Used a 24-hour window, which is within the documented constraints ("within last 180 days", "window ≤ 24 hours").
- **Expected:** Ring returns the newest image inside the part of the window that is covered by consent, or an error that names the consent boundary.
- **Actual:** Ring rejected any window whose start was earlier than the moment the app received consent, even when the window ended after consent. The docs list the 180-day and 24-hour constraints but not this one.
- **Severity:** Important. Snapshots, and every feature built on them, failed right after first linking.
- **Workaround:** We store our own link-audit time and use one second after it as the earliest `start_timestamp`.
- **Evidence:** `spatialguard_api/ring_service.py` (consent floor in `snapshot` and `event_snapshots`).
- **Suggestion:** Clamp partially authorized windows, or return a 4xx that includes the earliest permitted timestamp. Add the consent boundary to the documented constraints.

## 4. Development callback URLs need repeated manual updates

- **Date / status:** Sept 19–20, 2026 · resolved by stable hosting on Sept 21
- **Task attempted:** Test account linking, the app homepage, token exchange and webhooks from a local machine.
- **Steps taken:**
  1. Exposed the local gateway through an HTTPS quick tunnel.
  2. Pasted the hostname into the private app's four URL fields (Account Link, App Homepage, Token Exchange, Webhook).
  3. Repeated this after every tunnel restart.
- **Expected:** Configure a development profile once, or update all related URLs together.
- **Actual:** Every hostname change meant editing four portal fields. One stale field broke only part of the flow, which was hard to diagnose.
- **Severity:** Important.
- **Workaround:** First, a tunnel helper (`spatialguard/scripts/ring-tunnel.py`) printed all four URLs together. From Sept 21 the app runs on a stable Railway HTTPS domain (`/ring/link`, `/ring/home`, `/ring/token`, `/ring/webhook`).
- **Suggestion:** Offer reusable dev/staging callback profiles, a "base URL" field that derives all four, or a CLI/API to update them in one call.

## 5. Webhook delivery is hard to verify end to end

- **Date / status:** Sept 19–24, 2026 · partly resolved
- **Task attempted:** Prove the full path from a real trigger, through a signed webhook, to durable processing, a visit in the app, and a UI update.
- **Steps taken:**
  1. Activated the private app.
  2. Authorized the doorbell.
  3. Configured the webhook URL.
  4. Implemented HMAC-SHA256 verification of `X-Signature` over the raw body, duplicate suppression, durable retry and a dead-letter state.
- **Expected:** The developer console shows each delivery's type, time, HTTP status and retry state, and can send a signed test event to the configured endpoint.
- **Actual:**
  - Real signed **lifecycle** deliveries (`app_integration_added`, `device_added`) arrived and verified on Sept 19.
  - Real **motion** deliveries later drove visits on the hosted deployment; the Sept 24 recording analysis came from one.
  - Before that, a quiet endpoint could mean any of five things: no subscription, no event generated, delivery failure, a signature problem, or our own bug. The private app's configuration showed no delivery record that would separate them.
- **Severity:** Critical while blocked. Important now.
- **Workaround:**
  - Deterministic signed fixtures test the exact ingestion boundary.
  - An owner-visible delivery dashboard shows event type, request ID, received/processed state, retries and failure reason, without payloads.
  - Synthetic evidence stays labelled as synthetic.
- **Evidence:** `ring_service.py` (`webhook`), `ring_worker.py`; tests `test_gateway_has_no_owner_surface_and_validates_raw_signature`, `test_signed_malformed_webhook_is_rejected_before_queueing` and `test_duplicate_events_survive_restart_unknown_location_preserved`.
- **Suggestion:** Add a per-app webhook delivery log (attempts, status, latency) and a "send signed test event" button that works for private apps linked to real hardware, not only sandbox devices.

## 6. Clip download 403 pointed at the device, not the app permission

- **Date / status:** Sept 20–24, 2026 · resolved Sept 24
- **Task attempted:** Replay the recording behind a real motion event next to the floor-plan map, and analyze it for the visitor's path.
- **Steps taken:**
  1. POSTed `/v1/devices/{id}/media/video/download` with the event timestamp, `duration: 60000`, `codec: avc` and audio off.
  2. Followed the pre-signed redirect.
- **Expected:** An MP4, or an error that says which app permission or scope is missing.
- **Actual:**
  - The request was refused with 403 `REQUEST_FORBIDDEN` ("Client is not authorized for the device"). That reads as a device-access problem.
  - The real cause was that our private app had not been granted video-download access. Recorded clips worked once that access was enabled in the developer portal.
  - The Scope and Permissions page lists only "common scopes" and does not map scopes to endpoints. On Sept 20 we therefore wrongly concluded that no clip route was available to us, and disabled playback.
- **Severity:** Important. It cost about four days and nearly removed the feature.
- **Workaround:** Every clip error has a specific owner message, and 403 now tells the owner which developer-portal permission to check. Real recordings have been retrieved since Sept 24 (77 detector samples over 0–15.9 s of a 41.8 s clip, processed in 7.8 s on Railway).
- **Evidence:** `ring_provider.py` (`Provider.clip`); tests `test_clip_errors_are_actionable_and_redacted` and `test_incident_recording_uses_original_event_and_owner_authorization`; `spatialguard/docs/recorded-incident-movement.md`.
- **Suggestion:** Publish a scope-to-endpoint table. Use a distinct 403 code, such as `SCOPE_NOT_GRANTED`, naming the missing scope, separate from "no access to this device". Expose granted scopes on `/v1/users/me` or in the token response.

## 7. No signal for when an event's recording is downloadable

- **Date / status:** Sept 24, 2026 · worked around
- **Task attempted:** Analyze the recording automatically as soon as a motion webhook arrives.
- **Steps taken:** Requested the clip right after the signed `motion_detected` delivery was accepted.
- **Expected:** A recording-ready notification, or documented typical latency between a motion event and an available recording.
- **Actual:** Requests made too early return 425 `RECORDING_NOT_READY` (documented). We found no notification and no stated typical delay, so every integration has to guess a polling schedule.
- **Severity:** Important. A visit's path appears late or not at all if the client gives up too early.
- **Workaround:** The worker defers post-event media work briefly. Path analysis then retries the download on a bounded schedule of increasing delays, and the owner sees "Ring is still preparing this recording" instead of a failure.
- **Evidence:** `spatialguard_api/tracks.py` (`RETRY_DELAYS_S`), `ring_worker.py` (deferred media step); test `test_automatic_analysis_retries_until_the_recording_is_ready`.
- **Suggestion:** Add a `recording_available` webhook, or a `recording_ready_at` estimate on motion events. Document the typical p50/p95 delay per device class.

## 8. Device type isn't exposed

- **Date / status:** Sept 20, 2026 · cosmetic workaround
- **Task attempted:** Draw the right camera model (doorbell or Stick Up Cam) on the 3D floor plan after the owner pairs a device.
- **Steps taken:** Called `GET /v1/devices` with `include=status,capabilities,…`.
- **Expected:** A product family or device type field.
- **Actual:** The resource carries only `name` and `image_url`. The docs say explicitly not to infer type from `image_url`, because it "is not part of the API contract". Capabilities identify chimes, but not doorbell vs. stick-up camera.
- **Severity:** Minor.
- **Workaround:** We map two known artwork filenames only to choose a 3D illustration. Everything else renders as a generic camera, and no behavior, permission or analytics depends on it. We plan to let the owner choose the model while pairing, as the docs recommend.
- **Evidence:** `ring_service.py` (`hardware_model`); test `test_device_hardware_uses_product_artwork_not_owner_camera_names`.
- **Suggestion:** Add a stable `product_family` (doorbell / stick_up_cam / floodlight / indoor / chime) to the device resource.

## 9. Pre-signed media redirect hosts aren't documented

- **Date / status:** Sept 2026 · worked around
- **Task attempted:** Follow snapshot and clip redirects safely: never forward the bearer token to a third party, and reject open redirects.
- **Steps taken:** POSTed to the media endpoints and followed the documented `303 See Other` to the pre-signed `Location`.
- **Expected:** Docs name the host set for pre-signed media URLs, so clients can allowlist them.
- **Actual:** The docs say only "pre-signed Location URL". The hosts we saw were under `amazonvision.com` and `devices.amazon.dev`, which we learned only by observation.
- **Severity:** Minor. The risk is a too-broad allowlist, or breakage if hosts change.
- **Workaround:**
  - Allow HTTPS on port 443 only to `*.amazonvision.com` and `*.devices.amazon.dev`, with no userinfo or fragment.
  - Send the bearer token only to `api.amazonvision.com`.
  - Cap the redirect count.
- **Evidence:** `ring_provider.py` (`snapshot`, `clip`); tests `test_clip_follows_signed_redirect_without_forwarding_bearer` and `test_clip_rejects_untrusted_redirect`.
- **Suggestion:** Document the pre-signed host suffixes, with a guarantee or a change-notice process.

## 10. Keeping the nonce out of referrers broke our hosted link form

- **Date / status:** Sept 21, 2026 · resolved
- **Task attempted:** Complete Ring's one-way account link on the hosted deployment, where Ring redirects to our Account Link URL with the nonce in the query string.
- **Steps taken:** Served the linking page with `Referrer-Policy: no-referrer` so the nonce could never leak, then submitted the page's own HTML form.
- **Expected:** The same-origin form POST carries a normal `Origin`.
- **Actual:** Under `no-referrer` the browser sent `Origin: null` on the native form POST. Our CSRF origin guard rejected it before the code was validated. Earlier host-rewriting fixes behind Railway's proxy did not help.
- **Severity:** Minor, but confusing (linking worked locally and failed only when hosted).
- **Workaround:**
  - Use `Referrer-Policy: strict-origin`, so only the origin is ever sent and the nonce-bearing query string is not.
  - Compare against the exact configured HTTPS origin.
  - Keep rejecting null, foreign and cross-site submissions.
  - Keep the signed nonce, expiry and single-use checks.
- **Evidence:** `spatialguard/docs/hosted-ring-link-verification.md`; tests `test_hosted_link_form_claims_only_valid_signed_ring_account` and `test_gateway_accepts_public_origin_behind_host_rewriting`.
- **Suggestion:** In the Account Linking guide, recommend a referrer policy for the Account Link page and mention the `Origin: null` interaction.

---

## Feature requests

| Request | Why it matters to Pathlight | Priority |
|---|---|---|
| Per-app webhook delivery log, plus a signed test event for private apps with real devices | Shows exactly where an event-driven integration breaks, and stops teams from overclaiming "it works" | Critical |
| Scope-to-endpoint table and a distinct "scope not granted" error | Would have saved days on clip download (entry 6) | Critical |
| `recording_available` webhook or readiness estimate | Visitor paths could appear as soon as the clip exists, without guessed polling (entry 7) | Important |
| `product_family` on the device resource | Correct hardware in setup and on the map, without fragile heuristics (entry 8) | Important |
| Reusable dev/staging callback profiles | One-time configuration for local development (entry 4) | Important |
| Documented WHEP `Location` grammar and pre-signed media hosts | Secure clients without trial and error (entries 2 and 9) | Important |
| Consent-boundary clamping, or the earliest permitted timestamp, for media ranges | Snapshots work immediately after linking (entry 3) | Nice-to-have |

## Would we build with Ring again?

**Yes.** With account linking, authorized inventory, snapshots, bounded WHEP live view, recorded clips and signed webhooks, Pathlight turns cameras a shop already owns into foot-traffic analytics with no new hardware. The documentation is detailed, and its error tables (for example 416 and 425 on media) matched what we saw. The biggest improvements would be diagnostics: a delivery log, a test-event button, and errors that name the missing scope. Those would have saved us several days between "account linked" and "event-driven app working".
