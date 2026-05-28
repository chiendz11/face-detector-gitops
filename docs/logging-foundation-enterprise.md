# Logging Foundation Theo Hướng Enterprise Cho Face Detector

Tài liệu này mô tả lớp logging foundation cho Face Detector sau phần metrics foundation. Mục tiêu là có một pipeline logs đủ chuẩn để debug sandbox/staging/production, nhưng vẫn phù hợp solo project: không expose Loki/Grafana public, không hardcode secret, có retention theo môi trường, có labels chuẩn, và mọi thay đổi đi qua Terraform, Helm, PR, CI.

## 1. Logging Foundation Là Gì?

`Logging` là lớp thu thập, lưu trữ và truy vấn logs của hệ thống.

Ví dụ logs giúp trả lời:

```text
request verify face nào bị 500?
backend đang lỗi dependency nào?
worker có xử lý job enrollment không?
nginx nhận request nào từ public LoadBalancer?
ArgoCD hoặc pod có lỗi sync/runtime không?
```

Trong observability stack, logs khác metrics:

```text
metrics -> số đo dạng time series, Prometheus scrape định kỳ
logs    -> dòng sự kiện stdout/stderr, collector ship vào log store
traces  -> đường đi chi tiết của một request qua nhiều service
```

PR này triển khai logs. Tracing sẽ là phase riêng sau.

## 2. Stack Được Dùng

Stack logging:

```text
Grafana Alloy -> collector/agent đọc logs
Loki           -> lưu và query logs
Grafana        -> UI xem logs qua datasource Loki
```

Flow trên Kubernetes:

```text
Pod stdout/stderr
-> Alloy DaemonSet đọc pod logs trên node của chính nó
-> Alloy gắn labels chuẩn
-> Alloy push logs vào Loki Gateway
-> Loki lưu logs theo retention
-> Grafana query Loki bằng LogQL
-> Dashboard Face Detector Logs hiển thị logs theo app/service/env
```

Loki và Alloy được cài bằng Terraform trong `terraform/eks`.

Namespace dùng chung với monitoring:

```text
monitoring
```

Loki, Alloy và Grafana đều là tài nguyên nội bộ trong cluster. Không có service public cho Loki/Grafana.

## 3. Vì Sao Dùng Alloy Thay Vì App Tự Gửi Logs?

App nên ghi logs ra stdout/stderr. Kubernetes runtime sẽ giữ logs đó ở tầng pod/container.

Alloy làm nhiệm vụ collector:

```text
đọc logs từ Kubernetes pod
gắn metadata Kubernetes thành labels
push logs vào Loki
```

Alloy chạy dạng DaemonSet, nhưng discovery được giới hạn theo node:

```text
spec.nodeName = HOSTNAME của Alloy pod
```

Điều này tránh tình trạng mỗi Alloy pod đọc logs của toàn bộ cluster, gây trùng logs và tăng tải Kubernetes API.

Cách này tốt hơn app tự gửi logs vì:

- app không cần biết Loki endpoint;
- không phải nhúng credential logging vào từng service;
- logs của backend, nginx, worker, ArgoCD, platform đều đi qua một pipeline thống nhất;
- thay đổi logging config đi qua IaC/GitOps thay vì sửa từng app;
- khi pod die/restart, collector vẫn đọc logs theo metadata mới.

## 4. Labels Chuẩn

Alloy gắn các labels chính:

```text
env       -> sandbox, staging, production, hoặc identity sandbox-pr-123
cluster   -> tên EKS cluster
namespace -> namespace Kubernetes
app       -> tên app theo label Kubernetes
service   -> component/service, ví dụ backend, nginx, worker
pod       -> tên pod
container -> tên container
node      -> node chạy pod
```

Ví dụ LogQL:

```text
{namespace="facedetector", service="backend"}
{namespace="facedetector", service="nginx"}
{env="sandbox-pr-140", service="backend"} |~ "(?i)(error|exception|failed)"
```

## 5. Retention Theo Môi Trường

Default retention:

```text
sandbox    -> 7d
staging    -> 14d
production -> 30d
```

Có thể override bằng Terraform variable:

```text
logging_retention
```

Ví dụ:

```hcl
logging_retention = "14d"
```

Với solo project, Loki chạy dạng `SingleBinary` để chi phí thấp và vận hành đơn giản. Khi production lớn hơn, hướng tiếp theo là chuyển Loki sang object storage S3 và mode scalable/distributed.

## 6. Namespace Nào Được Thu Logs?

Default Alloy chỉ thu logs từ các namespace cần thiết:

```text
facedetector
argocd
monitoring
keda
kube-system
```

Mục đích là giảm noise và chi phí lưu logs.

Có thể override bằng Terraform variable:

```text
logging_namespace_selector_regex
```

Ví dụ chỉ thu app và ArgoCD:

```hcl
logging_namespace_selector_regex = "facedetector|argocd"
```

## 7. Grafana Datasource Và Dashboard

Terraform thêm datasource Loki vào Grafana của `kube-prometheus-stack`:

```text
uid: loki
url: http://loki-gateway.monitoring.svc.cluster.local
```

Helm chart app thêm dashboard:

```text
Face Detector Logs
```

Dashboard có các panel:

```text
Application Logs
Backend Logs
Nginx Boundary Logs
Errors And Warnings
```

Dashboard được đóng gói trong Helm chart app dưới dạng ConfigMap có label:

```text
grafana_dashboard: "1"
```

Grafana sidecar của kube-prometheus-stack sẽ import dashboard này.

## 8. Security Boundary

Logging foundation giữ boundary như sau:

