# Pathlight

**Foot-traffic analytics for the Ring cameras you already own.**

Pathlight maps Ring camera activity onto your own floor plan. A café, shop, clinic or office can see where visitors go, which areas are busiest, when the rush starts, and how long people stay, without buying people counters or new cameras. Each place gets a 2D/3D floor-plan twin, a people heatmap, week-over-week site analytics, queue alerts and a weekly plain-English insight written by Amazon Bedrock. One account can manage several places.

*Build, Ship, Shape: Amazon Developer Hackathon 2026 — **Ring track** (also entered in AWS Builder).*

| | |
|---|---|
| **Hosted app** | https://pathlight.up.railway.app |
| **Judge guide** | [JUDGES.md](JUDGES.md): a 5-minute path. Credentials are in the Devpost testing-instructions field. |
| **Friction log** | [FRICTION_LOG.md](FRICTION_LOG.md): 10 dated Ring entries plus feature requests |
| **Platforms** | Web (desktop and phone) and Android (Capacitor) |
| **Ring hardware used** | Physical Ring Video Doorbell (2nd Gen) on a real, linked Ring account |

> The repository and code namespaces are still called **SpatialGuard** (`spatialguard/`, `spatialguard_api`). The floor-plan twin engine is **TwinForge** (`services/api/twinforge`). Pathlight is the product built on both.

---

## What it does

- **Floor plan to twin.** Upload a PNG/JPEG floor plan. TwinForge traces rooms and doors into an editable 2D/3D model, with optional Amazon Bedrock vision that ignores furniture. You confirm two real dimensions before anything is published, and every published layout is an immutable revision.
- **Cameras on the map.** Place each Ring camera where it hangs and aim it. Pairing links the map camera to an authorized Ring device, and the owner picks its type (video doorbell, Stick Up Cam or another Ring camera), because Ring's API doesn't report one.
- **People heatmap.** Every visit becomes floor positions, and the heatmap shows where people actually walk and stop over a chosen time span.
- **Site analytics.** Visits per day against last week, visits by hour, a busy-times grid, zones with average time spent, and entrances. Real Ring visits and simulated demo visits can be counted separately (**Live only / All data**).
- **Real history on day one.** **Import last 7 days** reads each paired camera's Ring Event History and analyzes those recordings like live visits, so analytics start with real foot traffic.
- **Vehicles.** Ring Smart Alerts `vehicle` events are counted as cars by hour (the parking lot), separately from visits. No plates or images are kept.
- **Weekly insight.** Amazon Bedrock writes a short summary from the aggregate numbers only. No images or personal data are sent. Every note is checked before it is shown: each figure must match the data, a block list catches anything about who visitors are, and a failed note is replaced by a plain one.
- **Queue and crowding alerts.** Zones named like "Counter" or "Checkout" raise an alert when they pass their limit.
- **Property management.** Several places per account, with one analytics view per site and data export and deletion.
- **Visit replay.** Open a real Ring visit to play the Ring recording beside the map while the detected path grows on the floor plan.

**Honest by design:**
- Positions are estimates from the camera's placement and field of view, not calibrated measurements.
- Paths are anonymous floor points: no faces, no identity, and no link between visits or accounts.
- Foot-traffic analysis is a separate, off-by-default permission, and each recording is deleted after analysis.
- Simulated demo data is labelled **Simulated** everywhere.

## The innovation: positions without calibration

Camera analytics normally needs each camera calibrated: an installer, reference points, measuring. Pathlight skips that step. The owner drops each Ring camera on their floor plan where it hangs, aims it, and says what it is. Pathlight then estimates floor positions from those priors:
- each detected person's foot point,
- a linear angle-per-pixel bearing across the lens's field of view (the equidistant wide-angle model),
- a near/far cue from where the feet meet the floor.

Every position is shown as an estimate with an uncertainty footprint.

This builds on established single-view geometry and monocular localization work:
- the foot point as the ground position (Hoiem et al., IJCV 2008; Rezaei & Azarmi, 2020),
- ground-plane positions from an uncalibrated image (Criminisi et al., IJCV 2000; Aghaei et al., WACV 2021),
- the equidistant lens model (Kannala & Brandt, TPAMI 2006),
- uncertainty-aware single-camera localization (Bertoni et al., ICCV 2019).

The upgrade path is self-calibrating from the visitors themselves (Krahnstoever & Mendonça, ICCV 2005). Full method, references and limits: [`spatialguard/docs/position-estimation.md`](spatialguard/docs/position-estimation.md).

## How Ring is used (at runtime)

All Ring calls go to the official Ring Partner API from the server. Tokens never reach the browser or the Android app.

