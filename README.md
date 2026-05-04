# Face Detector For Office Access Control

This repository is a practical starter architecture for a face-recognition
access-control system in a small company. The target scenario is realistic:
fewer than 100 employees, one or a few entrance gates, one small server-side
environment managed either with Docker Compose or EKS, and one or more local
edge devices near the cameras.

## Deployment Model

- `edge-client/`: kiosk-side application at the entrance. This is the real
  user-facing interface for the security guard or employee.
- `backend/`: FastAPI APIs, business logic, recognition pipeline, and service
  integration for SQL, object storage, vector search, and background jobs.
- `frontend-admin/`: admin panel for employee enrollment, threshold tuning,
  role management, and audit review. It is served at `/admin/`.
- `nginx/`: reverse proxy that exposes `/admin/` and `/api/`.
- `docker-compose.yml`: base stack contract shared by all environments.
- `docker-compose.dev.yml`: local development override (builds images and brings db, redis, minio).
- `docker-compose.ci.yml`: CI override (uses prebuilt images and CI-specific runtime flags).
- `docker-compose.edge.yml`: edge-device stack.
- `deploy/`: Helm chart plus ArgoCD applications for GitOps deployments.
- `terraform/`: AWS bootstrap, EKS, and SSM state management.

## Why This Architecture Is Practical

For a company with fewer than 100 employees, you usually do not need a large
platform footprint. The real challenges are:

- stable camera input
- accurate face detection and cropping
- consistent embedding and matching
- reliable audit logging
- backup and recoverability

A single small local environment is often enough for:

- backend API
- worker
- Postgres
- MinIO
- Redis
- nginx

For AWS staging and production, the practical target is different:

- EKS runs only stateless workloads such as `backend`, `worker`, `frontend-admin`, and `nginx`
- PostgreSQL lives outside the cluster
- Redis or Valkey lives outside the cluster
- Amazon S3 is the primary object store
- autoscaling happens on stateless pods, not on data stores inside Kubernetes

## Runtime Topology

### Server side

- `nginx` listens on port `80`
- `/admin/` routes to `frontend-admin`
- `/api/` routes to `backend`
- `backend` talks to external PostgreSQL, external Redis or Valkey, and S3
- `worker` consumes async jobs from external Redis or Valkey and can scale independently from the API

### Edge side

- `edge-client` reads frames from the local camera
- faces are detected and cropped before upload
- crops are sent to `POST /api/vision/recognize`
- the kiosk UI confirms pass, fail, or retry

## Camera And Event Flow

- camera and raw video stay on the edge device in the current design
- the edge client detects faces locally and uploads only cropped JPEG payloads to the backend over HTTP
- `Redis` and `Celery` are the current async event mechanism for background work such as re-indexing or batch jobs
- there is intentionally no centralized video streaming pipeline or Kafka event bus yet, because the current workload does not need multi-consumer replayable event streams
- revisit centralized streaming only when many cameras, centralized live monitoring, or multiple downstream event consumers justify the extra platform cost

## Current Structure

```text
project-root/
|-- .github/
|   `-- workflows/
|       |-- ci.yml
|       |-- gitops-staging.yml
|       |-- gitops-production.yml
|       |-- app-cd.yml
|       `-- infrastructure.yml
|-- backend/
|-- frontend-admin/
|-- edge-client/
|-- nginx/
|-- docker-compose.yml
|-- docker-compose.dev.yml
|-- docker-compose.ci.yml
|-- docker-compose.edge.yml
|-- .env.example
|-- deploy/runtime/
|   |-- backend.staging.env.example
|   `-- backend.production.env.example
|-- edge-client/
|   `-- .env.example
`-- README.md
```

## URL Layout

- `http://your-server-domain/admin/`: admin frontend
- `http://your-server-domain/api/health`: backend health
- `edge-client`: entrance kiosk flow

## API Contract And E2E Smoke Test

