"""
Processing-In-Memory (PIM) / Near-Memory Core Model.
Simulates distributed near-bank SIMD units embedded in the logic die of 3D-stacked HBM/DRAM.
Executes computation locally with direct high-bandwidth TSV access without traversing the external interconnect.
"""

from typing import Dict, Any
from simulator.config import PIMConfig, MemorySubsystemConfig

class PIMComputeModel:
    def __init__(self, pim_config: PIMConfig, mem_config: MemorySubsystemConfig):
        self.pim_config = pim_config
        self.mem_config = mem_config
        self.total_flops = 0
        self.total_cycles = 0
        self.total_compute_time_ns = 0.0
        self.total_compute_energy_pj = 0.0
        self.total_sram_energy_pj = 0.0
        self.total_internal_mem_energy_pj = 0.0

    def reset(self):
        self.total_flops = 0
        self.total_cycles = 0
        self.total_compute_time_ns = 0.0
        self.total_compute_energy_pj = 0.0
        self.total_sram_energy_pj = 0.0
        self.total_internal_mem_energy_pj = 0.0

    @property
    def peak_gflops(self) -> float:
        """Peak theoretical compute throughput across all PIM units."""
        return self.pim_config.num_units * self.pim_config.clock_freq_ghz * self.pim_config.flops_per_cycle

    def execute_chunk(self, flops: int, data_bytes: int, access_pattern: str = "sequential") -> Dict[str, Any]:
        """
        Execute computation chunk on the near-memory PIM units.
        Reads/writes directly to local DRAM bank via internal TSVs (1024 GB/s).
        Zero external interconnect traffic.
        """
        if flops <= 0:
            return {"compute_time_ns": 0.0, "total_energy_pj": 0.0, "cycles": 0}

        cycle_ns = 1.0 / self.pim_config.clock_freq_ghz
        
        # 1. Pipeline compute latency
        compute_cycles = flops / (self.pim_config.num_units * self.pim_config.flops_per_cycle)
        compute_pipeline_ns = compute_cycles * cycle_ns

        # 2. Local memory access via TSVs (Internal memory access)
        # Internal TSV aggregate bandwidth: e.g. 1024 GB/s = 1024 bytes/ns
        tsv_transfer_ns = data_bytes / self.mem_config.internal_bandwidth_gb_s
        
        # Bank access latency depending on pattern
        if access_pattern == "sequential":
            bank_latency_ns = 12.0
        elif access_pattern == "strided":
            bank_latency_ns = 18.0
        else: # "random"
            bank_latency_ns = 25.0

        # PIM units overlap memory fetch with execution via double-buffering in local SRAM
        # Effective time is max(compute, memory) + initial bank latency
        total_pim_time_ns = bank_latency_ns + max(compute_pipeline_ns, tsv_transfer_ns)
        total_pim_cycles = int(total_pim_time_ns / cycle_ns)

        # 3. Energy consumption
        # PIM ALU compute energy
        compute_energy_pj = flops * self.pim_config.energy_compute_flop_pj
        
        # Local SRAM scratchpad access energy (each operand accessed via SRAM)
        sram_access_count = (data_bytes + 31) // 32
        sram_energy_pj = sram_access_count * self.pim_config.energy_sram_access_pj
        
        # Internal DRAM-to-logic-die TSV transfer energy
        internal_mem_energy_pj = data_bytes * self.mem_config.energy_dram_read_per_byte_pj
        
        total_energy_pj = compute_energy_pj + sram_energy_pj + internal_mem_energy_pj

        # Accumulate stats
        self.total_flops += flops
        self.total_cycles += total_pim_cycles
        self.total_compute_time_ns += total_pim_time_ns
        self.total_compute_energy_pj += compute_energy_pj
        self.total_sram_energy_pj += sram_energy_pj
        self.total_internal_mem_energy_pj += internal_mem_energy_pj

        return {
            "compute_time_ns": total_pim_time_ns,
            "pipeline_time_ns": compute_pipeline_ns,
            "tsv_transfer_time_ns": tsv_transfer_ns,
            "compute_energy_pj": compute_energy_pj,
            "sram_energy_pj": sram_energy_pj,
            "internal_mem_energy_pj": internal_mem_energy_pj,
            "total_energy_pj": total_energy_pj,
            "total_energy_uj": total_energy_pj / 1e6
        }

    def get_stats(self) -> Dict[str, Any]:
        total_energy = self.total_compute_energy_pj + self.total_sram_energy_pj + self.total_internal_mem_energy_pj
        return {
            "total_flops": self.total_flops,
            "total_cycles": self.total_cycles,
            "total_compute_time_ns": self.total_compute_time_ns,
            "total_compute_energy_pj": self.total_compute_energy_pj,
            "total_sram_energy_pj": self.total_sram_energy_pj,
            "total_internal_mem_energy_pj": self.total_internal_mem_energy_pj,
            "total_energy_pj": total_energy,
            "total_energy_uj": total_energy / 1e6,
            "total_energy_joules": total_energy / 1e12
        }
