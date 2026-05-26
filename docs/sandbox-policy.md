# Sandbox Policy

Tài liệu này mô tả custom governance gate tên `Sandbox Policy` cho pull request.

Mục tiêu của policy này là tách rõ ba quyết định khác nhau:

- có cần review bypass hay không
- có cần deploy sandbox thật hay không
- có chấp nhận rủi ro để merge không deploy sandbox hay không

## Mục Tiêu

- Giữ các thay đổi app bình thường chạy nhanh.
- Bắt buộc validation gần production cho các thay đổi chạm control plane hoặc hạ tầng quan trọng.
- Không trộn `self-approve`, `deploy-sandbox`, và `risk waiver` vào cùng một nhãn.
- Luôn có audit trail qua label, `report.json`, PR comment và workflow artifact.

## Các Lane

### Fast Lane

Áp dụng cho thay đổi local, ít blast radius.

Ví dụ:

- sửa logic nhỏ trong một service
- sửa UI không đụng backend contract
- thêm test
- sửa tài liệu

Kết quả: `Sandbox Policy` pass.

### Heavy Non-Critical Lane

Áp dụng cho thay đổi rộng hơn nhưng chưa chạm vùng hạ tầng/control-plane nguy hiểm.

Bot có thể gắn:

```text
sandbox-recommended
```

Nhãn này chỉ là khuyến nghị. Nó không tự block merge.

### Heavy Critical Lane

Áp dụng cho thay đổi chạm vùng quan trọng.

Bot gắn:

```text
sandbox-required
```

Khi đó PR bị block cho đến khi có một trong hai điều kiện:

- sandbox được deploy và validation pass, rồi bot gắn `sandbox-validated`
- owner gắn waiver rõ ràng bằng `skip-sandbox-approved`

Critical paths gồm:

- `.github/workflows/**`
- `.github/actions/**`
- `policies/**`
- Terraform
- Helm/deploy manifests
- ingress/reverse proxy
- database migrations
- IAM/network/auth
- script evaluator của sandbox policy

## Ý Nghĩa Các Label

- `allow-self-approve`: owner chủ động bật review governance bypass. Không bypass `sandbox-required`.
- `sandbox-recommended`: bot khuyến nghị deploy sandbox cho PR heavy non-critical.
- `sandbox-required`: bot hard-gate PR critical. Cần sandbox validation hoặc waiver.
- `deploy-sandbox` / `deploy-preview`: owner thể hiện intent muốn deploy sandbox thật. Đây không phải waiver.
- `sandbox-validated`: bot gắn sau khi sandbox apply + bootstrap/smoke validation pass cho đúng PR head hiện tại.
- `skip-sandbox-approved`: owner chấp nhận rủi ro, merge không deploy sandbox. Dùng hiếm và phải visible.
- `sandbox-active`: trạng thái vận hành để quota/cleanup biết sandbox đang tồn tại. Reviewer không tự gắn nhãn này.

## Trusted Label

Label do người gắn chỉ hợp lệ khi:

- latest label event actor là `github.repository_owner`
- actor không phải bot

Các label thuộc nhóm này:

```text
allow-self-approve
deploy-sandbox
deploy-preview
skip-sandbox-approved
```

Label do hệ thống gắn chỉ hợp lệ khi được `github-actions[bot]` gắn cho đúng PR head.

Các label thuộc nhóm này:

```text
sandbox-recommended
sandbox-required
sandbox-validated
ready-for-deploy
```

## Điều Kiện Pass

`Sandbox Policy` pass khi một trong các trường hợp sau đúng:

- PR thuộc fast lane.
- PR heavy nhưng non-critical, chỉ có `sandbox-recommended`.
- PR critical có trusted `sandbox-validated`.
- PR critical có trusted `skip-sandbox-approved`.

Policy không pass chỉ vì tồn tại các label sau:

```text
deploy-sandbox
deploy-preview
allow-self-approve
```

Lý do: ba nhãn này có ý nghĩa khác nhau. `allow-self-approve` là review governance, còn sandbox là environment governance.

## Auto-Apply Sandbox

Sandbox auto-apply chỉ đủ điều kiện khi:

- PR cùng repo, không phải fork.
- PR không ở draft.
- PR không phải Dependabot.
- Có trusted `deploy-sandbox` hoặc `deploy-preview`.
- PR chưa có `sandbox-validated` hợp lệ.
- Không có trusted `skip-sandbox-approved`.
- Các CI gate cần thiết đã xanh.

Với PR critical, auto-apply có thể chạy trong khi `Sandbox Policy` vẫn đang fail. Policy chỉ pass sau khi workflow deploy xong và bot refresh `sandbox-validated`.

## Report

Evaluator ghi file:

```text
.artifacts/sandbox-policy/report.json
```

Các field quan trọng:

- `classification`
- `riskLevel`
- `sandboxRecommended`
- `sandboxRequired`
- `deployLabelTrusted`
- `sandboxValidatedTrusted`
- `skipSandboxTrusted`
- `autoApplyEligible`
- `blockingReasons`
- `matchedOwners`
- `approvers`

`block: true` là tín hiệu để check `Sandbox Policy` fail và block merge.

## Vận Hành

- Nếu muốn policy thật sự enforce merge, require check `Sandbox Policy / evaluate` trên `master`.
- Giữ `deploy-sandbox` và `skip-sandbox-approved` owner-only.
- Gỡ deploy label khi không cần sandbox nữa.
- Destroy sandbox phải xóa stale `sandbox-validated`.
- Với solo project, `github.repository_owner` là ranh giới trusted human hợp lý.
- Với repo nhiều team, thay `github.repository_owner` bằng allowlist, environment approver, hoặc team authorization.
