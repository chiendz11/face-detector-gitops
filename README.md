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

Yes. Minimum practical backup plan:

- Postgres daily dump
- Qdrant scheduled snapshot
- MinIO versioning or periodic replication
- store backup artifacts outside the VPS if possible

### Do you need Kubernetes?

No, not for this scenario. It adds complexity without solving your main project
risks.

## Bonus-Point Priorities

If your goal is to maximize score with practical effort, prioritize:

1. `CI/CD` for VPS deployment
2. `Backup` for Postgres, Qdrant, and MinIO
3. `Monitoring` with Prometheus and Grafana or at least health alerts
4. `Model/config versioning` with model name, version, and threshold in config
5. `SSL/domain` via nginx and Let's Encrypt or Cloudflare

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
