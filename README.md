# Face Detector For Office Access Control

This repository is a practical starter architecture for a face-recognition
access-control system in a small company. The target scenario is realistic:
fewer than 100 employees, one or a few entrance gates, one VPS for server-side
services, and one or more local edge devices near the cameras.

## Deployment Model

- `edge-client/`: kiosk-side application at the entrance. This is the real
  user-facing interface for the security guard or employee.
- `backend/`: FastAPI APIs, business logic, recognition pipeline, and service
  integration for SQL, object storage, vector search, and background jobs.
- `frontend-admin/`: admin panel for employee enrollment, threshold tuning,
  role management, and audit review. It is served at `/admin/`.
- `nginx/`: reverse proxy that exposes `/admin/` and `/api/`.
- `docker-compose.yml`: VPS stack.
- `docker-compose.edge.yml`: edge-device stack.

## Why This Architecture Is Practical

For a company with fewer than 100 employees, you usually do not need
Kubernetes. The real challenges are:

- stable camera input
- accurate face detection and cropping
- consistent embedding and matching
- reliable audit logging
- backup and recoverability

A single VPS is enough for:

- backend API
- worker
- Postgres
- Qdrant
- MinIO
- Redis
- nginx

## Runtime Topology

### VPS side

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
|       `-- deploy.yml
|-- backend/
|-- frontend-admin/
|-- edge-client/
|-- nginx/
|-- docker-compose.yml
|-- docker-compose.edge.yml
|-- .env.example
`-- README.md
```

## URL Layout

- `http://your-vps-domain/admin/`: admin frontend
- `http://your-vps-domain/api/health`: backend health
- `edge-client`: entrance kiosk flow

## Run With Docker

### VPS stack

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

## Deploying to an AWS VPS

Use the helper scripts in `scripts/` to SSH into the instance and manage deployment.

1. Create or confirm your SSH key locally and set environment variables:

```bash
export VPS_HOST=your-vps-ip-or-hostname
export VPS_USER=ubuntu
export SSH_KEY_PATH=~/.ssh/your-aws-key.pem
```

2. Connect to your VPS:

```bash
bash scripts/ssh-to-vps.sh
```

3. Install Docker and Docker Compose on Ubuntu:

```bash
VPS_HOST=your-vps-ip VPS_USER=ubuntu SSH_KEY_PATH=~/.ssh/your-aws-key.pem bash scripts/setup-vps.sh
```

4. Deploy the repo and start services:

```bash
VPS_HOST=your-vps-ip VPS_USER=ubuntu SSH_KEY_PATH=~/.ssh/your-aws-key.pem bash scripts/deploy-to-vps.sh
```

This repo also supports a GitHub Container Registry deployment flow with separate staging and production environments.

- `staging` deploys from `main` branch to `/home/ubuntu/face-detector-staging`
- `production` deploys manually via workflow dispatch to `/home/ubuntu/face-detector` or `/home/ubuntu/face-detector-canary`
- Both workflows use `docker-compose.ghcr.yml` and can pull backend/frontend/edge images from GHCR

## AWS cloud deployment guidance

For AWS cloud production, the preferred direction is:

- `AWS RDS` for PostgreSQL with `pgvector` to store employee records and face embeddings
- `AWS S3` for original employee images and snapshots
- `AWS EC2` to run the Dockerized backend, frontend, and nginx services
- `AWS SSM Parameter Store` to keep environment secrets out of source control

This repo currently scaffolds the deployment flow and secret injection; the next step is to replace local service dependencies with cloud-managed equivalents.

### Recommended runtime mapping

- `DATABASE_URL`: connect to RDS Postgres with the `vector` extension enabled
- `DATABASE_REPLICA_URLS`: optional comma-separated read-replica URLs for higher availability and read scaling
- `AWS_S3_BUCKET` + `AWS_S3_REGION`: store raw employee photos and snapshots in S3
- `EMBEDDING_DIMENSIONS`: configure `pgvector` vector length to match your model
- `QDRANT_URL` / `MINIO_*`: remain available for local development, but production should use remote cloud services
- `AWS_S3_BUCKET` / `AWS_S3_REGION`: archive and backup large files to Amazon S3 while MinIO can remain a fast local cache

> Note: The backend class `VectorSearchService` is a vector-search abstraction. In the current cloud design it can use PostgreSQL + `pgvector` instead of a standalone Qdrant process.

## Hybrid storage architecture (MinIO + S3)

This code now supports a hybrid storage model:

