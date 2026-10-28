# Network Blackout Analyzer — DSA Project Documentation

## 1. Problem Statement & Mathematical Formulation
An enterprise network topology is modeled as an undirected weighted graph $G = (V, E)$, where:
- **Vertices ($V$)**: $V = \{R1, R2, R3, R4, R5, PC1, PC2, Server1\}$ ($|V| = 8$).
- **Edges ($E$)**:
  - Core ring: $(R1, R2), (R2, R3), (R3, R4), (R4, R1)$ with weight 1.
  - Primary Server Uplink: $(R3, R5)$ with weight 1.
  - Redundant Backup Uplink: $(R2, R5)$ with weight 5 (models higher OSPF cost / metric).
  - Access LAN links: $(R1, PC1), (R4, PC2), (R5, Server1)$ with weight 1.

The objective is to analyze network survivability, detect single points of failure (bridges and cut vertices), and evaluate dynamic failover routes during link blackouts.

---

## 2. Algorithms Implemented & Complexity Analysis

### 2.1 Breadth-First Search (BFS) & Depth-First Search (DFS)
- **Purpose**: Evaluates reachability and identifies isolated network components.
- **Data Structures**: Queue (`collections.deque`) for BFS, Stack (`list`) for DFS, `set` for visited tracking.
- **Time Complexity**: $\mathcal{O}(|V| + |E|)$ — each vertex and incident edge is explored once.
- **Space Complexity**: $\mathcal{O}(|V|)$ — auxiliary space for traversal queue/stack and visited sets.

### 2.2 Tarjan's Bridge-Finding Algorithm
- **Purpose**: Finds critical edges whose failure partitions the network into disconnected components.
- **Mechanism**: DFS spanning tree maintaining discovery times `tin[u]` and lowest reachable ancestor `low[u]`.
- **Condition**: An edge $(u, v)$ is a bridge if $low[v] > tin[u]$.
- **Time Complexity**: $\mathcal{O}(|V| + |E|)$.
- **Space Complexity**: $\mathcal{O}(|V|)$.

### 2.3 Tarjan's Articulation Points (Cut Vertices) Algorithm
- **Purpose**: Finds critical router nodes whose complete failure isolates portions of the network.
- **Conditions**:
  1. Root node of DFS tree with $\ge 2$ children in DFS tree.
  2. Non-root node $u$ with child $v$ such that $low[v] \ge tin[u]$.
- **Time Complexity**: $\mathcal{O}(|V| + |E|)$.
- **Space Complexity**: $\mathcal{O}(|V|)$.

### 2.4 Dijkstra's Shortest Path Algorithm
- **Purpose**: Simulates dynamic routing (OSPF shortest path first) from source (R1) to Server1.
- **Mechanism**: Min-priority heap (`heapq`). Under primary uplink failure $(R3, R5)$, Dijkstra dynamically recalculates the path via the backup link $(R2, R5)$.
- **Time Complexity**: $\mathcal{O}(|E| \log |V|)$ using min-heap.
- **Space Complexity**: $\mathcal{O}(|V|)$ for distances and predecessor map.
