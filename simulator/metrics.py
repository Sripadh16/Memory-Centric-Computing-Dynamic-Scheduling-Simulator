"""
Performance, Energy, and Data-Movement Metrics Collection.
Calculates execution time, total energy breakdown, interconnect traffic,
speedup, Energy-Delay Product (EDP), and decision engine overhead.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List

@dataclass
class SimulationMetrics:
    policy: str
    workload_name: str
    total_chunks: int
    host_chunks_executed: int
    pim_chunks_executed: int
    
    # Timing
    total_execution_time_ns: float
    total_compute_time_ns: float
    total_interconnect_time_ns: float
    total_decision_time_ns: float
    
    # Energy (uJ = microjoules, J = Joules)
    compute_energy_uj: float
    cache_energy_uj: float
    interconnect_energy_uj: float
    memory_energy_uj: float
    decision_energy_uj: float
    total_energy_uj: float
    total_energy_joules: float
    
    # Data Movement
    total_data_movement_bytes: int
    total_data_movement_mb: float
    
    # High-level Metrics
    speedup_vs_baseline: float = 1.0
    energy_reduction_pct: float = 0.0
    edp: float = 0.0 # Energy-Delay Product (Joules * seconds)
    edp_reduction_pct: float = 0.0
    decision_overhead_time_pct: float = 0.0
    decision_overhead_energy_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy": self.policy,
            "workload_name": self.workload_name,
            "total_chunks": self.total_chunks,
            "host_chunks_executed": self.host_chunks_executed,
            "pim_chunks_executed": self.pim_chunks_executed,
            "pim_ratio": self.pim_chunks_executed / max(1, self.total_chunks),
            "execution_time_ms": self.total_execution_time_ns / 1e6,
            "total_execution_time_ns": self.total_execution_time_ns,
            "compute_time_ms": self.total_compute_time_ns / 1e6,
            "interconnect_time_ms": self.total_interconnect_time_ns / 1e6,
            "decision_time_ms": self.total_decision_time_ns / 1e6,
            "compute_energy_uj": self.compute_energy_uj,
            "cache_energy_uj": self.cache_energy_uj,
            "interconnect_energy_uj": self.interconnect_energy_uj,
            "memory_energy_uj": self.memory_energy_uj,
            "decision_energy_uj": self.decision_energy_uj,
            "total_energy_uj": self.total_energy_uj,
            "total_energy_joules": self.total_energy_joules,
            "total_data_movement_mb": self.total_data_movement_mb,
            "total_data_movement_bytes": self.total_data_movement_bytes,
            "speedup": self.speedup_vs_baseline,
            "energy_reduction_pct": self.energy_reduction_pct,
            "edp": self.edp,
            "edp_reduction_pct": self.edp_reduction_pct,
            "decision_overhead_time_pct": self.decision_overhead_time_pct,
            "decision_overhead_energy_pct": self.decision_overhead_energy_pct
        }
