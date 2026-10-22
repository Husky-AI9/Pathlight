# Ring Partner API (v1) friction log: building Pathlight

| Reviewer | Status |
| :--- | :--- |
| **Pathlight team** (repository: Pathlight) | Complete |
| **Ring Developer Platform team** | For review |

*Build, Ship, Shape: Amazon Developer Hackathon 2026 · Primary track: Ring.* Written with
[Trag's friction log template](https://github.com/chris-trag/friction-log-guide/blob/main/templates/friction-log-template.md).
This log covers **Ring integration friction only**: the Ring Partner API, the developer portal and Ring's documentation.
It contains no credentials, account IDs, device IDs, private media or addresses.

For the hackathon's required fields, every friction entry lists the **task attempted, steps taken, expected vs.
actual result, severity, workaround used and an actionable recommendation**, plus the code and tests that show it.

## BLUF (bottom line up front)

We got the whole Ring integration working on a real linked account and physical cameras: account linking, device
inventory, snapshots, bounded WHEP live view, signed webhooks, recorded clips, Event History and Smart Alerts. The
API itself is solid and the documentation is detailed. The friction is in **diagnostics**: errors that point at the
wrong cause (a Cloudflare 1010 on token exchange, a device-access 403 that was really a missing app permission),
no webhook delivery log, and response shapes the docs don't show (the WHEP `Location`, Event History, encrypted
media). Two entries blocked a core flow outright, and one cost about four days. A first-time partner would get
there, but slower than they should.

**Grade:** B− (a strong API held back by silent or misleading failure modes)

**Size:** Large (about five weeks, several workflows, September 19 to October 19, 2026)

## Persona

- **Role:** Hackathon developer building a partner app (Pathlight) on the Ring Partner API, as a small team.
- **Experience with this product:** New to the Ring Partner API in September 2026. We started from the published
  developer documentation and Ring's `ring-api-helloworld` sample.
- **Goal:** Turn the Ring cameras a small business already owns into foot-traffic analytics: link the account, list
  the cameras, react to motion in real time, analyze the recording, and backfill the last week.
- **Technical context:** A new Python 3.11 backend (standard-library `urllib`, no Ring SDK), first on a Windows
  laptop behind an HTTPS quick tunnel, then on a Railway HTTPS deployment. A React web app and an Android
  (Capacitor) app on top.

## Scope

- [x] Create a private app and configure its four URLs (Account Link, App Homepage, Token Exchange, Webhook)
- [x] Complete one-way account linking and exchange the grant for tokens
- [x] List authorized devices with status, capabilities and configurations
- [x] Download a snapshot right after linking
- [x] Open and safely close a receive-only WHEP live view
- [x] Receive and verify signed webhooks (lifecycle and motion)
- [x] Download the recording behind a motion event and analyze it
- [x] Import the last 7 days from Event History
- [x] Handle encrypted (TAKE / E2EE) cameras and Smart Alerts motion subtypes

## Pros

- **The documentation is detailed where it exists.** The media error tables (for example `416` and `425` on clip
  download) matched exactly what we saw.
- **One-way account linking with a nonce** is secure and simple once understood, and kept Ring passwords out of
  our app entirely.
- **Webhook HMAC verification is straightforward:** `X-Signature` over the raw body worked on the first real
  delivery.
- **WHEP live view worked on real hardware** at 1280×720 on the day we tried it.
- **The `ring-api-helloworld` sample** filled gaps the reference left, notably the Event History response shape.
- **Ring kept improving the docs during the hackathon.** The Sept 16 TAKE release note, the Oct 5 Motion Detection
  update and the Oct 19 Computer Vision Guidelines each answered a real question we had.
- **The cameras people already own become a new product with no new hardware.** That is the reason we'd build on
  Ring again.

## Cons

- Some errors point at the wrong cause: an edge block on token exchange, and a device-access `403` that was really
  a missing app permission.
