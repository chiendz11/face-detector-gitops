# Ruleset Terms Guide (Easy English -> Vietnamese)

Tai lieu nay giai thich cac thuat ngu tieng Anh lien quan den GitHub Rulesets, Branch Protection va CI checks trong repo Face_dectector.

## 1) Nhom khai niem nen tang

### Ruleset
- Nghia: Bo quy tac bao ve branch (nhu master/main).
- Trong repo nay: Co 2 ruleset chinh la Shield va Flow.

### Branch protection
- Nghia: Co che chan merge neu chua dat dieu kien.
- Luu y: Ruleset la cach moi/manh hon de thay the branch protection co dien.

### Pull request (PR)
- Nghia: De xuat gop code tu branch A vao branch B.
- Quy tac review/check thuong duoc ap dung tren PR.

## 2) Nhom check va trang thai

### Status check
- Nghia: Ket qua kiem tra bat buoc truoc khi merge (CI, security, policy...).

### Required status check
- Nghia: Check bat buoc phai dat trang thai hop le (thuong la success).
- Trong repo nay: Context duoc require la CI Gateway / gateway.

### Context name
- Nghia: Ten check dung de ruleset so khop.
- Cuc ky quan trong: Match theo ten chinh xac (exact match), khong match mo ho.

### Check run
- Nghia: Mot lan chay cua 1 job.
- Vi du: job gateway trong workflow CI Gateway.

### Check suite
- Nghia: Tap hop cac check run cua mot lan kich hoat workflow.

### Expected
- Nghia: Ruleset dang doi check context duoc report cho commit hien tai.
- Thuong xuat hien khi workflow vua duoc trigger.

### Pending / In progress / Queued
- Pending: Dang chua xong.
- In progress: Dang chay.
- Queued: Dang cho runner tai nguyen.

### Success / Failure / Cancelled / Skipped
- Success: Dat.
- Failure: Khong dat.
- Cancelled: Bi huy.
- Skipped: Khong can chay (do dieu kien if/path).

## 3) Nhom review va merge policy

### Required approving review count
- Nghia: So luong approve toi thieu.
- Vi du: 1 = can it nhat 1 nguoi co quyen write approve.

### Code owner review
- Nghia: Can review tu nguoi duoc gan trong CODEOWNERS cho file bi thay doi.

### Dismiss stale reviews on push
- Nghia: Neu co commit moi, approve cu bi vo hieu va can review lai.

### Required review thread resolution
- Nghia: Tat ca thread comment dang open phai duoc resolve.

### Mergeable vs Blocked
- Mergeable: Co the merge ve mat ky thuat.
- Blocked: Dang bi policy chan (review/check/ruleset).

## 4) Nhom ruleset tham so nang cao

### strict_required_status_checks_policy
- true: Yeu cau branch phai up-to-date rat chat voi base truoc merge.
- false: Linh hoat hon, giam tinh trang UI bao pending tre.

### do_not_enforce_on_create
- Nghia: Co bo qua enforce ngay luc tao branch/PR hay khong.

### bypass_actors
- Nghia: Nhom/role duoc phep bypass ruleset.
- Trong repo nay: Admin role co bypass_mode = always.

### bypass_mode = always
- Nghia: Co the merge bo qua cac rule khi can (co trach nhiem).

## 5) Nhom event va trigger Actions

### pull_request
- Nghia: Workflow chay khi PR co su kien (opened, synchronize, reopened...).

### pull_request_target
- Nghia: Chay trong context cua base repo (nhay cam hon ve security).
- Thuong dung cho automation can quyen cao hon, vi du auto-merge Dependabot.

### workflow_call
- Nghia: Workflow tai su dung duoc goi tu workflow khac.

## 6) Cac hieu nham pho bien

### Hieu nham 1: "Da thay xanh o duoi, sao tren van pending?"
- Nguyen nhan thuong gap: Do tre dong bo UI hoac check context vua duoc reset theo commit moi.
- Cach xac minh nhanh: dung gh pr checks <pr> de xem trang thai backend thuc.

### Hieu nham 2: "Pending la do fail"
- Khong dung. Pending chi la chua hoan tat report cho context required.

### Hieu nham 3: "Skipped la loi"
- Khong dung. Skipped co the la hanh vi mong doi theo dieu kien if/path.

## 7) Mapping nhanh cho repo Face_dectector

- Required check chinh cho ruleset: CI Gateway / gateway
- App lane: verify-app (co the skipped neu khong touch app files)
- Platform lane: verify-platform
- Infra lane: verify-infra (co the skipped neu khong touch infra files)
- Final gate: gateway (tong hop ket qua va enforce)

## 8) Checklist debug nhanh khi thay pending lau

1. Xac minh backend check:
   - gh pr checks <pr-number> --repo chiendz11/Face_dectector
2. Xem rollup chi tiet:
   - gh pr view <pr-number> --json statusCheckRollup,mergeStateStatus
3. Neu can, xem check-runs tren dung head SHA:
   - GET /commits/<sha>/check-runs
4. Neu backend xanh ma UI con tre:
   - hard refresh PR page
5. Neu bi block boi review (khong phai check):
   - xu ly approve hoac dung admin bypass (theo chinh sach team)
