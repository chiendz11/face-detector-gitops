# Face Detector GitOps

Repository này là source-of-truth cho Kubernetes desired state của Face Detector.

## Nội dung

- `deploy/helm/face-detector`: Helm chart và values theo môi trường.
- `deploy/argocd`: AppProject và Application templates.
- `scripts/update_gitops_image_locks.py`: chỉ chấp nhận immutable `sha256` digest.

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
Xem [hướng dẫn cutover](docs/three-repository-cutover.md).
