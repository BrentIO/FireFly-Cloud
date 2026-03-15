# FireFly Cloud

Serverless AWS backend for managing Arduino firmware lifecycle. Handles firmware uploads, validation, status progression, and deletion via an HTTP API backed by Lambda, DynamoDB, and S3.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        API Gateway                          │
│              (HTTP API v2 + custom domain)                  │
└──────┬──────────┬──────────────┬────────────────────────────┘
       │          │              │
  GET /firmware  PATCH …/status  DELETE …
       │          │              │
       ▼          ▼              ▼
  func-api-  func-api-      func-api-
  firmware-  firmware-      firmware-
    get      status-patch    delete
       │          │              │
       └──────────┴──────┬───────┘
                         │
                    DynamoDB Table
                  (firefly-firmware)

S3 Bucket (firmware)
  incoming/*.zip  ──►  func-s3-firmware-uploaded  ──►  DynamoDB (READY_TO_TEST)
                            └──► processed/*.zip
  processed/*.zip (deleted) ──►  func-s3-firmware-deleted  ──►  DynamoDB (DELETED/REVOKED)
```

### CloudFormation Stacks

| Stack | Template | Description |
|---|---|---|
| `firefly-acm-api-gateway` | `templates/acm-api-gateway.yaml` | ACM certificate for API custom domain |
| `firefly-api-gateway` | `templates/api-gateway.yaml` | HTTP API Gateway v2 with custom domain and access logs |
| `firefly-dynamodb-firmware` | `templates/dynamodb-firmware.yaml` | DynamoDB firmware table with GSIs and TTL |
| `firefly-s3-firmware` | `templates/s3-firmware.yaml` | S3 firmware bucket with lifecycle rules and S3 event triggers |
| `firefly-shared-layer` | `lambdas/shared/template.yaml` | Shared Python layer (logging, AppConfig, feature flags) |
| `firefly-func-api-health-get` | `lambdas/func-api-health-get/template.yaml` | `GET /health` |
| `firefly-func-api-firmware-get` | `lambdas/func-api-firmware-get/template.yaml` | `GET /firmware`, `GET /firmware/{zip_name}` |
| `firefly-func-api-firmware-status-patch` | `lambdas/func-api-firmware-status-patch/template.yaml` | `PATCH /firmware/{zip_name}/status` |
| `firefly-func-api-firmware-delete` | `lambdas/func-api-firmware-delete/template.yaml` | `DELETE /firmware/{zip_name}` |
| `firefly-func-s3-firmware-uploaded` | `lambdas/func-s3-firmware-uploaded/template.yaml` | S3 upload event handler |
| `firefly-func-s3-firmware-deleted` | `lambdas/func-s3-firmware-deleted/template.yaml` | S3 delete event handler |

---

## API Reference

Full OpenAPI 3.0 specification: [`docs/openapi.yaml`](docs/openapi.yaml)

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/firmware` | List firmware records (filterable by `product_id`, `application`, `version`) |
| `GET` | `/firmware/{zip_name}` | Get a single firmware record including file manifest |
| `PATCH` | `/firmware/{zip_name}/status` | Transition firmware through the release state machine |
| `DELETE` | `/firmware/{zip_name}` | Delete firmware and initiate async DynamoDB status update |

---

## Firmware Lifecycle

### Upload Flow

1. Upload a ZIP to `s3://[bucket]/incoming/[filename].zip`
2. `func-s3-firmware-uploaded` is triggered automatically
3. The Lambda assigns a UUID (becomes the `zip_name`), validates `manifest.json`, verifies file SHA256 checksums, and moves the file to `processed/`
4. A DynamoDB record is created with `release_status: READY_TO_TEST`
5. On validation failure the file moves to `errors/` and an ERROR record is written

### manifest.json Format

The ZIP must contain a `manifest.json` at the root with the following fields:

```json
{
  "product_id": "firefly-controller-v2",
  "version": "2026.03.001",
  "class": "CONTROLLER",
  "application": "main",
  "branch": "main",
  "commit": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
  "created": "2026-03-15T00:00:00Z",
  "files": [
    { "name": "firmware.bin", "sha256": "<64-char hex>" }
  ]
}
```

All files listed in `files` must be present in the ZIP with matching SHA256 checksums.

### Status State Machine

```
READY_TO_TEST → TESTING → RELEASED → REVOKED
```

Use `PATCH /firmware/{zip_name}/status` with body `{"release_status": "<new_status>"}` to advance state. Skipping states is not permitted (returns 422).

Deleting firmware via `DELETE /firmware/{zip_name}` removes the S3 file and asynchronously sets the status to `DELETED` (or `REVOKED` if previously `RELEASED`). Items in `DELETED` or `REVOKED` state cannot be deleted again (returns 409).

### S3 Lifecycle Rules

| Prefix | Retention |
|---|---|
| `incoming/` | 1 day |
| `processing/` | 1 day |
| `errors/` | 7 days |
| `processed/` | 30 days |

---

## DynamoDB Schema

**Table:** configurable via `DYNAMODB_FIRMWARE_TABLE_NAME` GitHub variable (e.g., `firefly-firmware-dev`)
**Billing:** On-demand
**Deletion Protection:** Enabled

| Key | Type | Description |
|---|---|---|
| `pk` *(partition key)* | String | `{product_id}#{application}` — internal composite key, excluded from API responses |
| `version` *(sort key)* | String | Firmware version string (e.g., `2026.03.001`); error records use `ERROR#{version}#{uuid}` |

**Global Secondary Indexes:**

| Index | Partition Key | Use Case |
|---|---|---|
| `product_id-index` | `product_id` | Filter list by product |
| `zip_name-index` | `zip_name` | Single-item lookups by UUID filename |

**Notable Attributes:**

| Attribute | Description |
|---|---|
| `zip_name` | UUID filename (e.g., `550e8400-e29b-41d4-a716-446655440000.zip`) — primary identifier for API paths |
| `release_status` | `PROCESSING`, `READY_TO_TEST`, `TESTING`, `RELEASED`, `REVOKED`, `DELETED`, `ERROR` |
| `files` | Array of `{name, sha256}` — only returned by single-item GET |
| `ttl` | Unix timestamp for automatic DynamoDB cleanup (set on DELETED/REVOKED records) |

---

## Deployment

### Prerequisites

1. An AWS account with:
   - An S3 bucket for SAM deployment artifacts (e.g., `com.p5software.firefly-deployments`)
   - An ACM certificate for the API custom domain
   - A Route53 hosted zone for the domain
   - Two IAM entities:
     - **GitHub Actions IAM user** with `firefly-github-actions-cloudformation-access-policy` attached
     - **CloudFormation execution role** (`firefly-cloudformation-execution-role`) with `firefly-cloudformation-execution-policy` attached
   - IAM policies in `policies/` document the required permissions

2. GitHub repository with two environments configured: `dev` and `production`

### GitHub Secrets and Variables

Configure these on each GitHub environment (`dev`, `production`):

**Secrets:**

| Name | Description |
|---|---|
| `AWS_ACCESS_KEY_ID` | GitHub Actions IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | GitHub Actions IAM user secret key |
| `AWS_ACCOUNT_ID` | AWS account ID |
| `AWS_REGION` | AWS region (e.g., `us-east-1`) |
| `SAM_DEPLOYMENT_BUCKET_NAME` | S3 bucket for SAM deployment artifacts |
| `S3_FIRMWARE_BUCKET_NAME` | S3 bucket for firmware ZIPs |

**Variables:**

| Name | Description |
|---|---|
| `CLOUD_FORMATION_EXECUTION_ROLE_NAME` | Name of the CloudFormation execution role |
| `DYNAMODB_FIRMWARE_TABLE_NAME` | DynamoDB table name (e.g., `firefly-firmware-dev`) |

### Deploying

Trigger the **Deploy All** workflow manually from GitHub Actions:

```
Actions → 🚀 🚀 Deploy All → Run workflow → select environment
```

Stacks deploy in dependency order automatically. Individual stacks can also be deployed independently using their own workflows.

### Deleting

```
Actions → 🗑️ Delete All → Run workflow → select environment
```

> **Note:** DynamoDB deletion protection is enabled. You must manually disable it in the AWS Console before `delete-all` can remove the `firefly-dynamodb-firmware` stack.

---

## Shared Lambda Layer

All firmware functions (except `func-api-health-get`) use `firefly-shared-layer`, a Python layer located at `lambdas/shared/python/shared/`:

| Module | Description |
|---|---|
| `logging_config.py` | Configures JSON structured logging; log level driven by AppConfig |
| `app_config.py` | Fetches configuration from AWS AppConfig via the Lambda extension |
| `feature_flags.py` | Evaluates feature flags from AppConfig |

---

## Local Development

A LocalStack configuration for local testing is available in `.aws-local/`:

```bash
cd .aws-local
docker-compose up
```

Lambda functions read `S3_ENDPOINT` and `DYNAMODB_ENDPOINT` environment variables. These are set in `.vscode/launch.json` for VS Code debugging sessions.

---

## Testing

Integration tests live in `tests/integration/` and run against a deployed environment.

### Setup

```bash
pip install -r tests/requirements.txt
```

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `FIREFLY_API_URL` | No | API base URL (default: `https://api.p5software.com`) |
| `FIREFLY_FIRMWARE_BUCKET` | For upload tests | S3 firmware bucket name |

AWS credentials must be available via the standard boto3 credential chain.

### Running Tests

```bash
# All tests
pytest tests/integration/ -v

# Skip tests that require S3 upload (no AWS credentials needed)
pytest tests/integration/ -v -k "not (firmware_item or fresh_firmware_item)"
```

Tests that upload firmware wait up to 60 seconds for the S3 event to propagate and the record to appear in the API before proceeding.
