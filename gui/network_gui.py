"""
GUI module for Network Blackout Analyzer using Tkinter / ttk.
Provides visual topology rendering, manual toggles, blackout simulation,
bridge/articulation point highlighting, live logs, statistics, and recovery animations.
"""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from algorithms.graph import Graph, edge_key, NODES, EDGE_DEFINITIONS, POSITIONS


class NetworkBlackoutApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Network Blackout Analyzer | DSA Project")
        self.root.geometry("1160x780")
        self.root.minsize(1020, 700)

        self.graph = Graph(NODES)
        for u, v, weight, backup in EDGE_DEFINITIONS:
            self.graph.add_edge(u, v, weight, backup)

        self.edge_vars: dict[tuple[str, str], tk.BooleanVar] = {}
        self.last_path: list[str] = []
        self.last_bridges: set[tuple[str, str]] = set()
        self.last_articulations: set[str] = set()
        self.status = tk.StringVar(value="Network online. Select a link or run an analysis.")
        self._build_ui()
        self.refresh_view()
        self.log("Application initialized.")
        self.log("Topology: Core Ring R1-R2-R3-R4-R1; Primary Uplink R3-R5; Backup Link R2-R5.")
        self.log("Route metrics: Primary links = 1; Redundant backup R2-R5 = 5.")

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="NETWORK BLACKOUT ANALYZER",
                  font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Graph Resilience • Tarjan Bridges & Articulation Points • Dijkstra Failover",
                  font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 8))

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(body, width=340)
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)

        self.canvas = tk.Canvas(left, bg="#f7f9fc", highlightthickness=1,
                                highlightbackground="#d0d7e2", height=450)
        self.canvas.pack(fill="both", expand=True)

        ttk.Label(right, text="LINK STATUS (uncheck = DOWN)",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        link_box = ttk.Frame(right)
        link_box.pack(fill="x", pady=(5, 8))
        for u, v, weight, backup in EDGE_DEFINITIONS:
            key = edge_key(u, v)
            var = tk.BooleanVar(value=True)
            self.edge_vars[key] = var
            suffix = f"  [backup, cost {weight}]" if backup else f"  [cost {weight}]"
            cb = ttk.Checkbutton(
                link_box, text=f"{u} — {v}{suffix}", variable=var,
                command=lambda a=u, b=v, value=var: self.on_link_toggle(a, b, value)
            )
            cb.pack(anchor="w")

        ttk.Separator(right).pack(fill="x", pady=5)
        buttons = [
            ("Simulate Blackout (R3-R5)", self.simulate_blackout),
            ("Analyze Bridges (Tarjan)", self.analyze_bridges),
            ("Analyze Articulation Points (Cut Vertices)", self.analyze_articulation_points),
            ("Run BFS Reachability", self.run_bfs),
            ("Run DFS Traversal", self.run_dfs),
            ("Find Route to Server1", self.find_route),
            ("Analyze Current Failures", self.analyze_current_failures),
            ("Animate Link Recovery", self.animate_recovery),
            ("Reset Network", self.reset_network),
        ]
        for label, command in buttons:
            ttk.Button(right, text=label, command=command).pack(fill="x", pady=2)

        ttk.Label(right, text="STATUS", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        ttk.Label(right, textvariable=self.status, wraplength=320).pack(anchor="w")

        ttk.Separator(right).pack(fill="x", pady=6)
        ttk.Label(right, text="NETWORK STATISTICS", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.stats = tk.StringVar(value="Calculating network statistics...")
        ttk.Label(right, textvariable=self.stats, justify="left", wraplength=320).pack(anchor="w", pady=(3, 0))

        ttk.Label(outer, text="LIVE EVENT LOG", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        log_frame = ttk.Frame(outer)
        log_frame.pack(fill="both", expand=False)
        self.log_text = tk.Text(log_frame, height=8, wrap="word", state="disabled",
                                font=("Consolas", 9), bg="#101827", fg="#e6edf3",
                                insertbackground="white")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def log(self, message: str):
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def on_link_toggle(self, u, v, variable):
        key = edge_key(u, v)
        if variable.get():
            self.graph.failed_edges.discard(key)
            self.log(f"LINK UP: {u} — {v}")
        else:
            self.graph.failed_edges.add(key)
            self.log(f"LINK DOWN: {u} — {v}")
        self.last_path = []
        self.last_bridges.clear()
        self.last_articulations.clear()
        self.refresh_view()

    def simulate_blackout(self):
        key = edge_key("R3", "R5")
        self.graph.failed_edges.add(key)
        self.edge_vars[key].set(False)
        self.last_bridges.clear()
        self.last_articulations.clear()
        path, cost = self.graph.find_shortest_path("R1", "Server1")
        self.last_path = path or []
        self.refresh_view()
        self.log("BLACKOUT: primary uplink R3 — R5 is DOWN.")
        if path:
            self.log(f"FAILOVER ROUTE: {' -> '.join(path)} (total cost {cost:g}).")
            self.status.set(f"Primary link failed. Backup route active: {' → '.join(path)}")
        else:
            self.log("FAILOVER FAILED: Server1 is unreachable from R1.")
            self.status.set("Server1 is unreachable from R1.")

    def analyze_bridges(self):
        self.last_bridges = set(self.graph.find_bridges())
        self.last_path = []
        self.last_articulations.clear()
        self.refresh_view()
        if self.last_bridges:
            text = ", ".join(f"{u}-{v}" for u, v in sorted(self.last_bridges))
            self.log(f"TARJAN BRIDGES: {text}")
            self.status.set(f"Critical active bridge links: {text}")
        else:
            self.log("TARJAN BRIDGES: No active bridges in this component.")
            self.status.set("No active bridges detected.")

    def analyze_articulation_points(self):
        self.last_articulations = set(self.graph.find_articulation_points())
        self.last_path = []
        self.last_bridges.clear()
        self.refresh_view()
        if self.last_articulations:
            text = ", ".join(sorted(self.last_articulations))
            self.log(f"TARJAN ARTICULATION POINTS (Cut Vertices): {text}")
            self.status.set(f"Critical cut vertices (failure isolates nodes): {text}")
        else:
            self.log("TARJAN ARTICULATION POINTS: None found.")
            self.status.set("No articulation points detected.")

    def run_bfs(self):
        order, reachable = self.graph.bfs("R1")
        offline = sorted(set(self.graph.adj) - reachable)
        self.last_path = []
        self.last_bridges.clear()
        self.last_articulations.clear()
        self.refresh_view()
        self.log("BFS VISIT ORDER: " + (" -> ".join(order) if order else "(none)"))
        self.log("REACHABLE FROM R1: " + (", ".join(sorted(reachable)) or "None"))
        self.log("UNREACHABLE FROM R1: " + (", ".join(offline) if offline else "None"))
        self.status.set(f"BFS found {len(reachable)}/{len(self.graph.adj)} nodes reachable from R1.")

    def run_dfs(self):
        order, reachable = self.graph.dfs("R1")
        offline = sorted(set(self.graph.adj) - reachable)
        self.last_path = []
        self.last_bridges.clear()
        self.last_articulations.clear()
        self.refresh_view()
        self.log("DFS VISIT ORDER: " + (" -> ".join(order) if order else "(none)"))
        self.log("REACHABLE FROM R1: " + (", ".join(sorted(reachable)) or "None"))
        self.log("UNREACHABLE FROM R1: " + (", ".join(offline) if offline else "None"))
        self.status.set(f"DFS found {len(reachable)}/{len(self.graph.adj)} nodes reachable from R1.")

    def find_route(self):
        path, cost = self.graph.find_shortest_path("R1", "Server1")
        self.last_path = path or []
        self.last_bridges.clear()
        self.last_articulations.clear()
        self.refresh_view()
        if path:
            self.log(f"SHORTEST ROUTE TO Server1: {' -> '.join(path)} (cost {cost:g}).")
            self.status.set(f"Route cost {cost:g}: {' → '.join(path)}")
        else:
            self.log("NO ROUTE: Server1 cannot be reached from R1.")
            self.status.set("Server1 is unreachable from R1.")

    def analyze_current_failures(self):
        down = sorted(self.graph.failed_edges)
        order, reachable = self.graph.bfs("R1")
        offline = sorted(set(self.graph.adj) - reachable)
        path, cost = self.graph.find_shortest_path("R1", "Server1")
        self.last_path = path or []
        self.last_bridges.clear()
        self.last_articulations.clear()
        self.refresh_view()
        down_text = ", ".join(f"{u}-{v}" for u, v in down) if down else "None"
        offline_text = ", ".join(offline) if offline else "None"
        self.log(f"MULTI-LINK ANALYSIS: failed links = {down_text}.")
        self.log(f"REACHABILITY: {len(reachable)}/{len(self.graph.adj)} nodes reachable from R1; offline = {offline_text}.")
        if path:
            self.log(f"ROUTE STATUS: Server1 reachable via {' -> '.join(path)} (cost {cost:g}).")
            self.status.set(f"{len(down)} failed link(s). Server1 reachable; route cost {cost:g}.")
        else:
            self.log("ROUTE STATUS: Server1 is unreachable from R1.")
            self.status.set(f"{len(down)} failed link(s). Server1 is unreachable.")

    def animate_recovery(self):
        if getattr(self, "recovery_running", False):
            self.status.set("Recovery animation is already running.")
            return
        pending = sorted(self.graph.failed_edges)
        if not pending:
            self.status.set("No failed links to recover. The network is already online.")
            self.log("RECOVERY: no failed links; network already online.")
            return
        self.recovery_running = True
        self.last_path = []
        self.last_bridges.clear()
        self.last_articulations.clear()
        self.log(f"RECOVERY STARTED: restoring {len(pending)} failed link(s) one at a time.")

        def restore_next(index=0):
            if index >= len(pending):
                self.recovery_running = False
                path, cost = self.graph.find_shortest_path("R1", "Server1")
                self.last_path = path or []
                self.refresh_view()
                self.status.set("Recovery complete. All previously failed links are restored.")
                self.log("RECOVERY COMPLETE: all previously failed links restored.")
                if path:
                    self.log(f"POST-RECOVERY ROUTE: {' -> '.join(path)} (cost {cost:g}).")
                return
            key = pending[index]
            self.graph.failed_edges.discard(key)
            if key in self.edge_vars:
                self.edge_vars[key].set(True)
            self.refresh_view()
            self.log(f"LINK RECOVERED ({index + 1}/{len(pending)}): {key[0]} — {key[1]} is UP.")
            self.status.set(f"Recovering links: {index + 1}/{len(pending)} restored.")
            self.root.after(650, lambda: restore_next(index + 1))

        restore_next()

    def reset_network(self):
        self.graph.failed_edges.clear()
        for var in self.edge_vars.values():
            var.set(True)
        self.last_path = []
        self.last_bridges.clear()
        self.last_articulations.clear()
        self.refresh_view()
        self.status.set("All links restored.")
        self.log("RESET: all network links restored.")

    def refresh_view(self):
        self.canvas.delete("all")
        reachable = self.graph.get_reachable_nodes("R1")
        path_edges = {
            edge_key(self.last_path[i], self.last_path[i + 1])
            for i in range(len(self.last_path) - 1)
        }

        # Draw edges
        for u, v, weight, backup in EDGE_DEFINITIONS:
            x1, y1 = POSITIONS[u]
            x2, y2 = POSITIONS[v]
            key = edge_key(u, v)
            failed = key in self.graph.failed_edges
            bridge = key in self.last_bridges
            on_path = key in path_edges
            if failed:
                color, width, dash = "#dc2626", 3, (7, 4)
            elif bridge:
                color, width, dash = "#f59e0b", 5, ()
            elif on_path:
                color, width, dash = "#2563eb", 5, ()
            elif backup:
                color, width, dash = "#8b5cf6", 2, (4, 3)
            else:
                color, width, dash = "#94a3b8", 2, ()
            self.canvas.create_line(x1, y1, x2, y2, fill=color, width=width,
                                    dash=dash, capstyle=tk.ROUND)
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            label = "DOWN" if failed else (f"cost {weight}" if backup else str(weight))
            self.canvas.create_rectangle(mx - 25, my - 10, mx + 25, my + 10,
                                         fill="#f7f9fc", outline="")
            self.canvas.create_text(mx, my, text=label, fill="#334155",
                                    font=("Segoe UI", 8, "bold"))

        # Draw nodes
        for node, (x, y) in POSITIONS.items():
            is_cut = node in self.last_articulations
            if node not in reachable:
                fill = "#dc2626"
            elif is_cut:
                fill = "#d97706"  # Highlight articulation points in Amber/Gold
            elif node == "Server1":
                fill = "#0f766e"
            elif node.startswith("PC"):
                fill = "#64748b"
            else:
                fill = "#16a34a"

            radius = 24 if node.startswith("R") else 21
            outline_color = "#b45309" if is_cut else "white"
            outline_width = 3 if is_cut else 2
            self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius,
                                    fill=fill, outline=outline_color, width=outline_width)
            self.canvas.create_text(x, y, text=node, fill="white",
                                    font=("Segoe UI", 10, "bold"))

        # Legend
        legend = [
            ("#94a3b8", "Active link"), ("#dc2626", "Failed link"),
            ("#f59e0b", "Bridge edge"), ("#d97706", "Cut vertex"),
            ("#2563eb", "Selected route"), ("#8b5cf6", "Backup link"),
        ]
        y = 435
        x = 10
        for color, label in legend:
            self.canvas.create_line(x, y, x + 18, y, fill=color, width=4)
            self.canvas.create_text(x + 22, y, text=label, anchor="w",
                                   fill="#334155", font=("Segoe UI", 8))
            x += 105

        up_count = len(self.graph.weights) - len(self.graph.failed_edges)
        down_count = len(self.graph.failed_edges)
        bridge_count = len(self.graph.find_bridges())
        cut_count = len(self.graph.find_articulation_points())
        path, cost = self.graph.find_shortest_path("R1", "Server1")
        route_text = f"Available (cost {cost:g})" if path else "UNREACHABLE"
        reachable_count = len(reachable)
        self.stats.set(
            f"Nodes: {len(self.graph.adj)}\n"
            f"Links up: {up_count} | Links down: {down_count}\n"
            f"Reachable from R1: {reachable_count}/{len(self.graph.adj)}\n"
            f"Active bridges: {bridge_count} | Cut vertices: {cut_count}\n"
            f"R1 → Server1: {route_text}"
        )
