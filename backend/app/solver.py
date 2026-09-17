"""CVRP graph utilities and OR-Tools solver.

Same algorithmic pipeline as the research notebook: KD-Tree snapping, single-source
Dijkstra for the OD cost matrix, then Guided Local Search (OR-Tools) for the
capacitated vehicle routing problem, followed by shortest-path geometry
reconstruction along the real road network.
"""
from __future__ import annotations

import networkx as nx
import numpy as np
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point


def snap_points(kdtree: cKDTree, node_list: list, points) -> list:
    snapped = []
    for pt in points:
        _, idx = kdtree.query([pt.x, pt.y])
        snapped.append(node_list[idx])
    return snapped


def build_distance_matrix(graph: nx.Graph, locations: list) -> np.ndarray:
    unique_locs = list(set(locations))
    sp_dict = {}
    for u in unique_locs:
        try:
            sp_dict[u] = nx.single_source_dijkstra_path_length(graph, source=u, weight="weight")
        except Exception:
            sp_dict[u] = {}

    n = len(locations)
    matrix = np.zeros((n, n), dtype=int)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            d = sp_dict.get(locations[i], {}).get(locations[j])
            if d is None:
                d = Point(locations[i]).distance(Point(locations[j])) * 1.4
            matrix[i][j] = int(round(d))
    return matrix


def solve_cvrp(
    distance_matrix: np.ndarray,
    demands: list,
    num_vehicles: int,
    vehicle_capacity: int,
    depot_idx: int = 0,
    time_limit_s: int = 10,
):
    manager = pywrapcp.RoutingIndexManager(len(distance_matrix), num_vehicles, depot_idx)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(distance_matrix[from_node][to_node])

    transit_idx = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return int(demands[from_node])

    demand_idx = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_idx, 0, [vehicle_capacity] * num_vehicles, True, "Capacity"
    )

    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_params.time_limit.FromSeconds(time_limit_s)

    solution = routing.SolveWithParameters(search_params)
    return manager, routing, solution


def extract_routes(manager, routing, solution, demands, num_vehicles) -> list[dict]:
    routes = []
    for vehicle_id in range(num_vehicles):
        index = routing.Start(vehicle_id)
        route_distance = 0
        route_load = 0
        node_sequence = []
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            route_load += demands[node_index]
            node_sequence.append(node_index)
            previous_index = index
            index = solution.Value(routing.NextVar(index))
            route_distance += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
        node_index = manager.IndexToNode(index)
        node_sequence.append(node_index)

        if len(node_sequence) > 2:
            routes.append(
                {
                    "vehicle_id": vehicle_id + 1,
                    "node_sequence": node_sequence,
                    "distance_m": route_distance,
                    "load_kg": route_load,
                    "num_orders": len(node_sequence) - 2,
                }
            )
    return routes


def reconstruct_geometries(graph: nx.Graph, all_locations: list, routes: list) -> list[dict]:
    geometries = []
    for route in routes:
        seq = route["node_sequence"]
        coords = []
        for k in range(len(seq) - 1):
            u_node = all_locations[seq[k]]
            v_node = all_locations[seq[k + 1]]
            try:
                path_nodes = nx.shortest_path(graph, source=u_node, target=v_node, weight="weight")
                coords.extend(path_nodes)
            except nx.NetworkXNoPath:
                coords.extend([u_node, v_node])
        if len(coords) >= 2:
            geometries.append({**route, "geometry": LineString(coords)})
    return geometries
