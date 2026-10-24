"""
Publication-Quality Visualization Suite for Memory-Centric Computing Architecture.
Generates comprehensive plots:
1. Speedup comparison across policies
2. Interconnect data movement reduction
3. Detailed energy breakdown (Compute, Interconnect, Memory, Overhead)
4. Interconnect bandwidth sensitivity
5. Dynamic multi-phase placement execution timeline
6. Roofline placement model
"""

import os
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
JSON_PATH = os.path.join(RESULTS_DIR, "simulation_results.json")

# Styling: IEEE/ACM publication style
plt.rcParams.update({
    'font.sans-serif': 'DejaVu Sans',
    'font.size': 11,
    'axes.labelsize': 12,
    'axes.titlesize': 13,
    'xtick.labelsize': 11,
    'ytick.labelsize': 11,
    'legend.fontsize': 10,
    'figure.titlesize': 14,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight'
})

COLORS = {
    'ALWAYS_HOST': '#3b82f6',         # Blue
    'ALWAYS_PIM': '#ef4444',          # Red
    'DYNAMIC_INTELLIGENT': '#10b981', # Green (Ours)
    'ORACLE': '#8b5cf6'               # Purple
}

def load_data():
    with open(JSON_PATH, "r") as f:
        return json.load(f)

def plot_speedup_comparison(data):
    fig, ax = plt.subplots(figsize=(9, 5))
    policy_comp = data["policy_comparison"]
    
    workloads = list(policy_comp.keys())
    labels = ["Reusable\n(Dense GEMM)", "Streaming\n(SAXPY Filter)", "Random\n(Graph BFS)", "Mixed\nPipeline"]
    policies = ["ALWAYS_HOST", "ALWAYS_PIM", "DYNAMIC_INTELLIGENT", "ORACLE"]
    
    x = np.arange(len(workloads))
    width = 0.20

    for i, pol in enumerate(policies):
        speedups = [policy_comp[w][pol]["speedup"] for w in workloads]
        bars = ax.bar(x + (i - 1.5) * width, speedups, width, label=pol.replace("_", " "), color=COLORS[pol], edgecolor='black', linewidth=0.8)
        
        # Value annotations
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height:.1f}x',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points",
                        ha='center', va='bottom', fontsize=8, fontweight='bold')

    ax.set_ylabel("Speedup vs. Always-Host (Log Scale)")
    ax.set_title("Execution Speedup Across Placement Policies (Higher is Better)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_yscale('log')
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.1fx"))
    ax.axhline(1.0, color='gray', linestyle='--', linewidth=1, alpha=0.7)
    ax.grid(axis='y', linestyle=':', alpha=0.6)
    ax.legend(framealpha=0.9)

    out_path = os.path.join(RESULTS_DIR, "speedup_comparison.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

def plot_data_movement(data):
    fig, ax = plt.subplots(figsize=(9, 5))
    policy_comp = data["policy_comparison"]
    
    workloads = list(policy_comp.keys())
    labels = ["Reusable\n(Dense GEMM)", "Streaming\n(SAXPY Filter)", "Random\n(Graph BFS)", "Mixed\nPipeline"]
    policies = ["ALWAYS_HOST", "ALWAYS_PIM", "DYNAMIC_INTELLIGENT"]
    
    x = np.arange(len(workloads))
    width = 0.26

    for i, pol in enumerate(policies):
        traffic = [policy_comp[w][pol]["total_data_movement_mb"] for w in workloads]
        bars = ax.bar(x + (i - 1) * width, traffic, width, label=pol.replace("_", " "), color=COLORS[pol], edgecolor='black', linewidth=0.8)
        
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height:.1f}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points",
                        ha='center', va='bottom', fontsize=8)

    ax.set_ylabel("Host-Memory Interconnect Traffic (MB)")
    ax.set_title("Off-Chip Data Movement Reduction Across Host Bus (Lower is Better)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.grid(axis='y', linestyle=':', alpha=0.6)
    ax.legend(framealpha=0.9)

    out_path = os.path.join(RESULTS_DIR, "data_movement_reduction.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

def plot_energy_breakdown(data):
    fig, axes = plt.subplots(1, 4, figsize=(14, 5), sharey=False)
    policy_comp = data["policy_comparison"]
    workload_names = list(policy_comp.keys())
    titles = ["Dense GEMM (Reusable)", "SAXPY Filter (Streaming)", "Graph BFS (Random)", "Mixed Pipeline"]

    categories = ['Compute', 'Interconnect', 'Memory', 'Decision OH']
    cat_colors = ['#3b82f6', '#f59e0b', '#ec4899', '#64748b']

    for idx, w_name in enumerate(workload_names):
        ax = axes[idx]
        pols = ["ALWAYS_HOST", "ALWAYS_PIM", "DYNAMIC_INTELLIGENT"]
        pol_labels = ["Host", "PIM", "Dynamic"]
        
        bottom = np.zeros(len(pols))
        for c_idx, cat in enumerate(['compute_energy_uj', 'interconnect_energy_uj', 'memory_energy_uj', 'decision_energy_uj']):
            vals = np.array([policy_comp[w_name][p][cat] / 1000.0 for p in pols]) # in mJ
            ax.bar(pol_labels, vals, bottom=bottom, label=categories[c_idx] if idx == 0 else "", color=cat_colors[c_idx], edgecolor='black', linewidth=0.6)
            bottom += vals

        ax.set_title(titles[idx], fontsize=11)
        ax.set_ylabel("Energy (mJ)" if idx == 0 else "")
        ax.grid(axis='y', linestyle=':', alpha=0.5)

    fig.suptitle("Subsystem Energy Breakdown Across Architectural Policies", fontsize=13, y=1.02)
    fig.legend(loc='lower center', bbox_to_anchor=(0.5, -0.08), ncol=4, framealpha=0.9)
    
    out_path = os.path.join(RESULTS_DIR, "energy_breakdown.png")
    fig.savefig(out_path, bbox_inches='tight')
    plt.close(fig)
    print(f"Generated: {out_path}")

def plot_interconnect_sensitivity(data):
    fig, ax = plt.subplots(figsize=(8, 4.8))
    sens = data["interconnect_sensitivity"]
    bws = [int(k) for k in sens.keys()]
    
    host_times = [sens[str(bw)]["Streaming_ALWAYS_HOST"]["execution_time_ms"] for bw in bws]
    dyn_times = [sens[str(bw)]["Streaming_DYNAMIC_INTELLIGENT"]["execution_time_ms"] for bw in bws]

    ax.plot(bws, host_times, marker='o', linewidth=2.2, color='#3b82f6', label='Host Execution (Bus-bound)')
    ax.plot(bws, dyn_times, marker='s', linewidth=2.2, color='#10b981', label='Dynamic PIM Execution (In-Memory TSVs)')

    ax.set_xlabel("Interconnect Bandwidth (GB/s)")
    ax.set_ylabel("Execution Time (ms)")
    ax.set_title("Interconnect Sensitivity: Streaming Execution vs. Host Bus Bandwidth")
    ax.grid(True, linestyle=':', alpha=0.6)
    ax.legend(framealpha=0.9)

    out_path = os.path.join(RESULTS_DIR, "interconnect_sensitivity.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

def plot_roofline_and_placement():
    fig, ax = plt.subplots(figsize=(9, 5))
    
    # Intensities from 0.01 to 100 FLOPs/byte
    intensities = np.logspace(-2, 2.5, 200)

    # Host Roofline: Peak Compute = 1843 GFLOPs, Interconnect BW = 64 GB/s
    host_peak_compute = 1843.2
    host_bw = 64.0
    host_perf = np.minimum(host_peak_compute, intensities * host_bw)

    # PIM Roofline: Peak Compute = 128 GFLOPs, Internal TSV BW = 1024 GB/s
    pim_peak_compute = 128.0
    pim_bw = 1024.0
    pim_perf = np.minimum(pim_peak_compute, intensities * pim_bw)

    ax.plot(intensities, host_perf, color='#3b82f6', linewidth=2.5, label='Host CPU Roofline (64 GB/s link, 1.84 TFLOPs)')
    ax.plot(intensities, pim_perf, color='#ef4444', linewidth=2.5, linestyle='--', label='PIM Roofline (1024 GB/s TSVs, 128 GFLOPs)')

    # Annotate Key Workloads
    # Streaming: ~0.35 FLOPs/B
    ax.scatter([0.35], [np.minimum(host_peak_compute, 0.35 * host_bw)], color='#10b981', s=120, zorder=5)
    ax.scatter([0.35], [np.minimum(pim_peak_compute, 0.35 * pim_bw)], color='#10b981', s=120, zorder=5)
    ax.annotate("Streaming SAXPY\n(PIM favored: ~5.7x higher perf)", xy=(0.35, 128.0), xytext=(0.4, 250.0),
                arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=6), fontsize=9, fontweight='bold')

    # Random Graph BFS: ~0.15 FLOPs/B effective
    ax.scatter([0.15], [0.15 * host_bw], color='#f59e0b', s=120, zorder=5)
    ax.scatter([0.15], [0.15 * pim_bw], color='#f59e0b', s=120, zorder=5)
    ax.annotate("Random Graph BFS\n(PIM favored: 14x speedup)", xy=(0.15, 0.15 * pim_bw), xytext=(0.02, 35.0),
                arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=6), fontsize=9, fontweight='bold')

    # Reusable GEMM: ~16 FLOPs/B
    ax.scatter([16.0], [np.minimum(host_peak_compute, 16.0 * host_bw)], color='#3b82f6', s=120, zorder=5)
    ax.annotate("Dense GEMM (Host favored:\nHost compute is 14x faster)", xy=(16.0, host_peak_compute), xytext=(8.0, 600.0),
                arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=6), fontsize=9, fontweight='bold')

    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlabel("Operational Intensity (FLOPs / Byte)")
    ax.set_ylabel("Attainable Performance (GFLOPs)")
    ax.set_title("Architectural Roofline Model & Intelligent Placement Boundary")
    ax.grid(True, which='both', linestyle=':', alpha=0.5)
    ax.legend(framealpha=0.9, loc='lower right')

    out_path = os.path.join(RESULTS_DIR, "roofline_placement.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

def plot_dynamic_timeline(data):
    trace = data["mixed_trace"]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True)

    chunk_ids = [t["chunk_id"] for t in trace]
    decisions = [1 if t["decision"] == "PIM" else 0 for t in trace]
    latencies = [t["compute_time_ns"] + t["transfer_time_ns"] for t in trace]

    # Bar plot of decisions (0 = Host, 1 = PIM)
    colors = ['#ef4444' if d == 1 else '#3b82f6' for d in decisions]
    ax1.bar(chunk_ids, [1]*len(chunk_ids), color=colors, width=0.8, edgecolor='black', linewidth=0.5)
    ax1.set_yticks([0, 1])
    ax1.set_yticklabels(["Host CPU", "PIM Units"])
    ax1.set_ylabel("Selected Placement")
    ax1.set_title("Dynamic Computation Placement Across Heterogeneous Pipeline Phases")
    
    # Phase demarcations
    ax1.axvline(7.5, color='gray', linestyle='--')
    ax1.axvline(19.5, color='gray', linestyle='--')
    ax1.axvline(35.5, color='gray', linestyle='--')

    ax1.text(3.5, 0.5, "Phase 1: Random\n(Graph BFS)", ha='center', va='center', fontweight='bold', color='white', bbox=dict(boxstyle='round', facecolor='black', alpha=0.6))
    ax1.text(13.5, 0.5, "Phase 2: Streaming\n(SAXPY Filter)", ha='center', va='center', fontweight='bold', color='white', bbox=dict(boxstyle='round', facecolor='black', alpha=0.6))
    ax1.text(27.5, 0.5, "Phase 3: Reusable\n(Dense GEMM)", ha='center', va='center', fontweight='bold', color='white', bbox=dict(boxstyle='round', facecolor='black', alpha=0.6))
    ax1.text(39.5, 0.5, "Phase 4: Streaming\n(Aggregation)", ha='center', va='center', fontweight='bold', color='white', bbox=dict(boxstyle='round', facecolor='black', alpha=0.6))

    # Latency per chunk
    ax2.plot(chunk_ids, np.array(latencies) / 1000.0, marker='o', markersize=4, color='#10b981', linewidth=1.8)
    ax2.set_ylabel("Execution Latency (µs)")
    ax2.set_xlabel("Computational Chunk ID")
    ax2.grid(True, linestyle=':', alpha=0.5)

    out_path = os.path.join(RESULTS_DIR, "dynamic_timeline.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

def main():
    data = load_data()
    plot_speedup_comparison(data)
    plot_data_movement(data)
    plot_energy_breakdown(data)
    plot_interconnect_sensitivity(data)
    plot_roofline_and_placement()
    plot_dynamic_timeline(data)
    print("\n[OK] All 6 publication-quality figures generated successfully!")

if __name__ == "__main__":
    main()
