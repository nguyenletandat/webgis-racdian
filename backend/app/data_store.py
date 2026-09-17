"""Loads the AB/DA/TDH shapefiles once and builds the routing graph used by the solver.

Mirrors the preprocessing steps of ``Input_data/Network_Analysis_CVRP.ipynb``
(reproject to VN-2000 UTM 48N, build a NetworkX graph from the road segments,
index the graph nodes with a KD-Tree) so the notebook and the API stay consistent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import MultiLineString, Point

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "Input_data"
BACKEND_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TARGET_CRS = "EPSG:32648"  # VN-2000 UTM Zone 48N (metres)

ROAD_FILE = DATA_DIR / "Road_Network.shp"
DEPOT_FILE = DATA_DIR / "Depots.shp"
ORDERS_FILE = DATA_DIR / "Orders.shp"
BOUNDARY_FILE = BACKEND_DATA_DIR / "di_an_boundary.geojson"


def _build_road_graph(roads: gpd.GeoDataFrame) -> nx.Graph:
    graph = nx.Graph()
    for geom in roads.geometry:
        if geom is None or geom.is_empty:
            continue
        lines = geom.geoms if isinstance(geom, MultiLineString) else [geom]
        for line in lines:
            coords = list(line.coords)
            for i in range(len(coords) - 1):
                u = (round(coords[i][0], 2), round(coords[i][1], 2))
                v = (round(coords[i + 1][0], 2), round(coords[i + 1][1], 2))
                dist = Point(u).distance(Point(v))
                if dist > 0:
                    graph.add_edge(u, v, weight=dist)
    return graph


@dataclass
class NetworkContext:
    graph: nx.Graph
    kdtree: cKDTree
    node_list: list
    depot_point_metric: Point
    orders_metric: gpd.GeoDataFrame
    orders_wgs84: gpd.GeoDataFrame
    depot_wgs84: gpd.GeoDataFrame
    roads_wgs84: gpd.GeoDataFrame
    demand_col: str
    boundary_geojson: dict | None
    boundary_props: dict | None


def load_network() -> NetworkContext:
    roads = gpd.read_file(ROAD_FILE)
    depots = gpd.read_file(DEPOT_FILE)
    orders = gpd.read_file(ORDERS_FILE)

    roads_metric = roads if str(roads.crs) == TARGET_CRS else roads.to_crs(TARGET_CRS)
    depots_metric = depots.to_crs(TARGET_CRS)
    orders_metric = orders.to_crs(TARGET_CRS)

    demand_col = "KLCTR_up" if "KLCTR_up" in orders_metric.columns else None
    if demand_col is None:
        numeric_cols = orders_metric.select_dtypes(include=[np.number]).columns
        demand_col = numeric_cols[0]
    orders_metric[demand_col] = orders_metric[demand_col].fillna(0).astype(int)
    orders_metric = orders_metric.reset_index(drop=True)

    graph = _build_road_graph(roads_metric)
    node_list = list(graph.nodes())
    kdtree = cKDTree(np.array(node_list))

    boundary_geojson = None
    boundary_props = None
    if BOUNDARY_FILE.exists():
        with BOUNDARY_FILE.open(encoding="utf-8") as f:
            boundary_geojson = json.load(f)
        boundary_props = boundary_geojson["features"][0]["properties"]

    return NetworkContext(
        graph=graph,
        kdtree=kdtree,
        node_list=node_list,
        depot_point_metric=depots_metric.geometry.iloc[0],
        orders_metric=orders_metric,
        orders_wgs84=orders_metric.to_crs("EPSG:4326"),
        depot_wgs84=depots_metric.to_crs("EPSG:4326"),
        roads_wgs84=roads_metric.to_crs("EPSG:4326"),
        demand_col=demand_col,
        boundary_geojson=boundary_geojson,
        boundary_props=boundary_props,
    )