| Ring capability | Endpoint / mechanism | Where in code |
|---|---|---|
| One-way account linking and token exchange | Ring Appstore link with nonce, `POST https://oauth.ring.com/oauth/token`, `GET /v1/users/me`, `POST/PATCH /v1/accounts/me/app-integrations` | `spatialguard_api/ring_gateway.py`, `ring_service.py`, `ring_provider.py` |
| Authorized device inventory, status, capabilities | `GET /v1/devices?include=…` | `ring_service.py` |
| Signed webhooks (motion, button press, lifecycle) | HMAC-SHA256 `X-Signature` over the raw body, durable inbox, dedupe, bounded retries | `ring_service.py` (`webhook`), `ring_worker.py` |
| Snapshots | `POST /v1/devices/{id}/media/image/download` → pre-signed redirect | `ring_provider.py` (`snapshot`) |
| Recorded clips for visit paths | `POST /v1/devices/{id}/media/video/download` → OpenCV 5 + YOLO11n person detection → floor points | `ring_provider.py` (`clip`), `tracks.py`, `person_tracking.py` |
| Live view | WebRTC WHEP `…/media/streaming/whep/sessions`, bounded, video only | `ring_provider.py` (`stream`) |
| Event History backfill | `GET /v1/history/devices/{id}/events` → the same inbox and clip pipeline as webhooks | `ring_service.py` (`import_history`) |
| Smart Alerts subtypes | `sub_type` on motion webhooks: `vehicle` is counted as a vehicle, everything else is analyzed | `ring_worker.py`, `analytics.py` |
| Video encryption check | `e2e_encryption.enabled` in device configurations, read before any video processing | `ring_service.py` |
| Subscriptions | `GET /v1/accounts/me/subscriptions` | `ring_service.py` |

What we verified with real hardware:
- account linking,
- inventory,
- a snapshot,
- a 1280×720 live view,
- signed lifecycle webhooks,
- a motion event whose recording was analyzed into a 77-point path.

See `spatialguard/docs/verification.md`, `hosted-ring-link-verification.md` and `recorded-incident-movement.md`. How Pathlight meets Ring's Computer Vision Guidelines is in [ring-cv-guidelines.md](spatialguard/docs/ring-cv-guidelines.md).

## How AWS is used

| Service | Used for | Where |
|---|---|---|
| **Amazon Bedrock** — Converse API, Amazon Nova Pro (`us.amazon.nova-pro-v1:0`) | 1. The weekly site insight, from aggregate numbers only<br>2. Optional floor-plan vision: rooms and doors as JSON, validated by TwinForge before use<br>3. Optional cautious activity labels for opted-in snapshots | `spatialguard_api/insights.py`, `services/api/twinforge/vision_plan.py`, `spatialguard_api/classifier.py` |
| **Amazon SES** (v2 API via boto3) | Account verification, password-reset and alert email (Railway Hobby blocks SMTP) | `spatialguard_api/mail.py` |

Bedrock is called over HTTPS with a Bedrock API key (`AWS_BEARER_TOKEN_BEDROCK`) from the Railway-hosted server. If it isn't configured, each feature says so in the app rather than failing silently.

## Architecture

```text
 Ring Partner API ──webhooks / media──▶  Pathlight API + worker  ──HTTP SDK──▶  TwinForge engine
 (oauth.ring.com,                       (FastAPI, SQLite WAL,                  (floor-plan twin:
  api.amazonvision.com)                  YOLO11n via OpenCV)                    immutable revisions,
                                                │                               rooms, zones, cameras,
 Amazon Bedrock (Nova Pro) ◀──insight, labels───┤                               spatial queries,
 Amazon SES ◀──email────────────────────────────┤                               provenance)
                                                ▼
                                   React web app / Android (Capacitor)
                                   2D/3D map · heatmap · analytics · alerts
```

Pathlight never opens TwinForge's database; it uses TwinForge's public API and SDK, and a test enforces that boundary (`spatialguard/tests/test_architecture_boundary.py`). Ring-specific code lives only in Pathlight.

## Run it yourself

The **hosted app is the easiest way to evaluate**: see [JUDGES.md](JUDGES.md). To run locally:

### Option A — Docker (the path CI runs)

```sh
docker build -t pathlight .
docker run --rm --network host \
  -e SPATIALGUARD_ALLOWED_HOSTS=127.0.0.1:8010 \
  -e SPATIALGUARD_ORIGIN=http://127.0.0.1:8010 \
  -e PATHLIGHT_DEMO_ACCOUNTS=local \
  pathlight
```

Open http://127.0.0.1:8010. The local owner session opens automatically from `127.0.0.1`. Host networking keeps the request local, which is how CI runs it on Linux. Then load the demo café in a second terminal (standard library only):