- There is no webhook delivery log and no signed test event for a private app linked to real hardware.
- Several response shapes are undocumented: the WHEP `Location`, Event History, encrypted (TAKE) media, and the
  hosts behind pre-signed media redirects.
- Unstated constraints: snapshot ranges can't start before consent, and nothing says when a recording becomes
  downloadable.
- Development setup is manual: four callback URLs to re-enter on every tunnel restart.
- Some data partners need isn't exposed: device type, granted scopes, and the owner's Smart Alerts setting.

## Friction

### 1. OAuth token request rejected at Ring's edge

**Severity:** 🔥 Critical

**Timestamp:** Sept 19, 2026 (worked around the same day)

**Task:** Exchange the one-time authorization grant for tokens from a Python backend.

**Steps:**
1. Created a private app and configured its URLs.
2. Completed authorization through the Ring Appstore flow.
3. POSTed the documented token request to `https://oauth.ring.com/oauth/token` with Python's standard `urllib`.

**Expected:** Ring evaluates the grant and returns tokens or a structured OAuth error.

**Actual:** Ring's edge returned **Cloudflare Error 1010** before evaluating the request. The same request
succeeded once we replaced `urllib`'s default `User-Agent` with an explicit application user agent. Account linking
could not complete until then.

**Workaround:** Every Ring request now sends `User-Agent: SpatialGuard-Ring-Partner/1.0`.

**Recommendation:** Document the HTTP headers server-side clients must send (or must not send). Return a JSON error
that separates an edge-policy rejection from an invalid grant.

**Evidence:** `spatialguard/services/api/spatialguard_api/ring_provider.py` (`Provider.send`);
`spatialguard/docs/verification.md` (Sept 19).

### 2. WHEP session `Location` differs from the docs

**Severity:** 🔥 Critical

**Timestamp:** Sept 19, 2026 (worked around the same day)

**Task:** Open a bounded, receive-only live view and keep the session URL so we can close it safely.

**Steps:**
1. POSTed a video-only SDP offer to `/v1/devices/{id}/media/streaming/whep/sessions`.
2. Parsed the `Location` header.
3. Checked that the close URL stays on `api.amazonvision.com`, directly below this camera's session collection.

**Expected:** `Location` is `…/whep/sessions/{session_id}`, as the Live Video docs show.

**Actual:** The physical doorbell returned a valid `Location` that also carried a `location` query parameter. Our
strict validator rejected it, so the stream opened at Ring but we could not manage or close it.

**Workaround:** Resolve relative, root-relative or absolute references against the collection URL. Accept only the
single observed `location` query field, capped at 512 characters. Keep the host, path, single-segment and
no-fragment checks, and log only the URL shape (never IDs) when one is rejected.

**Recommendation:** Document the full `Location` grammar, including permitted query parameters, with an example of
the matching `DELETE`.

**Evidence:** `ring_provider.py` (`Provider.stream`); test
`test_ring_whep_location_accepts_safe_relative_session_reference`; first real 1280×720 live view on Sept 19
(`verification.md`).

### 3. Webhook delivery can't be verified end to end

**Severity:** 🔥 Critical while blocked; ⚠️ High now

**Timestamp:** Sept 19–24, 2026 (partly resolved)

**Task:** Prove the full path from a real trigger, through a signed webhook, to durable processing, a visit in the
app, and a UI update.

**Steps:**
1. Activated the private app and authorized the doorbell.
2. Configured the webhook URL.
3. Implemented HMAC-SHA256 verification of `X-Signature` over the raw body, duplicate suppression, durable retry
   and a dead-letter state.

**Expected:** The developer console shows each delivery's type, time, HTTP status and retry state, and can send a
signed test event to the configured endpoint.

**Actual:** Signed lifecycle deliveries (`app_integration_added`, `device_added`) arrived and verified on Sept 19,
and real motion deliveries later drove visits on the hosted deployment. Before that, a quiet endpoint could mean
any of five things: no subscription, no event generated, a delivery failure, a signature problem, or our own bug.
The private app showed no delivery record that would tell them apart.

