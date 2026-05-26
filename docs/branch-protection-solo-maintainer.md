# Bảo Vệ Branch Cho Solo Maintainer

Repo này dùng `CODEOWNERS` và custom policy checks như một lớp metadata/audit governance. Với dự án solo maintainer, không nên bật native GitHub review enforcement nếu chưa có reviewer thứ hai đáng tin cậy.

## Các Gate Merge Khuyến Nghị

Nên require các check sau trên `master`:

```text
CI Gateway / gateway
Sandbox Policy / evaluate
Repo Security / secret-scan
```

Nên bật các rule repository/branch sau:

- Require status checks to pass before merging.
- Require branches to be up to date before merging.
- Restrict direct pushes vào protected branch.
- Allow auto-merge sau khi required checks pass.

Với solo maintainer, nên tắt các native review rule này:

- Require pull request reviews before merging.
- Require review from Code Owners.

Lý do: nếu chỉ có một owner, native review gate có thể tự block chính owner dù CI và custom governance đã pass.

## Vai Trò Của CODEOWNERS

Trong repo solo, hãy coi `CODEOWNERS` là metadata và audit layer, không phải enforcement layer native của GitHub.

Nên dùng exact username:

```text
* @your-username
```

Không nên dùng team ownership cho self-approve bypass path:

```text
* @org/team
```

Custom sandbox-policy parser nên tiếp tục ignore team ownership khi quyết định self-approval. Cách này giữ scope bypass nhỏ và tránh tình huống thành viên team trong tương lai tự approve PR của chính họ thông qua team membership.

## CI Theo Domain

Enterprise-grade CI không nên dùng một app check khổng lồ cho mọi PR. Nếu chỉ đổi `edge-client/**`, PR không nên bị block bởi image scan của backend, frontend-admin hoặc nginx nếu những domain đó không đổi.

Nên dùng lane theo domain phía sau một gateway chung:

- `backend/**`: backend lint, tests, dependency checks, backend image checks.
- `frontend-admin/**`: frontend tests, build, dependency checks, frontend image checks.
- `edge-client/**`: edge-client tests, dependency checks, edge image checks.
- `nginx/**`: nginx image checks.
- Shared app files như compose files, image catalog, app CI workflows: chạy broader app lane.

Branch protection nên require aggregator ổn định:

```text
CI Gateway / gateway
```

Không nên require trực tiếp từng job domain, vì các job đó có thể skipped khi path tương ứng không đổi. Required check bị skipped/missing có thể làm PR pending hoặc blocked sai.

## Kiểm Tra Đầy Đủ

Full app image scans và compose-backed smoke tests nên chạy khi shared app contracts thay đổi. Chúng cũng nên chạy ở release hoặc scheduled workflows.

Không cần block một PR single-domain không liên quan bằng full scan của toàn bộ app.

## Governance Cho Self-Approve

Self-approve mặc định phải tắt. Bypass chỉ hợp lệ khi:

- actor là repository owner
- owner chủ động gắn governance label
- label event trusted và audit được
- policy report ghi actor, trusted label state, matched owners, approvers

Cách này giúp solo maintainer có flow merge sạch mà vẫn giữ automated checks và auditability.
