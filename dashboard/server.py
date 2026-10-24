"""
FastAPI Backend and Simulation REST API Server for MemCentric-Sim.
Built with FastAPI, Pydantic, and Uvicorn.
Provides endpoints for interactive simulation execution, telemetry, and artifact serving.
"""

import os
import sys
import json
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Ensure project root is accessible
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from simulator.config import SystemConfig
from simulator.engine import SimulationEngine
from simulator.decision_engine import PlacementPolicy
from simulator.workloads import WorkloadGenerator

DASHBOARD_DIR = os.path.dirname(__file__)
RESULTS_DIR = os.path.join(ROOT_DIR, "experiments", "results")

app = FastAPI(
    title="MemCentric-Sim API",
    description="Microarchitectural Memory-Centric Computing Simulator with Intelligent Computation Placement",
    version="2.0.0"
)

# Enable CORS for external frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SimulationRequest(BaseModel):
    workload: str = Field(default="mixed", description="Target workload: 'reusable', 'streaming', 'random', or 'mixed'")
    policy: str = Field(default="DYNAMIC_INTELLIGENT", description="Placement policy: DYNAMIC_INTELLIGENT, ALWAYS_HOST, ALWAYS_PIM, ORACLE")
    interconnect_bw: float = Field(default=64.0, ge=8.0, le=512.0, description="Interconnect link bandwidth in GB/s")
    matrix_dim: Optional[int] = Field(default=384, ge=64, le=1024)
    vector_elements: Optional[int] = Field(default=2 * 1024 * 1024)
    graph_nodes: Optional[int] = Field(default=150_000)

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "simulator": "MemCentric-Sim",
        "engine": "FastAPI + Uvicorn",
        "cache": "3-Level Set-Associative LRU",
        "memory": "Multi-Bank DRAM (tCAS, tRCD, tRP)"
    }

@app.get("/api/results")
async def get_results():
    """Returns stored precomputed experiment results."""
    json_path = os.path.join(RESULTS_DIR, "simulation_results.json")
    if not os.path.exists(json_path):
        raise HTTPException(status_code=404, detail="Experiment results not found. Run run_experiments.py first.")
    with open(json_path, "r") as f:
        data = json.load(f)
    return JSONResponse(content=data)

@app.get("/results/{filename}")
async def get_result_file(filename: str):
    """Serves generated plots and artifacts."""
    file_path = os.path.join(RESULTS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File {filename} not found")
    media_type = "image/png" if filename.endswith(".png") else "application/json"
    return FileResponse(file_path, media_type=media_type)

@app.post("/api/simulate")
async def simulate(req: SimulationRequest):
    """
    Executes a dynamic microarchitectural simulation run with explicit hardware interactions.
    """
    cfg = SystemConfig()
    cfg.interconnect.bandwidth_gb_s = req.interconnect_bw

    # Workload generation
    if req.workload == "reusable":
        dim = req.matrix_dim or 384
        chunks = WorkloadGenerator.create_dense_gemm(matrix_dim=dim, tile_size=64)
        w_name = "Dense_GEMM"
    elif req.workload == "streaming":
        elements = req.vector_elements or (2 * 1024 * 1024)
        chunks = WorkloadGenerator.create_streaming_pipeline(vector_size_elements=elements)
        w_name = "Streaming_SAXPY"
    elif req.workload == "random":
        nodes = req.graph_nodes or 150_000
        chunks = WorkloadGenerator.create_graph_bfs_spmv(num_nodes=nodes)
        w_name = "Graph_BFS"
    else: # mixed
        chunks = WorkloadGenerator.create_heterogeneous_mixed_pipeline()
        w_name = "Mixed_Pipeline"

    policy_enum = getattr(PlacementPolicy, req.policy, PlacementPolicy.DYNAMIC_INTELLIGENT)

    # 1. Run Baseline (Always Host) for relative comparative metrics
    baseline_engine = SimulationEngine(cfg)
    baseline_metrics = baseline_engine.run_workload(chunks, policy=PlacementPolicy.ALWAYS_HOST, workload_name=w_name)

    # 2. Run target policy
    engine = SimulationEngine(cfg)
    metrics = engine.run_workload(chunks, policy=policy_enum, workload_name=w_name)
    metrics_dict = metrics.to_dict()

    # Calculate comparative metrics
    base_time = baseline_metrics.total_execution_time_ns
    base_energy = baseline_metrics.total_energy_uj
    base_edp = baseline_metrics.edp

    speedup = base_time / max(1e-5, metrics.total_execution_time_ns)
    energy_reduc = ((base_energy - metrics.total_energy_uj) / max(1e-5, base_energy)) * 100.0
    energy_savings_mult = base_energy / max(1e-5, metrics.total_energy_uj)
    edp_reduc = ((base_edp - metrics.edp) / max(1e-5, base_edp)) * 100.0

    metrics_dict["speedup"] = speedup
    metrics_dict["energy_reduction_pct"] = energy_reduc
    metrics_dict["energy_savings_multiplier"] = energy_savings_mult
    metrics_dict["edp_reduction_pct"] = edp_reduc

    return {
        "status": "success",
        "metrics": metrics_dict,
        "baseline_metrics": baseline_metrics.to_dict(),
        "trace": engine.trace_log[:100]
    }

# Mount static frontend directory
app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="static")

def run_server(host="0.0.0.0", port=8080):
    print(f"[*] Starting MemCentric-Sim FastAPI server on http://localhost:{port}/")
    uvicorn.run("dashboard.server:app", host=host, port=port, log_level="info")

if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    run_server(port=port)
