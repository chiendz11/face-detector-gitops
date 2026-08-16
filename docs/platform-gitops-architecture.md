# Kiến Trúc Platform Workload Bằng Argo CD

## Mục Tiêu

Repo GitOps là source of truth duy nhất cho desired state Kubernetes, bao gồm cả ứng dụng và
platform workload. Terraform không còn cài trực tiếp các Helm release như Prometheus, Loki hoặc
ExternalDNS.

Ranh giới ownership cuối cùng:

```text
face-detector-infra
-> VPC, EKS, data services
-> IAM policy, IAM role, IRSA
-> EKS access entry
-> cài Argo CD tối thiểu

face-detector-gitops
-> Argo CD AppProject và Application
-> Helm chart/values của ứng dụng
-> kube-prometheus-stack, Loki, Alloy
-> metrics-server, KEDA, cluster-autoscaler, ExternalDNS
-> ServiceMonitor, PrometheusRule và Kubernetes RBAC liên quan
```

## Cấu Trúc Thư Mục

```text
deploy/
  argocd/
    projects/
      face-detector.yaml.tpl
      platform.yaml.tpl
    applications/
      face-detector/
        staging.yaml.tpl
        production.yaml.tpl
      platform.yaml.tpl
  helm/
    face-detector/
    platform-applications/
    platform-resources/
  platform/
    kube-prometheus-stack/
    loki/
    alloy/
    metrics-server/
    keda/
    cluster-autoscaler/
    external-dns/
```

Mỗi thư mục `deploy/platform/<addon>` có:

```text
values-common.yaml
values-sandbox.yaml
values-staging.yaml
values-production.yaml
```

`values-common.yaml` chứa contract dùng chung. File theo môi trường chỉ chứa khác biệt như
retention, replica, persistence và resource requests/limits.

## Hai AppProject Riêng

`face-detector` là project có quyền hẹp. Nó chỉ được đọc GitOps repo, deploy vào namespace
`facedetector` và chỉ tạo đúng nhóm resource mà app cần. Secret không do Argo CD app chart quản
lý vì runtime secret được bootstrap qua kênh riêng.

`face-detector-platform` là project đặc quyền hơn vì operator/add-on phải tạo CRD, ClusterRole,
APIService và resource trong `monitoring`, `kube-system`, `keda`, `argocd`. Project này chỉ allow
GitOps repo và các Helm repository đã khai báo rõ. Việc tách project ngăn app chart tự nâng quyền
thành platform administrator.

## Root Application Và Child Application

Workflow infra chỉ apply hai object bootstrap từ GitOps repo:

```text
AppProject face-detector-platform
Application face-detector-platform-<environment>
```

Root Application đọc chart `deploy/helm/platform-applications`. Chart này sinh child Application
độc lập cho từng workload:

```text
metrics-server
kube-prometheus-stack
Loki
Alloy
KEDA
cluster-autoscaler
ExternalDNS khi DNS được bật
platform-resources
```

Mỗi child Application pin chart version, dùng `releaseName` ổn định và đọc hai values file từ
GitOps repo bằng Argo CD multi-source. Vì vậy mỗi add-on có status, diff, history, health và đường
rollback riêng.

Child Applications dùng sync wave: monitoring/metrics trước, Loki/KEDA/autoscaler/DNS tiếp theo,
Alloy sau Loki và `platform-resources` sau Prometheus Operator CRD. Terraform bootstrap cấu hình
health check cho resource `Application`, nên root Application chỉ chuyển wave khi child trước đã
healthy. Workflow vẫn kiểm tra lại toàn bộ child status trước khi deploy app.

## Dữ Liệu Terraform Truyền Sang GitOps

Một số workload cần AWS prerequisite nhưng lifecycle pod vẫn do Argo CD quản lý:

```text
Terraform tạo cluster-autoscaler IAM role + IRSA trust
-> output cluster_autoscaler_role_arn
-> root Application truyền ARN vào Helm values
-> ServiceAccount cluster-autoscaler dùng ARN đó

Terraform tạo Route53 ExternalDNS IAM role khi dùng Route53
-> output external_dns_role_arn
-> root Application truyền ARN vào Helm values
-> ServiceAccount external-dns dùng ARN đó
```

Với Cloudflare, Terraform không tạo IAM role cho ExternalDNS. Workflow tạo Kubernetes Secret từ
GitHub Secret `CLOUDFLARE_API_TOKEN`; GitOps chỉ tham chiếu tên Secret, không lưu token trong Git.

## Flow Tạo Môi Trường Mới

```text
Infrastructure workflow
-> Terraform network
-> Terraform EKS cluster
-> Terraform data services
-> Terraform cluster-bootstrap
   -> IAM/IRSA prerequisites
   -> Argo CD
-> workflow tạo runtime Secret cần thiết
-> apply platform AppProject + root Application
-> Argo CD render child Applications
-> Argo CD cài platform workloads
-> chờ platform Synced/Healthy
-> apply Face Detector Application
-> Argo CD deploy app
```

Thứ tự này bảo đảm Prometheus Operator CRD và KEDA CRD có trước khi app chart tạo ServiceMonitor,
PrometheusRule hoặc ScaledObject.

## Chính Sách Theo Môi Trường

Sandbox và staging dùng automated sync, `prune` và `selfHeal`. Production root Application được
reconcile tự động vì nó chỉ cập nhật định nghĩa child Application; các child workload production
không có automated sync. Operator phải duyệt và sync platform child Applications trước, rồi mới
sync application production.

Chart version luôn được pin trong `deploy/helm/platform-applications/values.yaml`. Không dùng
`latest`. Thay đổi version hoặc values phải qua PR GitOps, CI render chart, review diff và merge.

## Flow Teardown

```text
destroy được phê duyệt
-> xóa Face Detector Application
-> xóa platform root Application
-> finalizer của root xóa child Applications
-> finalizer của child xóa Helm-rendered resources
-> xác nhận workload/LB được dọn
-> Terraform destroy Argo CD, IAM prerequisites, data, EKS và network
```

Phải xóa workload trước EKS để controller còn hoạt động và có thể dọn LoadBalancer, volume hoặc
DNS record do Kubernetes tạo.

## Rollback

Rollback workload không chạy `terraform apply`:

```text
revert GitOps commit thay chart version/values
-> Argo CD thấy desired state cũ
-> sync sandbox/staging tự động
-> production chờ manual sync
```

Terraform chỉ chạy lại khi AWS/EKS prerequisite thay đổi, ví dụ IAM policy, OIDC trust, EKS access
entry hoặc chính Argo CD bootstrap.
