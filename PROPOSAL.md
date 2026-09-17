# Đề xuất phát triển WebGIS RacDiAn

## 1. Hiện trạng trước khi có đề xuất này

Dự án chỉ có dữ liệu GIS (`Input_data/`: Orders, Depots, Road_Network cho 3 khu vực AB/DA/TDH) và một pipeline nghiên cứu trong `Network_Analysis_CVRP.ipynb`: dựng đồ thị mạng lưới đường (NetworkX), snap điểm gom bằng KD-Tree, tính ma trận OD bằng Dijkstra, giải CVRP bằng Guided Local Search (Google OR-Tools) — đạt tải trọng 97.6%–99.1% cho 150 điểm/3 xe (xem `Bao_cao_NCKH_Toi_uu_Tuyen_duong_CTR.md`). Đây là một engine tối ưu hóa thật, nhưng chỉ chạy được thủ công trong notebook, không có ứng dụng web đi kèm.

## 2. WebGIS tham chiếu (Thủ Dầu Một)

Đối chiếu: <https://nguyenletandat.github.io/webgis-tuyen-thu-gom-ctrsh/>

| Khía cạnh | WebGIS Thủ Dầu Một |
|---|---|
| Xử lý | 100% client-side (JavaScript trong trình duyệt) |
| Thuật toán | Nearest-Neighbor + 2-opt + Dijkstra — heuristic đơn giản |
| Ràng buộc tải trọng | Không có CVRP thật; "VRPTW" chỉ là lịch giờ cố định 15 phút/điểm |
| Dữ liệu | Tĩnh, OpenStreetMap, 1 phường, không có backend/DB |
| Cấu hình đội xe | Hard-code: 13 chuyến, 8 xe ép rác |
| Tính năng | Dashboard tổng quan, timeline hoạt động, so sánh trước/sau |

Đây là một bản demo trực quan hoá dựa trên heuristic nhẹ, phù hợp trình diễn nhưng không phải công cụ vận hành có ràng buộc tải trọng thật.

## 3. Định hướng khác biệt

| | WebGIS Thủ Dầu Một | WebGIS RacDiAn |
|---|---|---|
| Kiến trúc | Client-only | Backend thật (FastAPI) + Frontend tách biệt |
| Thuật toán | NN + 2-opt (xấp xỉ) | CVRP + Guided Local Search (OR-Tools) — đã kiểm chứng 97–99% tải trọng |
| Ràng buộc | Không có tải trọng thật | Tải trọng xe (Q), số xe (K); VRPTW/multi-depot ở giai đoạn 2 |
| Dữ liệu | Tĩnh, OSM only | Shapefile GIS thật (Road_Network/Orders/Depots, VN-2000 UTM 48N) |
| Tương tác | Xem + so sánh | "What-if" simulator: đổi số xe/tải trọng/số điểm → tối ưu lại on-demand qua API |
| Đầu ra | Bản đồ | Bản đồ + KPI (km, tải trọng %, thời gian giải) + bảng chi tiết từng tuyến |
| Khu vực dữ liệu | Phường Thủ Dầu Một | Dĩ An (đúng bộ dữ liệu `Orders.shp` 7.835 điểm dùng trong báo cáo NCKH) |
| Ranh giới hành chính | 1 phường, tĩnh | Phường Dĩ An theo cấu trúc 34 tỉnh thành 2025 (trích từ dữ liệu nguồn `Shp/`), kèm dân số/diện tích/mật độ để đối chiếu tải lượng CTRSH |
| Mở rộng tương lai | — | IoT mức đầy thùng rác → Dynamic VRP (đúng kiến nghị 5.2 của báo cáo) |

## 4. Kiến trúc kỹ thuật (đã triển khai ở MVP)

```
frontend/ (Leaflet, vanilla JS)  ──HTTP/JSON──▶  backend/ (FastAPI)
                                                     ├── data_store.py → nạp shapefile, dựng graph
                                                     └── solver.py     → snap, OD matrix, OR-Tools GLS, dựng hình học tuyến
```

