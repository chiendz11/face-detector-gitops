# Face Detector Cho Kiểm Soát Ra Vào Văn Phòng

Repo này là kiến trúc starter thực tế cho hệ thống nhận diện khuôn mặt dùng trong kiểm soát ra vào ở công ty nhỏ.

Kịch bản mục tiêu:

- dưới 100 nhân viên
- một hoặc vài cửa ra vào
- một backend/server-side environment nhỏ
- một hoặc nhiều edge device đặt gần camera
- có thể chạy local bằng Docker Compose hoặc cloud bằng AWS EKS

## 1. Mô Hình Triển Khai

Các phần chính:

- `edge-client/`: ứng dụng kiosk ở cửa ra vào. Đây là UI người dùng/bảo vệ thấy trực tiếp.
- `backend/`: FastAPI APIs, business logic, recognition pipeline, tích hợp SQL, object storage, vector search và background jobs.
- `frontend-admin/`: admin UI để quản lý nhân viên, enrollment bằng camera, threshold, role và audit review. App được serve ở `/admin/`.
- `nginx/`: reverse proxy expose `/admin/`, `/api/`, `/health`.
- `docker-compose.yml`: contract compose nền tảng dùng chung.
- `docker-compose.dev.yml`: override cho local development.
- `docker-compose.ci.yml`: override cho CI.
- `docker-compose.edge.yml`: stack edge-client.
- `deploy/`: Helm chart và ArgoCD applications cho GitOps deployment.
- `terraform/`: AWS bootstrap, EKS và SSM state/runtime management.

## 2. Vì Sao Kiến Trúc Này Thực Tế?

Với công ty nhỏ, vấn đề lớn nhất thường không phải platform phức tạp mà là:

- camera input ổn định
- detect/crop mặt đủ tốt
- embedding và matching nhất quán
- audit log tin cậy
- backup và khả năng restore

Local/dev stack có thể chạy đủ:

- backend API
- worker
- Postgres
- MinIO
- Redis
- nginx

Trên AWS staging/production, mô hình đúng hơn là:

- EKS chỉ chạy stateless workloads như `backend`, `worker`, `frontend-admin`, `nginx`
- PostgreSQL nằm ngoài cluster bằng RDS
- Redis hoặc Valkey nằm ngoài cluster
- S3 là object store chính
- autoscaling chỉ áp dụng cho pods stateless, không scale data store trong Kubernetes

## 3. Runtime Topology

### Phía Server

- `nginx` listen port `80` hoặc được LoadBalancer/TLS terminate phía trước.
- `/admin/` route tới `frontend-admin`.
- `/enroll/` redirect về `/admin/` để tương thích.
- `/api/` route tới `backend`.
- `/health` là public shallow health check.
- `backend` nói chuyện với PostgreSQL, Redis/Valkey và S3.
- `worker` consume async jobs từ Redis/Valkey và scale độc lập với API.

### Phía Edge

- `edge-client` đọc frame từ camera local.
- face được detect và crop ngay trên edge.
- chỉ upload cropped JPEG payload về `POST /api/vision/recognize`.
- kiosk UI hiển thị pass, fail hoặc retry.

Hiện không có pipeline stream raw video tập trung. Điều này giúp hệ thống đơn giản hơn và giảm chi phí.

## 4. Camera Và Event Flow

Flow chính:

```text
camera local
-> edge-client detect/crop mặt
-> upload face crop qua HTTP
-> backend tạo embedding hoặc verify
-> backend ghi recognition/audit logs
-> kiosk hiển thị kết quả
```

Redis và Celery hiện là cơ chế async cho các tác vụ nền như re-index hoặc batch job. Chưa cần Kafka/event bus nếu chưa có nhiều consumer hoặc replay requirement.

## 5. Cấu Trúc Repo

```text
project-root/
|-- .github/
|   `-- workflows/
|       |-- ci-gateway.yml
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
|-- deploy/
|-- terraform/
|-- docs/
`-- README.md
```

## 6. URL Layout

Local/dev:

- `http://localhost/admin/`: admin UI
- `http://localhost/enroll/`: redirect tương thích về admin UI
- `http://localhost/api/health`: backend/admin API health
- `http://localhost/health`: public shallow health qua nginx
- `http://localhost:8080`: edge kiosk web UI khi chạy local

Cloud/stable DNS:

