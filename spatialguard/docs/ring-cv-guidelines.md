# Pathlight and Ring's Computer Vision Guidelines

Ring published its [Computer Vision Guidelines](https://developer.amazon.com/docs/ring/computer-vision-guidelines.html) for partner apps on October 19, 2026. This page maps each guideline to what Pathlight does, with the code and tests that show it. Pathlight runs computer vision on Ring media in two places:

- **YOLO11n person detection** on recorded clips. It produces anonymous foot points on the floor plan.
- **Amazon Bedrock (Nova Pro)**, which writes the weekly note from aggregate numbers only. Optional snapshot labelling also uses Bedrock.

## Failure cases in Ring imagery

| Guideline | What Pathlight does | Where |
|---|---|---|
| **Small subjects, wide-angle lenses:** don't evaluate on tightly cropped images | The detector runs on the full Ring frame at native resolution. Positions come from the ground point (bottom-centre of the box), so it doesn't need a face or a large subject. Positions are labelled estimates, never measurements. | `person_tracking.py`, [position-estimation.md](position-estimation.md) |
| **Downward camera angle** | The floor position uses the camera's height-free bearing and a near/far distance curve from where the feet sit in the frame, not the person's proportions. | `heatmap.py` (`project_foot`) |
| **Night, IR and backlight:** don't rely on colour | Detection uses shape only and never colour. No colour, clothing or appearance attribute is stored or shown. | `person_tracking.py` |
| **VLM hallucination:** never treat VLM output as ground truth | Bedrock never sees images for the weekly note. Its text is checked against the data before it is shown (see guardrails below). Snapshot labels are marked as an AI interpretation that needs review. | `insights.py`, `ring_worker.py` |
| **Non-determinism** | Analytics, heatmaps and **Today's actions** are deterministic code. Only the weekly note comes from a model, and it has a deterministic fallback. | `analytics.py`, `actions.ts` |

## Guardrails on model output

| Guideline | What Pathlight does | Where |
|---|---|---|
| **Check every output** | Every weekly note is checked, not a sample. | `insights.check` |
| **Keyword block lists that can be updated without retraining** | A deterministic list of terms about identity, appearance, age, gender and accusations, such as "face", "women" and "suspicious". The model only ever sees counts, so any of these means it invented something about people. Operators extend the list with `PATHLIGHT_INSIGHT_BLOCKLIST` (comma-separated), with no code change. | `insights.BLOCKED_TERMS` |
| **Context validation** | Every figure in the note must come from the data: a count, a period-over-period change, a share of visits, or seconds quoted as minutes. When demo data is present, the note must say how many visits are simulated. | `insights.check` |
| **Defined fallback** | A note that fails a check is never shown. A plain note built only from the numbers replaces it, and the card says so ("Plain summary shown…"). A passing note shows "Checked: every figure matches your numbers". | `insights.fallback`, `AnalyticsView.tsx` |
| **Incident response** | Operators update the block list through a Railway variable, so it takes effect on the next deploy. [incident-response-runbook.md](incident-response-runbook.md) covers the rest. | |

## Platform behaviour

| Guideline | What Pathlight does | Where |
|---|---|---|
| **Watermark:** evaluate on watermarked imagery | Detection runs on the delivered (watermarked) clips. The snapshot-labelling prompt tells the model to ignore the provider watermark at the top edge. Clip requests don't ask for reduced resolution, so the fixed-size watermark covers as little of the frame as possible. | `classifier.py`, `ring_provider.py` (`clip`) |
| **TAKE and E2EE encryption:** degrade gracefully, don't retry or show an error | Each camera's `e2e_encryption.enabled` setting is read before any video processing, as Ring's FAQ Q13 asks. An encrypted camera's visits are still counted, but its recordings are never fetched, and Settings explains why. A recording that opens but has no decodable frame is marked **unreadable**, never "no person", so the visit isn't lost. | `ring_service.configuration_summary`, `incident_clip`, `tracks.py`, `person_tracking.RecordingUnreadable` |
| **Webhooks answer within 5 seconds; process asynchronously** | The webhook verifies the HMAC, writes a durable inbox row and returns. Clip download and detection run later in a background worker, which records acknowledgement time as a metric. | `ring_service.webhook`, `ring_worker.py`, `tracks.py` |
| **Motion subtypes:** read `sub_type`, default to unknown, skip only what's clearly irrelevant | Only `vehicle` is skipped for person analysis, and it is counted as a vehicle instead, never as a visit. Every other subtype, including unknown and `other_motion`, is analyzed. The subtype is kept in each visit's provenance. | `ring_worker.NOT_A_PERSON`, `analytics._vehicles` |
| **Fail safe at every stage** | Each stage has a defined default. A missing recording is retried on a widening schedule. An unauthorized or encrypted one is not retried, and the visit is kept. If the detector is down, it retries. If classification fails, the signed event is kept unlabelled. | `tracks.py`, `ring_worker.py` |
| **Privacy:** short retention, in-region, Permitted Content Policy | Each recording is written to scratch space only for detection, then deleted. Only foot points are kept. Foot-traffic analysis is a separate, off-by-default permission. Visits, paths and vehicle counts follow the owner's retention setting. The service is US-only. | `tracks.py`, `store.cleanup_retention`, [ring-appstore-review.md](ring-appstore-review.md) |

## Tests

- `spatialguard/tests/test_ring_history.py`:
  - encrypted cameras
  - undecodable recordings
  - vehicle subtypes
  - the insight guardrail and its fallback
  - the Event History import
- `spatialguard/tests/test_ring_connection.py`: webhook acknowledgement, retries, consent and authorization.
