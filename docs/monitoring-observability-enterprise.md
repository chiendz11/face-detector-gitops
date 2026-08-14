# Monitoring Và Observability Theo Hướng Enterprise Cho Face Detector

Tài liệu này mô tả monitoring stack mới cho hệ thống Face Detector, giải thích các thuật ngữ chính, flow vận hành, cách truy cập, và ranh giới giữa phần đã triển khai ngay trong repo với các phần nên mở rộng sau.

Mục tiêu là đủ chặt cho staging/production, nhưng vẫn phù hợp solo project: không public dashboard mặc định, không hardcode secret, không để app tự tạo resource vượt phạm vi GitOps, và mọi thay đổi đi qua Terraform, Helm, PR, CI.

## Roadmap Observability Theo PR

Repo sẽ triển khai observability theo từng PR nhỏ để giảm rủi ro vận hành:

```text
PR 1: feat/monitoring-foundation
-> kube-prometheus-stack
-> Grafana dashboard cơ bản
-> ServiceMonitor cho backend /metrics
-> PrometheusRule cơ bản
-> Alertmanager route tùy chọn qua Slack/Discord/webhook/email
-> ArgoCD app/deployment/pod/node alerts
-> backend /metrics tối thiểu: request count, latency, error count, dependency health

Local development cho PR monitoring nên chạy bằng Docker Compose trước khi deploy sandbox. Xem hướng dẫn chi tiết ở `docs/local-monitoring-dev.md`.

PR 2: feat/logging-foundation
-> Loki
-> Grafana Alloy hoặc OpenTelemetry Collector
-> log retention theo môi trường
-> log labels chuẩn: namespace, app, pod, container, env
-> dashboard logs theo app

Local development cho PR logging nên chạy bằng Docker Compose trước khi deploy sandbox. Xem hướng dẫn chi tiết ở `docs/local-logging-dev.md`.

PR 3: feat/app-observability
-> custom metrics cho face verify, enrollment, worker, vector search
-> Grafana dashboard domain-specific
-> alert cho verify failure spike, latency spike, worker backlog

PR 4: feat/tracing
-> OpenTelemetry FastAPI
-> OpenTelemetry Collector
-> Tempo
-> trace_id liên kết logs
-> Grafana trace dashboard

PR 5: feat/synthetic-edge-health
-> Blackbox Exporter hoặc CloudWatch Synthetics
-> edge heartbeat API
-> backend aggregate metrics cho edge health
-> dashboard edge health
-> alert edge offline

PR 6: feat/aws-audit-security-observability
-> CloudWatch Container Insights nếu cần
-> EKS control plane logs
-> CloudTrail
-> GuardDuty
-> ALB metrics/access logs
-> RDS/ElastiCache dashboards
```

Tài liệu này mô tả PR 1. Các phần logs, tracing, synthetic check, edge heartbeat và AWS audit/security sẽ được làm ở các PR sau để mỗi lớp có test, review và rollback riêng.

## 1. Monitoring Khác Observability Như Thế Nào?

`Monitoring` là việc đo trạng thái hệ thống và cảnh báo khi có vấn đề.

Ví dụ:

```text
backend còn sống không?
request 5xx có tăng không?
p95 latency có vượt 2 giây không?
pod có restart liên tục không?
CPU/RAM node có quá cao không?
```

`Observability` rộng hơn monitoring. Nó giúp trả lời câu hỏi vì sao hệ thống lỗi.

Ba trụ cột thường dùng:

```text
metrics  -> số đo dạng time series, ví dụ request count, latency, CPU
logs     -> dòng sự kiện dạng text/json, ví dụ request failed, deploy event
traces   -> hành trình một request qua nhiều service
```

Trong PR monitoring foundation này, repo triển khai phần metrics, dashboard, alerting trước. Logging tập trung và tracing sẽ là phase tiếp theo vì chúng cần quyết định storage/retention riêng.

## 2. Stack Đã Triển Khai

Stack chính:

```text
kube-prometheus-stack
-> Prometheus Operator
-> Prometheus
-> Alertmanager
-> Grafana
-> kube-state-metrics
-> node-exporter
```

Ý nghĩa từng thành phần:

- `Prometheus Operator`: controller quản lý Prometheus, ServiceMonitor, PrometheusRule theo kiểu Kubernetes-native.
- `Prometheus`: scrape metrics và lưu time series.
- `Alertmanager`: nhận alert từ Prometheus, gom nhóm, route sang Slack/email/webhook sau này.
- `Grafana`: dashboard UI để xem metrics.
- `kube-state-metrics`: xuất metrics về Kubernetes object như Deployment, Pod, HPA.
- `node-exporter`: xuất metrics về node Linux như CPU, RAM, disk, network.

Terraform cài stack này vào namespace:

```text
monitoring
```

