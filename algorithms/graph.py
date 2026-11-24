"""
Graph module for Network Blackout Analyzer.
Implements adjacency list, BFS, DFS, Dijkstra shortest path,
Tarjan's Bridge-Finding, and Tarjan's Articulation Points (Cut Vertices).
"""

from __future__ import annotations
import heapq
from collections import deque
from typing import Iterable
import time

NODES = ["R1", "R2", "R3", "R4", "R5", "PC1", "PC2", "Server1"]

# (endpoint A, endpoint B, cost, is_backup_link)
EDGE_DEFINITIONS = [
    ("R1", "R2", 1, False),
    ("R2", "R3", 1, False),
    ("R3", "R4", 1, False),
    ("R4", "R1", 1, False),
    ("R3", "R5", 1, False),  # Primary server uplink
    ("R2", "R5", 5, True),   # Higher-cost backup link
    ("R1", "PC1", 1, False),
    ("R4", "PC2", 1, False),
    ("R5", "Server1", 1, False),
]

POSITIONS = {
    "R1": (95, 190), "R2": (220, 85), "R3": (365, 115),
    "R4": (300, 280), "R5": (520, 190),
    "PC1": (55, 315), "PC2": (300, 370), "Server1": (635, 190),
}


def edge_key(u: str, v: str) -> tuple[str, str]:
    """Canonical key for an undirected edge."""
    return tuple(sorted((u, v)))


