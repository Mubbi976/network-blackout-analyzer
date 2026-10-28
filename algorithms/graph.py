"""
Graph module for Network Blackout Analyzer.
Implements adjacency list, BFS, DFS, Dijkstra shortest path,
Tarjan's Bridge-Finding, and Tarjan's Articulation Points (Cut Vertices).
"""

from __future__ import annotations
import heapq
from collections import deque
from typing import Iterable

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

    def neighbors(self, node: str):
        for neighbor in sorted(self.adj.get(node, ())):
            if edge_key(node, neighbor) not in self.failed_edges:
                yield neighbor

    def bfs(self, start: str) -> tuple[list[str], set[str]]:
        """Breadth-First Search: returns visit order and set of reachable nodes."""
        if start not in self.adj:
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
        if start not in self.adj:
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
            if node not in tin:
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
            if node not in tin:
                visit(node, None)
        return sorted(cut_vertices)

    def find_shortest_path(self, start: str, target: str) -> tuple[list[str] | None, float]:
        """Dijkstra's shortest path algorithm; backup link has a higher cost."""
        if start not in self.adj or target not in self.adj:
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
