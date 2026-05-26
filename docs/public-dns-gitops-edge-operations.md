# Vận Hành Public DNS, GitOps, Edge Device Và IAM Role

Tài liệu này mô tả cách vận hành domain công khai ổn định cho hệ thống Face Detector.

Hướng hiện tại của repo là:

```text
GitHub Student Pack domain
-> Cloudflare DNS free
-> ExternalDNS trong EKS
-> AWS LoadBalancer thật
-> Edge device dùng API_BASE_URL ổn định
```

Route53 vẫn có thể được giữ như một nhánh optional trong Terraform, nhưng không còn là đường mặc định. Với solo project và domain miễn phí từ GitHub Student Developer Pack, Cloudflare DNS là lựa chọn hợp lý hơn vì không cần trả phí hosted zone Route53.

## 1. Mục Tiêu

Mục tiêu của stable public DNS là không để edge device, admin UI, staging hoặc sandbox phụ thuộc vào hostname ngẫu nhiên của LoadBalancer.

Không nên dùng lâu dài:

```text
http://a1b2c3d4e5f6.ap-southeast-1.elb.amazonaws.com
```

Nên dùng:

```text
production: https://face.example.com
staging:    https://staging.face.example.com
sandbox:    https://sandbox-pr-130.face.example.com
```

Trong đó `face.example.com` là domain hoặc subdomain bạn lấy từ GitHub Student Pack và quản lý DNS bằng Cloudflare.

## 2. Flow DNS Chuẩn

Flow vận hành với Cloudflare:

```text
1. Lấy domain miễn phí từ GitHub Student Pack.
2. Add domain đó vào Cloudflare.
3. Trỏ nameserver ở registrar về Cloudflare nameservers.
4. Tạo Cloudflare API token chỉ có quyền sửa DNS của đúng zone.
5. Set GitHub variables/secrets.
6. Terraform EKS cài ExternalDNS provider cloudflare.
7. Workflow infrastructure tạo Kubernetes Secret chứa Cloudflare token.
8. Helm chart app gắn annotation hostname lên Service nginx.
9. ExternalDNS đọc annotation và tạo/cập nhật DNS record trong Cloudflare.
10. Edge device dùng API_BASE_URL trỏ tới stable hostname.
```

Điểm quan trọng:

- Cloudflare là DNS source of truth.
- Terraform không cần tạo Route53 hosted zone.
- Cloudflare API token không được hardcode trong repo.
- Cloudflare API token không nên đưa vào Terraform state.
- ExternalDNS chỉ được phép quản lý domain đã khai báo bằng `domainFilters`.

## 3. GitHub Variables Và Secrets

Repository variables:

```text
FACE_DETECTOR_BASE_DOMAIN
FACE_DETECTOR_DNS_PROVIDER
FACE_DETECTOR_PUBLIC_DNS_ENABLED
FACE_DETECTOR_PUBLIC_TLS_ENABLED
CLOUDFLARE_ZONE_ID
```

Repository secret:

```text
CLOUDFLARE_API_TOKEN
```

Ví dụ set bằng `gh cli`:

```powershell
gh variable set FACE_DETECTOR_BASE_DOMAIN --repo chiendz11/Face_dectector --body "face.example.com"
gh variable set FACE_DETECTOR_DNS_PROVIDER --repo chiendz11/Face_dectector --body "cloudflare"
gh variable set FACE_DETECTOR_PUBLIC_DNS_ENABLED --repo chiendz11/Face_dectector --body "true"
gh variable set FACE_DETECTOR_PUBLIC_TLS_ENABLED --repo chiendz11/Face_dectector --body "false"
gh variable set CLOUDFLARE_ZONE_ID --repo chiendz11/Face_dectector --body "<cloudflare-zone-id>"
gh secret set CLOUDFLARE_API_TOKEN --repo chiendz11/Face_dectector --body "<cloudflare-api-token>"
```

Ý nghĩa:

