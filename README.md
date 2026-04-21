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
- `docker-compose.yml`: local or single-server stack.
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

A single small environment is often enough for:

- backend API
- worker
- Postgres
- Qdrant
- MinIO
- Redis
- nginx

## Runtime Topology

### Server side

- `nginx` listens on port `80`
- `/admin/` routes to `frontend-admin`
- `/api/` routes to `backend`
- `backend` talks to Postgres, Qdrant, MinIO, and Redis
- `worker` runs background jobs such as re-indexing or batch enrollment

### Edge side

- `edge-client` reads frames from the local camera
- faces are detected and cropped before upload
- crops are sent to `POST /api/vision/recognize`
- the kiosk UI confirms pass, fail, or retry

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

## Run With Docker

### Server stack

```bash
docker compose up -d --build
```

This starts:

- `backend`
- `worker`
- `frontend-admin`
- `nginx`
- `db`
- `vector-db`
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

## Cost-saving workflow

The recommended student/lab workflow is:

1. run `Infrastructure Management` with `environment=staging` or `environment=production` to create the target VPC, EKS cluster, S3 bucket, and ArgoCD
2. keep working normally with trunk-based CI on pull requests and merges to `main` or `master`
3. let `GitOps Staging Promotion` write the successful CI commit SHA into `deploy/helm/face-detector/values-staging.yaml`
4. create a GitHub Release when you want production promotion, and let `GitOps Production Promotion` write the release commit SHA into `deploy/helm/face-detector/values-production.yaml`
5. run `ArgoCD Bootstrap` whenever a cluster is recreated or brought back online so SSM values, runtime secrets, and the correct environment-specific ArgoCD Application are seeded into that cluster
6. run `Infrastructure Management` with `destroy` when you are done for the day

This keeps the expensive EKS control plane and worker nodes off when you are not actively using them.

## Terraform layout

- `terraform/bootstrap`: one-time remote-state bootstrap for the S3 state bucket and DynamoDB lock table
- `terraform/eks`: EKS, VPC, S3 snapshot bucket, namespaces, and ArgoCD installation
- `terraform/ssm`: sync backend runtime env files into `/facedetector/<environment>/...`

> The `terraform/eks` and `terraform/ssm` modules are configured for an S3 remote backend. Create the backend bucket and lock table once with `terraform/bootstrap`, then use those names as `TF_STATE_BUCKET` and `TF_STATE_LOCK_TABLE` in GitHub secrets.

## GitHub Actions flow