```sh
python spatialguard/scripts/demo_cafe.py --local
```

In the app, open **Settings → Demo mode → Create two simulated weeks**. Then open **Home** (map and heatmap) and **Analytics**.

### Option B — Python and Node directly

Requires Python 3.11 and Node 22 (`.python-version`, `.nvmrc`).

```sh
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.lock
npm ci
npm run build --workspace spatialguard-web

export PYTHONPATH=services/api:packages/sdk-python:spatialguard/services/api   # PowerShell: $env:PYTHONPATH="services/api;packages/sdk-python;spatialguard/services/api"
export PATHLIGHT_DEMO_ACCOUNTS=local
python -m twinforge.cli init                       # creates .data/ and the engine credential
python -m uvicorn twinforge.api:create_app --factory --port 8000 &
python -m twinforge.worker &
python spatialguard/scripts/run.py                 # API :8010, Ring gateway :8011, worker
```

These are the same processes `spatialguard/scripts/container-start.sh` starts in the container.

### Optional configuration

Copy `.env.example` to `.env`, or set Railway Variables:

- `AWS_BEARER_TOKEN_BEDROCK` and `AWS_REGION`: weekly insight, floor-plan vision and activity labels.
- `RING_CLIENT_ID`, `RING_CLIENT_SECRET` and `RING_WEBHOOK_SECRET`: a Ring private app. Point its four URLs at `/ring/link`, `/ring/home`, `/ring/token` and `/ring/webhook`.
- `SPATIALGUARD_TOKEN_KEY`: a Fernet key that encrypts stored Ring tokens on Linux.
- `SPATIALGUARD_SES_*` / `SPATIALGUARD_SMTP_*`: email.

Hosted deployment details are in [`spatialguard/RAILWAY_DEPLOYMENT.md`](spatialguard/RAILWAY_DEPLOYMENT.md).

## Tests and CI

```sh
python -m pytest spatialguard/tests -q            # backend: Ring webhooks/media, analytics, heatmap, privacy, tenancy
npm run test --workspace spatialguard-web         # Playwright browser tests (needs the app on :8010)
```

The GitHub Actions workflow (`.github/workflows/spatialguard-ci.yml`) runs the backend tests, builds the Docker image and runs the browser suite against it. It also checks contract drift and builds the Android debug app. Finally, it runs `npm audit`, `pip-audit`, `bandit`, license collection and `gitleaks` across the full history.

## Repository map

| Path | What |
|---|---|
| `spatialguard/services/api/spatialguard_api/` | Pathlight API, worker, Ring integration, analytics, heatmap, alerts, insights |
| `spatialguard/apps/web/` | React app (web) and its Capacitor Android/iOS shells |
| `spatialguard/apps/expo-go/` | Expo Go mobile preview of the hosted app |
| `services/api/twinforge/` | TwinForge floor-plan twin engine (geometry, revisions, plan tracing) |
| `packages/` | Shared contracts, Python/TypeScript SDKs, 2D/3D view geometry |
| `spatialguard/tests/` | Backend tests |
| `spatialguard/docs/` | Verification records, Ring Appstore review notes, runbooks |
| `spatialguard/models/` | YOLO11n ONNX person detector (AGPL-3.0, see below) |

## Limits

- Positions are calibration-free estimates (see [position estimation](spatialguard/docs/position-estimation.md)). A wrong heading or range shifts a camera's positions consistently, so treat paths and heatmaps as directional.
- The detector follows one primary person per recording; it is not a multi-person identity tracker.
- Several physical Ring cameras are paired in the demo café. Any map camera without a Ring device is labelled **SIM**.
- Event History import is capped at the last 7 days and 40 events per camera. Ring decides which past recordings are still available, and a visit without a recording is counted with an estimated position.
- Cameras with Ring video encryption are counted but never analyzed, so they add no paths.
- The hosted preview uses SQLite on a mounted volume, with one replica.
- Ring Appstore certification has not been submitted yet. The draft reviewer notes are in `spatialguard/docs/ring-appstore-review.md`.

## License and credits

- **Code:** MIT ([LICENSE](LICENSE)).
- **`spatialguard/models/yolo11n.onnx`:** exported from Ultralytics YOLO11n and licensed **AGPL-3.0** (`spatialguard/models/YOLO-LICENSE.txt`), not MIT.
- **Fonts:** under their bundled licenses.
- **Demo café floor plan:** CC0 (OpenCAD Library).

Ring and Amazon are trademarks of Amazon.com, Inc. or its affiliates. Pathlight is an independent hackathon project and is not made or endorsed by Ring or Amazon.