- `FACE_DETECTOR_BASE_DOMAIN`: domain gốc của hệ thống, ví dụ `face.example.com`.
- `FACE_DETECTOR_DNS_PROVIDER`: provider cho ExternalDNS. Mặc định nên là `cloudflare`.
- `FACE_DETECTOR_PUBLIC_DNS_ENABLED`: bật stable hostname.
- `FACE_DETECTOR_PUBLIC_TLS_ENABLED`: bật TLS termination ở AWS LoadBalancer nếu đã có ACM certificate phù hợp.
- `CLOUDFLARE_ZONE_ID`: ID của zone Cloudflare. Đây không phải secret, nhưng nên để trong GitHub variable.
- `CLOUDFLARE_API_TOKEN`: token nhạy cảm, phải để trong GitHub secret.

## 4. Cloudflare API Token Nên Có Quyền Gì?

Token nên được scope nhỏ nhất có thể:

```text
Zone:Read
DNS:Edit
Zone Resources: chỉ đúng zone của domain Face Detector
```

Không nên dùng Global API Key.

Không nên cấp quyền account-wide nếu chỉ cần sửa DNS của một zone.

## 5. Terraform EKS Làm Gì?

`terraform/eks` nhận các biến:

```text
public_dns_enabled
public_dns_provider
public_dns_base_domain
cloudflare_zone_id
public_tls_enabled
public_tls_certificate_arn
external_dns_namespace
external_dns_cloudflare_secret_name
```

Khi `public_dns_enabled=true` và `public_dns_provider=cloudflare`:

- Terraform cài Helm chart `external-dns`.
- ExternalDNS provider là `cloudflare`.
- ExternalDNS chỉ scan Kubernetes Service.
- ExternalDNS chỉ quản lý domain trong `public_dns_base_domain`.
- ExternalDNS đọc token từ Kubernetes Secret `external-dns-cloudflare`.
- Terraform không ghi Cloudflare token vào state.

Kubernetes Secret được workflow `infrastructure.yml` tạo sau khi Terraform apply xong:

```text
Secret: external-dns-cloudflare
Key:    api-token
Value:  CLOUDFLARE_API_TOKEN từ GitHub secret
```

Đây là điểm quan trọng để tránh lưu secret nhạy cảm trong Terraform state.

## 6. Helm Chart App Làm Gì?

Helm chart có values:

```yaml
publicDns:
  enabled: false
  hostname: ""

publicTls:
  enabled: false
  certificateArn: ""
```

Khi public DNS bật, Service `nginx` có annotation:

```yaml
external-dns.alpha.kubernetes.io/hostname: sandbox-pr-130.face.example.com
```

ExternalDNS đọc annotation này và tạo DNS record trong Cloudflare trỏ về LoadBalancer thật.

## 7. TLS Và HTTPS

DNS và TLS là hai chuyện khác nhau.

DNS trả lời câu hỏi:

```text
face.example.com trỏ tới đâu?
```

TLS trả lời câu hỏi:

```text
Trình duyệt/edge có kết nối HTTPS an toàn tới endpoint đó không?
```

Hiện repo hỗ trợ AWS LoadBalancer TLS bằng ACM certificate:

```text
publicTls.enabled=true
publicTls.certificateArn=<ACM certificate ARN>
```

Với Cloudflare DNS, bạn có 3 hướng:

1. Ban đầu dùng DNS trước, để `FACE_DETECTOR_PUBLIC_TLS_ENABLED=false`.
2. Tạo ACM certificate trong AWS, copy DNS validation CNAME vào Cloudflare, rồi set `public_tls_certificate_arn`.
3. Sau này harden hơn bằng cert-manager + Let's Encrypt DNS-01 qua Cloudflare.

Hướng 1 là đủ để test stable DNS.

Hướng 2 phù hợp nếu vẫn muốn AWS LoadBalancer terminate TLS.

Hướng 3 là hướng tốt hơn nếu muốn toàn bộ vòng đời certificate nằm trong Kubernetes/IaC, nhưng nên làm bằng PR riêng.

