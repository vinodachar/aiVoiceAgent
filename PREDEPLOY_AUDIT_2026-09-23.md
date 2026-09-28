# Dograh predeployment audit — 23 September 2026

## Remediation update — 28 September 2026

The sections below this update preserve the original audit findings. Subsequent
remediation fixed the billing syntax error, initialized the pinned Pipecat
submodule, corrected failing test fixtures, added single-use authenticated media
connections and signed provider callbacks, made MinIO recordings private with
presigned access, and restricted database/cache host bindings to loopback.
Compatible dependency updates and Docker build fixes are included.

Validation completed on 26 September against the revised source:

- Backend: **1,514 passed**, 15 warnings, using disposable test services.
- Frontend: **18 tests passed**; production build passed.
- Fresh API Docker image built; isolated startup succeeded, health returned 200,
  unauthenticated workflow access returned 401, and `pip check` passed.
- Storage integration checks confirmed signed access works and anonymous
  GET/PUT/DELETE/LIST and altered-host signatures are rejected.
- Frontend production dependency audit after updates: no critical or high
  findings; 21 moderate and 4 low findings remained at the time of that scan.

**This is not yet a public-deployment approval.** Remaining dependency findings
need review, and the final deployment image still needs end-to-end telephony and
concurrency validation. Successful local calls used the existing running images,
not the rebuilt image. Local temporary Cloudflare tunnels failed repeatedly and
were restored by restarting the tunnel; AWS needs a stable HTTPS/WebSocket
callback address. Local agent configuration, credentials and call data live in
the database and are not included in this source repository.

## Original audit (historical)

**Verdict: NOT ready for public AWS deployment.** The existing Docker image runs, but this checkout has a startup syntax error, security issues, and incomplete/failed backend validation. This was a quick code and test audit, not a penetration test or certification of every feature.

## Validation performed

| Check | Result |
| --- | --- |
| Docker startup | API, UI, PostgreSQL, Redis and MinIO running and healthy |
| Live API health | `/api/v1/health` returned 200 |
| Unauthenticated workflow listing | `/api/v1/workflow/summary` returned 401 |
| Live UI | `/workflow/create` returned 200; agent creation form rendered |
| Python 3.13 syntax scan | 669 files scanned; billing route failed |
| Original checkout backend tests | 1,324 passed, 34 failed, 22 errors (including 20 collection errors) |
| Diagnostic copy backend tests | 1,377 passed, 8 failed, 17 collection errors |
| Frontend display-option tests | All 18 passed |
| Frontend production build | Passed compilation, lint/type checks and static generation; one React effect dependency warning |
| Frontend production dependency audit | 40 affected package entries: 1 critical, 8 high, 26 moderate, 5 low |
| Backend image dependency audit | Tool reported 17 advisory entries across 4 packages; report includes duplicate advisory IDs |
| Anonymous MinIO bucket listing | Returned 200 without credentials (max-keys=0; no recording content fetched) |
| Telephony authorization probe | Mocked database/provider confirmed unauthenticated endpoint accepts mismatched run/workflow IDs and updates call state |

Backend tests ran in disposable containers with a separate PostgreSQL database and Redis, without application API keys. They used the existing API image's installed Python/Pipecat dependencies, not a clean dependency installation from this checkout. The Pipecat submodule is uninitialized; its missing test helpers block collection. Therefore failures include dependency/test-harness mismatches and are not all proven product defects.

The second test run corrected only the disposable copy's billing syntax and installed the TypeScript test helper dependency. It does **not** mean the original checkout was repaired. No application source or customer data was changed by this audit. The existing modification to `api/routes/billing.py` was preserved.

## Deployment blockers

### 1. Public recording bucket permits anonymous modification — critical when exposed

`api/services/filesystem/minio.py:57–87` installs a wildcard-principal policy on every initialization, including GetObject, PutObject, DeleteObject and ListBucket. The development warning is not an environment restriction. Anonymous listing was also confirmed against the running local bucket.

`deploy/vps/Caddyfile:15` exposes `/voice-audio/*` through MinIO; the remote nginx template has a similar proxy. Deploying that combination publicly would allow unauthenticated recording discovery, reading, overwriting and deletion. The current local MinIO ports are loopback-bound; the public exposure concern applies to deployment.

Required: private storage, remove the anonymous policy, authenticated/signed downloads and uploads, and verify recording playback with those protections. Private S3 with an EC2 role is an AWS option, but its integration must be tested.

### 2. Telephony media connection lacks caller authentication and run binding — high

`api/routes/telephony.py:534` accepts WebSockets using numeric workflow/user/run IDs without a credential. The handler independently loads a run and workflow, and changes the run to RUNNING before invoking the provider. It does not verify their association there. A standalone mock demonstrated the state mutation and provider delegation with mismatched IDs; no live calls or records were affected.

`api/services/telephony/providers/vobiz/provider.py:349` accepts caller-supplied stream/call identifiers without verifying them against the expected call before starting the pipeline.

