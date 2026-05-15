# Sandbox Policy (Enterprise)

Tài liệu này mô tả policy và flow sandbox dùng trong repo.

## Mục tiêu
- Phân loại PR theo rủi ro (LIGHT / HEAVY).
- Áp dụng governance mạnh mẽ cho các thay đổi nhạy cảm (blocking).
- Cho phép developer velocity cho thay đổi low-risk (fast path).
- Duy trì audit trail và khả năng override có kiểm soát.

## Định nghĩa
- LIGHT: thay đổi có blast radius thấp, rollback dễ, không ảnh hưởng shared systems.
  - Ví dụ: `frontend/*`, `backend/api/*`, `tests/*`, docs, README.
  - Flow: CI + security → nếu pass thì merge được; sandbox optional.

- HEAVY: thay đổi có blast radius lớn, ảnh hưởng infra, CI/CD, mạng, IAM, DB migrations.
  - Ví dụ: `terraform/**`, `.github/workflows/**`, `backend/alembic/**`, `iam/**`, `network/**`.
  - Flow: governance checks (approvals/CODEOWNERS) → sandbox verify → merge.

## Blocking vs Advisory
- Blocking (governance core): `report.block == true` (tuyệt đối không deploy). Các nguyên nhân:
  - Thiếu approvals / CODEOWNERS trên heavy paths.
  - Chạm critical paths (terraform prod, db migrations, IAM/network, auth, ...).
  - Evaluator runtime error (`decision: "error"`).
  - Khi `block=true`, CI job `Sandbox Policy` sẽ fail và merge bị chặn (branch protection có thể áp dụng).

- Advisory: `decision` có thể là `pass|fail|advisory`; bot chỉ **recommend** `ready-for-deploy` khi `decision == "pass"` và CI gates OK. Advisory không ngăn merge.

## Labels và semantics
- `deploy-sandbox` / `deploy-preview`: human opt-in label — bắt buộc để auto-apply sandbox; chỉ chấp nhận khi label do `actor.type == 'User'` (không phải bot).
- `ready-for-deploy`: bot label chỉ để chỉ ra PR đã sẵn sàng (bot thêm khi `decision == 'pass'` và CI gates OK).
- `sandbox-active`: áp dụng khi sandbox đã được apply (dùng cho quota enforcement).
- `sandbox-exempt`: (optional) label cho phép bypass policy — chỉ cho phép do admin/CODEOWNERS; nếu dùng, phải log và audit.

## Report schema (versioned)
- File: `.artifacts/sandbox-policy/report.json`
- Trường tối thiểu:
```json
{
  "version": "1",
  "timestamp": "2026-05-14T12:00:00Z",
  "branch": "feature/xyz",
  "changedFiles": ["..."],
  "classification": "heavy",
  "decision": "pass|fail|advisory|error",
  "block": false,
  "blockingReasons": [],
  "touchesCriticalPaths": false,
  "approvers": [],
  "matchedOwners": [],
  "reasonGroups": [],
  "summary": "..."
}
```
- Lưu ý: `block==true` luôn có hiệu lực chặn deploy.

## Override & Governance
- Nếu team muốn override blocking behavior:
  - Thiết lập danh sách admin/CODEOWNERS được phép thêm `sandbox-exempt` hoặc trực tiếp approve PR.
  - Override phải được logged (comment + artifact) và ghi rõ lý do.

## Operational recommendations
- Add branch protection to require `Sandbox Policy` check for `master` (optional, nếu muốn blocking enforced).
- Maintain list of bot accounts for actor checks (e.g. `github-actions[bot]`, `dependabot[bot]`).
- Implement alerts for `decision == 'error'` (Slack/email) and surface artifact link.
- Add integration tests to validate full flow (light/heavy/blocking/override).

## Who to contact
- Platform/DevOps team: owner of sandbox policy & infra automation.

---
Document version: 1