**Workaround:** Deterministic signed fixtures test the exact ingestion boundary. An owner-visible delivery dashboard
shows event type, request ID, received and processed state, retries and failure reason, without payloads. Synthetic
evidence stays labelled as synthetic.

**Recommendation:** Add a per-app webhook delivery log (attempts, status, latency) and a "send signed test event"
button that works for private apps linked to real hardware, not only sandbox devices.

**Evidence:** `ring_service.py` (`webhook`), `ring_worker.py`; tests
`test_gateway_has_no_owner_surface_and_validates_raw_signature`,
`test_signed_malformed_webhook_is_rejected_before_queueing` and
`test_duplicate_events_survive_restart_unknown_location_preserved`.

### 4. Clip download `403` pointed at the device, not the app permission

**Severity:** ⚠️ High (about four days lost; the feature was nearly removed)

**Timestamp:** Sept 20–24, 2026 (resolved Sept 24)

**Task:** Replay the recording behind a real motion event next to the floor-plan map, and analyze it for the
visitor's path.

**Steps:**
1. POSTed `/v1/devices/{id}/media/video/download` with the event timestamp, `duration: 60000`, `codec: avc` and
   audio off.
2. Followed the pre-signed redirect.

**Expected:** An MP4, or an error naming the missing app permission or scope.

**Actual:** `403 REQUEST_FORBIDDEN` ("Client is not authorized for the device"), which reads as a device-access
problem. The real cause was that our private app hadn't been granted video-download access; clips worked once that
was enabled in the developer portal. The Scope and Permissions page lists only "common scopes" and doesn't map
scopes to endpoints, so on Sept 20 we wrongly concluded no clip route was available and disabled playback.

**Workaround:** Every clip error has a specific owner message, and a `403` now tells the owner which portal
permission to check. Real recordings have been retrieved since Sept 24: 77 detector samples over 0–15.9 s of a
41.8 s clip, processed in 7.8 s on the hosted server.

**Recommendation:** Publish a scope-to-endpoint table. Return a distinct `403` code, such as `SCOPE_NOT_GRANTED`,
naming the missing scope, separate from "no access to this device". Expose granted scopes on `/v1/users/me` or in
the token response.

**Evidence:** `ring_provider.py` (`Provider.clip`); tests `test_clip_errors_are_actionable_and_redacted` and
`test_incident_recording_uses_original_event_and_owner_authorization`;
`spatialguard/docs/recorded-incident-movement.md`.

### 5. Snapshot range that starts before app consent is rejected

**Severity:** ⚠️ High

**Timestamp:** Sept 19–20, 2026 (worked around)

**Task:** Download the latest still for a camera right after the account is linked.

**Steps:**
1. POSTed `/v1/devices/{id}/media/image/download` with `type: latest_in_range`.
2. Used a 24-hour window, within the documented constraints ("within last 180 days", "window ≤ 24 hours").

**Expected:** The newest image inside the consented part of the window, or an error that names the consent
boundary.

**Actual:** Ring rejected any window that started before the app received consent, even when it ended after. The
docs list the 180-day and 24-hour limits but not this one, so snapshots and everything built on them failed right
after first linking.

**Workaround:** We store our own link time and use one second after it as the earliest `start_timestamp`.

**Recommendation:** Clamp partly authorized windows, or return a 4xx that includes the earliest permitted
timestamp. Add the consent boundary to the documented constraints.

**Evidence:** `spatialguard_api/ring_service.py` (consent floor in `snapshot` and `event_snapshots`).

### 6. No signal for when an event's recording is downloadable

**Severity:** ⚠️ High

**Timestamp:** Sept 24, 2026 (worked around)

**Task:** Analyze the recording automatically as soon as a motion webhook arrives.

**Steps:** Requested the clip right after the signed `motion_detected` delivery was accepted.

**Expected:** A recording-ready notification, or a documented typical delay between a motion event and its
recording.