Required: short-lived, single-use authentication bound to the expected run/provider/call; validate workflow, organization and execution user against the run before accepting media or mutating state. Test both legitimate calls and unauthorized/replayed connections.

### 3. Vobiz answer callback lacks signature verification — high

`api/services/telephony/providers/vobiz/routes.py:55` accepts the answer webhook with caller-supplied workflow/user/run/organization parameters. Unlike the hangup/ring callbacks, this route does not invoke signature verification. Its organization context is caller supplied.

Required: validate the provider signature and derive tenant/workflow context from the stored run, rejecting mismatches.

### 4. Current source cannot start/build reproducibly — blocking

`api/routes/billing.py:208` contains a pasted URL after a function declaration, producing a Python SyntaxError. The existing running API uses a prebuilt image, so its health does not validate this source. The pinned Pipecat submodule is also missing (`afe5b6b6c90ad04557ad93b69f7f6ba662c2072e`).

Required: repair syntax, initialize the pinned submodule, install matching dependencies, then build and test the exact immutable image intended for AWS.

### 5. Known dependency vulnerabilities need remediation and retesting

`npm audit --omit=dev` flagged Next.js (installed 15.5.14) at critical severity, plus other high-severity packages. Advisory counts are registry findings, not proof every advisory is exploitable in this application. Backend image findings cover msgpack, nltk, python-multipart and transformers. The Python scan describes the existing image plus audit tools, not a fresh source build.

Required: review applicable advisories, upgrade to patched compatible versions, rebuild, and rerun security and regression checks. Do not blindly apply forced major upgrades.

## Remaining validation gaps

- The diagnostic backend run still fails campaign resume, managed STT/TTS correlation, caller-number pool expectations, two billing response assertions, and the Rumik service-factory expectation. These require triage against the pinned dependency environment. Pool tests compare suffixed concurrency-slot identifiers with bare numbers; their messages alone do not establish a cross-tenant leak.
- Seventeen modules cannot collect, primarily due to missing Pipecat test helpers. Audio pipeline coverage is therefore incomplete.
- Browser navigation was blocked by automatic approval review, which associated the action with an unrelated Instagram origin. Only the visible agent creation page was verified; no attempt was made to access that unrelated site.
- This audit made no new real PSTN call, billing transaction, provider purchase, or multi-tenant load test. Earlier successful phone calls do not certify a new AWS deployment.
- Verify tenant isolation, workflow editing/publishing, campaign scheduling/retries, two-way audio, interruption handling, hangup callbacks, recordings, billing, restart recovery and 1–2 simultaneous calls using the final deployment image.
- Root Compose publishes PostgreSQL and Redis on all host interfaces. AWS deployment must keep database/cache ports private and replace insecure example credentials in deployment templates.

## AWS pilot option after blockers are resolved

Use one EC2 `c7i-flex.large` (2 vCPU, 4 GiB) as an initial sizing candidate for 1–2 concurrent calls, with approximately 30 GB encrypted gp3 storage, Docker Compose, HTTPS reverse proxy, private database/cache networking and private recording storage. This is a sizing recommendation, not a measured concurrency guarantee. Build images before deploying; profile memory and audio latency under two simultaneous calls.

Avoid adding RDS, a load balancer or a NAT gateway for the initial small pilot. Use a stable domain and HTTPS/WebSocket endpoint for Vobiz; a temporary local tunnel is not a production endpoint. Configure cost alerts, limited log/recording retention and backups. A single instance has downtime during failure or maintenance and is not yet a multi-business production architecture.

AWS lists c7i-flex.large among Free plan eligible instance types. Eligibility means credits can cover eligible usage; it does not mean unlimited free runtime. New accounts receive $100 in credits, with opportunities to earn more. The Free account plan ends after six months or credit exhaustion, whichever occurs first; AWS says the account closes automatically when that plan expires. A Paid account plan can incur charges beyond credits. Confirm the account's plan, remaining credit, region and console cost estimate before provisioning. Storage, public IPv4, transfer and logs must be included in the estimate. Gemini and Vobiz charges are separate from AWS credits.

Sources: [AWS compute eligibility](https://aws.amazon.com/free/compute/), [AWS plan terms](https://docs.aws.amazon.com/en_en/awsaccountbilling/latest/aboutv2/free-tier-plans.html).

Use a locally configured AWS profile or temporary authenticated session for deployment; do not paste secret access keys into chat. Nothing was deployed to AWS during this audit.

## Evidence location

Raw local evidence is under `/private/tmp/dograh-audit-20260923/`: `backend-tests.xml`, `backend-tests-adjusted.xml`, corresponding logs, `npm-audit.json`, `pip-audit.json`, `ui-build-network.log`, `ui-tests.log`, and `security-probe.log`. Raw test logs may contain local paths and test fixture details; review before sharing. Disposable audit containers are removed after completion; application containers remain running.