class Graph:
    """Undirected weighted graph stored as an adjacency list."""

    def __init__(self, nodes: Iterable[str] = ()):
        self.adj: dict[str, set[str]] = {node: set() for node in nodes}
        self.weights: dict[tuple[str, str], float] = {}
        self.failed_edges: set[tuple[str, str]] = set()
        self.failed_nodes: set[str] = set()
        self.backup_edges: set[tuple[str, str]] = set()

    def add_node(self, node: str) -> None:
        self.adj.setdefault(node, set())

    def add_edge(self, u: str, v: str, weight: float = 1, backup: bool = False) -> None:
        self.add_node(u)
        self.add_node(v)
        self.adj[u].add(v)
        self.adj[v].add(u)
        key = edge_key(u, v)
        self.weights[key] = weight
        self.failed_edges.discard(key)
        if backup:
            self.backup_edges.add(key)
        else:
            self.backup_edges.discard(key)

    def remove_edge(self, u: str, v: str) -> None:
        """Remove an edge from the graph entirely."""
        self.adj.get(u, set()).discard(v)
        self.adj.get(v, set()).discard(u)
        key = edge_key(u, v)
        self.weights.pop(key, None)
        self.failed_edges.discard(key)
        self.backup_edges.discard(key)

    def toggle_edge(self, u: str, v: str) -> bool:
        """Toggle an edge's simulated operational state; return True if now UP."""
        key = edge_key(u, v)
        if key not in self.weights:
            raise ValueError(f"Unknown edge: {u}-{v}")
        if key in self.failed_edges:
            self.failed_edges.remove(key)
            return True
        self.failed_edges.add(key)
        return False

    def edge_is_up(self, u: str, v: str) -> bool:
        return edge_key(u, v) not in self.failed_edges

    def toggle_node(self, node: str) -> bool:
        """Toggle a node's simulated operational state; return True if now UP."""
        if node not in self.adj:
            raise ValueError(f"Unknown node: {node}")
        if node in self.failed_nodes:
            self.failed_nodes.remove(node)
            return True
        self.failed_nodes.add(node)
        return False

    def neighbors(self, node: str):
        if node in self.failed_nodes:
            return
        for neighbor in sorted(self.adj.get(node, ())):
            if neighbor not in self.failed_nodes and edge_key(node, neighbor) not in self.failed_edges:
                yield neighbor

    def bfs(self, start: str) -> tuple[list[str], set[str]]:
        """Breadth-First Search: returns visit order and set of reachable nodes."""
        if start not in self.adj or start in self.failed_nodes:
            return [], set()
        order, seen = [], {start}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in self.neighbors(node):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        return order, seen

    def dfs(self, start: str) -> tuple[list[str], set[str]]:
        """Depth-First Search: returns visit order and set of reachable nodes."""
        if start not in self.adj or start in self.failed_nodes:
            return [], set()
        order, seen = [], set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            order.append(node)
            stack.extend(n for n in reversed(list(self.neighbors(node))) if n not in seen)
        return order, seen

    def get_reachable_nodes(self, start_node: str) -> set[str]:
        return self.bfs(start_node)[1]

    def find_bridges(self) -> list[tuple[str, str]]:
        """
        Tarjan's Bridge-Finding Algorithm in O(V + E).
        A bridge is an edge whose removal increases the number of connected components.
        Condition: low[child] > tin[u]
        """
        timer = 0
        tin: dict[str, int] = {}
        low: dict[str, int] = {}
        bridges: list[tuple[str, str]] = []

        def visit(node: str, parent: str | None) -> None:
            nonlocal timer
            tin[node] = low[node] = timer
            timer += 1
            for neighbor in self.neighbors(node):
                if neighbor == parent:
                    continue
                if neighbor in tin:
                    low[node] = min(low[node], tin[neighbor])
                else:
                    visit(neighbor, node)
                    low[node] = min(low[node], low[neighbor])
                    if low[neighbor] > tin[node]:
                        bridges.append(edge_key(node, neighbor))

        for node in sorted(self.adj):
            if node not in self.failed_nodes and node not in tin:
                visit(node, None)
        return sorted(set(bridges))

    def find_articulation_points(self) -> list[str]:
        """
        Tarjan's Articulation Points (Cut Vertices) Algorithm in O(V + E).
        An articulation point is a vertex whose removal increases the number of connected components.
        Conditions:
          1. Root of DFS tree with children count >= 2.
          2. Non-root node u with a child v such that low[v] >= tin[u].
        """
        timer = 0
        tin: dict[str, int] = {}
        low: dict[str, int] = {}
        cut_vertices: set[str] = set()

        def visit(node: str, parent: str | None) -> None:
            nonlocal timer
            tin[node] = low[node] = timer
            timer += 1
            children = 0
            for neighbor in self.neighbors(node):
                if neighbor == parent:
                    continue
                if neighbor in tin:
                    low[node] = min(low[node], tin[neighbor])
                else:
                    children += 1
                    visit(neighbor, node)
                    low[node] = min(low[node], low[neighbor])
                    if parent is not None and low[neighbor] >= tin[node]:
                        cut_vertices.add(node)
            if parent is None and children >= 2:
                cut_vertices.add(node)

        for node in sorted(self.adj):
            if node not in self.failed_nodes and node not in tin:
                visit(node, None)
        return sorted(cut_vertices)

    def find_shortest_path(self, start: str, target: str) -> tuple[list[str] | None, float]:
        """Dijkstra's shortest path algorithm; backup link has a higher cost."""
        if (start not in self.adj or target not in self.adj
                or start in self.failed_nodes or target in self.failed_nodes):
            return None, float("inf")
        distances = {node: float("inf") for node in self.adj}
        previous: dict[str, str] = {}
        distances[start] = 0
        heap = [(0, start)]

        while heap:
            distance, node = heapq.heappop(heap)
            if distance != distances[node]:
                continue
            if node == target:
                break
            for neighbor in self.neighbors(node):
                candidate = distance + self.weights[edge_key(node, neighbor)]
                if candidate < distances[neighbor]:
                    distances[neighbor] = candidate
                    previous[neighbor] = node
                    heapq.heappush(heap, (candidate, neighbor))

        if distances[target] == float("inf"):
            return None, float("inf")
        path = [target]
        while path[-1] != start:
            path.append(previous[path[-1]])
        path.reverse()
        return path, distances[target]

    def dijkstra_steps(self, start: str, target: str) -> list[dict]:
        """Execution snapshots for interactive Dijkstra visualization."""
        if (start not in self.adj or target not in self.adj
                or start in self.failed_nodes or target in self.failed_nodes):
            return [{"selected": None, "distances": {}, "queue": [],
                     "path": None, "cost": float("inf")}]
        distances = {node: float("inf") for node in self.adj}
        distances[start] = 0
        heap = [(0, start)]
        steps = []
        while heap:
            distance, node = heapq.heappop(heap)
            if distance != distances[node]:
                continue
            steps.append({
                "selected": node,
                "distances": dict(distances),
                "queue": sorted(heap),
            })
            if node == target:
                break
            for neighbor in self.neighbors(node):
                candidate = distance + self.weights[edge_key(node, neighbor)]
                if candidate < distances[neighbor]:
                    distances[neighbor] = candidate
                    heapq.heappush(heap, (candidate, neighbor))
                    steps.append({
                        "selected": node,
                        "distances": dict(distances),
                        "queue": sorted(heap),
                        "updated": neighbor,
                    })
        path, cost = self.find_shortest_path(start, target)
        return steps + [{"selected": target if path else None, "distances": dict(distances),
                         "queue": [], "path": path, "cost": cost}]

    def bfs_steps(self, start: str) -> list[dict]:
        """BFS snapshots containing queue state and nodes visited per level."""
        if start not in self.adj or start in self.failed_nodes:
            return []
        seen = {start}
        queue = deque([start])
        order = []
        steps = []
        while queue:
            level = len(queue)
            level_nodes = []
            for _ in range(level):
                node = queue.popleft()
                level_nodes.append(node)
                order.append(node)
                for neighbor in self.neighbors(node):
                    if neighbor not in seen:
                        seen.add(neighbor)
                        queue.append(neighbor)
            steps.append({"visited": list(order), "queue": list(queue),
                           "level": list(level_nodes)})
        return steps

    def dfs_steps(self, start: str) -> list[dict]:
        """DFS snapshots containing traversal order and stack state."""
        if start not in self.adj or start in self.failed_nodes:
            return []
        seen = set()
        stack = [(start, False)]
        order = []
        steps = []
        while stack:
            node, exiting = stack.pop()
            if exiting:
                steps.append({"visited": list(order), "stack": [n for n, _ in stack],
                              "current": node, "exiting": True})
                continue
            if node in seen:
                continue
            seen.add(node)
            order.append(node)
            stack.append((node, True))
            for neighbor in reversed(list(self.neighbors(node))):
                if neighbor not in seen:
                    stack.append((neighbor, False))
            steps.append({"visited": list(order),
                          "stack": [n for n, _ in stack], "current": node,
                          "exiting": False})
        return steps

    def tarjan_steps(self) -> list[dict]:
        """Tarjan DFS snapshots with discovery, low-link, and result state."""
        timer = 0
        tin: dict[str, int] = {}
        low: dict[str, int] = {}
        bridges: set[tuple[str, str]] = set()
        cuts: set[str] = set()
        steps = []

        def visit(node: str, parent: str | None) -> None:
            nonlocal timer
            tin[node] = low[node] = timer
            timer += 1
            children = 0
            steps.append({"current": node, "tin": dict(tin), "low": dict(low),
                          "bridges": sorted(bridges), "articulations": sorted(cuts),
                          "dfs_tree": list(tin)})
            for neighbor in self.neighbors(node):
                if neighbor == parent:
                    continue
                if neighbor in tin:
                    low[node] = min(low[node], tin[neighbor])
                else:
                    children += 1
                    visit(neighbor, node)
                    low[node] = min(low[node], low[neighbor])
                    if low[neighbor] > tin[node]:
                        bridges.add(edge_key(node, neighbor))
                    if parent is not None and low[neighbor] >= tin[node]:
                        cuts.add(node)
                steps.append({"current": node, "tin": dict(tin), "low": dict(low),
                              "bridges": sorted(bridges),
                              "articulations": sorted(cuts),
                              "dfs_tree": list(tin)})
            if parent is None and children >= 2:
                cuts.add(node)

        for node in sorted(self.adj):
            if node not in self.failed_nodes and node not in tin:
                visit(node, None)
        steps.append({"current": None, "tin": dict(tin), "low": dict(low),
                      "bridges": sorted(bridges), "articulations": sorted(cuts),
                      "dfs_tree": list(tin), "final": True})
        return steps

    def connected_components(self) -> list[list[str]]:
        components = []
        unseen = set(self.adj) - self.failed_nodes
        while unseen:
            start = min(unseen)
            reachable = self.bfs(start)[1]
            component = sorted(reachable)
            components.append(component)
            unseen -= reachable
        return components

    def node_degrees(self) -> dict[str, int]:
        return {node: sum(1 for neighbor in self.neighbors(node))
                for node in self.adj if node not in self.failed_nodes}

    def network_resilience_score(self, source: str = "R1") -> dict:
        """Calculate health from reachable nodes, components, and active links."""
        total_nodes = len(self.adj)
        reachable = self.get_reachable_nodes(source)
        active_links = sum(
            1 for u, v in self.weights
            if u not in self.failed_nodes and v not in self.failed_nodes
            and edge_key(u, v) not in self.failed_edges
        )
        total_links = len(self.weights)
        components = self.connected_components()
        node_ratio = len(reachable) / total_nodes if total_nodes else 0
        link_ratio = active_links / total_links if total_links else 0
        connectivity_penalty = max(0, len(components) - 1) * 10
        score = round(max(0, (node_ratio * 70 + link_ratio * 30 - connectivity_penalty)))
        return {
            "score": score,
            "reachable": len(reachable),
            "total_nodes": total_nodes,
            "active_links": active_links,
            "total_links": total_links,
            "components": components,
            "connectivity_loss_percent": round((1 - node_ratio) * 100, 1),
        }

    def backup_link_candidates(self, eligible_nodes: Iterable[str] | None = None) -> list[dict]:
        """Enumerate missing node pairs and rank them by resilience improvement."""
        candidates = []
        nodes = sorted(set(eligible_nodes) & set(self.adj) if eligible_nodes is not None
                       else self.adj)
        original = self.network_resilience_score()
        original_failure_health = self._average_single_link_failure_health()
        bridges = set(self.find_bridges())
        cuts = set(self.find_articulation_points())
        for i, u in enumerate(nodes):
            if u in self.failed_nodes:
                continue
            for v in nodes[i + 1:]:
                if v in self.failed_nodes:
                    continue
                key = edge_key(u, v)
                if key in self.weights:
                    continue
                self.add_edge(u, v, 2, True)
                improved = self.network_resilience_score()
                candidate_failure_health = self._average_single_link_failure_health()
                candidate_bridges = set(self.find_bridges())
                candidate_cuts = set(self.find_articulation_points())
                self.remove_edge(u, v)
                improvement = improved["score"] - original["score"]
                single_failure_gain = round(
                    candidate_failure_health - original_failure_health, 2
                )
                bridges_reduced = max(0, len(bridges) - len(candidate_bridges))
                articulations_reduced = max(0, len(cuts) - len(candidate_cuts))
                if single_failure_gain > 0:
                    reason = (
                        f"improves average health under single-link failure "
                        f"by {single_failure_gain:g} points"
                    )
                elif bridges_reduced:
                    reason = f"removes {bridges_reduced} critical bridge link(s)"
                elif articulations_reduced:
                    reason = f"removes {articulations_reduced} articulation point(s)"
                else:
                    reason = "adds an alternate inter-router path"
                candidates.append({
                    "u": u, "v": v, "weight": 2,
                    "score": improved["score"],
                    "improvement": improvement,
                    "single_failure_gain": single_failure_gain,
                    "bridges_reduced": bridges_reduced,
                    "articulations_reduced": articulations_reduced,
                    "reason": reason,
                })
        candidates.sort(key=lambda item: (
            item["single_failure_gain"], item["improvement"],
            item["articulations_reduced"],
            item["bridges_reduced"], item["score"],
        ), reverse=True)
        return candidates

    def _average_single_link_failure_health(self) -> float:
        total_score = 0
        scenarios = 0
        for key in self.weights:
            u, v = key
            if (key in self.failed_edges or u in self.failed_nodes
                    or v in self.failed_nodes):
                continue
            self.failed_edges.add(key)
            total_score += self.network_resilience_score()["score"]
            self.failed_edges.remove(key)
            scenarios += 1
        return total_score / scenarios if scenarios else 0

    def failure_report(self, scenario: str = "Custom failure",
                        previous_path: list[str] | None = None,
                        previous_cost: float = float("inf")) -> dict:
        path, cost = self.find_shortest_path("R1", "Server1")
        reachable = self.get_reachable_nodes("R1")
        return {
            "scenario": scenario,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "failed_links": [f"{u}-{v}" for u, v in sorted(self.failed_edges)],
            "failed_routers": sorted(self.failed_nodes),
            "affected_devices": sorted(set(self.adj) - reachable),
            "components": self.connected_components(),
            "bridges": [f"{u}-{v}" for u, v in self.find_bridges()],
            "articulation_points": self.find_articulation_points(),
            "previous_route": previous_path or [],
            "previous_cost": previous_cost,
            "new_route": path or [],
            "new_cost": cost,
            "resilience": self.network_resilience_score(),
        }

    def restore_all(self) -> int:
        count = len(self.failed_edges) + len(self.failed_nodes)
        self.failed_edges.clear()
        self.failed_nodes.clear()
        return count