**Actual:** Early requests return `425 RECORDING_NOT_READY` (documented), but there's no notification and no stated
typical delay, so every integration has to guess a polling schedule. If a client gives up too early, the visitor's
path appears late or not at all.

**Workaround:** The worker defers media work briefly, then retries the download on a bounded schedule of increasing
delays. The owner sees "Ring is still preparing this recording" instead of a failure.

**Recommendation:** Add a `recording_available` webhook, or a `recording_ready_at` estimate on motion events.
Document the typical p50 and p95 delay per device class.

**Evidence:** `spatialguard_api/tracks.py` (`RETRY_DELAYS_S`), `ring_worker.py` (deferred media step); test
`test_automatic_analysis_retries_until_the_recording_is_ready`.

### 7. Encrypted (TAKE) video has no documented response shape

**Severity:** ⚠️ High (a wrong "no person" silently undercounts traffic)

**Timestamp:** Oct 19, 2026 (worked around)

**Task:** Analyze recordings from every paired camera, and degrade gracefully on encrypted ones, as the Computer
Vision Guidelines ask.

**Steps:** Read the Sept 16 release note, Developer FAQ Q10–Q13 and the Oct 19 Computer Vision Guidelines.

**Expected:** A status code, content type or header that marks an encrypted clip, so a client can tell
"encrypted" from "corrupt" or "empty".

**Actual:** The docs say only that TAKE video requests "continue to succeed but return encrypted content". An
encrypted MP4 can open in OpenCV and decode zero frames. A detector then reports "no person", and the visit
disappears from analytics without any visible error.

**Workaround:** Read `configurations.e2e_encryption.enabled` (FAQ Q13) before fetching any recording, and skip
encrypted cameras. Separately, treat a recording with no decodable frame as **unreadable**, never as an empty
scene, so the visit stays counted. Settings tells the owner in plain words why that camera has no paths.

**Recommendation:** Return a distinct status (for example `409` with an `encrypted_media` error code) or an
`X-Ring-Media-Encrypted` header for TAKE content.

**Evidence:** `ring_service.py` (`configuration_summary`, `incident_clip`), `person_tracking.py`
(`RecordingUnreadable`), `tracks.py`; tests `test_encrypted_camera_keeps_the_visit_and_never_reads_video` and
`test_undecodable_recording_is_not_reported_as_an_empty_scene`.

### 8. Event History has an endpoint but no documented schema