```text
Loki      -> internal ClusterIP
Grafana   -> internal ClusterIP
Alloy     -> chạy trong cluster
Public LB -> không expose /logs, /loki, /grafana
```

Muốn xem Grafana/Loki trong sandbox thì dùng `kubectl port-forward` qua EKS access entry/RBAC đã cấp riêng cho principal được phép.

Không nên public Loki ra internet. Loki chứa logs runtime, có thể có thông tin nhạy cảm nếu app log sai.

## 9. Local Dev Và Kubernetes Khác Nhau Thế Nào?

Local dev dùng:

```text
docker-compose.logging.yml
Alloy đọc Docker logs qua /var/run/docker.sock
Loki chạy local ở http://localhost:3100
Grafana local ở http://localhost:3000
```

Local chỉ kiểm tra:

```text
app có tạo logs không
Alloy có ship logs không
labels có đúng không
Grafana dashboard query có data không
LogQL cơ bản có đúng không
```

Kubernetes/sandbox kiểm tra thêm:

```text
Terraform cài Loki/Alloy đúng không
Alloy DaemonSet có chạy trên node không
RBAC của Alloy đọc pod logs được không
Loki service/gateway nội bộ có ready không
Grafana datasource Loki có được provision không
dashboard ConfigMap có được sidecar import không
retention theo env có đúng không
ArgoCD sync Helm chart logging dashboard có đúng không
```

## 10. Manual Test Trên Sandbox

Ví dụ PR sandbox là `140`:

```powershell
$PR_NUMBER = "140"
$CLUSTER = "face-detector-sbx-pr-$PR_NUMBER"
$REGION = "ap-southeast-1"

aws eks update-kubeconfig --region $REGION --name $CLUSTER
kubectl get ns
```

Kiểm tra stack logging:

```powershell
kubectl -n monitoring get pods
kubectl -n monitoring get svc
kubectl -n monitoring get pods | findstr loki
kubectl -n monitoring get pods | findstr alloy
```

Kỳ vọng:

```text
loki pod Ready
loki-gateway service tồn tại
alloy DaemonSet pod Ready trên node
grafana pod Ready
```

Port-forward Loki:

```powershell
kubectl -n monitoring port-forward svc/loki-gateway 3100:80
```

Terminal khác:

```powershell
curl.exe -fsS http://localhost:3100/ready
```

Query logs bằng Loki API:

```powershell
$query = [uri]::EscapeDataString('{namespace="facedetector"}')
Invoke-RestMethod "http://localhost:3100/loki/api/v1/query_range?query=$query&limit=20" | ConvertTo-Json -Depth 10
```

Query backend:

```powershell
$query = [uri]::EscapeDataString('{namespace="facedetector",service="backend"}')
Invoke-RestMethod "http://localhost:3100/loki/api/v1/query_range?query=$query&limit=20" | ConvertTo-Json -Depth 10
```

Query lỗi:

```powershell
$query = [uri]::EscapeDataString('{namespace="facedetector"} |~ "(?i)(error|exception|traceback|warning|failed)"')
Invoke-RestMethod "http://localhost:3100/loki/api/v1/query_range?query=$query&limit=20" | ConvertTo-Json -Depth 10
```

Port-forward Grafana:

```powershell
kubectl -n monitoring get svc | findstr grafana
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
```

Nếu service name khác do chart fullname override, dùng service Grafana thực tế từ lệnh `kubectl -n monitoring get svc | findstr grafana`.

Lấy password Grafana:

```powershell
kubectl -n monitoring get secret kube-prometheus-stack-grafana -o jsonpath="{.data.admin-password}" | % { [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($_)) }
```

Nếu secret name khác, tìm bằng:

```powershell
kubectl -n monitoring get secret | findstr grafana
```

Mở:

```text
http://localhost:3000
```

Kỳ vọng:

```text
Datasource Loki tồn tại
Dashboard Face Detector Logs tồn tại
Panel Backend Logs có dữ liệu sau khi tạo traffic
Panel Errors And Warnings hiển thị lỗi nếu có request fail
```

## 11. Tạo Traffic Để Có Logs

Lấy public hostname hiện tại:

```powershell
$HOSTNAME = kubectl -n facedetector get svc nginx -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

Gọi health:

```powershell
1..20 | ForEach-Object {
  curl.exe -fsS "http://$HOSTNAME/health" | Out-Null
}
```

Tạo request lỗi nhẹ:

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" "http://$HOSTNAME/api/not-found"
```

Sau đó query lại Loki/Grafana.

## 12. Acceptance Criteria

Logging foundation được coi là pass khi:

- `loki` và `alloy` chạy trong namespace `monitoring`;
- Loki `/ready` trả ready qua port-forward;
- Alloy ship được logs từ namespace `facedetector`;
- logs có labels `env`, `cluster`, `namespace`, `app`, `service`, `pod`, `container`;
- Grafana có datasource Loki uid `loki`;
- dashboard `Face Detector Logs` xuất hiện;
- query backend/nginx logs có dữ liệu sau khi tạo traffic;
- query error/warning hoạt động;
- Loki/Grafana không public ra ngoài internet;
- retention đúng theo môi trường hoặc theo override.

## 13. Khi Nào Cần Nâng Cấp Tiếp?

Khi production traffic lớn hơn, nên nâng cấp:

```text
Loki SingleBinary -> SimpleScalable hoặc Distributed
filesystem storage -> S3 object storage
retention 30d -> 60d/90d tùy compliance
basic dashboards -> dashboard theo domain face recognition
logs only -> logs có trace_id liên kết với Tempo
```

Các phần này thuộc PR app observability/tracing sau.