- MinIO local store for fast writes and low-latency access
- Amazon S3 for backup, archive, versioning, and long-term retention

To enable hybrid mode, keep local MinIO running and set `AWS_S3_BUCKET`/`AWS_S3_REGION` in your environment. The snapshot upload path will still use MinIO as the local store, while a copy is also persisted to S3.
### Minimal IAM access pattern

For GitHub Actions / EC2 bootstrapping you should use an IAM principal that can:

- read SSM parameters under `/facedetector/*`
- list and get objects from the S3 bucket
- optionally use `rds-db:connect` if you enable IAM DB authentication

A sample policy file is available at `aws/iam-policy-face-detector.json`.

## Using AWS SSM to generate .env files

The deploy workflows now generate `.env.production` or `.env.staging` on the GitHub Actions runner by reading values from AWS SSM Parameter Store.

Required GitHub secrets for this flow:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION` (optional; defaults to `ap-southeast-1`)
- `REGISTRY_ORG`
- `REGISTRY_HOST` (optional; defaults to `ghcr.io`)
- `VPS_HOST`
- `VPS_USER`
- `VPS_SSH_KEY`
- `VPS_GHCR_USERNAME`
- `VPS_GHCR_TOKEN`

The workflow will:

1. configure AWS credentials on the runner
2. call AWS SSM to fetch production/staging app secrets
3. write `.env.production` / `.env.staging`
4. SCP the generated env file to the EC2 instance

If you use private GHCR packages, the VPS also needs a read token:

- `VPS_GHCR_USERNAME`: GitHub username or org
- `VPS_GHCR_TOKEN`: PAT with `read:packages` or package read access

You can rollback a failed release with:

```bash
VPS_HOST=your-vps-ip VPS_USER=ubuntu SSH_KEY_PATH=~/.ssh/your-aws-key.pem \
GHCR_USERNAME=github GHCR_TOKEN=your-token \
REGISTRY_HOST=ghcr.io REGISTRY_ORG=your-org \
ROLLBACK_TAG=previous-tag \
TARGET_DIR=/home/ubuntu/face-detector \
bash scripts/vps-rollback-ghcr.sh
```

Alternatively, you can trigger a rollback from GitHub directly using the `Rollback Deployment` workflow and choose:

- `environment`: `production` or `staging`
- `rollback_tag`: optional tag to rollback to

If you omit `ROLLBACK_TAG`, the rollback script will use the previous deployment tag recorded by `vps-deploy-ghcr.sh`.

The production workflow will log in on the VPS, pull the images, deploy the stack, and run a health check.

> The deploy script preserves an existing `/opt/face-detector/.env` file if one already exists, so secrets and custom production settings are not overwritten.

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

<<<<<<< HEAD
## CI/CD Best Practices Included

This repo now follows a more realistic CI/CD flow:

- `pull_request` CI to catch issues early (lint, tests, build, dependency audit)
- `main` CI to run deeper validation, build images, and smoke test the integrated stack
- `deploy` workflow to update the VPS and validate the deployed service with a health check
- optional Docker registry push when `REGISTRY_*` secrets are configured

## Performance and Accuracy Test Scripts

### Load / stress testing with Locust

A Locust script is provided in `scripts/load_test_locust.py`.

Example command:

```bash
pip install -r backend/requirements.txt
LOCUST_IMAGE_DIR=./scripts/load_test_images locust -f scripts/load_test_locust.py --host=http://your-vps-domain -u 100 -r 20 --run-time 5m --headless
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

### Optional registry secrets

To push built images from `main` CI, configure these repository secrets:

- `REGISTRY_HOST` (optional; defaults to `ghcr.io`)
- `REGISTRY_ORG` or namespace
- `REGISTRY_USERNAME` (optional; defaults to `${{ github.actor }}` for GitHub Container Registry)
- `REGISTRY_PASSWORD` (optional; defaults to `${{ secrets.GITHUB_TOKEN }}` for GitHub Container Registry)

If you use GitHub Container Registry, you usually only need:

- `REGISTRY_ORG=your-github-username-or-org`

The workflow can then authenticate with the built-in `GITHUB_TOKEN`.

=======
>>>>>>> master
## Important Environment Variables

See `.env.example`:

- `DATABASE_URL`
- `REDIS_URL`
- `QDRANT_URL`
- `MINIO_*`
- `MODEL_NAME`
- `MODEL_VERSION`
- `MATCH_THRESHOLD`
- `BACKEND_BASE_URL`
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