**Severity:** ⚠️ High (a backfill is a new customer's fastest path to value)

**Timestamp:** Oct 19, 2026 (worked around)

**Task:** On pairing, bring in the last week of real Ring events, so a new owner's analytics start with real foot
traffic instead of an empty week.

**Steps:** Read the API reference, where `GET /v1/history/devices/{device_id}/events` appears only in the endpoint
table, and Ring's `ring-api-helloworld` sample (`scripts/event_history.py`).

**Expected:** Response fields, a time-range filter, pagination and retention, as the Media Clips and Snapshots
sections document theirs.

**Actual:** Only the sample shows the shape (`data[].attributes.event_type` such as `motion.human` or `ding`, and
`attributes.start`) and an `event_types` filter. Nothing documents time ranges, page links, retention, or whether
history and clips are limited to events after app consent.

**Workaround:** Parse defensively (epoch seconds, epoch milliseconds or ISO 8601; `event_type` or `type`). Filter
the time range on our side. Follow a `links.next` page only when it points back to `api.amazonvision.com`, with a
page cap. Cap each camera at 40 events, and skip events a webhook already delivered (same device and kind within
10 seconds). Imported events run through the normal pipeline and are labelled "Ring Event History".

**Recommendation:** Document the Event History response, `since` and `until` parameters, pagination and
retention, and whether event IDs match webhook `data.id`, so clients can deduplicate exactly.

**Evidence:** `ring_service.py` (`import_history`, `history_kind`, `history_time`); tests
`test_event_history_import_queues_real_past_visits_once` and `test_event_history_follows_ring_pages`.

### 9. Development callback URLs need repeated manual updates

**Severity:** ⚡ Medium

**Timestamp:** Sept 19–20, 2026 (resolved by stable hosting on Sept 21)

**Task:** Test account linking, the app homepage, token exchange and webhooks from a local machine.

**Steps:**
1. Exposed the local gateway through an HTTPS quick tunnel.
2. Pasted the hostname into the private app's four URL fields.
3. Repeated this after every tunnel restart.

**Expected:** Configure a development profile once, or update all related URLs together.

**Actual:** Every hostname change meant editing four portal fields, and one stale field broke only part of the
flow, which was hard to diagnose.

**Workaround:** A tunnel helper (`spatialguard/scripts/ring-tunnel.py`) printed all four URLs together. From
Sept 21 the app runs on a stable HTTPS domain (`/ring/link`, `/ring/home`, `/ring/token`, `/ring/webhook`).

**Recommendation:** Offer reusable dev and staging callback profiles, a "base URL" field that derives all four, or
an API to update them in one call.

### 10. Pre-signed media redirect hosts aren't documented

**Severity:** ⚡ Medium (security: the risk is a too-broad allowlist, or breakage if hosts change)

**Timestamp:** Sept 2026 (worked around)

**Task:** Follow snapshot and clip redirects safely: never forward the bearer token to a third party, and reject
open redirects.

**Steps:** POSTed to the media endpoints and followed the documented `303 See Other` to the pre-signed `Location`.

**Expected:** The docs name the hosts for pre-signed media URLs, so clients can allowlist them.

**Actual:** The docs say only "pre-signed Location URL". The hosts we saw were under `amazonvision.com` and
`devices.amazon.dev`, which we learned only by observation.

**Workaround:** Allow HTTPS on port 443 only to `*.amazonvision.com` and `*.devices.amazon.dev`, with no userinfo
or fragment. Send the bearer token only to `api.amazonvision.com`, and cap the number of redirects.

**Recommendation:** Document the pre-signed host suffixes, with a guarantee or a change-notice process.

**Evidence:** `ring_provider.py` (`snapshot`, `clip`); tests
`test_clip_follows_signed_redirect_without_forwarding_bearer` and `test_clip_rejects_untrusted_redirect`.

### 11. Device type isn't exposed

**Severity:** ℹ️ Low

**Timestamp:** Sept 20, 2026 (resolved by asking the owner)

**Task:** Show the right camera model (doorbell or Stick Up Cam) on the 3D floor plan after the owner pairs a
device.

**Steps:** Called `GET /v1/devices` with `include=status,capabilities,…`.

**Expected:** A product family or device type field.

**Actual:** The resource carries only `name` and `image_url`, and the docs say not to infer type from
`image_url` because it "is not part of the API contract". Capabilities identify chimes, but not a doorbell from a
stick-up camera.

**Workaround:** The owner picks the camera type while pairing, as the docs recommend. Two known artwork filenames
still choose the default 3D illustration, and nothing else depends on them.

**Recommendation:** Add a stable `product_family` (doorbell, stick_up_cam, floodlight, indoor, chime) to the
device resource.

**Evidence:** `ring_service.py` (`hardware_model`); test
`test_device_hardware_uses_product_artwork_not_owner_camera_names`.

### 12. Motion subtype depends on the owner's Smart Alerts setting

**Severity:** ℹ️ Low

**Timestamp:** Oct 19, 2026 (worked around)

**Task:** Analyze clips only when a person is likely, and count cars at the parking camera from Ring's `vehicle`
alerts.

**Steps:** Read the Oct 5 Motion Detection update and the Computer Vision Guidelines on subtypes.

**Expected:** A subtype a partner can rely on.

**Actual:** With Smart Alerts off, every motion is `motion`. With them on, it's `human`, `vehicle`,
`package_delivery` or `other_motion`. The owner's setting, not the scene, decides what a partner receives, and a
partner can't see that setting.

**Workaround:** Skip person analysis only for `vehicle`, and count those as vehicles, never as visits. Analyze
everything else, including `motion` and `other_motion`. Show the vehicles card only when vehicle alerts exist, and
say it comes from Ring Smart Alerts.

**Recommendation:** Report the owner's Smart Alerts state in the device configuration, so apps can explain
missing vehicle counts.

**Evidence:** `ring_worker.py` (`NOT_A_PERSON`, `is_vehicle`), `analytics.py` (`_vehicles`); test
`test_ring_vehicle_alert_is_counted_and_never_a_visit`.

### 13. Keeping the link nonce out of referrers broke the hosted link form

**Severity:** ℹ️ Low (confusing: it worked locally and failed only when hosted)

**Timestamp:** Sept 21, 2026 (resolved)

**Task:** Complete Ring's one-way account link on the hosted deployment, where Ring redirects to our Account Link
URL with the nonce in the query string.

**Steps:** Served the linking page with `Referrer-Policy: no-referrer`, so the nonce could never leak, then
submitted the page's own HTML form.

**Expected:** The same-origin form POST carries a normal `Origin`.

**Actual:** Under `no-referrer`, the browser sent `Origin: null` on the form POST. Our CSRF origin check rejected
it before the code was validated.

**Workaround:** Use `Referrer-Policy: strict-origin`, so only the origin is ever sent and the nonce-bearing query
string isn't. Compare against the exact configured HTTPS origin, keep rejecting null, foreign and cross-site
submissions, and keep the signed nonce, expiry and single-use checks.

**Recommendation:** In the Account Linking guide, recommend a referrer policy for the Account Link page and
mention the `Origin: null` interaction.

**Evidence:** `spatialguard/docs/hosted-ring-link-verification.md`; tests
`test_hosted_link_form_claims_only_valid_signed_ring_account` and
`test_gateway_accepts_public_origin_behind_host_rewriting`.

## Questions

- Which HTTP headers does Ring's edge require or block for server-side clients? (Friction 1)
- Which scope does each endpoint need, and how can an app read the scopes it was granted? (Friction 4)
- What is the typical delay between a motion event and a downloadable recording, per device class? (Friction 6)
- How should a client recognize encrypted (TAKE) content in a media response? (Friction 7)
- Do Event History event IDs match webhook `data.id`? Are history and clips limited to events after app consent,
  and how far back does history go? (Friction 8)
- Are the pre-signed media hosts stable, and will changes be announced? (Friction 10)
- Is a device type or product family field planned for the device resource? (Friction 11)

## Recommendations

Ranked by priority:

1. **Webhook delivery log and a signed test event for private apps on real hardware.** This shows exactly where an
   event-driven integration breaks (Friction 3). 🔥
2. **A scope-to-endpoint table and a distinct "scope not granted" error.** This alone would have saved us about
   four days (Friction 4). 🔥
3. **Name the cause in edge rejections on token exchange,** and document required headers (Friction 1). 🔥
4. **Document the WHEP `Location` grammar** with an example `DELETE` (Friction 2). 🔥
5. **A `recording_available` webhook or readiness estimate,** so paths appear as soon as the clip exists
   (Friction 6). ⚠️
6. **A distinct status or header for encrypted (TAKE) media,** so encrypted clips can't be mistaken for empty
   scenes (Friction 7). ⚠️
7. **A documented Event History schema** with `since` and `until`, pagination, retention and ID matching
   (Friction 8). ⚠️
8. **Clamp media ranges at the consent boundary,** or return the earliest permitted timestamp (Friction 5). ⚠️
9. **Reusable dev and staging callback profiles** (Friction 9). ⚡
10. **Document the pre-signed media hosts** (Friction 10). ⚡
11. **Add `product_family` to the device resource,** and expose the owner's Smart Alerts state (Friction 11
    and 12). ℹ️
