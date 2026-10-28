"""
Network Blackout Analyzer - Main Entry Point
DSA Project: Graph Algorithms, Bridges, Cut Vertices, and Failover Simulation.

Run with: python network_blackout.py
"""

import sys
import os

# Ensure package root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from tkinter import ttk
from gui.network_gui import NetworkBlackoutApp


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    NetworkBlackoutApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
