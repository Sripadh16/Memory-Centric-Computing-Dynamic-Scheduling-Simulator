"""
Experiment Suite Runner.
Executes systematic comparisons across workloads, policies, and architectural parameters.
Saves structured JSON results for reporting and visualization.
"""

import os
import sys
import json

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import Dict, Any, List
from simulator.config import SystemConfig
from simulator.engine import SimulationEngine
from simulator.decision_engine import PlacementPolicy
from simulator.workloads import WorkloadGenerator

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

def run_policy_comparison() -> Dict[str, Any]:
    print("[1/3] Running Policy Comparison across 4 Workloads...")
    
    workloads = {
        "Reusable_Dense_GEMM": WorkloadGenerator.create_dense_gemm(matrix_dim=512, tile_size=64),
        "Streaming_SAXPY_Filter": WorkloadGenerator.create_streaming_pipeline(vector_size_elements=4*1024*1024, chunk_elements=128*1024),
        "Random_Graph_BFS": WorkloadGenerator.create_graph_bfs_spmv(num_nodes=250_000, edges_per_node=16, chunk_nodes=25_000),
        "Mixed_Heterogeneous_Pipeline": WorkloadGenerator.create_heterogeneous_mixed_pipeline()
    }

    policies = [
        PlacementPolicy.ALWAYS_HOST,
        PlacementPolicy.ALWAYS_PIM,
        PlacementPolicy.DYNAMIC_INTELLIGENT,
        PlacementPolicy.ORACLE
    ]

    all_results = {}

    for w_name, chunks in workloads.items():
        all_results[w_name] = {}
        baseline_time = 0.0
        baseline_energy = 0.0
        baseline_edp = 0.0

        for pol in policies:
            engine = SimulationEngine()
            metrics = engine.run_workload(chunks, policy=pol, workload_name=w_name)
            res_dict = metrics.to_dict()

            if pol == PlacementPolicy.ALWAYS_HOST:
                baseline_time = metrics.total_execution_time_ns
                baseline_energy = metrics.total_energy_uj
                baseline_edp = metrics.edp
                res_dict["speedup"] = 1.0
                res_dict["energy_reduction_pct"] = 0.0
                res_dict["edp_reduction_pct"] = 0.0
            else:
                speedup = baseline_time / max(1e-5, metrics.total_execution_time_ns)
                energy_reduc = ((baseline_energy - metrics.total_energy_uj) / max(1e-5, baseline_energy)) * 100.0
                edp_reduc = ((baseline_edp - metrics.edp) / max(1e-5, baseline_edp)) * 100.0
                res_dict["speedup"] = speedup
                res_dict["energy_reduction_pct"] = energy_reduc
                res_dict["edp_reduction_pct"] = edp_reduc

            all_results[w_name][pol.value] = res_dict
            print(f"  [{w_name}] {pol.value:<20}: Time={res_dict['execution_time_ms']:.2f} ms | Speedup={res_dict['speedup']:.2f}x | Energy={res_dict['total_energy_joules']*1000:.2f} mJ | Data={res_dict['total_data_movement_mb']:.1f} MB")

    return all_results

def run_interconnect_sensitivity() -> Dict[str, Any]:
    print("\n[2/3] Running Interconnect Bandwidth Sensitivity Sweep (16 to 256 GB/s)...")
    bw_list = [16.0, 32.0, 64.0, 128.0, 256.0]
    sensitivity_results = {}

    for bw in bw_list:
        cfg = SystemConfig()
        cfg.interconnect.bandwidth_gb_s = bw
        sensitivity_results[str(int(bw))] = {}

        # Test on Streaming and Reusable
        stream_chunks = WorkloadGenerator.create_streaming_pipeline(vector_size_elements=2*1024*1024, chunk_elements=128*1024)
        for pol in [PlacementPolicy.ALWAYS_HOST, PlacementPolicy.DYNAMIC_INTELLIGENT]:
            engine = SimulationEngine(cfg)
            metrics = engine.run_workload(stream_chunks, policy=pol, workload_name="Streaming_BW_Sweep")
            sensitivity_results[str(int(bw))][f"Streaming_{pol.value}"] = metrics.to_dict()

    return sensitivity_results

def run_trace_inspection() -> List[Dict[str, Any]]:
    print("\n[3/3] Generating Detailed Execution Trace for Mixed Pipeline...")
    engine = SimulationEngine()
    mixed_chunks = WorkloadGenerator.create_heterogeneous_mixed_pipeline()
    engine.run_workload(mixed_chunks, policy=PlacementPolicy.DYNAMIC_INTELLIGENT, workload_name="Mixed_Trace")
    return engine.trace_log

def main():
    policy_results = run_policy_comparison()
    sensitivity_results = run_interconnect_sensitivity()
    trace_results = run_trace_inspection()

    full_output = {
        "policy_comparison": policy_results,
        "interconnect_sensitivity": sensitivity_results,
        "mixed_trace": trace_results
    }

    output_path = os.path.join(RESULTS_DIR, "simulation_results.json")
    with open(output_path, "w") as f:
        json.dump(full_output, f, indent=2)

    print(f"\n[OK] Experiments successfully completed! Results saved to: {output_path}")

if __name__ == "__main__":
    main()