12. **Recommend a referrer policy for the Account Link page** (Friction 13). ℹ️

## Video timestamps

These sessions weren't screen-recorded. The dates below come from the commit history and the verification
records in `spatialguard/docs/`.

| Date | Event |
| :--- | :--- |
| Sept 18, 2026 | Read the Ring developer documentation as published that day |
| Sept 19, 2026 | Token exchange blocked at the edge (Friction 1), then fixed. First signed lifecycle webhooks. First 1280×720 WHEP live view after the `Location` fix (Friction 2) |
| Sept 19–20, 2026 | Snapshots fail after first linking (Friction 5). Four callback URLs re-entered on every tunnel restart (Friction 9) |
| Sept 20, 2026 | Clip download returns `403`; playback disabled on a wrong conclusion (Friction 4) |
| Sept 21, 2026 | Moved to stable HTTPS hosting. Hosted link form fixed (Friction 13) |
| Sept 24, 2026 | Video-download permission enabled; first real recording analyzed into a 77-point path in 7.8 s. Retry-until-ready added (Friction 6) |
| Oct 5, 2026 | Ring's Motion Detection update (subtypes) |
| Oct 19, 2026 | Ring's Computer Vision Guidelines. Encrypted-camera handling (Friction 7), Event History import (Friction 8) and Smart Alerts vehicles (Friction 12) |