- production: `https://face.example.com`
- staging: `https://staging.face.example.com`
- sandbox: `https://sandbox-pr-123.face.example.com`

## 7. API Contract Và E2E Smoke Test

- Contract API source-of-truth nằm ở `docs/api-contract.yml`.
- File pointer Markdown nằm ở `docs/api-contract.md`.
- Compose-backed smoke test nằm ở `scripts/ci-e2e-test.sh`.
- HTTP smoke assertions nằm trong `backend/tests/e2e/`.
- Unit và service-level integration tests nằm trong `backend/tests/` và chạy bằng `pytest`.

## 8. Chạy Local Bằng Docker

### Server Stack

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Lệnh này chạy:

- backend
- worker
- frontend-admin
- nginx
- db
- minio
- redis

### Edge Stack

```bash
docker compose -f docker-compose.edge.yml up -d --build
```

Hoặc chạy chung:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.edge.yml up -d --build
```

Trên Windows dev, camera thường nên chạy edge-client trực tiếp bằng venv local thay vì container, vì Docker Desktop Linux container không tự có `/dev/video0`.

## 9. Deploy Lên AWS Cloud

Runtime cloud khuyến nghị:

- Terraform tạo/xóa hạ tầng AWS.
- Amazon EKS chạy Kubernetes control plane và worker nodes.
- GHCR là registry duy nhất cho backend, frontend-admin, nginx và edge images.
- Helm đóng gói app stack.
- ArgoCD reconciliation trong cluster.
- AWS SSM Parameter Store giữ runtime values.
- AWS S3 lưu snapshot/audit object.
- Cloudflare DNS + ExternalDNS tạo stable public DNS khi bật. Route53 chỉ là nhánh optional nếu sau này muốn AWS quản lý DNS.

Git giữ application state. Secrets/runtime values nằm trong GitHub Secrets và AWS SSM.

## 10. Staging Và Production

| Thành phần | Staging | Production |
| --- | --- | --- |
| Compute | EKS nhỏ, thường 1-2 nodes | EKS production envelope |
| API | HPA, thường 1 -> 3 pods | HPA, thường 2 -> 20 pods |
| Worker | KEDA, thường 1 -> 3 pods | KEDA production envelope |
| Database | RDS PostgreSQL nhỏ | RDS PostgreSQL Multi-AZ |
| Queue | Redis/Valkey external | Redis/Valkey HA |
| Storage | S3 | S3 |
| Edge AI | fake/replayed hoặc real test | real edge devices |
| Độ phức tạp | production-like scale thấp | cao hơn |

Staging và production dùng cùng GitOps + EKS toolchain để promotion, ArgoCD và runtime secrets giống nhau.

## 11. Workflow Tiết Kiệm Chi Phí

Workflow phù hợp lab/student:

1. Chạy `Infrastructure Management` với `environment=staging` hoặc `production` để tạo VPC, EKS, S3, ArgoCD.
2. Phát triển bình thường bằng PR và merge vào `master`.
3. `GitOps Staging Promotion` ghi commit SHA đã pass release vào `values-staging.yaml`.
4. Tạo GitHub Release khi muốn promote production.
5. `GitOps Production Promotion` ghi release commit SHA vào `values-production.yaml` sau approval.
6. Chạy `ArgoCD Bootstrap` khi cluster mới tạo hoặc bật lại.
7. Destroy hạ tầng khi không dùng để tiết kiệm chi phí.

EKS environment có thể disposable, nhưng data store vẫn external và có backup.

## 12. Terraform Layout

- `terraform/bootstrap`: bootstrap remote state, lock table, IAM roles và OIDC trust. Route53 hosted zone/cert/DNSSEC/query logs chỉ là nhánh optional, không cần dùng nếu DNS nằm ở Cloudflare.
- `terraform/eks`: VPC, EKS, RDS, Redis, S3 snapshot bucket, namespaces, ArgoCD, metrics-server, KEDA, cluster-autoscaler, ExternalDNS.
- `terraform/ssm`: sync backend runtime env vào `/facedetector/<environment>/...`.

`terraform/eks` và `terraform/ssm` dùng S3 remote backend. Hãy tạo backend bucket và lock table một lần bằng `terraform/bootstrap`, rồi cấu hình `TF_STATE_BUCKET` và `TF_STATE_LOCK_TABLE`.

## 13. Luồng GitHub Actions

Secrets/variables quan trọng:

- `AWS_REGION`
- `TF_STATE_BUCKET`
- `TF_STATE_LOCK_TABLE`
- `TF_STATE_REGION`
- `STAGING_BACKEND_ENV_FILE`
- `PRODUCTION_BACKEND_ENV_FILE`
- `SANDBOX_BACKEND_ENV_FILE`
- `ARGOCD_REPO_USERNAME`
- `ARGOCD_REPO_TOKEN`
- `GHCR_USERNAME`
- `GHCR_TOKEN`

OIDC role secrets:

- `AWS_ROLE_SANDBOX_ARN`
- `AWS_ROLE_SANDBOX_PLAN_ARN`
- `AWS_ROLE_SANDBOX_APPLY_ARN`
- `AWS_ROLE_SANDBOX_DESTROY_ARN`
- `AWS_ROLE_SANDBOX_APPDEPLOY_ARN`
- `AWS_ROLE_STAGING_ARN`
- `AWS_ROLE_PRODUCTION_ARN`
- `AWS_ROLE_BOOTSTRAP_ARN`

Sau khi OIDC hoạt động, xóa IAM user secrets legacy:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
```

