# Face Detector GitOps

Repository này là source-of-truth cho Kubernetes desired state của Face Detector.

## Nội dung

- `deploy/helm/face-detector`: Helm chart của ứng dụng và values theo môi trường.
- `deploy/helm/platform-applications`: root chart tạo từng Argo CD child Application cho platform.
- `deploy/helm/platform-resources`: ServiceMonitor, PrometheusRule và RBAC tích hợp platform.
- `deploy/platform`: values theo môi trường cho monitoring, logging, autoscaling và DNS.
- `deploy/argocd/projects`: AppProject tách riêng boundary ứng dụng và platform.
- `deploy/argocd/applications`: root Application của platform và Application của ứng dụng.
- `scripts/update_gitops_image_locks.py`: chỉ chấp nhận immutable `sha256` digest.

Terraform không cài các platform Helm workload. Terraform chỉ bootstrap EKS prerequisites,
IAM/IRSA và Argo CD; sau đó Argo CD đọc repo này để reconcile toàn bộ desired state Kubernetes.

## Promotion

```text
face-detector-app publish image@sha256
-> repository_dispatch
-> GitOps automation cập nhật values
-> mở pull request
-> GitOps CI / gateway
-> merge master
-> Argo CD phát hiện desired state mới
```

Staging và production đều đi qua pull request. Production còn dừng tại GitHub
Environment `production` trước khi tạo promotion PR, và Argo CD production giữ manual sync.

Repository này không có AWS credentials, không build application image và không chạy Terraform.
Xem [kiến trúc platform GitOps](docs/platform-gitops-architecture.md) và
[hướng dẫn cutover](docs/three-repository-cutover.md).