Không nên bật Cloudflare proxy để dùng HTTPS kiểu "Flexible" cho dữ liệu nhận diện khuôn mặt, vì khi đó kết nối Cloudflare -> origin có thể không end-to-end TLS.

## 8. Hostname Theo Môi Trường

Workflow `app-cd.yml` sinh hostname như sau:

```text
production -> face.example.com
staging    -> staging.face.example.com
sandbox    -> sandbox-pr-<pr-number>.face.example.com
```

Nếu DNS chưa bật:

```text
publicDns.enabled=false
smoke test fallback về LoadBalancer hostname
```

Nếu DNS bật:

```text
publicDns.enabled=true
publicDns.hostname=<stable-hostname>
smoke test ưu tiên stable hostname
```

## 9. Edge Device Dùng DNS Như Nào?

Edge device không đổi code contract. Nó vẫn đọc:

```text
API_BASE_URL
```

Ví dụ:

```text
production: API_BASE_URL=https://face.example.com
staging:    API_BASE_URL=https://staging.face.example.com
sandbox:    API_BASE_URL=http://sandbox-pr-130.face.example.com
```

Không hardcode URL vào Docker image.

Khi deploy edge thật, cấu hình `API_BASE_URL` bằng:

- file `.env` khi dev local
- systemd environment file trên Linux mini PC
- MDM, Ansible, SSM hoặc remote config nếu quản lý nhiều edge device

Khi domain đổi, giữ domain cũ trong một giai đoạn chuyển tiếp rồi update edge config theo batch.

## 10. ArgoCD Và GitOps Flow

ArgoCD vẫn sync app từ Git.

DNS không làm thay đổi nguyên tắc GitOps:

```text
Git thay đổi values/template
-> ArgoCD sync Helm chart
-> Service nginx có annotation hostname
-> ExternalDNS tạo DNS record trong Cloudflare
```

Staging và production vẫn nên deploy bằng immutable image digest, không deploy `latest`.

Production promotion vẫn nên đi qua GitHub Environment `production` để owner/admin approve trước khi update `values-production.yaml`.

Production không auto-sync tuyệt đối nữa:

```text
GitHub Release published
-> GitOps Production Promotion chờ approval ở GitHub Environment production
-> workflow update values-production.yaml bằng immutable digest
-> ArgoCD thấy application OutOfSync
-> trusted operator mở ArgoCD
-> kiểm tra diff
-> manual sync face-detector-production
```

Lý do: production có thêm một lớp approval ở tầng GitOps runtime. Nếu image/digest đã được promote nhầm, ArgoCD vẫn không tự apply ngay.

ArgoCD hardening:

```text
Application staging/production
-> dùng project: face-detector
-> AppProject chỉ allow repo URL hiện tại
-> AppProject chỉ allow namespace app
-> AppProject chỉ allow các resource Helm chart cần: Deployment, Service, ConfigMap, Job, HPA, ScaledObject
-> không allow cluster-scoped resource
-> không cho Helm chart quản lý Secret
-> sync window chặn auto-sync cho face-detector-production
-> vẫn cho phép manual sync production
```

ArgoCD server hardening:

```text
server service = ClusterIP
server.insecure = false
UI không expose public mặc định
RBAC bật
exec tắt
RBAC audit log bật
log format JSON
notifications controller bật
```

Nếu sau này expose ArgoCD UI public thì bắt buộc phải thêm:

```text
TLS thật
SSO/OIDC
RBAC groups rõ ràng
IP allowlist hoặc private access
audit log retention
```

Repo credential hardening:

```text
Khuyến nghị 1, đường chính: GitHub App
-> installation chỉ cấp quyền đọc repo này
-> secret dùng ARGOCD_GITHUB_APP_ID, ARGOCD_GITHUB_APP_INSTALLATION_ID, ARGOCD_GITHUB_APP_PRIVATE_KEY

Khuyến nghị 2, fallback: Deploy key
-> deploy key read-only trên đúng repo này
-> private key lưu ở ARGOCD_REPO_DEPLOY_KEY

Fallback legacy:
-> ARGOCD_REPO_TOKEN
-> chỉ giữ để tương thích, không nên là đường production lâu dài
```