`POST /api/optimize` nhận `sample_size`, `num_vehicles`, `vehicle_capacity_kg`, `time_limit_s`, chạy lại đúng pipeline của notebook (snap KD-Tree → Dijkstra OD matrix → OR-Tools Guided Local Search → tái tạo LineString theo mạng đường thật) và trả GeoJSON tuyến đường cùng KPI — thay vì phải sửa tay biến trong notebook rồi chạy lại từng cell.

## 5. Lộ trình 3 giai đoạn

### Giai đoạn 1 — MVP vận hành (đã có trong repo này)
- API tối ưu hóa CVRP on-demand, dữ liệu khu vực Dĩ An
- Bản đồ tương tác: điểm gom, depot, tuyến tối ưu theo màu xe
- Bảng điều khiển tham số (số xe, tải trọng, số điểm gom) + KPI + bảng chi tiết tuyến

### Giai đoạn 2 — VRPTW + multi-depot
- Thêm khung giờ cấm tải đô thị, khung giờ xả rác của hộ dân/doanh nghiệp
- Hỗ trợ nhiều trạm trung chuyển
- Phân vai trò Điều phối viên / Tài xế / Quản lý; xuất lịch trình PDF cho tài xế, GeoJSON/Shapefile cho GIS
- Lưu trữ có phiên bản (PostGIS) thay vì đọc trực tiếp shapefile mỗi lần khởi động

### Giai đoạn 3 — Dynamic VRP + mở rộng toàn đô thị
- Mô phỏng/tích hợp cảm biến IoT mức đầy thùng rác → tối ưu lại theo thời gian thực
- Phân cụm phân cấp (hierarchical clustering) để scale từ 150 điểm thử nghiệm lên toàn bộ ~7.800 điểm của `Orders.shp`

## 6. Ranh giới hành chính (bổ sung từ `Shp/`)

WebGIS Thủ Dầu Một có lớp "ranh giới hành chính phường" nhưng chỉ là 1 phường tĩnh. `Shp/VN34TinhThanh/Việt Nam (phường xã) - 34.geojson` (nạp toàn bộ ranh giới xã/phường cả nước theo cấu trúc 34 tỉnh thành sau sáp nhập 2025) cho phép bổ sung đúng ranh giới hành chính hiện hành của khu vực nghiên cứu — không phải trích thủ công.

`backend/scripts/prepare_context_layers.py` dùng `ijson` để stream qua file ~280 MB đó (không nạp toàn bộ vào RAM) và trích đúng 1 feature — **Phường Dĩ An** (`ma_xa=25942`) — ghi ra `backend/data/di_an_boundary.geojson` (34 KB, được commit vào repo; file nguồn trong `Shp/` không commit vì quá lớn).

Dữ liệu ranh giới cho thấy: Phường Dĩ An hiện tại (thuộc TP. Hồ Chí Minh sau sáp nhập) là kết quả sáp nhập của **An Bình + Dĩ An + một phần Tân Đông Hiệp** — trùng khớp với 2 bộ điểm gom `AB_points`/`DA_points` sẵn có trong `Input_data/`, và giải thích vì sao dữ liệu nghiên cứu được tổ chức theo 2 mã khu vực đó. Diện tích 21.38 km², dân số 227.817 người, mật độ ~10.656 người/km² — các con số này được hiển thị trực tiếp trên WebGIS (mục "Ranh giới hành chính") làm cơ sở đối chiếu tải lượng CTRSH phát sinh theo đầu người với kết quả tối ưu hóa tuyến.

## 7. Vì sao chọn khu vực Dĩ An (DA)

`Orders.shp` (7.835 điểm, dùng trong báo cáo NCKH) trùng khớp số bản ghi với `DA_mer_points.dbf` (7.835 bản ghi) — tức bộ dữ liệu chính của cả notebook lẫn báo cáo vốn đã là khu vực Dĩ An. TDH (Thủ Dầu Một, 4.079 điểm) đã được dùng ở WebGIS tham chiếu nên không tái sử dụng để tránh trùng lặp phạm vi nghiên cứu.
