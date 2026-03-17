# FireFly-Cloud — Claude Working Notes

## Project Overview

AWS SAM-based serverless backend for FireFly lighting controller firmware distribution. Python 3.13 on ARM64 Lambda. LocalStack (port 4566) for local development.

## Architecture

- **S3 private bucket** (`firefly-firmware`): firmware ZIPs move through `incoming/` → `processing/` → `processed/` or `errors/`
- **S3 public bucket** (`firefly-firmware-public`): released firmware binaries; `revoked/` prefix is access-denied via bucket policy, expires after 90 days via lifecycle
- **CloudFront**: fronts the public bucket at `firmware.somewhere.com` for device OTA delivery
- **DynamoDB** (`firefly-firmware`): firmware metadata, keyed on `pk` (`product_id#application`) + `version` (SK)
- **API Gateway** (HTTP): custom domain

## Lambda Functions

| Function | Trigger | Purpose |
|---|---|---|
| `func-s3-firmware-uploaded` | S3 `incoming/*.zip` | Validates manifest, computes SHA256, writes DynamoDB `PROCESSING` → `READY_TO_TEST` or `ERROR`, moves to `processed/` or `errors/` |
| `func-s3-firmware-deleted` | S3 delete on `processed/` or `errors/` | Marks non-RELEASED/REVOKED records `DELETED` with 10-day TTL |
| `func-api-health-get` | GET /health | 200 OK |
| `func-api-firmware-get` | GET /firmware, GET /firmware/{zip_name} | List/fetch firmware metadata |
| `func-api-firmware-status-patch` | PATCH /firmware/{zip_name}/status | Status transitions; RELEASED copies binaries to public bucket; REVOKED moves to `revoked/` prefix |
| `func-api-firmware-delete` | DELETE /firmware/{zip_name} | 409 if RELEASED (must REVOKE first) |
| `func-api-ota-get` | GET /ota/{product_id}/{application}?current_version={version} | Returns next sequential RELEASED version; `current_version` required |

## release_status State Machine

`PROCESSING` → `READY_TO_TEST` → `TESTING` → `RELEASED` → `REVOKED` → `DELETED`

`ERROR` is set by `func-s3-firmware-uploaded` on validation failure. `DELETED` is set by `func-s3-firmware-deleted`.

## Shared Utilities (`lambdas/shared/`)

- `app_config.py`: JSON config from AWS AppConfig Extension (port 2772)
- `logging_config.py`: structured JSON logging with per-function log levels from AppConfig
- `feature_flags.py`: boolean feature flag evaluation via AppConfig

## DynamoDB Schema

Fields: `pk`, `version`, `class`, `application`, `branch`, `commit`, `created`, `files`, `release_status`, `zip_name`, `ttl`

## Docs Repo

`/Users/brent/GitHub/FireFly/cloud/` — `.md` files and PlantUML diagrams in `/cloud/lambdas/images/`

---

## Git Workflow Rules

- **Never commit directly to `main`** — always create a feature branch first, even for hotfixes.
- **Before creating any new branch**, run `git checkout main && git pull`.

---

## Completed Work

| Date | Description |
|---|---|
| 2026-03-15 | OTA firmware delivery system: public S3 bucket, CloudFront, `func-api-ota-get`, status-patch S3 side effects, revocation flow |
| 2026-03-16 | Sequential OTA delivery + error tests: `current_version` required, next-version logic, 409 for revoked-latest, firmware upload error tests (5 scenarios), OTA sequencing tests, `CLEANUP_TEST_RECORDS` fixture, OTA docs corrections (SPIFFS→LittleFS, payload format, new `ota_update_flow.md`) |
| 2026-03-16 | Fix regression: allow manual S3 deletions to update ERROR records |

---

## Remaining To-Do Items

### esp32FOTA Library (BrentIO/esp32FOTA)

The FireFly-Cloud OTA sequential delivery is server-complete, but the device library needs two changes before end-to-end operation works:

1. **`use_current_version` config flag** — Add a boolean to `FOTAConfig_t` (in `src/esp32FOTA.hpp`) mirroring the `use_device_id` pattern. When enabled, append `?current_version=<major>.<minor>.<patch>` to the manifest URL in `execHTTPcheck()` (`src/esp32FOTA.cpp`). The version integers are already in `_cfg.sem`.

2. **409 Conflict handling** — Currently any non-200 response triggers `HTTP_ERROR`. The 409 (device running revoked firmware with no newer release) should surface a distinct error state on the device rather than a generic HTTP error.

**Reference:** `/Users/brent/GitHub/FireFly/cloud/ota_update_flow.md` — "Library Dependency" section.
