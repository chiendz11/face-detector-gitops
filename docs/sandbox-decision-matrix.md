# Ma Trận Quyết Định Sandbox

Tài liệu này giúp reviewer quyết định khi nào cần dùng sandbox PR tốn chi phí, và khi nào chỉ cần fast lane CI bình thường.

## Quy Tắc Mặc Định

- Sandbox là quyết định có chủ đích của reviewer/owner, không tự động deploy cho mọi PR.
- Label chính nên dùng là `deploy-sandbox`.
- `deploy-preview` vẫn được chấp nhận như alias tương thích.
- Mặc định dùng fast lane. Chỉ nâng lên sandbox khi blast radius đủ lớn.
- Sandbox auto-apply chỉ chạy cho PR cùng repo, không draft, và sau khi các lane verify liên quan đã xanh.
- `Sandbox Policy` tách recommendation khỏi enforcement:
  - heavy non-critical: bot gắn `sandbox-recommended`, không tự block merge.
  - critical: bot gắn `sandbox-required`, block merge cho đến khi có sandbox validation hoặc owner waiver.
- `deploy-sandbox` và `deploy-preview` chỉ thể hiện intent deploy. Chúng không phải waiver.

## Heavy Lane: Thường Nên Deploy Sandbox

Dùng `deploy-sandbox` khi PR có blast radius đáng kể và reviewer cần thấy hệ thống chạy tích hợp thật.

Ví dụ:

- thay đổi hành vi cross-service
- thay đổi ingress, image, hoặc service-to-service path
- thay đổi Dockerfile hoặc compose override có ảnh hưởng runtime
- thay đổi mà unit/integration/static check không đủ tạo confidence

Với các thay đổi này, bot có thể gắn `sandbox-recommended`. Owner/DevOps vẫn có thể merge sau khi required CI pass nếu quyết định sandbox không đáng chi phí.

## Critical Lane: Bắt Buộc Validation Hoặc Waiver

Critical changes phải được validation trong sandbox hoặc được owner waiver rõ ràng.

Ví dụ:

- database migrations
- workflow, policy, Terraform
- IAM, networking, authentication
- reverse proxy hoặc runtime hardening
- deployment contract có thể ảnh hưởng staging/production
- DNS, Cloudflare, Route53 optional, ArgoCD, ExternalDNS, hoặc GitHub OIDC trust

Kết quả hợp lệ:

- owner gắn `deploy-sandbox` hoặc `deploy-preview`, auto-apply chạy, hệ thống refresh `sandbox-validated`
- owner gắn `skip-sandbox-approved` để chấp nhận rủi ro

`allow-self-approve` không đủ để pass gate này.

## Fast Lane: Không Gắn Sandbox Label Mặc Định

Giữ PR ở normal CI path nếu thay đổi nhỏ và blast radius thấp.

Ví dụ:

- logic trong một service/module
- UI/UX không đổi backend, ingress, runtime contract
- test, docs, refactor nội bộ
- dependency update nhỏ, scope hẹp, CI xanh

## Checklist Cho Reviewer

- Xác nhận PR thật sự cần integrated runtime validation trước khi tiêu sandbox capacity.
- Nếu `Sandbox Policy` fail với `sandbox-required`, chọn một trong ba hướng:
  - deploy sandbox và chờ `sandbox-validated`
  - gắn `skip-sandbox-approved`
  - tách PR để isolate critical files
- Kiểm tra các lane `App CI`, `Repo Security`, `Infra CI`, `Platform CI`, `Terraform PR Plan` đã xanh trước khi chờ auto-apply.
- Tôn trọng quota một sandbox cho mỗi owner. Nếu owner đã có sandbox active, đóng hoặc destroy sandbox cũ trước.
- Gỡ deploy label khi không cần sandbox nữa.
- Dùng protected manual DevOps lane cho thí nghiệm `devops/*`, workflow, IAM, hoặc trust-boundary thay vì label reviewer thông thường.

## Lifecycle Và Governance

- Auto-destroy là bắt buộc.
- PR sandbox bị destroy khi PR close, chuyển draft, hoặc gỡ deploy label cuối cùng.
- `sandbox-active` là operational state, không phải reviewer intent.
- `sandbox-validated` là system state cho PR head hiện tại.
- `skip-sandbox-approved` là owner waiver, nên hiếm và phải visible trong PR labels/artifacts.
- Sandbox là môi trường review tạm thời, không phải shared test stack lâu dài.
- Janitor cleanup sandbox quá hạn, PR đã đóng/draft, hoặc có `teardown-sandbox` trusted. Janitor không được destroy sandbox đang mở chỉ vì schedule nightly.

## Quy Tắc Escalation

Nếu một thay đổi vừa chạm application surface vừa chạm trusted control plane, hãy ưu tiên lane nặng hơn: chạy sandbox và yêu cầu approval/protection phù hợp.
