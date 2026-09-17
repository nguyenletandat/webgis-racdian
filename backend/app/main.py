"""WebGIS RacDiAn — CVRP route-optimization API.

Serves the optimization engine that was previously trapped inside a Jupyter
notebook (Input_data/Network_Analysis_CVRP.ipynb) as an on-demand HTTP API,
plus the static frontend, so vehicle count / capacity can be changed and
re-optimized from the browser instead of re-running the notebook by hand.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import geopandas as gpd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import solver
from .data_store import NetworkContext, load_network

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

COLORS = [
    "#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e",
    "#d62728", "#17becf", "#bcbd22", "#8c564b",
    "#e377c2", "#7f7f7f",
]

_ctx: Optional[NetworkContext] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ctx
    _ctx = load_network()
    print(
        f"[startup] graph: {_ctx.graph.number_of_nodes()} nodes / "
        f"{_ctx.graph.number_of_edges()} edges, {len(_ctx.orders_metric)} orders"
    )
    yield


app = FastAPI(title="WebGIS RacDiAn - CVRP Optimization API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_ctx() -> NetworkContext:
    if _ctx is None:
        raise HTTPException(status_code=503, detail="Dữ liệu mạng lưới chưa sẵn sàng, thử lại sau vài giây.")
    return _ctx


class OptimizeRequest(BaseModel):
    sample_size: int = Field(150, ge=5, le=2000, description="Số điểm gom rác đưa vào bài toán")
    num_vehicles: int = Field(8, ge=1, le=30, description="Số xe tối đa có thể điều động")
    vehicle_capacity_kg: int = Field(3000, ge=100, le=20000, description="Tải trọng tối đa mỗi xe (kg)")
    seed: int = Field(42, ge=0, description="Seed để chọn mẫu điểm gom ổn định giữa các lần gọi")
    time_limit_s: int = Field(10, ge=1, le=30, description="Giới hạn thời gian giải (giây)")


@app.get("/api/meta")
def get_meta():
    ctx = get_ctx()
    return {
        "total_orders": int(len(ctx.orders_metric)),
        "total_demand_kg": int(ctx.orders_metric[ctx.demand_col].sum()),
        "road_nodes": ctx.graph.number_of_nodes(),
        "road_edges": ctx.graph.number_of_edges(),
        "demand_column": ctx.demand_col,
        "ward": ctx.boundary_props,
    }


@app.get("/api/boundary")
def get_boundary():
    ctx = get_ctx()
    if ctx.boundary_geojson is None:
        raise HTTPException(
            status_code=404,
            detail="Chưa có ranh giới hành chính — chạy backend/scripts/prepare_context_layers.py trước.",
        )
    return ctx.boundary_geojson


@app.get("/api/depots")
def get_depots():
    ctx = get_ctx()
    return ctx.depot_wgs84.__geo_interface__


@app.get("/api/orders")
def get_orders(sample_size: int = 150, seed: int = 42):
    ctx = get_ctx()
    gdf = ctx.orders_wgs84
    n = min(sample_size, len(gdf))
    sample = gdf.sample(n=n, random_state=seed) if n < len(gdf) else gdf
    return sample[[ctx.demand_col, "geometry"]].__geo_interface__


@app.get("/api/road-network")
def get_road_network():
    ctx = get_ctx()
    return ctx.roads_wgs84[["geometry"]].__geo_interface__


@app.post("/api/optimize")
def optimize(req: OptimizeRequest):
    ctx = get_ctx()
    gdf = ctx.orders_metric
    n = min(req.sample_size, len(gdf))
    sample = gdf.sample(n=n, random_state=req.seed) if n < len(gdf) else gdf
    sample = sample.reset_index(drop=True)

    order_points = list(sample.geometry)
    order_demands = sample[ctx.demand_col].astype(int).tolist()

    total_demand = sum(order_demands)
    total_capacity = req.num_vehicles * req.vehicle_capacity_kg
    if total_demand > total_capacity:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Tổng khối lượng rác ({total_demand} kg) vượt quá tổng sức chứa đội xe "
                f"({req.num_vehicles} xe x {req.vehicle_capacity_kg} kg = {total_capacity} kg). "
                "Hãy tăng số xe hoặc tải trọng mỗi xe."
            ),
        )

    depot_node = solver.snap_points(ctx.kdtree, ctx.node_list, [ctx.depot_point_metric])[0]
    order_nodes = solver.snap_points(ctx.kdtree, ctx.node_list, order_points)

    all_locations = [depot_node] + order_nodes
    all_demands = [0] + order_demands

    t0 = time.perf_counter()
    distance_matrix = solver.build_distance_matrix(ctx.graph, all_locations)
    manager, routing, solution = solver.solve_cvrp(
        distance_matrix,
        all_demands,
        req.num_vehicles,
        req.vehicle_capacity_kg,
        depot_idx=0,
        time_limit_s=req.time_limit_s,
    )
    if solution is None:
        raise HTTPException(
            status_code=422,
            detail="Không tìm được lời giải khả thi trong giới hạn thời gian. Hãy tăng số xe, tải trọng hoặc thời gian giải.",
        )

    routes = solver.extract_routes(manager, routing, solution, all_demands, req.num_vehicles)
    geometries = solver.reconstruct_geometries(ctx.graph, all_locations, routes)
    elapsed = time.perf_counter() - t0

    features = []
    for g in geometries:
        line_wgs84 = gpd.GeoSeries([g["geometry"]], crs=ctx.orders_metric.crs).to_crs("EPSG:4326").iloc[0]
        idx = g["vehicle_id"] - 1
        features.append(
            {
                "type": "Feature",
                "geometry": line_wgs84.__geo_interface__,
                "properties": {
                    "vehicle_id": g["vehicle_id"],
                    "color": COLORS[idx % len(COLORS)],
                    "distance_km": round(g["distance_m"] / 1000, 2),
                    "load_kg": g["load_kg"],
                    "capacity_kg": req.vehicle_capacity_kg,
                    "utilization_pct": round(g["load_kg"] / req.vehicle_capacity_kg * 100, 1),
                    "num_orders": g["num_orders"],
                },
            }
        )

    vehicles_used = len(geometries)
    total_distance_km = round(sum(g["distance_m"] for g in geometries) / 1000, 2)
    total_load_kg = int(sum(g["load_kg"] for g in geometries))
    avg_utilization = (
        round(sum(g["load_kg"] / req.vehicle_capacity_kg for g in geometries) / vehicles_used * 100, 1)
        if vehicles_used
        else 0.0
    )

    return {
        "type": "FeatureCollection",
        "features": features,
        "kpi": {
            "vehicles_used": vehicles_used,
            "vehicles_available": req.num_vehicles,
            "total_orders_served": int(sum(g["num_orders"] for g in geometries)),
            "total_orders_requested": n,
            "total_distance_km": total_distance_km,
            "total_load_kg": total_load_kg,
            "avg_utilization_pct": avg_utilization,
            "solve_time_s": round(elapsed, 2),
        },
    }


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
