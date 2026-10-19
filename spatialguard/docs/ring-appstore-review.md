# Ring Appstore review: build settings, reviewer notes and listing text

**Prepared:** October 1, 2026 · **Product:** Pathlight · **Hosted at:** https://spatialguard-production.up.railway.app

This page is the practical companion to `10-10-ring-appstore-and-hackathon-checklist.md`.
It covers what the code now does for review, the Railway settings for the build Ring
reviews, ready-to-paste reviewer notes, draft listing text, and the steps only the owner
can take in the Ring Developer Portal.

## What the review build does

| Ring rule | How Pathlight meets it |
|---|---|
| Content Policy 1.2.4: no collecting, mapping or deriving personal data about people on video without explicit consent | Visitor paths are only made after the owner turns on the separate, off-by-default **Foot-traffic analysis** permission (Settings → Privacy, and onboarding). It needs Ring access first, explains what is detected, and asks the owner to tell visitors that cameras are in use. Without it, no recording is downloaded for analysis. Paths are anonymous floor points: no faces, no identity, no link between visits, places or accounts. |
| Content Policy 1.2.3: no tracking individuals across customers or locations | Every visit is scoped to one owner and one place. Nothing is compiled across Ring customers. |
| Content Policy 4.1: privacy policy discloses data, uses, third parties, retention, deletion, consent withdrawal | `/privacy`, `/terms` and `/data-deletion` were rewritten on October 1, 2026 to match the code: foot-traffic analysis, recordings deleted after analysis, Amazon Bedrock as the only AI processor, no AI training, retention periods and every deletion path. |
| Content Policy 4.1.3: deletion of all stored Ring data | Deleting a visit, a place or the account removes visits, visitor paths, analytics, alerts and insights. Retention cleanup removes expired visits and their paths. |
| Program Requirement 2.4: no monitoring of Amazon's products or services | Pathlight shows owners the health of their own cameras (current status, 7-day history, offline emails), the same owner-facing use as the certified Cam Uptime Alerts app. It does not measure or report on Ring's service. The certification profile can still turn these off (`SPATIALGUARD_RELEASE_PROFILE=certification`). |
| Program Requirement 6: territory | United States only. |
| Single AI provider | OpenAI has been removed. Amazon Bedrock (Nova Pro) writes the weekly insight from aggregate numbers only, labels snapshots only with the separate "Activity labels" permission, and reads printed floor-plan labels only when the owner chooses it during import. |

## Railway settings for the review build

| Setting | Value | Why |
|---|---|---|
| `AWS_BEARER_TOKEN_BEDROCK` | your Bedrock API key | **Missing on Railway today**: the weekly insight shows "AI insights aren't set up on this server". All AI features now use it. |
| `AWS_REGION` | `us-west-2` | Bedrock region. |
| `PATHLIGHT_DEMO_ACCOUNTS` | empty, or your own account only | Never include the account you give Ring reviewers: demo mode adds simulated customers. |
| `SPATIALGUARD_FEATURE_CLASSIFICATION` | unset (on) or `false` | Activity labels send snapshots to Bedrock. Turning it off is the lower-risk first submission until Ring confirms Bedrock processing in writing. Visitor-path movement no longer depends on this flag. |
| `OPENAI_API_KEY`, `TWINFORGE_VISION_MODEL`, `SPATIALGUARD_CLASSIFIER_MODEL` | delete | No longer read. |

## Reviewer notes (paste into the portal; each field takes 20–4000 characters)

**Account creation**

> Open https://spatialguard-production.up.railway.app and choose "Create account". Enter any email you can read and a password of at least 8 characters, then confirm the email from the verification message. A short onboarding asks which permissions to grant: turn on "Ring cameras" and "Foot-traffic analysis" to test the full experience ("Activity labels" is optional). You can change these later in Settings → Privacy. To try the product without a Ring account first, choose "Try the demo home", which loads sample data clearly labelled "Demo".

**Ring account linking**

> Linking starts from the Ring Appstore. Sign in to Pathlight first in the same browser. Open the Pathlight listing in the Ring Appstore (Pathlight's Settings → Ring cameras → "Open Ring Appstore" links there) and choose Sign in. Ring sends you to Pathlight's linking page, which confirms the signed-in Pathlight account and links it; Pathlight never sees the Ring password. If you start the Ring flow on another device, choose "Create Ring sign-in code" in Pathlight and enter that one-time code on the linking page instead. The page shows "Ring account connected", and Settings → Ring cameras lists the authorized cameras ("Refresh Ring cameras" reloads them). On the floor-plan map, select a camera and choose "Pair" to assign a Ring device. To revoke access, choose "Disconnect Ring" or remove Pathlight in Ring's My Apps; Pathlight then stops all Ring processing.

**End-to-end test scenario**

> 1. Sign in, then upload a floor plan (Settings → Places & floor plans) or load the demo home. 2. Pair a Ring camera with a camera on the map. 3. Walk in front of that camera. Within about a minute a new visit appears in Activity, the camera pulses on the map, and, with Foot-traffic analysis on, the detected path appears on the floor plan; the recording is deleted after analysis. 4. Open the visit to replay the Ring clip beside the map. 5. Turn on the people heatmap (people button on the map). 6. Open Analytics for visits per hour, busiest zones, time spent and week-over-week, plus the weekly AI insight written by Amazon Bedrock from aggregate numbers. 7. Queue alerts appear when a zone named like "Counter" passes its limit. 8. Settings → Privacy shows each permission; Delete account removes all data after disconnecting Ring.

## Draft listing text (check lengths in the portal)

- **Name:** Pathlight
- **Short description (≤125):** Turn the Ring cameras you already own into foot-traffic analytics for your shop, café or office.
- **Detailed description (≤500):** Pathlight maps Ring camera events onto your floor plan. See where visitors go, which areas are busiest, when the rush starts, and how long people stay, with a heatmap, week-over-week analytics, queue alerts at the counter, and a weekly plain-English insight from Amazon Bedrock. Pathlight never recognises faces or identifies people: it keeps anonymous positions and deletes each recording after analysis. Works in any web browser.
- **Features (≤400):** Floor-plan map in 2D and 3D · Visitor heatmap · Site analytics: visits per hour, busiest and quietest zones, time spent, entrances, week over week · Queue and crowding alerts · Visit replay with the Ring clip · Weekly AI insight (aggregate numbers only) · Multi-place ready · Export and full data deletion.
- **Requirements (≤500):** A Ring video doorbell or camera with motion events and a Ring plan that saves recordings (needed for foot-traffic paths). A floor plan image of your space (or use the built-in demo). A modern web browser on desktop or phone. United States only.

## Steps only the owner can take

1. Set the Railway variables above and redeploy. Then check `/v1/sites/{id}/analytics/insight` writes an insight.
2. Create a **Public App** in the Ring Developer Portal (the current app is private), with production and staging HTTPS endpoints, and test linking with both.
3. Ask Ring in writing to confirm the foot-traffic use case under Content Policy 1.2.4 (owner opt-in, anonymous floor points, recordings deleted after analysis, visitor notice), and that sending opted-in snapshots to Amazon Bedrock is acceptable. Record the answers.
4. Complete the five Privacy & Legal Questionnaire tabs so they match this build: data processing (person detection on recordings, recordings deleted), AI governance (Bedrock, no training), third parties (Railway, Amazon Bedrock, Ring).
5. Have counsel review the privacy policy and terms before public launch.
6. Prepare the listing images (1024×1024 icon and up to 5 screenshots, each under 2 MB) and paste the reviewer notes above.
