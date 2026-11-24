# NET-BLACKOUT — Network Blackout Analyzer

An interactive educational network-resilience analyzer built around graph data structures and algorithms. It models an enterprise network, simulates link and router failures, detects vulnerable infrastructure, recalculates shortest routes, tests redundant links, and demonstrates recovery.

> **Scope:** This project simulates graph-based network behavior and selected OSPF concepts for learning and demonstration. It is not a router, packet-capture tool, or complete standards-compliant OSPF implementation.

## Project at a glance

- **Core model:** Undirected, weighted graph represented by an adjacency list.
- **Default topology:** 8 devices and 9 links.
- **Primary path:** `R1 → R2 → R3 → R5 → Server1`, cost **4**.
- **Failover path:** When `R3–R5` fails, traffic can use `R1 → R2 → R5 → Server1`, cost **7**.
- **Interfaces:** Tkinter desktop GUI and a browser-based NOC dashboard.
- **Main algorithms:** BFS, DFS, Dijkstra shortest path, Tarjan bridges, and Tarjan articulation points.

## Network topology

The initial network contains these devices:

| Device | Role |
| --- | --- |
| R1 | Edge router and route-analysis source |
| R2 | Distribution router |
| R3 | Core router and primary server-uplink neighbor |
| R4 | Branch router |
| R5 | Services-core router |
| PC1 | Client endpoint connected to R1 |
| PC2 | Branch endpoint connected to R4 |
| Server1 | Destination server connected to R5 |

| Link | Cost | Purpose |
| --- | ---: | --- |
| R1–R2 | 1 | Core ring |
| R2–R3 | 1 | Core ring |
| R3–R4 | 1 | Core ring |
| R4–R1 | 1 | Core ring |
| R3–R5 | 1 | Primary server uplink |
| R2–R5 | 5 | Higher-cost backup uplink |
| R1–PC1 | 1 | Client access |
| R4–PC2 | 1 | Branch access |
| R5–Server1 | 1 | Server access |

Links are undirected. An edge failure takes the edge out of traversal and routing; a router failure makes that node unavailable along with all incident connections. Link weights represent simulated routing costs, not measured latency.

## Features

### Topology and live state

- View and interact with the network graph and link costs.
- Toggle links up or down and observe route recalculation.
- Highlight active routes, failed links, backup links, bridges, articulation points, and unreachable devices.
- Inspect an event log with simulated routing and recovery messages.
- The browser dashboard has a live packet-flow visualization for both PC1 and PC2. Choose the source endpoint, inspect its current route and cost, then click **Send packet**; successful, in-flight, and dropped packet counts are displayed. Traffic follows active links and routers, and an endpoint or route failure is reported as a dropped packet.

### Vulnerability and connectivity analysis

- Tarjan bridge detection identifies active links whose removal disconnects a component.
- Tarjan articulation-point detection identifies nodes whose removal increases the number of components.
- BFS-based reachability and connected-component analysis identify devices that are reachable or isolated from the analysis source.
- The Python graph API also exposes active node degrees and failure-report data.
- The dashboard highlights detected bridges and cut vertices on the topology.

### Shortest-path routing and failover

- Dijkstra calculates a least-cost route through active links and routers.
- After a failure, SPF is recalculated from the current topology; unavailable links and nodes are excluded.
- The dashboard reports route changes and costs in the event log and identifies whether the active path uses a backup link.
- In the default topology, failing `R3–R5` changes the route from cost 4 to cost 7 via `R2–R5`. Failing both server uplinks makes `Server1` unreachable from `R1`.

### Multiple failures and What-If scenarios

The browser resilience lab includes:

1. Primary uplink failure (`R3–R5`).
2. Backup uplink failure (`R2–R5`).
3. Simultaneous uplink failure.
4. R3 router failure.
5. Cascading core failure (both uplinks and core routers R3 and R4).

The web lab applies these cases to its in-memory simulation state, reports reachability and routing consequences, and can restore the failed links and routers. The desktop GUI also supports individual link/router toggles and analysis of the current combination of failures.

### Resilience and performance indicators

The resilience score is calculated from the live graph state—not a stored scenario result:

```text
score = max(0, 70 × reachable-node ratio
              + 30 × active-link ratio
              − 10 × (connected components − 1))
```

The result is rounded to a whole-number percentage. The reachable-node ratio is measured from R1 over all modeled nodes; active-link ratio is measured against all modeled links. A failed router remains part of the modeled node denominator but cannot be reached.

The browser dashboard also reports active/failed links, reachable devices, connectivity loss, available simple routes and average route cost, and packet delivery ratio once transmissions have occurred. These are simulation metrics, not production network telemetry.

### Backup-link recommendations

- Candidate router-to-router links are simulated against the current topology before recommendation.
- The candidates are ranked using their effect on average resilience across single-link-failure simulations, current connectivity score, and Tarjan vulnerability indicators.
- The recommendation includes an explanation and can be added to the running simulation.
- Applying a recommended link updates the graph and reruns route analysis. Resetting the desktop network removes links added during that run.
- Candidate links and their costs are hypothetical design options, not deployment instructions.

### Recovery and reports

- Restore failed links and routers sequentially, with visible status and elapsed recovery time.
- Recalculate connectivity and routes after each restoration step.
- Export a failure report as CSV from either interface.
- The browser can also print the report or save it as PDF using the browser's print dialog.
- Report data includes the scenario, failed links and routers, affected devices, route and costs, bridges, articulation points, resilience score, connectivity loss, and recovery details where available.