Service của Prometheus, Grafana và Alertmanager đều là:

```text
ClusterIP
```

Tức là nội bộ cluster, không expose public ra Internet mặc định.

## 3. Vì Sao Không Public Grafana Ngay?

Với enterprise-grade, dashboard vận hành không nên public trước khi có:

```text
TLS
SSO
RBAC
audit log
rate limiting
IP allowlist hoặc private network
```

Hiện tại cách truy cập sandbox đúng là dùng `kubectl port-forward` khi cần debug. IAM user cá nhân không có quyền mặc định; nếu cần xem Grafana UI thường xuyên, hãy cấu hình repo variable `MONITORING_PORT_FORWARD_PRINCIPAL_ARNS_JSON` với IAM role/principal được phép port-forward theo RBAC tối thiểu.

```powershell
aws eks update-kubeconfig --region ap-southeast-1 --name <cluster-name> --role-arn <monitoring-observer-role-arn>
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
```

Sau đó mở:

```text
http://localhost:3000
```

Mật khẩu Grafana mặc định do Helm chart tạo trong Kubernetes Secret. Lấy bằng:

```powershell
kubectl -n monitoring get secret kube-prometheus-stack-grafana -o jsonpath="{.data.admin-password}" | %{ [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($_)) }
```

RBAC port-forward chỉ cấp quyền trong namespace `monitoring`:

```text
get/list/watch pods, services, endpoints
get/list/watch endpointslices
create pods/portforward
get secret kube-prometheus-stack-grafana
```

Production sau này có thể expose Grafana qua internal ingress hoặc VPN, nhưng không nên public thẳng chỉ bằng LoadBalancer.

## 4. App Backend Xuất Metrics Như Thế Nào?

Backend FastAPI có endpoint nội bộ:

```text
GET /metrics
```

Endpoint này dùng format Prometheus text exposition.

Các metrics app đang xuất:

```text
face_detector_http_requests_total
face_detector_http_request_duration_seconds
face_detector_http_requests_in_progress
face_detector_http_errors_total
face_detector_dependency_health_status
```

Ý nghĩa:

- `face_detector_http_requests_total`: tổng số HTTP request theo method, route, status code.
- `face_detector_http_request_duration_seconds`: histogram đo latency request.
- `face_detector_http_requests_in_progress`: số request đang xử lý.
- `face_detector_http_errors_total`: tổng số HTTP request trả về 5xx.
- `face_detector_dependency_health_status`: trạng thái dependency, trong đó `1` là healthy, `0` là unhealthy, `-1` là chưa biết.

Backend cũng có readiness endpoint:

```text
GET /ready
```

Endpoint này kiểm tra dependency thật như database và Redis. Kubernetes readiness probe dùng `/ready`, còn `/health` vẫn là shallow liveness/public health.

Nginx public hiện không route `/metrics`. Prometheus scrape trực tiếp qua backend `ClusterIP` trong Kubernetes.

Flow:

```text
backend pod
-> exposes /metrics
-> backend Service port http
-> ServiceMonitor chọn backend Service
-> Prometheus scrape /metrics mỗi 30 giây
-> Grafana đọc dữ liệu từ Prometheus
-> PrometheusRule tạo alert khi có bất thường
```

## 5. Helm Chart App Đã Thêm Gì?

Trong chart:

```text
deploy/helm/face-detector
```

Đã thêm values:

```yaml
monitoring:
  enabled: true
  serviceMonitor:
    enabled: true
    interval: 30s
    scrapeTimeout: 10s
  prometheusRule:
    enabled: true
  alertmanagerConfig:
    enabled: false
    receiver: slack
```

Đã thêm template:

```text
templates/servicemonitor-backend.yaml
templates/prometheusrule-backend.yaml
templates/alertmanagerconfig.yaml
templates/grafana-dashboard-overview.yaml
```

`ServiceMonitor` nói cho Prometheus biết cần scrape backend ở `/metrics`.

`PrometheusRule` tạo alert cơ bản:

```text
FaceDetectorBackendDown
FaceDetectorBackendHighErrorRate
FaceDetectorBackendHighLatencyP95
FaceDetectorDependencyUnhealthy
FaceDetectorDeploymentUnavailable
FaceDetectorPodRestartSpike
```

`AlertmanagerConfig` mặc định tắt. Khi bật, chart có thể route alert sang Slack hoặc webhook bằng Kubernetes Secret riêng. Repo không hardcode webhook URL.

`grafana-dashboard-overview.yaml` tạo dashboard cơ bản cho request rate, 5xx rate, p95 latency, dependency health và pod restarts.

## 6. ArgoCD AppProject Được Mở Quyền Gì?

AppProject `face-detector` trước đó giới hạn resource được phép sync.

Vì chart giờ có `ServiceMonitor`, `PrometheusRule` và `AlertmanagerConfig`, AppProject được mở thêm đúng các resource này:

```text
monitoring.coreos.com/ServiceMonitor
monitoring.coreos.com/PrometheusRule
monitoring.coreos.com/AlertmanagerConfig
```

Điểm quan trọng: AppProject vẫn không mở quyền rộng kiểu `*/*`.

Đây là cách enterprise-grade:

```text
ứng dụng cần resource nào thì whitelist resource đó
không dùng project default lâu dài
không cho chart tự tạo Secret ứng dụng
không mở cluster-wide permission nếu không cần
```

## 7. Terraform Platform Đã Thêm Gì?

Trong:

```text
terraform/platform
```

Đã thêm:

```text
kubernetes_namespace.monitoring
helm_release.kube_prometheus_stack
```

Biến mới:

```text
enable_monitoring
monitoring_namespace
monitoring_retention
kube_prometheus_stack_chart_version
```

Output mới:

```text
monitoring_enabled
monitoring_namespace
```

Mặc định:

```text
enable_monitoring = true
monitoring_namespace = monitoring
kube_prometheus_stack_chart_version = 85.3.3
retention staging/sandbox = 7d
retention production = 30d
```

Các service control plane của monitoring vẫn là nội bộ `ClusterIP`.

## 8. Vì Sao Disable Một Số Control Plane Targets Trên EKS?

Trong EKS managed control plane, một số component như:

```text
kube-controller-manager
kube-scheduler
etcd
```

không expose metrics giống cluster tự quản lý.

Nếu bật nguyên default rules của kube-prometheus-stack, Prometheus có thể tạo alert nhiễu kiểu control plane target down dù thực tế EKS đang bình thường.

Vì vậy Terraform tắt các target này:

```text
kubeControllerManager.enabled = false
kubeScheduler.enabled = false
kubeEtcd.enabled = false
```

Đây là tuning phù hợp cho managed Kubernetes.

## 9. ArgoCD Metrics

ArgoCD Helm values đã bật metrics và ServiceMonitor cho các component chính khi monitoring được bật:

```text
argocd-server
argocd-repo-server
argocd-application-controller
argocd-redis
argocd-notifications
```

Flow:

```text
ArgoCD component
-> metrics service
-> ServiceMonitor
-> Prometheus
-> Grafana dashboard / alert sau này
```

Điều này giúp quan sát:

```text
sync status
repo server latency
controller reconcile behavior
notification failures
```

## 10. Alerting Hiện Tại

Alert app-level đã có trong Helm chart:

```text
FaceDetectorBackendDown
FaceDetectorBackendHighErrorRate
FaceDetectorBackendHighLatencyP95
FaceDetectorDependencyUnhealthy
FaceDetectorDeploymentUnavailable
FaceDetectorPodRestartSpike
```

Alert platform-level được Terraform tạo trong namespace monitoring:

```text
FaceDetectorArgoCdAppDegraded
FaceDetectorArgoCdAppOutOfSync
FaceDetectorKubernetesNodeNotReady
```

Các alert Kubernetes-level mặc định đến từ kube-prometheus-stack, ví dụ:

```text
pod crash loop
deployment rollout stuck
node disk/memory/cpu pressure
Prometheus target down
```

Route alert ra Slack/webhook chưa hardcode trong repo. Đây là chủ ý đúng:

```text
alert rule nằm trong Git
alert destination nằm trong secret/config riêng
```

Khi cần bật routing, tạo Secret chứa webhook URL trong namespace app rồi bật:

```yaml
monitoring:
  alertmanagerConfig:
    enabled: true
    receiver: slack
    secretName: alertmanager-receiver
    secretKey: webhook-url
    channel: "#alerts"
```

Email/Discord có thể đi qua webhook receiver hoặc mở rộng AlertmanagerConfig ở PR riêng.

## 11. Flow Khi Deploy Staging/Production

Flow tổng quát:

```text
Terraform infrastructure apply
-> tạo namespace monitoring
-> cài kube-prometheus-stack
-> cài ArgoCD với metrics ServiceMonitor
-> app-cd deploy Face Detector chart
-> chart tạo backend ServiceMonitor và PrometheusRule
-> chart tạo dashboard Grafana và AlertmanagerConfig nếu được bật
-> Prometheus scrape backend /metrics
-> Grafana có dữ liệu
-> Alertmanager nhận alert nếu rule firing
```

Với ArgoCD:

```text
GitOps values đổi
-> ArgoCD sync app
-> AppProject cho phép ServiceMonitor/PrometheusRule/AlertmanagerConfig
-> Prometheus tự phát hiện target mới
```

## 12. Flow Khi Debug Sự Cố

Ví dụ edge verify bị chậm hoặc lỗi 500:

