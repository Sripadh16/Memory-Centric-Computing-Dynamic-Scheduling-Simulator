"""
Root Experiment Runner Script.
Runs the entire simulation suite and generates all analytical plots.
Usage:
    python run_experiments.py
"""

import sys
import os

if __name__ == "__main__":
    print("=" * 70)
    print("Memory-Centric Computing Architecture: Dynamic Placement Simulator")
    print("=" * 70)

    # 1. Run simulation suite
    import experiments.run_all as run_all
    run_all.main()

    # 2. Generate plots
    import experiments.plot_results as plot_results
    plot_results.main()

    print("\n" + "=" * 70)
    print("All experiments and plots have been generated in 'experiments/results/'")
    print("Launch interactive visualizer using: python run_dashboard.py")
    print("=" * 70)