### Step-by-step algorithm viewer

The browser **Resilience & Algorithm Lab** tab provides **Step Backward**, **Step Forward**, **Play**, **Pause**, and **Reset** controls. It displays the current step and state for:

- **BFS:** traversal order, current node, queue, and visited nodes.
- **DFS:** traversal order and stack state.
- **Dijkstra:** selected nodes, tentative-distance updates, priority queue activity, resulting route, and route cost.
- **Tarjan:** discovery times, low-link values, DFS visitation, bridges, and articulation points.

The Python graph class also provides snapshot methods for BFS, DFS, Dijkstra, and Tarjan runs.

### Simulated OSPF behavior

The dashboard event log describes simulated link-state advertisements (LSAs), link-state database refreshes, shortest-path-first (SPF) recalculation, route changes, and recovery convergence time. These messages illustrate the concepts; they do not exchange real LSAs or implement the full OSPF protocol.

## Presentation outline

Use this sequence to introduce the problem, demonstrate the DSA, and close with design tradeoffs:

1. **Problem and objective** — Explain why a single failed link or router can interrupt service and why redundancy matters.
2. **Model and assumptions** — Introduce the 8-device, 9-link weighted graph, active/failed state, and simulated link costs.
3. **Baseline route** — Show the initial `R1 → Server1` route and cost 4; explain why Dijkstra chooses it over the higher-cost backup.
4. **Graph traversal** — Run BFS or DFS and discuss reachability, queues/stacks, and complexity.
5. **Vulnerability detection** — Highlight bridges and articulation points; explain Tarjan's `tin` and `low` conditions.
6. **Single-link failover** — Fail `R3–R5`, show the route switch to the backup and cost increase from 4 to 7, and connect the event to simulated OSPF SPF recalculation.
7. **Multiple/cascading failures** — Compare primary, backup, simultaneous-uplink, router, and cascading scenarios; identify affected devices and disconnected components.
8. **Resilience measurement** — Explain the score inputs and compare baseline and failed-state values; distinguish topology health from packet-delivery statistics.
9. **Redundancy design** — Generate and apply a candidate router link; explain how simulated failure cases inform the recommendation.
10. **Recovery and reporting** — Restore links/routers, show route recovery and elapsed time, then export a CSV or print/save a PDF report.
11. **Limitations and future work** — Clarify simulated versus real OSPF/traffic, discuss chosen score weights, and identify where a more realistic topology or external data could be added.

**Suggested live demo:** start on the healthy graph → step through Dijkstra or Tarjan → fail the primary uplink → inspect failover and score → fail both uplinks → inspect isolation → restore → recommend/apply a redundant link → send a packet manually → export the report.

## Run the application

### Browser dashboard

From the repository root:

```bash
python server.py
```

Open `http://localhost:8080`. The server serves the local dashboard and attempts to open it in a browser.

### Tkinter desktop GUI

From the repository root:

```bash
python network_blackout.py
```

The desktop GUI includes link/router controls, route finding, BFS/DFS, bridge and articulation analysis, resilience and component summaries, backup-link recommendation/application, CSV report export, and sequential failure recovery.

## Project structure

| Path | Responsibility |
| --- | --- |
| `algorithms/graph.py` | Graph model, operational state, BFS/DFS, Dijkstra, Tarjan, resilience, recommendation, and failure-report algorithms |
| `gui/network_gui.py` | Tkinter topology visualization, controls, status, event log, recovery, and report export |
| `network_blackout.py` | Desktop application entry point |
| `server.py` | Local static dashboard server |
| `web/index.html` | Browser NOC dashboard, simulation interactions, algorithm view, and report export |
| `tests/test_graph.py` | Unit tests for graph algorithms, failures, recovery, score, and recommendation |
| `docs/project_documentation.md` | Shorter project reference documentation |

## Algorithms and complexity

Let `V` be the number of modeled devices and `E` the number of modeled links.

| Algorithm | Use | Complexity |
| --- | --- | --- |
| BFS | Reachability, components, traversal order | `O(V + E)` |
| DFS | Traversal and connected components | `O(V + E)` |
| Tarjan bridges | Identify cut-edges | `O(V + E)` |
| Tarjan articulation points | Identify cut vertices | `O(V + E)` |
| Dijkstra with binary min-heap | Least-cost route for non-negative edge weights | `O((V + E) log V)` |
| Backup candidates | Simulates missing router pairs and single-link failures | Repeated graph analyses; depends on candidate-pair count |

For Tarjan's undirected DFS, a tree edge `(u, v)` is a bridge if `low[v] > tin[u]`. A non-root vertex `u` is an articulation point if some child `v` satisfies `low[v] >= tin[u]`; a DFS root is an articulation point when it has at least two DFS-tree children.

## Tests

Run the graph unit tests from the repository root:

```bash
python -m unittest tests/test_graph.py
```

The tests cover traversal, shortest paths and failover, unreachable destinations, bridge/articulation detection, edge and router state, disconnected components, resilience scores, backup-link candidate ranking, algorithm snapshots, reports, and recovery.

## Deployment

The browser dashboard is a static HTML page and may be deployed using the repository's existing Vercel or GitHub Pages configuration. The Python desktop application and local server run separately and are not hosted by those static-site deployments.
