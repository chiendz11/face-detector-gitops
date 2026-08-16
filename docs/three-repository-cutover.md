# Cutover GitOps Sau Khi Tách Repository

## Trách Nhiệm Của Repo

Repo này chỉ lưu desired state Kubernetes:

- Helm chart và values cho app lẫn platform workload ở sandbox/staging/production;
- Argo CD AppProject và Application templates;
- image tag theo commit và immutable digest `sha256`;
- workflow mở promotion PR.

Repo không build image, không có AWS credential và không chạy Terraform.

## GitHub Apps Và Biến Cấu Hình

Workflow nhận dispatch chỉ tin exact actor đã cấu hình:

```text
APP_RELEASE_BOT_LOGIN=<app-to-gitops-dispatcher>[bot]
```

Workflow tạo branch/PR dùng GitHub App riêng, lưu tại repo này:

```text
GITOPS_WRITER_APP_ID
GITOPS_WRITER_APP_PRIVATE_KEY
```

App writer chỉ cài trên `face-detector-gitops`. Không dùng cùng private key với dispatcher
được lưu trong app repo. `master` phải chặn direct push kể cả từ automation; bot chỉ mở PR.

## Flow Promotion

```text
face-detector-app publish image@sha256
-> dispatcher App gửi promote-staging-v1
-> workflow xác minh source_repository và github.actor
-> update values-staging.yaml
-> writer App tạo automation branch và PR
-> GitOps CI / gateway
-> merge PR
-> Argo CD đọc commit mới và reconcile staging
```

Production thêm hai gate:

```text
GitHub Release
-> Environment production chờ owner/admin approve
-> promotion PR
-> review/checks/merge
-> Argo CD production manual sync
```

Rollback là revert commit promotion để quay về digest cũ. Không rebuild image và không dùng
`latest`.

## Argo CD Boundary

AppProject ứng dụng chỉ allow URL của repo này và namespace app. AppProject platform được tách
riêng, chỉ allow repo này cùng các upstream Helm repository đã pin để quản lý operator/add-on.
Argo CD dùng GitHub App/deploy credential chỉ đọc repo GitOps; nó không đọc app repo và không đọc
infra repo.

Terraform chỉ bootstrap Argo CD và AWS/EKS prerequisites. kube-prometheus-stack, Loki, Alloy,
metrics-server, KEDA, cluster-autoscaler và ExternalDNS đều do child Application trong repo này
quản lý. Xem `docs/platform-gitops-architecture.md`.

## Trước Khi Bật Actions

1. Merge migration PR sau khi review.
2. Tạo GitHub Environment `production` với required reviewer.
3. Cài dispatcher App và writer App đúng repository.
4. Set secrets/variable nêu trên.
5. Tạo ruleset require `GitOps CI / gateway` và chặn direct push.
6. Cập nhật Argo CD repository credential sang repo mới.
7. Chỉ bật Actions khi app và infra repo cũng đã sẵn sàng cho cutover.