Nếu dùng deploy key, ArgoCD Application sẽ dùng repo URL dạng:

```text
git@github.com:OWNER/REPO.git
```

Nếu dùng GitHub App hoặc repo public, ArgoCD Application sẽ dùng:

```text
https://github.com/OWNER/REPO.git
```

## 11. Route53 Còn Dùng Không?

Với hướng Student Pack + Cloudflare:

```text
Không cần Route53 hosted zone.
Không cần trả phí Route53 hosted zone.
Không cần delegate nameserver về Route53.
```

Route53 code có thể giữ như optional fallback nếu sau này bạn muốn AWS quản lý DNS, nhưng đường mặc định của repo là:

```text
FACE_DETECTOR_DNS_PROVIDER=cloudflare
```

Nếu dùng Route53 thì mới cần:

```text
FACE_DETECTOR_DNS_PROVIDER=route53
manage_public_dns_zone=true
validate_public_dns_certificate=true
```

## 12. Sandbox Governance Cho DNS/IAM

Thay đổi DNS, IAM, Terraform, workflow hoặc ArgoCD template là control-plane change. Sandbox policy có thể gắn:

```text
sandbox-required
```

PR pass bằng một trong hai đường:

```text
owner gắn deploy-sandbox
-> sandbox apply/bootstrap/smoke pass
-> bot gắn sandbox-validated
-> sandbox-policy/evaluate pass
```

hoặc:

```text
owner gắn skip-sandbox-approved
-> waiver rõ ràng
-> sandbox-policy/evaluate pass
```

`allow-self-approve` không bypass `sandbox-required`.

## 13. Checklist Triển Khai Cloudflare DNS

1. Lấy domain qua GitHub Student Developer Pack.
2. Add domain vào Cloudflare.
3. Đổi nameserver ở registrar sang Cloudflare nameservers.
4. Tạo Cloudflare API token với `Zone:Read` và `DNS:Edit`.
5. Set GitHub variables/secrets:

```powershell
gh variable set FACE_DETECTOR_BASE_DOMAIN --repo chiendz11/Face_dectector --body "face.example.com"
gh variable set FACE_DETECTOR_DNS_PROVIDER --repo chiendz11/Face_dectector --body "cloudflare"
gh variable set FACE_DETECTOR_PUBLIC_DNS_ENABLED --repo chiendz11/Face_dectector --body "true"
gh variable set FACE_DETECTOR_PUBLIC_TLS_ENABLED --repo chiendz11/Face_dectector --body "false"
gh variable set CLOUDFLARE_ZONE_ID --repo chiendz11/Face_dectector --body "<cloudflare-zone-id>"
gh secret set CLOUDFLARE_API_TOKEN --repo chiendz11/Face_dectector --body "<cloudflare-api-token>"
```

6. Gắn `deploy-sandbox` cho PR DNS/infra.
7. Đợi infrastructure apply và app bootstrap pass.
8. Kiểm tra record trong Cloudflare:

```text
sandbox-pr-<pr-number>.face.example.com
```

9. Test health:

```powershell
curl http://sandbox-pr-<pr-number>.face.example.com/health
```

10. Khi đã có TLS thật, bật:

```powershell
gh variable set FACE_DETECTOR_PUBLIC_TLS_ENABLED --repo chiendz11/Face_dectector --body "true"
```

## 14. Khi Domain Thay Đổi

Flow an toàn:

```text
add domain mới vào Cloudflare
-> tạo API token/zone config mới nếu cần
-> update FACE_DETECTOR_BASE_DOMAIN
-> deploy sandbox/staging trước
-> update edge API_BASE_URL theo batch
-> giữ domain cũ trong rollback window
-> chỉ bỏ domain cũ khi edge fleet đã ổn định
```

Không đổi domain bằng cách sửa image hoặc hardcode endpoint trong code.
