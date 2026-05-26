# Hợp Đồng API

Hợp đồng API chính thức của hệ thống nằm trong file:

```text
docs/api-contract.yml
```

File Markdown này chỉ đóng vai trò chỉ dẫn để backend, frontend-admin, edge-client và smoke test không phải duy trì hai bản mô tả API khác nhau.

Khi cần thay đổi request/response API:

1. Sửa `docs/api-contract.yml` trước.
2. Cập nhật backend để đúng contract mới.
3. Cập nhật frontend-admin hoặc edge-client nếu contract ảnh hưởng UI/client.
4. Cập nhật smoke test hoặc integration test liên quan.

Không nên ghi thêm contract chi tiết vào file `.md` này, vì dễ tạo drift giữa tài liệu và contract thật.