```text
1. Mở Grafana qua port-forward.
2. Xem backend request rate, 5xx rate, p95 latency.
3. Xem pod restart, CPU/RAM, DB/Redis symptoms.
4. Nếu cần log chi tiết, dùng kubectl logs trước.
5. Nếu lỗi lặp lại nhiều, thêm alert hoặc dashboard panel tương ứng.
```

Lệnh nhanh:

```powershell
kubectl -n facedetector get pods
kubectl -n facedetector logs deploy/backend --tail=200
kubectl -n monitoring get servicemonitor,prometheusrule
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
```

## 13. Vì Sao Chưa Thêm Loki/Tempo Ngay?

Logging và tracing cần quyết định thêm:

```text
retention bao lâu?
lưu ở S3 hay PVC?
log có chứa dữ liệu nhạy cảm không?
có cần mask employee code, image path, auth token không?
chi phí ingest mỗi ngày bao nhiêu?
```

Nếu thêm Loki/Tempo mà chưa có retention/storage policy, hệ thống dễ:

```text
tốn chi phí bất ngờ
đầy disk/PVC
lưu log nhạy cảm quá lâu
khó xóa dữ liệu theo policy
```

Vì vậy phase hiện tại tập trung metrics/alert trước. Phase sau nên thêm:

```text
Grafana Loki hoặc AWS CloudWatch Logs
Grafana Alloy hoặc Promtail
OpenTelemetry Collector
Grafana Tempo hoặc managed tracing
log redaction policy
retention policy theo môi trường
```

## 14. Edge Device Nên Được Monitor Như Thế Nào Sau Này?

Edge device không nên chỉ rely vào backend logs.

Nên có heartbeat:

```text
edge device
-> gửi heartbeat định kỳ lên backend
-> backend lưu device status
-> metrics xuất số device online/offline
-> alert nếu device offline quá ngưỡng
```

Metrics gợi ý:

```text
face_detector_edge_heartbeat_age_seconds
face_detector_edge_verify_requests_total
face_detector_edge_camera_errors_total
face_detector_edge_backend_request_failures_total
```

Page admin có thể hiển thị:

```text
Devices
-> online/offline
-> last heartbeat
-> app version
-> camera status
-> backend connectivity
```

Đây là phase rất quan trọng cho production edge deployment.

## 15. Security Boundary

Ranh giới bảo mật hiện tại:

```text
/health  -> public shallow/liveness path qua Nginx
/metrics -> chỉ backend nội bộ, Prometheus scrape qua ClusterIP
Grafana  -> ClusterIP, truy cập bằng port-forward
Prometheus/Alertmanager -> ClusterIP
```

Không nên expose:

```text
/metrics public
Prometheus public
Alertmanager public
Grafana public không SSO/TLS/RBAC
```

## 16. Test Plan

Local checks:

```powershell
python -m pytest backend/tests/test_health_api.py
python -m unittest scripts.tests.test_release_contracts
helm lint deploy/helm/face-detector
helm template face-detector deploy/helm/face-detector
terraform -chdir=terraform/platform fmt -check
terraform -chdir=terraform/platform validate
```

Cluster checks sau deploy:

```powershell
kubectl -n monitoring get pods
kubectl -n monitoring get prometheus,alertmanager
kubectl -n facedetector get servicemonitor,prometheusrule
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
```

Kiểm tra backend metrics:

```powershell
kubectl -n facedetector port-forward svc/backend 8000:8000
curl http://localhost:8000/metrics
```

## 17. Các Bước Nâng Cấp Tiếp Theo

Các bước tiếp theo đi đúng roadmap:

```text
PR 2: logging foundation với Loki + Alloy hoặc OTel Collector.
PR 3: domain-specific app observability cho verify/enrollment/worker/vector search.
PR 4: tracing với OpenTelemetry + Tempo.
PR 5: synthetic checks + edge heartbeat.
PR 6: AWS audit/security observability.
Sau khi có đủ production traffic: thêm SLO burn-rate alerts.
```

SLO gợi ý:

```text
availability: 99.5% cho admin/backend staging, cao hơn cho production nếu cần
latency: p95 verify request dưới 2 giây
error rate: 5xx dưới 1% trong 30 phút
edge heartbeat: device offline quá 5 phút thì warning, quá 15 phút thì critical
```

## 18. Kết Luận

Monitoring foundation hiện tại đưa repo sang hướng vận hành có quan sát được:

```text
cluster metrics
Kubernetes object metrics
backend HTTP metrics
ArgoCD metrics
app-level alert rules
internal Grafana/Prometheus/Alertmanager
GitOps-safe ServiceMonitor/PrometheusRule
```

Đây là nền hợp lý để chạy staging/production. Khi có domain, TLS, SSO, và quyết định retention rõ ràng, có thể mở rộng tiếp sang logging/tracing mà không phá vỡ kiến trúc hiện tại.
