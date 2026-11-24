"""
Comprehensive automated unit tests for Network Blackout Analyzer graph algorithms.
Covers BFS, DFS, Dijkstra failover, Tarjan's bridges, Tarjan's articulation points,
edge removal, and disconnected graph scenarios.
"""

import os
import sys
import unittest

# Ensure the root project directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from algorithms.graph import Graph, edge_key, NODES, EDGE_DEFINITIONS


def make_graph() -> Graph:
    g = Graph(NODES)
    for u, v, weight, backup in EDGE_DEFINITIONS:
        g.add_edge(u, v, weight, backup)
    return g


class GraphAlgorithmTests(unittest.TestCase):
    def setUp(self):
        self.graph = make_graph()

    def test_bfs_and_dfs_reach_all_nodes_when_network_is_up(self):
        bfs_order, bfs_seen = self.graph.bfs("R1")
        dfs_order, dfs_seen = self.graph.dfs("R1")
        self.assertEqual(set(NODES), bfs_seen)
        self.assertEqual(set(NODES), dfs_seen)
        self.assertEqual(len(NODES), len(bfs_order))
        self.assertEqual(len(NODES), len(dfs_order))

    def test_primary_route_is_preferred(self):
        path, cost = self.graph.find_shortest_path("R1", "Server1")
        self.assertEqual(["R1", "R2", "R3", "R5", "Server1"], path)
        self.assertEqual(4, cost)

    def test_primary_link_failure_uses_backup_route(self):
        self.graph.failed_edges.add(edge_key("R3", "R5"))
        path, cost = self.graph.find_shortest_path("R1", "Server1")
        self.assertEqual(["R1", "R2", "R5", "Server1"], path)
        self.assertEqual(7, cost)

    def test_shortest_route_avoids_two_failed_routers(self):
        self.graph.failed_nodes.update({"R3", "R4"})
        path, cost = self.graph.find_shortest_path("R1", "Server1")
        self.assertEqual(["R1", "R2", "R5", "Server1"], path)
        self.assertEqual(7, cost)
        self.assertNotIn("R3", self.graph.get_reachable_nodes("R1"))
        self.assertNotIn("R4", self.graph.get_reachable_nodes("R1"))

    def test_three_failed_routers_can_make_server_unreachable(self):
        self.graph.failed_nodes.update({"R2", "R3", "R4"})
        path, cost = self.graph.find_shortest_path("R1", "Server1")
        self.assertIsNone(path)
        self.assertEqual(float("inf"), cost)

    def test_failed_source_router_has_no_reachable_nodes(self):
        self.assertFalse(self.graph.toggle_node("R1"))
        self.assertEqual(([], set()), self.graph.bfs("R1"))
        self.assertEqual((None, float("inf")), self.graph.find_shortest_path("R1", "Server1"))
        self.assertTrue(self.graph.toggle_node("R1"))
        self.assertIsNotNone(self.graph.find_shortest_path("R1", "Server1")[0])

    def test_both_server_uplinks_failed_makes_server_unreachable(self):
        self.graph.failed_edges.update({edge_key("R3", "R5"), edge_key("R2", "R5")})
        path, cost = self.graph.find_shortest_path("R1", "Server1")
        self.assertIsNone(path)
        self.assertEqual(float("inf"), cost)
        self.assertNotIn("Server1", self.graph.get_reachable_nodes("R1"))

    def test_tarjan_bridges_initial_state(self):
        bridges = set(self.graph.find_bridges())
        expected = {
            edge_key("R1", "PC1"),
            edge_key("R4", "PC2"),
            edge_key("R5", "Server1"),
        }
        self.assertEqual(expected, bridges)

    def test_failed_edges_convert_backup_to_bridge(self):
        self.graph.failed_edges.add(edge_key("R3", "R5"))
        bridges = set(self.graph.find_bridges())
        self.assertIn(edge_key("R2", "R5"), bridges)

    def test_tarjan_articulation_points_initial_state(self):
        cut_nodes = set(self.graph.find_articulation_points())
        self.assertTrue({"R1", "R4", "R5"}.issubset(cut_nodes))

    def test_tarjan_articulation_points_on_primary_failure(self):
        self.graph.failed_edges.add(edge_key("R3", "R5"))
        cut_nodes = set(self.graph.find_articulation_points())
        self.assertIn("R2", cut_nodes)
        self.assertIn("R5", cut_nodes)

    def test_remove_edge_permanently(self):
        self.graph.remove_edge("R1", "PC1")
        self.assertNotIn(edge_key("R1", "PC1"), self.graph.weights)
        self.assertNotIn("PC1", self.graph.adj["R1"])
        self.assertNotIn("PC1", self.graph.get_reachable_nodes("R1"))

    def test_toggle_edge_switches_state(self):
        key = edge_key("R3", "R5")
        self.assertTrue(self.graph.edge_is_up("R3", "R5"))
        self.assertFalse(self.graph.toggle_edge("R3", "R5"))
        self.assertFalse(self.graph.edge_is_up("R3", "R5"))
        self.assertTrue(self.graph.toggle_edge("R3", "R5"))
        self.assertTrue(self.graph.edge_is_up("R3", "R5"))

    def test_disconnected_subgraph_traversal(self):
        self.graph.failed_edges.update({
            edge_key("R1", "R4"),
            edge_key("R3", "R4"),
            edge_key("R4", "PC2"),
        })
        order, seen = self.graph.bfs("R4")
        self.assertEqual(["R4"], order)
        self.assertEqual({"R4"}, seen)

    def test_resilience_and_components_are_calculated_from_state(self):
        initial = self.graph.network_resilience_score()
        self.assertEqual(100, initial["score"])
        self.graph.failed_edges.update({
            edge_key("R3", "R5"),
            edge_key("R2", "R5"),
        })
        failed = self.graph.network_resilience_score()
        self.assertLess(failed["score"], initial["score"])
        self.assertGreaterEqual(len(failed["components"]), 2)

    def test_backup_candidates_return_ranked_missing_links(self):
        initial_weights = dict(self.graph.weights)
        initial_adjacency = {node: set(neighbors)
                             for node, neighbors in self.graph.adj.items()}
        candidates = self.graph.backup_link_candidates()
        self.assertTrue(candidates)
        self.assertIn("u", candidates[0])
        self.assertIn("v", candidates[0])
        self.assertIn("reason", candidates[0])
        self.assertEqual(initial_weights, self.graph.weights)
        self.assertEqual(initial_adjacency, self.graph.adj)

    def test_backup_candidates_skip_failed_routers(self):
        self.graph.toggle_node("R3")
        candidates = self.graph.backup_link_candidates()
        self.assertTrue(all("R3" not in (candidate["u"], candidate["v"])
                            for candidate in candidates))

    def test_backup_candidates_can_be_limited_to_router_nodes(self):
        candidates = self.graph.backup_link_candidates(["R1", "R5"])
        self.assertTrue(candidates)
        self.assertTrue(all(candidate["u"] in {"R1", "R5"} and
                            candidate["v"] in {"R1", "R5"}
                            for candidate in candidates))

    def test_backup_candidates_rank_single_link_failure_resilience(self):
        candidate = self.graph.backup_link_candidates(
            [node for node in NODES if node.startswith("R")]
        )[0]
        self.assertGreater(candidate["single_failure_gain"], 0)
        self.assertIn("single-link failure", candidate["reason"])

    def test_algorithm_step_snapshots(self):
        bfs_steps = self.graph.bfs_steps("R1")
        dfs_steps = self.graph.dfs_steps("R1")
        dijkstra_steps = self.graph.dijkstra_steps("R1", "Server1")
        tarjan_steps = self.graph.tarjan_steps()
        self.assertTrue(bfs_steps)
        self.assertTrue(dfs_steps)
        self.assertTrue(dijkstra_steps)
        self.assertTrue(tarjan_steps)
        self.assertEqual(["R1", "R2", "R3", "R5", "Server1"],
                         dijkstra_steps[-1]["path"])

    def test_dijkstra_steps_report_unavailable_endpoints(self):
        self.graph.toggle_node("R1")
        steps = self.graph.dijkstra_steps("R1", "Server1")
        self.assertIsNone(steps[-1]["path"])
        self.assertEqual(float("inf"), steps[-1]["cost"])

    def test_restore_all_and_failure_report(self):
        self.graph.toggle_edge("R3", "R5")
        self.graph.toggle_node("R4")
        report = self.graph.failure_report("Custom dual failure")
        self.assertEqual(["R4"], report["failed_routers"])
        self.assertEqual(["R3-R5"], report["failed_links"])
        self.assertEqual(2, self.graph.restore_all())
        self.assertEqual(set(), self.graph.failed_edges)
        self.assertEqual(set(), self.graph.failed_nodes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