## 14. DNS Public Ổn Định Cho Edge Và Admin

Repo hỗ trợ stable public DNS bằng Cloudflare DNS + ExternalDNS. Đây là hướng phù hợp khi dùng domain miễn phí từ GitHub Student Developer Pack.

GitHub repo variables:

```text
FACE_DETECTOR_BASE_DOMAIN
FACE_DETECTOR_DNS_PROVIDER
FACE_DETECTOR_PUBLIC_DNS_ENABLED
FACE_DETECTOR_PUBLIC_TLS_ENABLED
CLOUDFLARE_ZONE_ID
```

GitHub repo secret:

```text
CLOUDFLARE_API_TOKEN
```

Ví dụ:

```powershell
gh variable set FACE_DETECTOR_BASE_DOMAIN --repo chiendz11/Face_dectector --body "face.example.com"
gh variable set FACE_DETECTOR_DNS_PROVIDER --repo chiendz11/Face_dectector --body "cloudflare"
gh variable set FACE_DETECTOR_PUBLIC_DNS_ENABLED --repo chiendz11/Face_dectector --body "true"
gh variable set FACE_DETECTOR_PUBLIC_TLS_ENABLED --repo chiendz11/Face_dectector --body "false"
gh variable set CLOUDFLARE_ZONE_ID --repo chiendz11/Face_dectector --body "<cloudflare-zone-id>"
gh secret set CLOUDFLARE_API_TOKEN --repo chiendz11/Face_dectector --body "<cloudflare-api-token>"
```

Sau khi domain đã nằm trong Cloudflare và ExternalDNS đã tạo record, edge device dùng:

```text
API_BASE_URL=https://face.example.com
```

Chi tiết nằm ở:

```text
docs/public-dns-gitops-edge-operations.md
```

## 15. Workflow Đang Hoạt Động

- `CI Gateway`: gateway tổng hợp theo domain/lane.
- `App CI`: verify app path.
- `App Release`: publish images lên GHCR từ trusted branch.
- `GitOps Staging Promotion`: promote staging bằng immutable digest.
- `GitOps Production Promotion`: promote production khi publish GitHub Release và có approval gate.
- `Terraform PR Plan`: plan sandbox từ PR.
- `Sandbox Auto Apply`: apply sandbox khi owner gắn `deploy-sandbox`.
- `Sandbox Auto Destroy`: destroy sandbox khi PR close/draft/remove label.
- `Sandbox Janitor`: cleanup sandbox quá hạn hoặc lệch state.
- `Infrastructure Management`: apply/destroy sandbox/staging/production.
- `ArgoCD Bootstrap`: seed SSM runtime secret và ArgoCD Application.
- `Terraform Bootstrap Apply`: cập nhật bootstrap/IAM/DNS foundation.

## 16. Mapping Runtime Trên EKS

- `backend`, `worker`, `frontend-admin`, `nginx` được deploy bằng Helm chart `deploy/helm/face-detector`.
- PostgreSQL, Redis/Valkey, S3 nằm ngoài cluster.
- Sandbox và staging dùng `values-staging.yaml`.
- Production dùng `values-production.yaml`.
- `nginx` là public entry point.
- Kubernetes secret `face-detector-env` được tạo từ SSM trong `ArgoCD Bootstrap`.
- Khi có `GHCR_USERNAME` và `GHCR_TOKEN`, bootstrap tạo `ghcr-pull-secret`.
- `metrics-server`, `KEDA`, `cluster-autoscaler` được cài bằng Terraform.

