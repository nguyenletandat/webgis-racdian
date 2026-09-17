# WebGIS RacDiAn

WebGIS hỗ trợ ra quyết định cho bài toán **tối ưu hóa tuyến thu gom chất thải rắn sinh hoạt (CTRSH)** bằng GIS + CVRP (Capacitated Vehicle Routing Problem), khu vực nghiên cứu **Dĩ An**.

Khác với các WebGIS trực quan hoá tuyến CTRSH hiện có (chạy heuristic Nearest-Neighbor/2-opt hoàn toàn phía client, dữ liệu tĩnh), dự án này đưa **engine tối ưu hóa thật** — dựng đồ thị mạng lưới đường, ma trận OD bằng Dijkstra, giải CVRP bằng thuật toán Metaheuristic *Guided Local Search* (Google OR-Tools) — ra sau một API, để người dùng có thể đổi số xe / tải trọng / số điểm gom và **tối ưu lại theo thời gian thực** ngay trên trình duyệt, thay vì phải chỉnh sửa và chạy lại notebook Python.

Xem [`PROPOSAL.md`](PROPOSAL.md) để biết định hướng đầy đủ và so sánh chi tiết với WebGIS tham chiếu (Thủ Dầu Một).

## Kiến trúc

```
frontend/ (Leaflet + vanilla JS, tĩnh)  ──HTTP/JSON──▶  backend/ (FastAPI)
                                                            │
                                                            ├── data_store.py  → nạp Road_Network/Depots/Orders (Input_data/*.shp),
                                                            │                    reproject VN-2000 UTM 48N, dựng đồ thị NetworkX + KD-Tree
                                                            └── solver.py      → snap điểm gom, ma trận OD (Dijkstra), giải CVRP
                                                                                 (OR-Tools, Guided Local Search), dựng lại hình học tuyến
```

Backend nạp `Input_data/Road_Network.shp`, `Depots.shp`, `Orders.shp` trực tiếp — cùng một bộ dữ liệu và cùng pipeline tiền xử lý với `Input_data/Network_Analysis_CVRP.ipynb`, để notebook (phân tích/báo cáo NCKH) và API (ứng dụng vận hành) luôn nhất quán.

## Chạy thử

Yêu cầu Python **3.11 64-bit** (geopandas/OR-Tools không có wheel ổn định cho Windows 32-bit).

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Mở trình duyệt tại `http://localhost:8000` — frontend được phục vụ tĩnh từ cùng server FastAPI, không cần bước build riêng.

## API

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/api/meta` | Thống kê tổng quan: số điểm gom, tổng khối lượng rác, số nút/đoạn đường |
| GET | `/api/depots` | GeoJSON vị trí trạm trung chuyển |
| GET | `/api/orders?sample_size=150` | GeoJSON điểm gom rác (lấy mẫu ngẫu nhiên có seed cố định) |
| GET | `/api/road-network` | GeoJSON mạng lưới đường (lớp nền) |
| GET | `/api/boundary` | GeoJSON ranh giới hành chính Phường Dĩ An (sau sáp nhập 2025) |
| POST | `/api/optimize` | Chạy CVRP với `sample_size`, `num_vehicles`, `vehicle_capacity_kg`, `time_limit_s` → trả GeoJSON tuyến đường + KPI |

## Cấu trúc thư mục

```
backend/
  app/
    data_store.py   # nạp + tiền xử lý dữ liệu GIS, dựng graph
    solver.py        # snap, ma trận OD, CVRP solver, dựng hình học
    main.py          # FastAPI app + endpoints + phục vụ frontend tĩnh
  data/
    di_an_boundary.geojson   # ranh giới hành chính Phường Dĩ An (trích từ Shp/, xem scripts/)
  scripts/
    prepare_context_layers.py   # trích ranh giới hành chính từ Shp/VN34TinhThanh/*.geojson
  requirements.txt
frontend/
  index.html
  style.css
  app.js
Input_data/            # shapefile gốc (dùng chung với notebook nghiên cứu)
Network_Analysis_CVRP.ipynb   # (trong Input_data/) pipeline nghiên cứu gốc
Bao_cao_NCKH_...md            # báo cáo khoa học
PROPOSAL.md            # đề xuất định hướng phát triển & lộ trình
```

> `Shp/` (ranh giới hành chính OSM toàn quốc, ~2.2 GB) chỉ tồn tại local, không commit vào git — `backend/data/di_an_boundary.geojson` là phần đã trích xuất và đủ dùng để chạy ứng dụng.

## Lộ trình phát triển tiếp theo

Xem chi tiết trong [`PROPOSAL.md`](PROPOSAL.md#lộ-trình-3-giai-đoạn):

1. **MVP (hiện tại):** tối ưu on-demand qua API, dashboard KPI, bản đồ tương tác.
2. **VRPTW + multi-depot:** khung giờ cấm tải, khung giờ xả rác, nhiều trạm trung chuyển, phân vai trò Điều phối/Tài xế/Quản lý, xuất PDF lịch trình.
3. **Dynamic VRP + mở rộng toàn đô thị:** tích hợp cảm biến IoT mức đầy thùng rác, phân cụm phân cấp để scale lên toàn bộ ~7.800 điểm gom.