## Screen recording

- Full session: not recorded. The evidence for each entry is the code, tests and verification records it links
  to, and the demo video shows the working result on real Ring cameras.

## Test environment

- **OS:** Windows (local development, behind an HTTPS quick tunnel) until Sept 20; Linux container on Railway from
  Sept 21.
- **Device:** A physical Ring Video Doorbell (2nd Gen) from Sept 19, then three physical Ring cameras on the same
  linked US account with an active Ring plan.
- **SDK/API version tested:** Ring Partner API v1 (`api.amazonvision.com`, `oauth.ring.com`), with no Ring SDK.
  Docs as published Sept 18, 2026, plus the Sept 16 TAKE note, the Oct 5 Motion Detection update and the Oct 19
  Computer Vision Guidelines.
- **Clients:** Chrome (web app and WHEP live view) and the Android app (Capacitor).
- **Runtime versions:** Python 3.11 (standard-library `urllib`), Node 22, OpenCV 5 with YOLO11n.

## What succeeded

- ✅ One-way account linking and token exchange, after adding an explicit `User-Agent`
- ✅ Authorized device inventory with status, capabilities and configurations
- ✅ Snapshots, with a start time after the consent moment
- ✅ Bounded, receive-only WHEP live view at 1280×720, opened and closed safely
- ✅ Signed lifecycle and motion webhooks, verified and processed durably
- ✅ Recorded clips analyzed into floor-plan paths (77 points in 7.8 s on the hosted server)
- ✅ Event History backfill of the last 7 days through the same pipeline
- ✅ Encrypted cameras counted but never analyzed; Smart Alerts vehicles counted apart from visits

## What failed

- ❌ Token exchange with Python's default user agent (Cloudflare 1010)
- ❌ Managing and closing a live view until the undocumented `Location` shape was accepted
- ❌ Snapshots with a window starting before consent
- ❌ Clip download for four days, behind a `403` that pointed at the device instead of the missing permission
- ❌ Verifying webhook delivery from the Ring side: no delivery log, no test event for real hardware

## Appendix

### Scratch pad

- Severity scale used: 🔥 Critical blocked a core flow; ⚠️ High cost significant time or forced a workaround users
  or reviewers would notice; ⚡ Medium slowed us down or carries a risk; ℹ️ Low is a papercut or documentation gap.
- The biggest pattern: when something failed, the API usually didn't say *why*. Better diagnostics (a delivery
  log, a test-event button, errors that name the missing scope) would have saved several days between "account
  linked" and "event-driven app working".
- **Would we build with Ring again? Yes.** Ring turns cameras a shop already owns into a new product with no new
  hardware, and the API did everything we needed once each gap was understood.
