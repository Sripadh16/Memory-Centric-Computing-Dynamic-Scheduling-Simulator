"""
Main Memory-Centric Simulation Engine.
Coordinates Host, PIM, Interconnect, Memory Subsystem, and Runtime Decision Engine.
Executes traces, manages dynamic data movement, and calculates comprehensive metrics.
"""

from typing import List, Dict, Any, Optional
from simulator.config import SystemConfig
from simulator.interconnect import InterconnectModel
from simulator.memory import MemorySubsystemModel
from simulator.host_core import HostComputeModel
from simulator.pim_core import PIMComputeModel
from simulator.decision_engine import IntelligentDecisionEngine, PlacementDecision, PlacementPolicy
from simulator.workloads import ComputeChunk
from simulator.metrics import SimulationMetrics

class SimulationEngine:
    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config or SystemConfig()
        self.interconnect = InterconnectModel(self.config.interconnect)
        self.memory = MemorySubsystemModel(self.config.memory)
        self.host = HostComputeModel(self.config.host)
        self.pim = PIMComputeModel(self.config.pim, self.config.memory)
        self.decision_engine = IntelligentDecisionEngine(
            self.config.decision_engine,
            self.config.host,
            self.config.pim,
            self.config.interconnect,
            self.config.memory
        )
        self.trace_log: List[Dict[str, Any]] = []

    def reset(self):
        self.interconnect.reset()
        self.memory.reset()
        self.host.reset()
        self.pim.reset()
        self.decision_engine.reset()
        self.trace_log.clear()

    def run_workload(
        self,
        chunks: List[ComputeChunk],
        policy: PlacementPolicy = PlacementPolicy.DYNAMIC_INTELLIGENT,
        workload_name: str = "Custom_Workload"
    ) -> SimulationMetrics:
        """
        Execute a sequence of computational chunks under a given placement policy.
        Simulates explicit interactions between compute resources, interconnect, and memory.
        """
        self.reset()
        
        host_chunks = 0
        pim_chunks = 0
        current_data_locations: Dict[int, str] = {} # chunk_id -> 'memory' or 'host_cache'

        # Initialize residency
        for c in chunks:
            current_data_locations[c.chunk_id] = c.data_residence

        for chunk in chunks:
            residence = current_data_locations.get(chunk.chunk_id, "memory")

            # 1. Dynamic Decision Making (with explicit latency and energy overhead)
            decision, decision_info = self.decision_engine.decide(
                policy=policy,
                flops=chunk.flops,
                data_bytes=chunk.data_bytes,
                reuse_factor=chunk.reuse_factor,
                access_pattern=chunk.access_pattern,
                data_residence=residence
            )

            chunk_trace: Dict[str, Any] = {
                "chunk_id": chunk.chunk_id,
                "phase_name": chunk.phase_name,
                "kernel_name": chunk.kernel_name,
                "flops": chunk.flops,
                "data_bytes": chunk.data_bytes,
                "access_pattern": chunk.access_pattern,
                "reuse_factor": chunk.reuse_factor,
                "decision": decision.value,
                "reason": decision_info["reason"],
                "decision_time_ns": decision_info["decision_time_ns"],
                "decision_energy_pj": decision_info["decision_energy_pj"]
            }

            # 2. Execution path based on placement
            if decision == PlacementDecision.HOST:
                host_chunks += 1
                transfer_time_ns = 0.0
                transfer_energy_pj = 0.0
                mem_time_ns = 0.0
                mem_energy_pj = 0.0

                # If data was resident in memory, must transfer to host across interconnect
                if residence == "memory":
                    # Step A: DRAM access to read data
                    mem_res = self.memory.access(chunk.data_bytes, is_write=False, access_pattern=chunk.access_pattern)
                    mem_time_ns = mem_res["latency_ns"]
                    mem_energy_pj = mem_res["energy_pj"]

                    # Step B: Transfer across CXL interconnect to host
                    xfer_res = self.interconnect.transfer(chunk.data_bytes, direction="mem_to_host")
                    transfer_time_ns = xfer_res["latency_ns"]
                    transfer_energy_pj = xfer_res["energy_pj"]

                    # Mark resident in host cache for potential reuse
                    if chunk.reuse_factor > 1.5:
                        current_data_locations[chunk.chunk_id] = "host_cache"

                # Step C: Execute compute on host CPU cores with cache hierarchy
                host_res = self.host.execute_chunk(
                    flops=chunk.flops,
                    data_bytes=chunk.data_bytes,
                    reuse_factor=chunk.reuse_factor,
                    access_pattern=chunk.access_pattern
                )

                chunk_trace.update({
                    "compute_time_ns": host_res["compute_time_ns"],
                    "transfer_time_ns": transfer_time_ns,
                    "memory_time_ns": mem_time_ns,
                    "compute_energy_pj": host_res["compute_energy_pj"],
                    "cache_energy_pj": host_res["cache_energy_pj"],
                    "interconnect_energy_pj": transfer_energy_pj,
                    "memory_energy_pj": mem_energy_pj,
                    "bytes_transferred": chunk.data_bytes if residence == "memory" else 0
                })

            else: # PlacementDecision.PIM
                pim_chunks += 1
                transfer_time_ns = 0.0
                transfer_energy_pj = 0.0

                # Data is accessed directly inside memory via high-bandwidth TSVs
                # If data had previously been modified in host cache, writeback flits would occur
                if residence == "host_cache":
                    # Flush back to memory before PIM execution
                    flush_res = self.interconnect.transfer(chunk.data_bytes, direction="host_to_mem")
                    transfer_time_ns += flush_res["latency_ns"]
                    transfer_energy_pj += flush_res["energy_pj"]
                    current_data_locations[chunk.chunk_id] = "memory"

                # PIM executes locally in logic die
                pim_res = self.pim.execute_chunk(
                    flops=chunk.flops,
                    data_bytes=chunk.data_bytes,
                    access_pattern=chunk.access_pattern
                )

                # Return small scalar result / status token to host
                sync_res = self.interconnect.transfer(chunk.output_bytes, direction="mem_to_host")
                transfer_time_ns += sync_res["latency_ns"]
                transfer_energy_pj += sync_res["energy_pj"]

                chunk_trace.update({
                    "compute_time_ns": pim_res["compute_time_ns"],
                    "transfer_time_ns": transfer_time_ns,
                    "memory_time_ns": 0.0, # Included in PIM execution model
                    "compute_energy_pj": pim_res["compute_energy_pj"],
                    "cache_energy_pj": pim_res["sram_energy_pj"],
                    "interconnect_energy_pj": transfer_energy_pj,
                    "memory_energy_pj": pim_res["internal_mem_energy_pj"],
                    "bytes_transferred": chunk.output_bytes + (chunk.data_bytes if residence == "host_cache" else 0)
                })

            self.trace_log.append(chunk_trace)

        # 3. Aggregate system-wide metrics
        return self._compile_metrics(workload_name, policy.value, len(chunks), host_chunks, pim_chunks)

    def _compile_metrics(
        self,
        workload_name: str,
        policy_name: str,
        total_chunks: int,
        host_chunks: int,
        pim_chunks: int
    ) -> SimulationMetrics:
        # Time components
        total_compute_time_ns = self.host.total_compute_time_ns + self.pim.total_compute_time_ns
        total_xfer_time_ns = self.interconnect.total_transfer_time_ns
        total_dec_time_ns = self.decision_engine.total_decision_time_ns
        total_mem_time_ns = self.memory.total_access_time_ns

        # Total elapsed time includes compute, data transfers, memory accesses, and decision overhead
        total_time_ns = total_compute_time_ns + total_xfer_time_ns + total_dec_time_ns + total_mem_time_ns

        # Energy components (uJ)
        compute_energy_uj = (self.host.total_compute_energy_pj + self.pim.total_compute_energy_pj) / 1e6
        cache_energy_uj = (self.host.total_cache_energy_pj + self.pim.total_sram_energy_pj) / 1e6
        interconnect_energy_uj = self.interconnect.total_energy_pj / 1e6
        memory_energy_uj = (self.memory.total_energy_pj + self.pim.total_internal_mem_energy_pj) / 1e6
        decision_energy_uj = self.decision_engine.total_decision_energy_pj / 1e6

        total_energy_uj = compute_energy_uj + cache_energy_uj + interconnect_energy_uj + memory_energy_uj + decision_energy_uj
        total_energy_joules = total_energy_uj / 1e6

        # Data movement
        total_bytes = self.interconnect.total_bytes_host_to_mem + self.interconnect.total_bytes_mem_to_host
        total_mb = total_bytes / (1024 * 1024)

        # Energy-Delay Product: Joules * seconds
        edp = total_energy_joules * (total_time_ns / 1e9)

        # Decision overhead proportions
        dec_time_pct = (total_dec_time_ns / max(1e-5, total_time_ns)) * 100.0
        dec_energy_pct = (decision_energy_uj / max(1e-5, total_energy_uj)) * 100.0

        return SimulationMetrics(
            policy=policy_name,
            workload_name=workload_name,
            total_chunks=total_chunks,
            host_chunks_executed=host_chunks,
            pim_chunks_executed=pim_chunks,
            total_execution_time_ns=total_time_ns,
            total_compute_time_ns=total_compute_time_ns,
            total_interconnect_time_ns=total_xfer_time_ns,
            total_decision_time_ns=total_dec_time_ns,
            compute_energy_uj=compute_energy_uj,
            cache_energy_uj=cache_energy_uj,
            interconnect_energy_uj=interconnect_energy_uj,
            memory_energy_uj=memory_energy_uj,
            decision_energy_uj=decision_energy_uj,
            total_energy_uj=total_energy_uj,
            total_energy_joules=total_energy_joules,
            total_data_movement_bytes=total_bytes,
            total_data_movement_mb=total_mb,
            edp=edp,
            decision_overhead_time_pct=dec_time_pct,
            decision_overhead_energy_pct=dec_energy_pct
        )