- API request and response contracts now live in `docs/api-contract.yml` as the source-of-truth contract file.
- Local or CI compose-backed smoke test lives in `scripts/ci-e2e-test.sh`.
- HTTP smoke assertions run in `backend/tests/e2e/`, while the shell script is responsible for infra bring-up, Alembic migration, and service readiness checks.
- Unit and service-level integration tests stay under `backend/tests/` and are executed by default with `pytest`.

## Run With Docker

### Server stack

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

This starts:

- `backend`
- `worker`
- `frontend-admin`
- `nginx`
- `db`
- `minio`
- `redis`

### Edge stack

```bash
docker compose -f docker-compose.edge.yml up -d --build
```

This starts:

- `edge-client`

This repo now supports an AWS EKS deployment flow driven by Terraform, Helm, and ArgoCD.

## AWS cloud deployment guidance

The current preferred runtime model is:

- `Terraform` to create and destroy AWS infrastructure on demand
- `Amazon EKS` for the Kubernetes control plane and worker nodes
- `GitHub Container Registry (GHCR)` as the single image registry for backend, frontend-admin, and edge images
- `Helm` for packaging the application stack
- `ArgoCD` for continuous reconciliation inside the cluster
- `AWS SSM Parameter Store` for application environment values
- `AWS S3` for archived snapshots and backups

The repository keeps the application state in Git and the runtime secrets in SSM, while GitHub Actions bridges the two.

## Staging and Production Shape

| Component | Staging | Production |
| --- | --- | --- |
| Compute | EKS, typically 1-2 nodes with reactive headroom | EKS |
| API | HPA, typically 1 -> 3 pods | HPA, typically 2 -> 20 pods |
| Worker | KEDA, typically 1 -> 3 pods | KEDA, production envelope |
| Database | small RDS PostgreSQL | RDS PostgreSQL Multi-AZ |
| Queue | external Redis or Valkey | external Redis or Valkey with HA |
| Storage | S3 | S3 |
| Edge AI | fake or replayed data | real edge devices |
| Complexity | production-like behavior at low scale | higher |

This repository currently keeps staging and production on the same GitOps + EKS toolchain so promotion, ArgoCD, and runtime secrets behave the same. If you later collapse staging to ECS or EC2, keep the same external `DATABASE_URL`, `REDIS_URL`, and `AWS_S3_BUCKET` contract.

## Cost-saving workflow

The recommended student/lab workflow is:

1. run `Infrastructure Management` with `environment=staging` or `environment=production` to create the target VPC, EKS cluster, S3 bucket, and ArgoCD
2. keep working normally with trunk-based CI on pull requests and merges to `main` or `master`
3. let `GitOps Staging Promotion` write the successful CI commit SHA into `deploy/helm/face-detector/values-staging.yaml`
4. create a GitHub Release when you want production promotion, and let `GitOps Production Promotion` write the release commit SHA into `deploy/helm/face-detector/values-production.yaml`
5. run `ArgoCD Bootstrap` whenever a cluster is recreated or brought back online so SSM values, runtime secrets, and the correct environment-specific ArgoCD Application are seeded into that cluster
6. run `Infrastructure Management` with `destroy` when you are done for the day

This keeps the expensive EKS environment disposable without forcing stateful data stores back into the cluster. That is a lab cost-control choice, not the application elasticity model: while a cluster is running, scaling should be reactive through HPA, KEDA, and cluster-autoscaler rather than driven by a business-hours schedule.

## Terraform layout

- `terraform/bootstrap`: one-time remote-state bootstrap for the S3 state bucket and DynamoDB lock table
- `terraform/eks`: EKS, VPC, private data subnets, managed PostgreSQL, managed Redis, S3 snapshot bucket, namespaces, ArgoCD, metrics-server, KEDA, and cluster-autoscaler defaults for both staging and production
- `terraform/ssm`: sync backend runtime env files into `/facedetector/<environment>/...`

> The `terraform/eks` and `terraform/ssm` modules are configured for an S3 remote backend. Create the backend bucket and lock table once with `terraform/bootstrap`, then use those names as `TF_STATE_BUCKET` and `TF_STATE_LOCK_TABLE` in GitHub secrets.

