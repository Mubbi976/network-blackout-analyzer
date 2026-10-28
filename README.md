# Network Blackout Analyzer

An academic Data Structures and Algorithms (DSA) project in Python demonstrating graph resilience, bridge and articulation point detection, and dynamic failover routing.

## Project Structure
```text
NetworkBlackoutAnalyzer/
│
├── network_blackout.py           # Main application entry point
├── requirements.txt              # Environment dependencies
├── README.md                     # Setup and usage guide
├── .gitignore                    # Git tracking rules
│
├── algorithms/                   # Core DSA graph implementation
│   ├── __init__.py
│   └── graph.py                  # Graph, BFS, DFS, Tarjan, Dijkstra
│
├── gui/                          # Presentation layer
│   ├── __init__.py
│   └── network_gui.py            # Tkinter/ttk Canvas UI & event handlers
│
├── tests/                        # Automated unit test suite
│   ├── __init__.py
│   └── test_graph.py             # 11 unit tests for algorithms
│
└── docs/                         # Academic documentation
    └── project_documentation.md  # Viva defense & complexity breakdown
```

---

## Visual Studio Code Setup & Execution

### 1. Open Project in VS Code
Open VS Code, press `Ctrl + K, Ctrl + O` (or **File -> Open Folder...**), and select the `NetworkBlackoutAnalyzer` folder.

### 2. Configure Python Virtual Environment
Open the VS Code integrated terminal (`Ctrl + ~`):

```bash
# Windows (PowerShell / Command Prompt)
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Run Automated Tests
Verify all 11 unit tests pass:
```bash
python -m unittest tests/test_graph.py -v
```

### 4. Launch the Interactive GUI
You now have **two GUI options** to run this project:

#### Option A: Modern Enterprise Web NOC Dashboard (Recommended)
Launch the modern, responsive web dashboard with live Dijkstra path glow, draggable nodes, and telemetry cards:
```bash
python server.py
```
*(Automatically opens your browser to `http://localhost:8080`)*

#### Option B: Native Desktop Tkinter GUI
Run the native desktop Tkinter interface:
```bash
python network_blackout.py
```
