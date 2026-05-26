# Tổng Kết Gia Cố Theo Hướng Enterprise

Tài liệu này ghi lại các thay đổi lớn giúp repo chuyển từ CI/CD cơ bản sang mô hình delivery có governance rõ hơn, gần với enterprise-grade nhưng vẫn phù hợp solo project.

Trọng tâm:

- tách trust boundary giữa PR untrusted và workflow trusted
- giảm quyền mặc định trong GitHub Actions
- đưa policy thành code
- hardening hạ tầng và supply chain
- giữ audit trail cho deploy, sandbox, release và DNS

## 1. Mục Tiêu

Hardening trong repo hướng tới năm mục tiêu thực tế:

1. Tách validation của PR khỏi publish/deploy flow có quyền cao.
2. Không dựa vào implicit trust trong GitHub Actions.
3. Biến governance rules thành policy có thể chạy tự động.
4. Tạo evidence cho image, release, SBOM và attestation.
5. Rollout an toàn: advisory trước, hard gate sau khi flow đã ổn.

## 2. CI/CD Được Tách Theo Bề Mặt Tin Cậy

Repo không còn coi mọi automation là một pipeline lẫn lộn. Các lane chính:

### Kiểm Tra Ứng Dụng

Files:

```text
.github/workflows/app-ci.yml
.github/workflows/reusable-app-ci.yml
```

Mục đích:

- lint/test backend, frontend-admin, edge-client
- dependency/security checks
- build image để verify
- chạy smoke e2e bằng compose

Giá trị enterprise:

- PR code không có quyền publish release image
- app verification tách khỏi deploy concerns

### Phát Hành Ứng Dụng

Files:

```text
.github/workflows/app-release.yml
.github/workflows/reusable-app-release.yml
```

Mục đích:

- publish images chỉ từ trusted branch flow
- tạo SBOM/provenance evidence
- sign artifacts/images

Giá trị enterprise:

- image publication chỉ chạy ở trusted lane
- release có evidence rõ, không chỉ dựa vào logs

### Kiểm Tra Hạ Tầng

Files:

```text
.github/workflows/infra-ci.yml
.github/workflows/reusable-infra-ci.yml
```

Mục đích:

- validate Terraform và Helm
- chạy IaC security scanning
- chạy policy-as-code

Giá trị enterprise:

- infra risk được phát hiện trước apply
- Terraform/Helm có lane riêng

### Governance Nền Tảng

Files:

```text
.github/workflows/platform-ci.yml
.github/workflows/reusable-platform-ci.yml
policies/
```

Mục đích:

- validate workflow governance
- kiểm tra composite actions
- kiểm tra rules liên quan trust boundary

Giá trị enterprise:

- workflow/policy changes được coi là control-plane changes
- tránh sửa workflow nguy hiểm mà không bị phát hiện

## 3. CI Gateway Tổng Hợp Required Check

Repo dùng `CI Gateway / gateway` làm required check chính.

Lý do:

- backend/frontend/edge/nginx lane có thể skipped theo changed path
- nếu require trực tiếp từng job, GitHub có thể chờ missing check
- gateway luôn chạy và tổng hợp kết quả cuối

Flow:

```text
PR opened/synchronize
-> detect changed paths
-> chạy lane cần thiết
-> gateway tổng hợp
-> report CI Gateway / gateway
```

## 4. Sandbox Governance

Sandbox policy phân loại PR theo blast radius.

Các nhãn chính:

- `sandbox-recommended`: bot khuyến nghị deploy sandbox.
- `sandbox-required`: hard gate cho critical changes.
- `deploy-sandbox`: owner cho phép deploy sandbox thật.
- `sandbox-validated`: bot xác nhận sandbox apply/bootstrap/smoke pass.
- `skip-sandbox-approved`: owner waiver rõ ràng.
- `allow-self-approve`: review governance, không bypass sandbox.

Nguyên tắc:

```text
self-approve = review governance
deploy-sandbox = environment governance
skip-sandbox-approved = risk waiver governance
```

Không trộn ba quyết định này vào cùng một label.

## 5. Sandbox Auto Apply Và Auto Destroy

Auto apply chỉ chạy khi:

- PR cùng repo
- không draft
- actor/label trusted
- owner gắn `deploy-sandbox` hoặc `deploy-preview`
- CI gates liên quan đã xanh
- quota cho owner còn trống

Auto destroy chạy khi:

- PR closed/merged
- PR chuyển draft
- deploy label cuối cùng bị gỡ
- owner gắn `teardown-sandbox`
- janitor phát hiện sandbox quá hạn hoặc state lệch

Destroy chạy từ trusted workflow trên default branch, không chạy workflow code từ PR branch.

## 6. GitHub OIDC Và IAM Role Split

Repo dùng GitHub OIDC để assume AWS roles, không dùng long-lived IAM user keys.

Role legacy:

```text
Role-Sandbox
```

Role split theo nhiệm vụ:

```text
Role-Sandbox-Plan
Role-Sandbox-Apply
Role-Sandbox-Destroy
Role-Sandbox-AppDeploy
```

Ý nghĩa:

- plan chỉ cần quyền đọc
- apply cần quyền tạo/update sandbox infra
- destroy cần quyền xóa sandbox đúng scope
- appdeploy cần quyền bootstrap/deploy app vào EKS

`Role-Bootstrap` quản lý lớp nền móng như IAM roles, trust policy và state backend. Nếu sau này chọn Route53 thì role này cũng có thể quản lý hosted zone, ACM certificate, DNSSEC và query logging, nhưng đường mặc định hiện tại là Cloudflare DNS.

## 7. Terraform Bootstrap Là Source Of Truth

Sửa IAM trên AWS Console có thể chạy ngay nhưng dễ drift.

Flow chuẩn:

```text
PR đổi terraform/bootstrap
-> CI validate
-> merge master
-> owner chạy Terraform Bootstrap Apply
-> GitHub Environment bootstrap yêu cầu approval
-> workflow assume Role-Bootstrap
-> terraform apply cập nhật AWS
```

GitHub secret chỉ lưu ARN như con trỏ runtime. Quyền thật nằm trong IAM policy trên AWS, và policy đó nên được quản lý bằng Terraform.

## 8. Stable Public DNS Cho Edge Và Admin

Repo hỗ trợ stable DNS bằng:

- domain lấy từ GitHub Student Developer Pack
- Cloudflare DNS free
- ExternalDNS trong EKS với provider `cloudflare`
- Cloudflare API token đặt trong GitHub Secret và Kubernetes Secret
- Helm values `publicDns` và `publicTls`
- Route53/ACM là nhánh optional nếu sau này muốn AWS quản lý DNS/TLS

URL mong muốn:

```text
production: https://face.example.com
staging:    https://staging.face.example.com
sandbox:    https://sandbox-pr-123.face.example.com
```

Edge device không hardcode URL trong code. Edge đọc:

```text
API_BASE_URL
```

Chi tiết vận hành nằm ở:

```text
docs/public-dns-gitops-edge-operations.md
```

## 9. ArgoCD Và GitOps Promotion

Staging:

```text
merge master
-> App Release publish images lên GHCR
-> GitOps Staging Promotion resolve digest
-> update values-staging.yaml
-> commit [skip ci]
-> ArgoCD sync staging
```

Production:

```text
publish GitHub Release
-> GitOps Production Promotion chạy
-> environment production yêu cầu approval
-> owner/admin approve
-> workflow resolve digest
-> update values-production.yaml
-> ArgoCD thấy Git đổi nhưng không auto-sync production
-> trusted operator manual sync face-detector-production trong ArgoCD
```

Điểm quan trọng:

- ArgoCD sync theo Git, không theo tag mới trên GHCR.
- Production không nên dùng `latest`.
- values file nên dùng immutable digest.
- ArgoCD Application không dùng `project: default` lâu dài. Repo dùng AppProject riêng `face-detector` để giới hạn:
  - repo Git được phép sync
  - namespace đích
  - loại Kubernetes resource được phép tạo
  - không cho chart tự quản lý Secret ứng dụng
- Repo credential của ArgoCD ưu tiên GitHub App hoặc read-only deploy key. `ARGOCD_REPO_TOKEN` chỉ là fallback legacy, không phải đường vận hành khuyến nghị.

Flow bootstrap ArgoCD hiện tại:

```text
app-cd workflow chạy
-> tạo/cập nhật ArgoCD repo credential
   -> ưu tiên ARGOCD_GITHUB_APP_*
   -> nếu không có thì dùng ARGOCD_REPO_DEPLOY_KEY
   -> nếu không có nữa mới fallback ARGOCD_REPO_TOKEN
-> apply AppProject face-detector
-> apply Application staging/production
-> ArgoCD chỉ sync trong boundary của AppProject
```

Ý nghĩa enterprise:

- PAT rộng không còn là lựa chọn chính.
- Nếu dùng deploy key, key chỉ nên có quyền read-only đúng repo này.
- Nếu dùng GitHub App, installation chỉ nên cấp quyền read repository contents cho đúng repo.
- AppProject chặn việc Application vô tình sync sang namespace/repo/resource ngoài phạm vi thiết kế.

Hardening ArgoCD control plane:

```text
ArgoCD server
-> service type ClusterIP
-> không public expose UI mặc định
-> server.insecure=false
-> log format JSON
-> RBAC enabled
-> exec disabled
-> RBAC log enforcement enabled
-> notifications controller enabled
```

Production sync policy:

```text
staging/sandbox
-> auto sync, prune, selfHeal

production
-> không auto sync
-> AppProject có sync window deny auto toàn thời gian cho face-detector-production
-> manualSync=true
-> owner/admin approve GitHub production promotion trước
-> trusted operator sync thủ công trong ArgoCD sau
```

SSO/RBAC production:

