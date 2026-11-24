# Network Blackout Analyzer

## Overview

Network Blackout Analyzer is a graph-based network resilience tool. It models an eight-node enterprise topology, simulates router or link failures, detects critical infrastructure, and recalculates routes from R1 to Server1.

The project includes a Tkinter desktop application and an interactive browser dashboard.

## Topology

The undirected weighted graph contains:

- **Nodes:** R1, R2, R3, R4, R5, PC1, PC2, Server1
- **Core ring:** R1-R2-R3-R4-R1
- **Primary server uplink:** R3-R5, cost 1
- **Backup uplink:** R2-R5, cost 5
- **Access links:** R1-PC1, R4-PC2, R5-Server1

Edge and node states can be toggled to simulate blackouts. All algorithms operate on the remaining active graph.

## Algorithms

| Algorithm | Purpose | Time complexity |
| --- | --- | --- |
| BFS | Reachability and visit order | O(\|V\| + \|E\|) |
| DFS | Reachability and traversal | O(\|V\| + \|E\|) |
| Tarjan bridge finding | Detect cut-edges whose failure disconnects the graph | O(\|V\| + \|E\|) |
| Tarjan articulation points | Detect cut-nodes whose failure disconnects the graph | O(\|V\| + \|E\|) |
| Dijkstra | Find the lowest-cost R1-to-Server1 route | O(\|E\| log \|V\|) |

An edge `(u, v)` is a bridge when `low[v] > tin[u]` during Tarjan traversal. A non-root node is a cut vertex when `low[child] >= tin[node]`; a root is a cut vertex when it has at least two DFS children.

Dijkstra excludes failed edges and nodes. The normal route is R1-R2-R3-R5-Server1, cost 4. Failure of R3-R5 causes failover to R1-R2-R5-Server1, cost 7.

## Interfaces

- **Desktop:** Run `python network_blackout.py` for the Tkinter visualization and controls.
- **Browser:** Run `python server.py`, then open `http://localhost:8080`. The server serves `web/index.html` and opens the page automatically.
- **Web controls:** Simulate outages, recover the topology, highlight bridges and cut vertices, and run BFS or DFS traversals. Packet flow starts only when **Send packet** is clicked; the panel reports delivered, in-flight, and dropped packets.
- **Resilience lab:** Run predefined link and router failure scenarios, compare pre/post route and resilience details, inspect connectivity health, and export a failure report as CSV or print/save it as PDF.
- **Redundancy planning:** Simulate candidate links against the active topology, rank candidates by connectivity and bridge reduction, and apply a recommendation to the running simulation.
- **Algorithm controls:** Step through, play, pause, and reset BFS, DFS, Dijkstra SPF, and Tarjan snapshots. OSPF convergence and LSA messages are educational simulation behavior, not a complete OSPF implementation.

## Implementation

- `algorithms/graph.py`: graph model and algorithms
- `gui/network_gui.py`: desktop visualization and controls
- `network_blackout.py`: desktop entry point
- `server.py`: local HTTP server
- `web/index.html`: browser dashboard
- `tests/test_graph.py`: graph algorithm and failure tests
- `algorithms/graph.py`: resilience scoring, components, backup-link ranking, failure reports, and algorithm snapshots

## Testing

Run the unit tests with:

```bash
python -m unittest tests/test_graph.py
```

Tests cover traversal, failover, unreachable destinations, bridge and cut-node detection, edge and node toggling, permanent edge removal, resilience scoring, candidate links, algorithm snapshots, and recovery reports.
