# Local Logging Development

Tài liệu này mô tả cách chạy logging stack bằng Docker Compose để dev và manual test trước khi đưa logging foundation lên Kubernetes sandbox.

## Mục Tiêu

Local logging giúp kiểm tra phần log pipeline cơ bản:

```text
container stdout/stderr
-> Grafana Alloy đọc Docker logs
-> Alloy gắn labels chuẩn
-> Alloy push logs vào Loki
-> Grafana query Loki
-> dashboard logs hiển thị theo service/app/env
```

Local logging không thay thế test Kubernetes. Nó chỉ kiểm tra logic pipeline logs và dashboard query. Khi lên Kubernetes vẫn phải test DaemonSet/collector, namespace labels, retention theo env, RBAC, ArgoCD sync và log volume thật.

## Stack Local

Overlay logging:

```text
docker-compose.logging.yml
```

Service được thêm:

```text
loki  -> lưu và query logs
alloy -> đọc Docker container logs rồi push vào Loki
```

Grafana datasource/dashboard được thêm vào stack local monitoring:

```text
monitoring/local/grafana/provisioning/datasources/loki.yml
monitoring/local/grafana/dashboards/face-detector-local-logs.json
```

Alloy đọc Docker logs qua Docker socket local:

```text
/var/run/docker.sock
```

Đây là cơ chế chỉ dùng cho local dev. Không expose Docker socket kiểu này trong production app pod.

## Chạy Stack

Từ root repo:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.monitoring.yml -f docker-compose.logging.yml up -d --build
```

URL chính:

```text
Grafana: http://localhost:3000
Loki:    http://localhost:3100
Alloy:   http://localhost:12345
```

Grafana local mặc định:

```text
username: admin
password: admin
```

Nếu trước đó bạn đã chạy Grafana local với volume cũ, password trong volume sẽ được giữ lại và biến môi trường `admin/admin` không reset lại user. Khi chỉ test local và muốn quay về password mặc định, dọn volume bằng:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.monitoring.yml -f docker-compose.logging.yml down -v
```

## Manual Test Logging

### 1. Kiểm tra container chạy

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.monitoring.yml -f docker-compose.logging.yml ps
```

Kỳ vọng:

```text
loki      Up
alloy     Up
grafana   Up
backend   Up
nginx     Up
```

### 2. Kiểm tra Loki ready

```powershell
curl.exe -fsS http://localhost:3100/ready
```

Kỳ vọng:

```text
ready
```

### 3. Tạo log từ app

Gọi vài endpoint qua Nginx và backend trực tiếp:

```powershell
1..20 | ForEach-Object {
  curl.exe -fsS http://localhost/health | Out-Null
  curl.exe -fsS http://localhost:8000/health | Out-Null
  curl.exe -fsS http://localhost:8000/ready | Out-Null
}
```

Tạo một request lỗi nhẹ để có log kiểm tra:

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" http://localhost/api/not-found
```

### 4. Query Loki bằng API

```powershell
$query = [uri]::EscapeDataString('{env="local",namespace="local",app="face-detector"}')
Invoke-RestMethod "http://localhost:3100/loki/api/v1/query_range?query=$query&limit=20" | ConvertTo-Json -Depth 10
```

Kỳ vọng:

```text
status = success
data.result có stream logs
labels có env, namespace, app, service, container
```

Query riêng backend:

```powershell
$query = [uri]::EscapeDataString('{env="local",service="backend"}')
Invoke-RestMethod "http://localhost:3100/loki/api/v1/query_range?query=$query&limit=20" | ConvertTo-Json -Depth 10
```

Query riêng Nginx:

```powershell
$query = [uri]::EscapeDataString('{env="local",service="nginx"}')
Invoke-RestMethod "http://localhost:3100/loki/api/v1/query_range?query=$query&limit=20" | ConvertTo-Json -Depth 10
```

### 5. Kiểm tra Grafana datasource và dashboard

Mở:

```text
http://localhost:3000
```

Vào:

```text
Dashboards -> Face Detector -> Face Detector Local Logs
```

Kỳ vọng có panel:

```text
All Compose Logs
Backend Logs
Nginx/API Boundary Logs
Errors And Warnings
```

Nếu dashboard chưa có log, đợi 15-30 giây rồi tạo traffic lại. Alloy cần đọc Docker logs, push sang Loki, sau đó Grafana mới query thấy.

### 6. Kiểm tra bằng Grafana API

```powershell
$auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:admin"))
Invoke-RestMethod -Headers @{Authorization="Basic $auth"} "http://localhost:3000/api/datasources/uid/loki" | ConvertTo-Json -Depth 5
Invoke-RestMethod -Headers @{Authorization="Basic $auth"} "http://localhost:3000/api/search?query=Face%20Detector%20Local%20Logs" | ConvertTo-Json -Depth 5
```

Kỳ vọng:

```text
datasource uid = loki
dashboard uid = face-detector-local-logs
```

## Labels Chuẩn

Alloy gắn các labels local:

```text
env="local"
namespace="local"
app="face-detector"
service="<compose service>"
container="<container name>"
compose_project="face_detector"
container_id="<docker container id>"
```

Mục tiêu là giữ query gần giống Kubernetes:

```text
env
namespace
app
service
container
```

Khi lên Kubernetes, collector sẽ lấy labels từ pod/container/namespace thay vì Docker Compose labels.

## Retention Local

Loki local hiện giữ logs trong:

```text
168h = 7 ngày
```

Đây là default hợp lý cho dev. Khi lên Kubernetes nên cấu hình retention theo env:

```text
sandbox    7 ngày
staging    14 ngày
production 30-90 ngày
```

## Boundary

Local logging expose các cổng này trên máy dev:

```text
3100 Loki
12345 Alloy
3000 Grafana
```

Đây chỉ là local dev. Production không nên public Loki hoặc collector. Grafana production nếu expose phải có TLS, SSO/RBAC và audit.

## Khi Nào Được Đưa Lên Sandbox

Chỉ nên mở PR/sandbox khi local đạt:

```text
Loki ready
Alloy running
Loki query có logs
labels env/namespace/app/service/container đúng
Grafana datasource Loki hoạt động
Dashboard Face Detector Local Logs có logs
```

Sau đó sandbox mới kiểm tra phần Kubernetes-native:

```text
Alloy hoặc collector chạy đúng mode trong cluster
log labels từ namespace/pod/container đúng
Loki retention theo env
Grafana dashboard được import qua ConfigMap/sidecar
không expose Loki public
ArgoCD sync logging resources
```

## Dọn Local

Dừng stack:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.monitoring.yml -f docker-compose.logging.yml down
```

Dọn cả volume Loki/Grafana/Prometheus:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.monitoring.yml -f docker-compose.logging.yml down -v
```
