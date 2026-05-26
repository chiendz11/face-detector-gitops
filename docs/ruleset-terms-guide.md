# Giải Thích Thuật Ngữ Ruleset, Branch Protection Và CI

Tài liệu này giải thích các thuật ngữ hay gặp khi debug GitHub Rulesets, Branch Protection và CI checks trong repo `Face_dectector`.

## 1. Nhóm Khái Niệm Nền Tảng

### Ruleset

Ruleset là bộ quy tắc bảo vệ branch hoặc tag.

Ví dụ: ruleset áp vào `master` có thể yêu cầu PR, required checks, review, hoặc chặn direct push.

### Branch Protection

Branch Protection là cơ chế bảo vệ branch kiểu cũ của GitHub.

Ruleset là cơ chế mới hơn, linh hoạt hơn. Repo nên dùng Ruleset cho policy enterprise, nhưng vẫn cần hiểu Branch Protection vì UI GitHub có thể hiển thị cả hai.

### Pull Request

Pull request, thường gọi là PR, là đề xuất merge code từ branch này vào branch khác.

Review, CI, security scan và policy checks thường chạy trên PR.

## 2. Nhóm Check Và Trạng Thái

### Status Check

Status check là kết quả kiểm tra gắn vào commit hoặc PR.

Ví dụ:

```text
CI Gateway / gateway
Sandbox Policy / evaluate
Repo Security / secret-scan
```

### Required Status Check

Required status check là check bắt buộc phải pass trước khi merge.

Trong repo này, context quan trọng nhất nên require là:

```text
CI Gateway / gateway
```

### Context Name

Context name là tên chính xác của check mà ruleset dùng để so khớp.

Tên này phải match exact. Nếu ruleset require `CI Gateway / gateway` nhưng workflow thật report `gateway`, GitHub sẽ chờ một check không bao giờ xuất hiện.

### Check Run

Check run là một lần chạy của một job.

Ví dụ: job `gateway` trong workflow `CI Gateway`.

### Check Suite

Check suite là tập hợp các check run thuộc một lần workflow được trigger.

### Expected

`Expected` nghĩa là GitHub đang chờ check context được report cho commit hiện tại.

Nếu check bị expected mãi, thường là do:

- required context name sai
- workflow không trigger cho changed path đó
- job bị skip nhưng lại bị require trực tiếp
- commit mới reset status

### Pending, In Progress, Queued

- `Pending`: chưa có kết quả cuối.
- `In progress`: đang chạy.
- `Queued`: đang chờ runner.

### Success, Failure, Cancelled, Skipped

- `Success`: pass.
- `Failure`: fail.
- `Cancelled`: bị hủy.
- `Skipped`: bị bỏ qua theo điều kiện `if` hoặc path filter.

`Skipped` không nhất thiết là lỗi. Nhưng không nên require trực tiếp một job có thể skipped theo domain.

## 3. Nhóm Review Và Merge Policy

### Required Approving Review Count

Số lượng approve tối thiểu cần có trước khi merge.

Ví dụ `1` nghĩa là cần ít nhất một reviewer hợp lệ approve.

### Code Owner Review

Yêu cầu review từ người hoặc team được khai báo trong `CODEOWNERS` cho file thay đổi.

Với solo maintainer, native GitHub code owner review có thể gây self-block. Khi đó nên dùng CODEOWNERS làm metadata cho custom policy thay vì native enforcement.

### Dismiss Stale Reviews On Push

Nếu có commit mới, approve cũ bị vô hiệu và cần review lại.

### Required Review Thread Resolution

Tất cả thread comment đang open phải được resolve trước khi merge.

### Mergeable Và Blocked

- `Mergeable`: về mặt kỹ thuật có thể merge.
- `Blocked`: đang bị rule, review, required check, hoặc sandbox policy chặn.

## 4. Nhóm Tham Số Ruleset Nâng Cao

### strict_required_status_checks_policy

- `true`: branch phải up-to-date rất chặt với base trước khi merge.
- `false`: linh hoạt hơn, giảm tình trạng pending/reset quá thường xuyên.

### do_not_enforce_on_create

Quy định có enforce ngay lúc tạo branch hay không.

### bypass_actors

Danh sách actor được phép bypass ruleset.

Nên giới hạn cực hẹp và chỉ dùng cho break-glass.

### bypass_mode = always

Actor trong bypass list có thể bỏ qua rule khi cần. Đây là quyền nhạy cảm và phải có trách nhiệm audit.

## 5. Nhóm Event Và Trigger GitHub Actions

### pull_request

Workflow chạy khi PR có event như `opened`, `synchronize`, `reopened`.

Đây là context an toàn hơn cho code từ PR.

### pull_request_target

Workflow chạy trong context của base repository. Context này có quyền cao hơn nên phải cẩn thận.

Repo này dùng `pull_request_target` cho các parent workflow cần policy gate, label governance, hoặc sandbox orchestration.

### workflow_call

Workflow có thể được gọi lại từ workflow khác.

Repo này dùng reusable workflows để giữ trusted workflow definition trên default branch.

## 6. Hiểu Nhầm Phổ Biến

### Đã xanh ở dưới nhưng trên vẫn pending

Nguyên nhân thường gặp:

- UI GitHub sync chậm
- check context vừa reset do commit mới
- ruleset require một context khác với context thật

Xác minh bằng:

```powershell
gh pr checks <pr-number> --repo chiendz11/Face_dectector
```

### Pending Không Đồng Nghĩa Fail

`Pending` chỉ nghĩa là chưa có kết quả cuối. Nó khác `Failure`.

### Skipped Không Đồng Nghĩa Lỗi

Job skipped có thể là đúng nếu changed path không thuộc domain của job đó.

Vì vậy branch protection nên require `CI Gateway / gateway`, không require từng job domain như backend/frontend/edge/nginx.

## 7. Mapping Nhanh Cho Repo

- Required check chính: `CI Gateway / gateway`
- App lane: `verify-app`
- Platform lane: `verify-platform`
- Infra lane: `verify-infra`
- Sandbox policy: `Sandbox Policy / evaluate`
- Secret scan: `Repo Security / secret-scan`
- Final gate: `gateway`

## 8. Checklist Debug Pending Lâu

1. Xem trạng thái backend checks:

```powershell
gh pr checks <pr-number> --repo chiendz11/Face_dectector
```

2. Xem rollup và merge state:

```powershell
gh pr view <pr-number> --repo chiendz11/Face_dectector --json statusCheckRollup,mergeStateStatus
```

3. Nếu nghi required context sai, xem check-runs của head SHA:

```text
GET /repos/<owner>/<repo>/commits/<sha>/check-runs
```

4. Nếu backend xanh nhưng UI chưa cập nhật, hard refresh trang PR.

5. Nếu bị block bởi review, xử lý approval hoặc dùng admin bypass theo policy đã định.
