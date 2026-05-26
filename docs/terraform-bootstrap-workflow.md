# Workflow Terraform Bootstrap

`terraform/bootstrap` quản lý lớp nền móng mà các workflow khác phụ thuộc vào.

Lớp này gồm:

- S3 bucket lưu Terraform remote state.
- DynamoDB table dùng làm lock table cho Terraform state.
- GitHub OIDC IAM roles và permission policies cho sandbox workflows.
- `Role-Bootstrap`, tức role được phép cập nhật chính lớp bootstrap.
- IAM/state foundation cho các workflow khác. Route53 hosted zone, wildcard ACM certificate, DNSSEC và DNS query logging chỉ là nhánh optional nếu bạn chọn AWS Route53 thay vì Cloudflare DNS.

Runbook tiếng Việt đầy đủ về bootstrap, DNS ổn định, ArgoCD, edge device config và task-scoped IAM roles nằm ở:

```text
docs/public-dns-gitops-edge-operations.md
```

## Vì Sao Bootstrap Nhạy Cảm?

Bootstrap kiểm soát IAM và Terraform state. Nếu cấu hình sai, các workflow khác có thể mất quyền deploy hoặc có quyền quá rộng.

Vì vậy local `terraform apply` nên được coi là break-glass path. Flow chuẩn là chạy qua GitHub Actions:

```text
Actions
-> Terraform Bootstrap Apply
-> Run workflow
```

## Cấu Hình GitHub Cần Có

Tạo GitHub Environment:

```text
bootstrap
```

Environment này nên yêu cầu owner approval trước khi job được chạy.

Các secret hoặc variable cần cấu hình:

```text
AWS_ROLE_BOOTSTRAP_ARN
AWS_REGION
TF_STATE_BUCKET
TF_STATE_LOCK_TABLE
TF_STATE_REGION
```

`AWS_ROLE_BOOTSTRAP_ARN` phải trỏ tới IAM role do `terraform/bootstrap` quản lý, thường là:

```text
Role-Bootstrap
```

## Flow Bình Thường

```text
PR thay đổi terraform/bootstrap hoặc bootstrap workflow
-> CI validate Terraform syntax/contracts
-> PR merge vào master
-> owner chạy Terraform Bootstrap Apply với command=plan
-> owner xem plan output
-> owner chạy Terraform Bootstrap Apply với command=apply và confirm_apply=apply-bootstrap
-> GitHub Environment bootstrap yêu cầu owner approval
-> workflow assume AWS_ROLE_BOOTSTRAP_ARN
-> terraform/bootstrap apply cập nhật AWS IAM/state foundation
```

Workflow luôn checkout trusted default branch. Nếu dispatch từ ref khác, workflow sẽ fail. Workflow này không fallback sang sandbox, staging hoặc production roles.

## Bootstrap Lần Đầu

Lần đầu tiên tạo Terraform state backend và `Role-Bootstrap` có thể vẫn cần admin credentials từ máy tin cậy.

Sau lần đầu, các thay đổi tiếp theo nên đi qua workflow `Terraform Bootstrap Apply` để có:

- PR review
- CI validation
- Git history
- GitHub Environment approval
- audit trail rõ ràng

## Khi Nào Cần Chạy Bootstrap?

Chạy bootstrap khi thay đổi các thành phần nền móng như:

- Terraform state bucket hoặc lock table.
- GitHub OIDC trust policy.
- IAM role/policy cho sandbox split roles.
- Role-Bootstrap.
- IAM role hoặc trust policy.
- Terraform state backend.
- Route53 hosted zone, ACM certificate, DNSSEC hoặc DNS query logging nếu đang dùng nhánh Route53 optional.

Với hướng hiện tại `FACE_DETECTOR_DNS_PROVIDER=cloudflare`, việc add domain vào Cloudflare, đổi nameserver và tạo Cloudflare API token không cần `terraform/bootstrap apply`. Bạn chỉ cần set GitHub variables/secrets rồi để `terraform/eks` cài ExternalDNS provider Cloudflare.

Không cần chạy bootstrap cho thay đổi app code thông thường.