Required GitHub secrets for the new flow:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION` (optional; defaults to `ap-southeast-1`)
- `TF_STATE_BUCKET`
- `TF_STATE_LOCK_TABLE`
- `STAGING_BACKEND_ENV_FILE` (optional but recommended; multiline backend runtime env file for staging)
- `PRODUCTION_BACKEND_ENV_FILE` (optional but recommended; multiline backend runtime env file for production)
- `ARGOCD_REPO_USERNAME` (optional; needed when the GitHub repository is private)
- `ARGOCD_REPO_TOKEN` (optional; needed when the GitHub repository is private)
- `GHCR_USERNAME` (optional; needed only when GHCR images are private)
- `GHCR_TOKEN` (optional; needed only when GHCR images are private)

If `STAGING_BACKEND_ENV_FILE` or `PRODUCTION_BACKEND_ENV_FILE` is not set, `ArgoCD Bootstrap` falls back to the committed template under `deploy/runtime/`. For real staging or production deployments, prefer the secret-backed env file so runtime values do not live in Git.

The backend runtime templates in `deploy/runtime/` are also the canonical copy-paste starting point for `STAGING_BACKEND_ENV_FILE` and `PRODUCTION_BACKEND_ENV_FILE`.

Recommended repository variables for the two-cluster setup:

- `STAGING_EKS_CLUSTER_NAME` (optional; defaults to `face-detector-staging`)
- `PRODUCTION_EKS_CLUSTER_NAME` (optional; defaults to `face-detector-production`)
- `STAGING_SNAPSHOT_BUCKET_NAME` (optional; defaults to `face-detector-employee-images-staging`)
- `PRODUCTION_SNAPSHOT_BUCKET_NAME` (optional; defaults to `face-detector-employee-images-production`)
- `SSM_KMS_KEY_ID` (optional; customer-managed KMS key for SSM `SecureString` parameters)

The active workflows are:

- `CI Pipeline`: trunk-based validation on pull requests and pushes to `main` or `master`, plus GHCR image publish on push
- `GitOps Staging Promotion`: after `CI Pipeline` succeeds on `main` or `master`, commits the exact immutable image SHA into `values-staging.yaml`
- `GitOps Production Promotion`: when a GitHub Release is published, resolves the release commit SHA and commits it into `values-production.yaml`
- `ArgoCD Bootstrap`: manually seeds SSM-backed runtime secrets, optional GHCR pull credentials, and the correct ArgoCD Application into the selected cluster
- `Infrastructure Management`: manual `apply` or `destroy` for the selected EKS infrastructure

The promotion workflows commit with `[skip ci]` so GitOps config updates do not trigger an infinite CI rebuild loop.

There is intentionally no per-PR preview environment in this setup. For a solo workflow, local validation plus on-demand EKS bring-up is cheaper and simpler than creating temporary namespaces or releases for every pull request.

## Runtime mapping on EKS

- `backend`, `worker`, `frontend-admin`, `nginx`, `db`, `redis`, and `minio` are deployed by the Helm chart under `deploy/helm/face-detector`
- staging tracks `deploy/helm/face-detector/values-staging.yaml` through `deploy/argocd/staging-application.yaml.tpl`
- production tracks `deploy/helm/face-detector/values-production.yaml` through `deploy/argocd/production-application.yaml.tpl`
- `nginx` remains the single public entry point and proxies `/api/`, `/admin/`, and snapshot traffic
- the Kubernetes secret `face-detector-env` is generated from SSM during `ArgoCD Bootstrap`, with SSM values sourced from the secret-backed backend env file when provided
- SSM runtime values are stored as `SecureString` by default and decrypted during bootstrap when generating `.env.runtime`
- when `GHCR_USERNAME` and `GHCR_TOKEN` are provided, `ArgoCD Bootstrap` also creates `ghcr-pull-secret` so the cluster can pull private GHCR images
- `MINIO_PUBLIC_ENDPOINT` is rewritten from the Kubernetes load balancer hostname after deployment

## Hybrid storage architecture (MinIO + S3)

This code still supports a hybrid storage model:

- MinIO stays in-cluster as the fast local object store
- Amazon S3 stores the archived copy of snapshots for longer retention

To enable hybrid mode, keep `AWS_S3_BUCKET` and `AWS_S3_REGION` set in SSM. The application will keep writing to MinIO locally while also copying objects to S3.

### Minimal IAM access pattern

For GitHub Actions and EKS worker nodes you should use an IAM principal that can:

- read and write SSM parameters under `/facedetector/*`
- create and manage EKS, VPC, and S3 resources for the lab environment
- list and get objects from the S3 snapshot bucket

A sample policy file is available at `aws/iam-policy-face-detector.json`.

## Security and Resilience Testing

The current deployment now includes an Nginx API rate limit for `/api/` at `5r/s` with burst handling. This helps protect the backend from noisy or abusive clients and returns `429` when limits are exceeded.

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

For availability, use RDS Multi-AZ or read-replica endpoints in addition to backups, and configure `DATABASE_REPLICA_URLS` so read-heavy vector searches can fail over transparently.

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

- keep `frontend-admin` on the VPS under `/admin/`
- use one nginx domain
- avoid CORS
- keep debugging and deployment simpler

If you later want a more modern split deployment, only move the admin frontend
to Vercel or Netlify. The backend and data services should still stay on the
VPS.

### Do you need cache?

Yes, but keep it small:

- Redis as the message queue broker
- optional short-lived cache for system config
- optional cooldown cache to prevent repeated recognition spam

Do not spend project time on multi-layer cache before the core recognition flow
works correctly.

### Do you need backup?

<<<<<<< HEAD
Yes. Minimum practical backup plan for this repo is:

- if using local Qdrant for development, schedule Qdrant snapshots or back up the `qdrant_data` volume
- AWS S3 for raw employee images and snapshots, so image backups live outside the VPS
- store backup artifacts outside the VPS whenever possible, such as pushing dumps to S3 or another storage host

In the current cloud-aligned design, the production vector store is `pgvector` inside Postgres, so the embedding backup is the same as the database backup.

If you keep the legacy local `vector-db` service for dev, treat it as a separate cache/secondary index and back it up with snapshots or volume copies rather than relying on it as the primary source of truth.
=======
Yes. Minimum practical backup plan:

No, not for this scenario. It adds complexity without solving your main project
risks.

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
- snapshot upload to MinIO
- vector indexing in Qdrant
- background re-indexing jobs
- kiosk UI richer than console output
- tests and database migrations

## Suggested Next Steps

1. Implement Postgres models for employees, users, roles, and recognition logs.
2. Replace stub recognition services with DeepFace and Qdrant integration.
3. Add authentication and role-based admin APIs.
4. Expand the edge kiosk UI beyond console status output.
5. Add backup scripts, monitoring compose, and stronger CI/CD verification.
