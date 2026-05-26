# Playbook Chuyển Sang GitHub Rulesets Enterprise

Playbook này mô tả cách chuyển enforcement từ branch protection cũ sang GitHub Rulesets. Mục tiêu là tách rule cho workflow/policy changes khỏi rule cho app changes.

## Phạm Vi

- Branch mục tiêu: `master`, `main`, `production`
- Required check chung: `CI Gateway / gateway`
- Control plane do CODEOWNERS quản lý: `.github/workflows/**`, `.github/actions/**`, `policies/**`

## Giai Đoạn 1: Rulesets

Tạo hai branch ruleset. Bypass chỉ dành cho emergency break-glass identities.

### 1. Ruleset Bảo Mật Cao Cho Workflow Và Policy

Khuyến nghị:

- Target refs: `refs/heads/master`, `refs/heads/main`, `refs/heads/production`
- File conditions: `.github/workflows/**`, `.github/actions/**`, `policies/**`, `.github/CODEOWNERS`
- Require pull request before merging: bật
- Required approvals: `1`
- Require code owner review: bật nếu có ít nhất hai trusted humans
- Dismiss stale reviews: bật
- Require approval of the most recent reviewable push: bật
- Require conversation resolution: bật
- Restrict deletions: bật
- Required status checks: `CI Gateway / gateway`
- Bypass list: chỉ emergency identities

Với solo maintainer, có thể tắt native code owner review để tránh tự block. Khi có thêm reviewer tin cậy, bật lại.

### 2. Ruleset Cho Luồng Phát Triển App Code

Khuyến nghị:

- Target refs: `refs/heads/master`, `refs/heads/main`, `refs/heads/production`
- File conditions: `backend/**`, `frontend-admin/**`, `edge-client/**`, `nginx/**`, runtime app files
- Require pull request before merging: bật
- Required approvals: tùy team; solo maintainer có thể để `0`
- Dismiss stale reviews: bật nếu có review thật
- Require conversation resolution: bật
- Required status checks: `CI Gateway / gateway`

## Giai Đoạn 2: CI Gateway

Dùng một workflow tổng hợp luôn chạy trên PR. Workflow này quyết định lane nào cần chạy dựa trên changed paths.

File đã implement:

```text
.github/workflows/ci-gateway.yml
```

Hành vi:

- App paths thay đổi: chạy reusable app verification lane.
- Platform/workflow/policy paths thay đổi: chạy reusable platform governance lane.
- Infra paths thay đổi: chạy reusable infra verification lane.
- Luôn emit kết quả cuối cùng dưới context `CI Gateway / gateway`.

Cách này tránh tình trạng required check bị pending mãi vì job/domain tương ứng bị skip.

## Giai Đoạn 3: Tách Trách Nhiệm

Repo hiện tại là solo-maintainer. Khi cần audit-grade SoD thật sự, nên chuyển owner sang team identities:

```text
* @org/developers
.github/workflows/ @org/devops-leads
policies/ @org/security-team
docs/ @org/technical-writers
```

Ít nhất hai trusted humans nên có quyền review workflow/policy changes.

## Checklist Vận Hành

1. Bật Secret Scanning và Push Protection trong repository settings.
2. Tạo hai Rulesets như trên.
3. Chuyển required checks từ branch protection sang rulesets.
4. Set `CI Gateway / gateway` là required status check trong cả hai rulesets.
5. Giữ emergency bypass nhỏ nhất có thể và ghi lý do.
6. Test bằng ba PR:
   - docs-only PR
   - app-code PR
   - workflow/policy PR