## GitHub Actions flow

Required GitHub secrets for the new flow:

- `AWS_REGION` (optional; defaults to `ap-southeast-1`)
- `TF_STATE_BUCKET`
- `TF_STATE_LOCK_TABLE`
- `TF_STATE_REGION` (optional; defaults to `AWS_REGION`, but set it explicitly when the Terraform state bucket lives in another region)
- `STAGING_BACKEND_ENV_FILE` (optional but recommended; multiline backend runtime env file for staging)
- `PRODUCTION_BACKEND_ENV_FILE` (optional but recommended; multiline backend runtime env file for production)
- `SANDBOX_BACKEND_ENV_FILE` (optional; when unset, sandbox workflows reuse the staging runtime contract)
- `ARGOCD_REPO_USERNAME` (optional; needed when the GitHub repository is private)
- `ARGOCD_REPO_TOKEN` (optional; needed when the GitHub repository is private)
- `GHCR_USERNAME` (optional; needed only when GHCR images are private)
- `GHCR_TOKEN` (optional; needed only when GHCR images are private)

Required GitHub secrets for GitHub OIDC role assumption:

- `AWS_ROLE_SANDBOX_ARN` preferred. A repository variable fallback still works during migration, but the sensitive ARN should move to a secret.
- `AWS_ROLE_STAGING_ARN` preferred. A repository variable fallback still works during migration, but the sensitive ARN should move to a secret.
- `AWS_ROLE_PRODUCTION_ARN` preferred. A repository variable fallback still works during migration, but the sensitive ARN should move to a secret.

If `STAGING_BACKEND_ENV_FILE` or `PRODUCTION_BACKEND_ENV_FILE` is not set, `ArgoCD Bootstrap` falls back to the committed template under `deploy/runtime/`. For real staging or production deployments, prefer the secret-backed env file so runtime values do not live in Git.

When `SANDBOX_BACKEND_ENV_FILE` is not set, sandbox plan/apply/bootstrap runs fall back to the staging runtime contract and then rewrite infrastructure endpoints from the sandbox Terraform outputs.

After you finish the GitHub OIDC migration, delete the legacy `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` secrets. The infrastructure workflows no longer use IAM user credentials.

Terraform state does not have to live in the same region as the deployed infrastructure. When the backend bucket and lock table are in a different region, set `TF_STATE_REGION` so workflow `terraform init` can reach the correct S3 and DynamoDB backend while `AWS_REGION` still points at the target workload region.