- `ARGOCD_OIDC_CONFIG` là GitHub secret để bật OIDC config cho ArgoCD.
- `ARGOCD_ADMIN_RBAC_SUBJECTS` là GitHub variable dạng JSON list, ví dụ `["face-admins"]` hoặc `["admin@example.com"]`.
- Khi production có OIDC config, local admin user sẽ bị tắt để tránh dùng account mặc định lâu dài.
- Nếu chưa có OIDC config, local admin vẫn còn để tránh tự khóa khỏi cluster; đây là trạng thái bootstrap, không phải mục tiêu production lâu dài.

Notifications:

- `ARGOCD_NOTIFICATIONS_RECIPIENTS` là GitHub variable dạng JSON list, ví dụ `["slack:platform"]`.
- Controller notifications đã bật, nhưng chỉ gửi ra ngoài khi đã cấu hình recipients và service secret tương ứng.

## 10. Supply Chain Controls

Repo đã có các lớp evidence:

- SBOM
- provenance
- image signing
- attestation
- GHCR immutable SHA tags
- CodeQL/Trivy/Checkov integration

Mục tiêu là biết image nào được build từ commit nào, workflow nào, và evidence nào đi kèm.

## 11. Policy-As-Code

Policy nằm trong:

```text
policies/
```

Các nhóm policy:

- GitHub workflow governance
- composite action governance
- Terraform policy
- Kubernetes manifest policy
- exceptions data

Giá trị:

- rule nằm trong repo
- thay đổi rule đi qua PR
- CI có thể enforce hoặc advisory
- audit dễ hơn so với rule nằm rải rác trong workflow script

## 12. CODEOWNERS Và Solo Maintainer

Với solo maintainer:

- dùng CODEOWNERS làm metadata/audit layer
- không bật native code owner review gate nếu chưa có reviewer thứ hai
- custom policy có thể đọc CODEOWNERS để xác định owner
- self-approve phải explicit bằng label và actor trusted

Khi có team:

- bật code owner review cho control-plane paths
- tách team dev, devops, security
- hạn chế bypass actors

## 13. Trạng Thái Đã Implement

Đã có:

- lane split theo trust boundary
- explicit workflow permissions
- CI Gateway aggregator
- sandbox policy hard gate
- sandbox auto apply/destroy/janitor
- GitHub OIDC role assumption
- task-scoped sandbox role support
- Terraform bootstrap workflow có approval
- ArgoCD GitOps promotion bằng digest
- production promotion approval gate
- stable public DNS design bằng Cloudflare + ExternalDNS
- policy-as-code với Conftest/Rego
- Checkov/Trivy/security scans
- release evidence, SBOM, signing, attestation
- SHA-pinned external actions
- docs vận hành DNS/GitOps/edge/IAM roles

## 14. Việc Còn Có Thể Hardening Tiếp

- Xóa fallback `AWS_ROLE_SANDBOX_ARN` sau khi 4 scoped roles đã chạy ổn end-to-end.
- Chuyển thêm advisory IaC findings thành hard fail khi đã thống nhất exceptions.
- Thêm expiry date cho temporary exceptions.
- Verify signatures/attestations ở GitOps promotion hoặc deploy time.
- Bổ sung policy cho Helm, image metadata và release rules.
- Thêm GHCR image lifecycle cleanup.
- Hoàn thiện production DNS/TLS sau khi domain thật đã add vào Cloudflare, nameserver đã trỏ về Cloudflare và TLS path đã được chọn.

## 15. Bước Tiếp Theo Khuyến Nghị

1. Lấy domain qua GitHub Student Developer Pack và add vào Cloudflare.
2. Trỏ nameserver ở registrar về Cloudflare.
3. Tạo Cloudflare API token chỉ có `Zone:Read` và `DNS:Edit` cho đúng zone.
4. Set `FACE_DETECTOR_BASE_DOMAIN`, `FACE_DETECTOR_DNS_PROVIDER=cloudflare`, `CLOUDFLARE_ZONE_ID` và `CLOUDFLARE_API_TOKEN`.
5. Bật `FACE_DETECTOR_PUBLIC_DNS_ENABLED=true`.
6. Test sandbox qua stable DNS.
7. Chọn TLS path: ACM thủ công với DNS validation trong Cloudflare, hoặc cert-manager + Let's Encrypt bằng PR riêng.
8. Sau khi scoped roles ổn, xóa legacy sandbox role fallback.

## 16. Tổng Kết

Repo đã vượt qua mức CI/CD đơn giản. Hệ thống hiện có:

- trust boundary rõ ràng
- workflow permissions tường minh
- policy-as-code
- sandbox governance có audit
- OIDC thay cho IAM user keys
- GitOps promotion bằng digest
- DNS ổn định cho edge/admin
- release evidence và supply-chain controls

Điểm quan trọng nhất: governance không còn chỉ nằm trong thói quen vận hành. Nó đã được đưa vào workflow, policy, Terraform và tài liệu.