## 17. Chiến Lược Object Storage

- Local Docker Compose dùng MinIO.
- Staging/production dùng S3.
- Backend trả presigned S3 URL trên cloud, nên Kubernetes không cần proxy object traffic qua MinIO trong cluster.

## 18. Kiểm Thử Bảo Mật Và Khả Năng Chịu Lỗi

Nginx có rate limit cho `/api/`:

- `NGINX_RATE_LIMIT_ENABLED`
- `NGINX_RATE_LIMIT_ZONE_RATE`
- `NGINX_RATE_LIMIT_BURST`
- `NGINX_RATE_LIMIT_MODE`

Scripts hỗ trợ:

- `scripts/security_tests.py`: kiểm tra rate-limit và auth admin.
- `scripts/concurrency_test.py`: gửi concurrent requests tới recognition endpoint.
- `scripts/load_test_locust.py`: load test bằng Locust.

Ví dụ:

```bash
python scripts/security_tests.py --host http://localhost --image-path ./tests/fixtures/sample-face.jpg
python scripts/concurrency_test.py --host http://localhost --image-path ./tests/fixtures/sample-face.jpg --workers 2
```

Locust:

```bash
LOCUST_IMAGE_DIR=./tests/fixtures locust -f scripts/load_test_locust.py --host http://localhost --headless -u 50 -r 5 --run-time 2m
```

## 19. Hướng Dẫn Backup

Minimum backup plan:

- automated RDS snapshots
- point-in-time recovery / WAL retention
- S3 versioning hoặc replication
- periodic restore drill vào staging
- IaC và runtime config lưu bằng code/SSM để rebuild sạch

Với `pgvector`, restore target phải có extension vector trước khi import logical dump.

## 20. Biến Môi Trường Quan Trọng

Backend local dùng `.env.example`.

Backend runtime templates:

```text
deploy/runtime/backend.staging.env.example
deploy/runtime/backend.production.env.example
```

Edge config:

```text
edge-client/.env.example
```

Backend keys thường gặp:

- `DATABASE_URL`
- `DATABASE_REPLICA_URLS`
- `REDIS_URL`
- `MINIO_*`
- `AWS_S3_BUCKET`
- `AWS_S3_REGION`
- `EMBEDDING_PROVIDER`
- `MODEL_NAME`
- `MODEL_VERSION`
- `EMBEDDING_DIMENSIONS`
- `DEEPFACE_DETECTOR_BACKEND`
- `DEEPFACE_ALIGN`
- `DEEPFACE_ENFORCE_DETECTION`
- `EMBEDDING_ALLOW_HASH_FALLBACK`
- `MATCH_THRESHOLD`
- `ENROLLMENT_MIN_SAMPLES`
- `ENROLLMENT_MAX_SAMPLES`

Default embedding runtime là DeepFace:

```text
MODEL_NAME=Facenet512
EMBEDDING_DIMENSIONS=512
```

`hash` provider chỉ dùng cho deterministic unit tests và smoke plumbing. Không dùng `hash` làm face-recognition model thật.

Edge keys:

- `API_BASE_URL`
- `EDGE_DEVICE_NAME`
- `SCAN_INTERVAL_SECONDS`

## 21. Trạng Thái Hiện Tại

Repo đã có nền tảng deployment, governance và CI/CD khá đầy đủ, nhưng business features vẫn cần tiếp tục hoàn thiện:

- employee CRUD
- role/auth management
- production-grade snapshot upload và retention trên S3
- pgvector indexing/search behavior
- background re-indexing jobs
- enrollment quality checks và liveness controls
- tests và migrations cho toàn bộ workflow nghiệp vụ

## 22. Bước Tiếp Theo Gợi Ý

1. Hoàn thiện employee/admin CRUD và auth.
2. Hoàn thiện multi-sample enrollment và quality checks.
3. Thêm audit UI cho recognition logs, audit logs, devices.
4. Test full flow: enroll -> verify edge -> log -> audit.
5. Chạy sandbox/staging với stable DNS sau khi domain thật đã add vào Cloudflare và nameserver ở registrar đã trỏ về Cloudflare.