`Infrastructure Management` now reads `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `REDIS_PASSWORD` from that same environment contract so the managed RDS and Redis resources use the same credentials as the application.

The backend runtime templates in `deploy/runtime/` are also the canonical copy-paste starting point for `STAGING_BACKEND_ENV_FILE` and `PRODUCTION_BACKEND_ENV_FILE`.

Recommended repository variables for the two-cluster setup:

- `STAGING_EKS_CLUSTER_NAME` (optional; defaults to `face-detector-staging`)
- `PRODUCTION_EKS_CLUSTER_NAME` (optional; defaults to `face-detector-production`)
- `SANDBOX_EKS_CLUSTER_PREFIX` (optional; defaults to `face-detector-sbx`, and sandbox cluster names are derived from the PR number)
- `STAGING_SNAPSHOT_BUCKET_NAME` (optional; defaults to `face-detector-employee-images-staging`)
- `PRODUCTION_SNAPSHOT_BUCKET_NAME` (optional; defaults to `face-detector-employee-images-production`)
- `SANDBOX_SNAPSHOT_BUCKET_PREFIX` (optional; defaults to `face-detector-sbx`)
- `STAGING_NODE_INSTANCE_TYPE`, `STAGING_NODE_MIN_SIZE`, `STAGING_NODE_MAX_SIZE`, `STAGING_NODE_DESIRED_SIZE` (optional; default to a small reactive-scaling staging envelope with 1 desired node and up to 2 nodes)
- `PRODUCTION_NODE_INSTANCE_TYPE`, `PRODUCTION_NODE_MIN_SIZE`, `PRODUCTION_NODE_MAX_SIZE`, `PRODUCTION_NODE_DESIRED_SIZE` (optional; default to a larger production node group envelope)
- `SANDBOX_NODE_INSTANCE_TYPE`, `SANDBOX_NODE_MIN_SIZE`, `SANDBOX_NODE_MAX_SIZE`, `SANDBOX_NODE_DESIRED_SIZE` (optional; default to a staging-sized sandbox envelope)
- `SSM_KMS_KEY_ID` (optional; customer-managed KMS key for SSM `SecureString` parameters)

OIDC trust policy templates for the three GitHub roles live under `aws/`, and the full setup checklist is documented in `aws/github-oidc-setup.md`.

The enterprise trust model in this repository is default-branch anchored. Today the repository default branch is still `master`, so the strict reusable workflow references and AWS `job_workflow_ref` strings use `@refs/heads/master`. If you later rename the default branch to `main`, update those pins and trust strings together.

The active workflows are:

- `CI Pipeline`: trunk-based validation on pull requests and pushes to `main` or `master`, plus GHCR image publish on push
- `Terraform PR Plan`: a `pull_request_target` parent on `main` or `master` that calls a reusable child workflow, resolves an exact PR sandbox identity, assumes `Role-Sandbox` through GitHub OIDC, and comments EKS plus SSM plan output back onto the PR
- `GitOps Staging Promotion`: after `CI Pipeline` succeeds on `main` or `master`, commits the exact immutable image SHA into `values-staging.yaml`
- `GitOps Production Promotion`: when a GitHub Release is published, resolves the release commit SHA and commits it into `values-production.yaml`
- `Sandbox Auto Apply`: the developer-facing `pull_request_target` parent that gates on draft state, deploy label, and quota before calling the reusable infrastructure and bootstrap workflows from the default branch
- `Sandbox Auto Destroy`: the developer-facing `pull_request_target` parent that tears down `sandbox-active` PR sandboxes on close, convert-to-draft, or final deploy-label removal
- `Sandbox Janitor`: TTL and nightly cleanup for `sandbox-active` PR sandboxes using the same reusable infrastructure destroy workflow
- `Sandbox DevOps Verify`: the privileged manual-dispatch lane for `devops/*` branches; the parent workflow can evolve on `devops/*`, but it calls the child infrastructure and bootstrap workflows pinned to the default branch so the AWS trust decision stays anchored on the approved workflow definition
- `ArgoCD Bootstrap`: reusable bootstrap workflow plus manual rescue entry point for shared environments and sandbox admin recovery
- `Infrastructure Management`: reusable infrastructure workflow plus manual rescue entry point for sandbox, staging, and production

The promotion workflows commit with `[skip ci]` so GitOps config updates do not trigger an infinite CI rebuild loop.

There is intentionally no automatic per-PR application preview environment in this setup. The infrastructure sandbox is now an exact-state-per-PR environment with cost gates and janitor cleanup, but it remains tightly controlled because EKS and RDS are expensive.

For the trust boundary, keep the sandbox AWS role limited to `main`, `master`, and `devops/*` trusted refs. Protect `devops/*` with GitHub branch rules, and require DevOps approval for `.github/workflows/*` and `aws/github-oidc-*` through `CODEOWNERS` once you have more than one maintainer. If you want AWS to validate the exact reusable workflow path, not just the trusted ref, you must customize GitHub's OIDC `sub` claim to include `job_workflow_ref` and then match that customized `sub` in AWS. If you later move AWS role ARNs into a GitHub Environment such as `Sandbox-Internal`, update the AWS trust policy to match the environment-based OIDC subject because GitHub changes the default `sub` claim for jobs that reference an environment.

If you are working solo, keep the same separation anyway: use `feature/*` or `dev/*` for app work, and reserve `devops/*` for Terraform, workflow, and OIDC experiments. That keeps your everyday application flow simple while preserving a clean high-risk lane for infrastructure changes.

The dual-track sandbox layout is intentionally split by identity context: developer PR sandboxes use `sandboxes/pr-<number>/...`, while manual DevOps previews use `admin-previews/<owner>/<branch>/...`. The admin deployment identity itself is `admin-<actor>-<branch_hash>`, while the state path keeps the readable owner and branch namespace. That keeps Terraform state and cleanup responsibilities separated between the automatic PR lane and the manual admin lane.

## Runtime Mapping on EKS

- `backend`, `worker`, `frontend-admin`, and `nginx` are deployed by the Helm chart under `deploy/helm/face-detector`
- PostgreSQL, Redis or Valkey, and S3 stay external to the cluster
- sandbox and staging both track `deploy/helm/face-detector/values-staging.yaml` through `deploy/argocd/staging-application.yaml.tpl`, but sandbox clusters get isolated SSM paths under `/facedetector/sandbox/<cluster-name>/...`
- staging tracks `deploy/helm/face-detector/values-staging.yaml` through `deploy/argocd/staging-application.yaml.tpl`
- production tracks `deploy/helm/face-detector/values-production.yaml` through `deploy/argocd/production-application.yaml.tpl`
- `nginx` remains the single public entry point and proxies `/api/` and `/admin/`
- the Kubernetes secret `face-detector-env` is generated from SSM during `ArgoCD Bootstrap`, with SSM values sourced from the secret-backed backend env file and then patched with Terraform-managed endpoints when provided
- SSM runtime values are stored as `SecureString` by default and decrypted during bootstrap when generating `.env.runtime`
- when `GHCR_USERNAME` and `GHCR_TOKEN` are provided, `ArgoCD Bootstrap` also creates `ghcr-pull-secret` so the cluster can pull private GHCR images
- `metrics-server` is installed by Terraform so the backend HPA can scale on pod resource usage
- `KEDA` is installed by Terraform in both staging and production so the worker can scale on Redis queue depth while still using a native Kubernetes HPA under the hood
- `cluster-autoscaler` is installed by Terraform in both staging and production so node capacity can follow backend HPA and worker KEDA demand

## Object Storage Strategy

- local Docker Compose uses MinIO as the development object store
- staging and production use Amazon S3 as the primary snapshot and audit object store
- the backend returns presigned S3 URLs in cloud environments, so Kubernetes does not have to proxy object traffic through an in-cluster MinIO service while object access stays time-limited

### Minimal IAM access pattern

Split the AWS identity story into two parts:

- GitHub Actions should assume `Role-Sandbox`, `Role-Staging`, and `Role-Prod` through GitHub OIDC. The trust policy templates live in `aws/github-oidc-trust-policy-*.json`.
- Runtime workloads inside AWS still need their own IAM permissions for SSM, S3, and any future service integration.

For GitHub Actions and EKS worker nodes you should still ensure the relevant principals can:

- read and write SSM parameters under `/facedetector/*`
- create and manage EKS, VPC, and S3 resources for the lab environment when the role is meant to run Terraform
- list and get objects from the S3 snapshot bucket

A sample runtime access policy file is available at `aws/iam-policy-face-detector.json`. The GitHub OIDC role setup is documented in `aws/github-oidc-setup.md`.

## Security and Resilience Testing

The current deployment now includes an Nginx API rate limit for `/api/` at `5r/s` with burst handling. This helps protect the backend from noisy or abusive clients and returns `429` when limits are exceeded.

Rate limiting is parameterized via environment variables rendered into the Nginx config at container startup:

- `NGINX_RATE_LIMIT_ENABLED` (`true` or `false`)
- `NGINX_RATE_LIMIT_ZONE_RATE` (default `5r/s`)
- `NGINX_RATE_LIMIT_BURST` (default `10`)
- `NGINX_RATE_LIMIT_MODE` (default `nodelay`)

`docker-compose.dev.yml` and `docker-compose.ci.yml` can set `NGINX_RATE_LIMIT_ENABLED=false` to avoid flaky smoke tests, while production keeps it enabled.

Use the helper scripts in `scripts/` to verify common hardening behavior:

- `scripts/security_tests.py`:
  - rate-limit validation against `/api/vision/recognize`
  - authorization checks for admin endpoints
- `scripts/concurrency_test.py`:
  - send concurrent requests to the recognition endpoint
  - observe whether duplicate recognition events appear under simultaneous load

Example usage:

```bash
python scripts/security_tests.py --host http://localhost --image-path ./tests/fixtures/sample-face.jpg
python scripts/concurrency_test.py --host http://localhost --image-path ./tests/fixtures/sample-face.jpg --workers 2
```

### Load testing with Locust and Nginx rate limiting

This repo now includes `scripts/load_test_locust.py` which exercises `/api/vision/recognize` and flags `429` responses as rate-limited failures. Run it with:

```bash
LOCUST_IMAGE_DIR=./tests/fixtures locust -f scripts/load_test_locust.py --host http://localhost --headless -u 50 -r 5 --run-time 2m
```

If Nginx rate limiting is active, you should see `429` responses appear in the Locust report.

### What this verifies

- request throttling on the public API
- unauthorized admin access is rejected
- the recognition path can be exercised under concurrent submission

### What still needs explicit application logic

The current code provides API-layer hardening and restart-based resiliency, but deduplication of repeated recognition events is not yet implemented as a business rule. If you need "only one attendance event per employee per passage", add application-side logic to collapse same-employee events within a short window or derive a stable event key from the device/session.

### Backup guidance

A simple database dump is a good starting point, but in a production-grade system you should not rely on it as the only backup method.

Recommended backup components:

- automated scheduled Postgres backups or RDS snapshots
- point-in-time recovery / WAL archive retention for faster restore
- S3 versioning or replication for original photo objects
- a periodic verification process that restores a backup to a staging instance
- infrastructure and config as code so environment state can be reprovisioned

For availability, start with RDS Multi-AZ plus backups. Only populate `DATABASE_REPLICA_URLS` after you have a real reader endpoint and a read path that can tolerate replica lag.

For `pgvector`, ensure the vector extension is installed in the restore target before importing a logical dump.

## Practical Decisions

### Frontend user should be what?

For this use case, the user-facing frontend should be the kiosk at the gate,
not another public web app. It should eventually show:

- camera preview
- scanning state
- matched employee name or failure state
- retry instructions
- recent recognition events for the guard

### Admin frontend on VPS or on a platform?

Default recommendation for this repo:

- keep `frontend-admin` behind the same `nginx` entry point under `/admin/`
- use one public domain and one ingress path layout
- avoid CORS
- keep staging and production behavior simpler

If you later move the admin frontend to a separate platform, do it only after auth, monitoring, and CORS behavior are already stable.

### Do you need cache?

Yes, but keep it small:

- use external Redis or Valkey as the Celery broker and result backend
- keep queue and cache concerns on the same managed service only while the workload is still small
- optional short-lived cache for system config and recognition cooldowns can live there too
- scale workers from queue depth through KEDA instead of manually tuning deployment replicas

Do not spend project time on multi-layer cache before the core recognition flow
works correctly.

### Do you need backup?

Yes. Minimum practical backup plan for this repo is:

- automated RDS snapshots and point-in-time recovery
- S3 versioning for raw snapshots and audit objects
- periodic restore drills into a staging database
- backup artifacts stored outside the running cluster
- infrastructure and runtime config stored as code so the environment can be rebuilt cleanly

In the current cloud-aligned design, the vector store is `pgvector` inside Postgres, so embedding durability follows the database backup strategy.

## Bonus-Point Priorities

If your goal is to maximize score with practical effort, prioritize:

1. `CI/CD` for VPS deployment
2. `Backup` for Postgres, Qdrant, and MinIO
3. `Monitoring` with Prometheus and Grafana or at least health alerts
4. `Model/config versioning` with model name, version, and threshold in config
5. `SSL/domain` via nginx and Let's Encrypt or Cloudflare

## CI/CD Best Practices Included

This repo now follows a clearer single-registry CI/CD flow:

- `pull_request` CI to catch issues early with linting, unit tests, security scans, image builds, and Helm validation
- `main` or `master` CI to publish immutable GHCR images tagged with the commit SHA
- `GitOps Staging Promotion` to move staging to the exact GHCR image tag that passed CI, without rebuilding it
- `GitOps Production Promotion` to move production only when a GitHub Release is cut
- `ArgoCD Bootstrap` to reconnect Git, SSM, and cluster runtime state whenever an environment is brought back online
- `Infrastructure Management` to turn the EKS environment on only when you need it and destroy it when you are done

## Performance and Accuracy Test Scripts

### Load / stress testing with Locust

A Locust script is provided in `scripts/load_test_locust.py`.

Example command:

```bash
pip install -r backend/requirements.txt
LOCUST_IMAGE_DIR=./scripts/load_test_images locust -f scripts/load_test_locust.py --host=http://your-server-domain -u 100 -r 20 --run-time 5m --headless
```

This script sends concurrent `POST /api/vision/recognize` requests using sample JPG/PNG images.

- `-u 100` starts 100 simulated users
- `-r 20` spawns 20 users per second
- `--run-time 5m` runs for 5 minutes

### Model accuracy evaluation

A Python evaluation script is provided in `scripts/evaluate_model.py`.

Prepare two labeled folders:

```text
dataset/gallery/<employee_id>/<image>.jpg
 dataset/query/<employee_id>/<image>.jpg
```

Then run:

```bash
python scripts/evaluate_model.py --gallery-dir dataset/gallery --query-dir dataset/query --threshold 0.35
```

The script prints precision, recall, F1-score, and a classification report.

### Evidence for reports

- Capture the Locust dashboard or headless statistics
- Capture the evaluation metrics output from `evaluate_model.py`

### Optional GHCR pull secrets

`CI Pipeline` pushes to GHCR with the built-in `GITHUB_TOKEN`, so no extra registry secret is required for publishing.

If your GHCR packages are private, configure these repository secrets so Kubernetes can pull the images during `ArgoCD Bootstrap`:

- `GHCR_USERNAME`
- `GHCR_TOKEN`

If your GHCR packages are public, you can leave both unset.

## Important Environment Variables

Backend local development and Docker Compose use `.env.example`.

Backend runtime templates for SSM/EKS live in `deploy/runtime/backend.staging.env.example` and `deploy/runtime/backend.production.env.example`.

Edge-device config lives in `edge-client/.env.example` plus optional environment-specific copies.

Common backend runtime keys:

- `DATABASE_URL`
- `DATABASE_REPLICA_URLS`
- `REDIS_URL`
- `MINIO_*`
- `AWS_S3_BUCKET`
- `AWS_S3_REGION`
- `MODEL_NAME`
- `MODEL_VERSION`
- `MATCH_THRESHOLD`

Edge-device keys:

- `API_BASE_URL`
- `EDGE_DEVICE_NAME`
- `SCAN_INTERVAL_SECONDS`

## Current Status

This is still a scaffold. The deployment shape now matches the intended real
architecture, but the core business features still need implementation:

- employee CRUD
- role and authentication management
- actual DeepFace embedding and matching
- production-grade snapshot upload and retention on S3
- richer `pgvector` indexing and search behavior
- background re-indexing jobs
- kiosk UI richer than console output
- tests and database migrations

## Suggested Next Steps

1. Implement Postgres models for employees, users, roles, and recognition logs.
2. Replace stub recognition services with DeepFace and Qdrant integration.
3. Add authentication and role-based admin APIs.
4. Expand the edge kiosk UI beyond console status output.
5. Add backup scripts, monitoring compose, and stronger CI/CD verification.
