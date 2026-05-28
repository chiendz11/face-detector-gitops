# Local Monitoring Development

Tài liệu này mô tả cách chạy monitoring stack bằng Docker Compose để dev và manual test metrics trước khi đưa thay đổi lên Kubernetes sandbox.

## Vì Sao Cần Local Monitoring

Quy trình chuẩn không nên nhảy thẳng từ code lên EKS chỉ để kiểm tra dashboard hoặc PromQL. Với metrics foundation, vòng đời hợp lý là:

```text
dev local bằng compose
-> kiểm tra backend /metrics
-> Prometheus scrape được backend
-> Grafana dashboard có dữ liệu
-> alert expression không sai cú pháp
-> CI contract/helm template
-> sandbox Kubernetes
-> staging
-> production
```

Local compose không thay thế sandbox Kubernetes. Nó chỉ kiểm tra phần app metrics, Prometheus scrape config, dashboard query và alert rule cơ bản. Các phần Kubernetes-native như `ServiceMonitor`, `PrometheusRule`, `AlertmanagerConfig`, Grafana sidecar import, RBAC và ArgoCD sync vẫn phải test ở sandbox.

## Stack Local

File overlay:

```text
docker-compose.monitoring.yml
```

Các service được thêm:

```text
prometheus   -> scrape backend /metrics
grafana      -> xem dashboard local
alertmanager -> nhận alert local, route null mặc định
```

Các config nằm trong:

```text
monitoring/local/prometheus/prometheus.yml
monitoring/local/prometheus/rules/face-detector-local.yml
monitoring/local/grafana/provisioning/
monitoring/local/grafana/dashboards/
monitoring/local/alertmanager/alertmanager.yml
```

Prometheus gắn label local vào backend metrics:

```text
namespace="local"
service="backend"
app="face-detector"
component="backend"
```

Nhờ vậy dashboard local có query gần giống dashboard Kubernetes, nhưng không cần `ServiceMonitor`.

## Chạy Stack

Từ root repo:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.monitoring.yml up -d --build
```

Các URL chính:

```text
Backend metrics: http://localhost:8000/metrics
Backend health:  http://localhost:8000/health
Backend ready:   http://localhost:8000/ready
Prometheus:      http://localhost:9090
Alertmanager:    http://localhost:9093
Grafana:         http://localhost:3000
```

Grafana local mặc định:

```text
username: admin
password: admin
```

Có thể override bằng biến môi trường:

```powershell
$env:GRAFANA_ADMIN_USER = "admin"
$env:GRAFANA_ADMIN_PASSWORD = "local-dev-password"
$env:GRAFANA_PORT = "3000"
$env:PROMETHEUS_PORT = "9090"
$env:ALERTMANAGER_PORT = "9093"
$env:BACKEND_METRICS_PORT = "8000"
```

## Manual Test Metrics

### 1. Kiểm tra backend sống

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
```

Kỳ vọng:

```text
/health trả 200
/ready trả ready nếu DB và Redis local khỏe
```

### 2. Kiểm tra backend expose metrics

```powershell
Invoke-WebRequest http://localhost:8000/metrics | Select-String "face_detector_http_requests_total|face_detector_http_request_duration_seconds|face_detector_dependency_health_status"
```

Kỳ vọng có các series:

```text
face_detector_http_requests_total
face_detector_http_request_duration_seconds_bucket
face_detector_http_request_duration_seconds_count
face_detector_http_request_duration_seconds_sum
face_detector_http_errors_total
face_detector_http_requests_in_progress
face_detector_dependency_health_status
```

### 3. Tạo traffic để dashboard có dữ liệu

```powershell
1..30 | ForEach-Object {
  Invoke-RestMethod http://localhost:8000/health | Out-Null
  Invoke-RestMethod http://localhost:8000/ready -ErrorAction SilentlyContinue | Out-Null
}
```

### 4. Kiểm tra Prometheus scrape backend

Mở:

```text
http://localhost:9090/targets
```

Kỳ vọng target `face-detector-backend` là `UP`.

Hoặc query bằng API:

```powershell
Invoke-RestMethod 'http://localhost:9090/api/v1/query?query=up{job="face-detector-backend"}'
Invoke-RestMethod 'http://localhost:9090/api/v1/query?query=sum(rate(face_detector_http_requests_total{namespace="local",service="backend"}[5m]))'
Invoke-RestMethod 'http://localhost:9090/api/v1/query?query=min(face_detector_dependency_health_status{namespace="local",service="backend"})'
```

Kỳ vọng:

```text
up == 1
request rate có data sau khi tạo traffic
dependency health >= 1 nếu DB/Redis khỏe
```

### 5. Kiểm tra Grafana dashboard

Mở:

```text
http://localhost:3000
```

Vào:

```text
Dashboards -> Face Detector -> Face Detector Local Overview
```

Kỳ vọng các panel có dữ liệu:

```text
Backend Request Rate
Backend 5xx Rate
Backend P95 Latency
Dependency Health
HTTP Requests By Status
HTTP Latency Buckets
Dependency Health By Dependency
Requests In Progress
```

Nếu panel trống, tạo traffic lại rồi đợi Prometheus scrape ít nhất 15-30 giây.

### 6. Kiểm tra alert rule local

Mở:

```text
http://localhost:9090/alerts
```

Kỳ vọng có rule:

```text
LocalFaceDetectorBackendDown
LocalFaceDetectorHighErrorRate
LocalFaceDetectorHighLatencyP95
LocalFaceDetectorDependencyUnhealthy
```

Test backend down:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.monitoring.yml stop backend
```

Đợi khoảng 1-2 phút rồi kiểm tra `LocalFaceDetectorBackendDown`.

Bật backend lại:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.monitoring.yml up -d backend
```

Test dependency unhealthy:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.monitoring.yml stop redis
Invoke-RestMethod http://localhost:8000/ready -ErrorAction SilentlyContinue
```

Đợi Prometheus scrape rồi kiểm tra `LocalFaceDetectorDependencyUnhealthy`.

Bật Redis lại:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.monitoring.yml up -d redis
Invoke-RestMethod http://localhost:8000/ready
```

## Kiểm Tra Security Boundary Local

Backend `/metrics` được expose trực tiếp ở port `8000` chỉ để dev local. Nginx public path vẫn không route `/metrics`.

Kiểm tra:

```powershell
Invoke-WebRequest http://localhost/health
Invoke-WebRequest http://localhost/metrics
```

Kỳ vọng:

```text
/health qua Nginx trả 200
/metrics qua Nginx không trả Prometheus metrics
```

Trong Kubernetes, Prometheus scrape backend qua service nội bộ. Không expose `/metrics` public qua Nginx/LB.

## Khi Nào Được Đưa Lên Sandbox

Chỉ nên mở PR/sandbox khi local đã đạt các điều kiện:

```text
backend /metrics có đủ series
Prometheus target UP
dashboard local có dữ liệu sau khi tạo traffic
alert rules hiện trong Prometheus
/metrics không public qua Nginx
```

Sau đó sandbox sẽ kiểm tra phần Kubernetes-native:

```text
ServiceMonitor
PrometheusRule
Grafana dashboard ConfigMap
AlertmanagerConfig nếu bật receiver
RBAC port-forward
ArgoCD sync
```

## Dọn Local

Dừng stack:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.monitoring.yml down
```

Dọn cả volume Prometheus/Grafana local:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.monitoring.yml down -v
```
