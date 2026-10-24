"""
Intelligent Computation Placement / Runtime Decision Engine.
Dynamically decides whether computation should be executed on Host CPU or PIM Units
based on data location, operational intensity, movement cost, cache reuse, and access pattern.
Explicitly accounts for decision latency and energy overhead.
"""

from typing import Dict, Any, Tuple
from enum import Enum
from simulator.config import DecisionEngineConfig, HostConfig, PIMConfig, InterconnectConfig, MemorySubsystemConfig

class PlacementDecision(Enum):
    HOST = "HOST"
    PIM = "PIM"

class PlacementPolicy(Enum):
    DYNAMIC_INTELLIGENT = "DYNAMIC_INTELLIGENT" # Cost-model & telemetry driven (Ours)
    ALWAYS_HOST = "ALWAYS_HOST"                 # Baseline: Traditional von Neumann
    ALWAYS_PIM = "ALWAYS_PIM"                   # Baseline: Static near-memory offload
    ORACLE = "ORACLE"                           # Theoretical optimum per-phase

class IntelligentDecisionEngine:
    def __init__(
        self,
        config: DecisionEngineConfig,
        host_config: HostConfig,
        pim_config: PIMConfig,
        interconnect_config: InterconnectConfig,
        memory_config: MemorySubsystemConfig
    ):
        self.config = config
        self.host_config = host_config
        self.pim_config = pim_config
        self.interconnect_config = interconnect_config
        self.memory_config = memory_config

        # Decision statistics and overhead counters
        self.total_decisions = 0
        self.host_placements = 0
        self.pim_placements = 0
        self.total_decision_cycles = 0
        self.total_decision_time_ns = 0.0
        self.total_decision_energy_pj = 0.0
        self.decision_history = []

    def reset(self):
        self.total_decisions = 0
        self.host_placements = 0
        self.pim_placements = 0
        self.total_decision_cycles = 0
        self.total_decision_time_ns = 0.0
        self.total_decision_energy_pj = 0.0
        self.decision_history = []
        self._last_phase_key = None

    def evaluate_cost_model(
        self,
        flops: int,
        data_bytes: int,
        reuse_factor: float,
        access_pattern: str,
        data_residence: str = "memory"
    ) -> Dict[str, Any]:
        """
        Analytical runtime cost model to estimate Host vs PIM execution time and energy.
        """
        operational_intensity = flops / max(1, data_bytes) # FLOPs/byte

        # 1. Estimate Host Execution Time and Energy
        # Data transfer cost if data is currently in memory
        if data_residence == "memory":
            num_flits = (data_bytes + self.interconnect_config.flit_size_bytes - 1) // self.interconnect_config.flit_size_bytes
            wire_bytes = num_flits * (self.interconnect_config.flit_size_bytes + self.interconnect_config.packet_header_overhead_bytes)
            t_xfer_ns = self.interconnect_config.base_latency_ns + (wire_bytes / self.interconnect_config.bandwidth_gb_s)
            e_xfer_pj = wire_bytes * 8.0 * self.interconnect_config.energy_per_bit_pj
        else:
            t_xfer_ns = 0.0
            e_xfer_pj = 0.0

        # Host compute capability
        host_peak_gflops = self.host_config.num_cores * self.host_config.clock_freq_ghz * self.host_config.flops_per_cycle
        t_host_compute_ns = (flops / host_peak_gflops)

        # Host cache behavior estimate
        if access_pattern == "random":
            cache_miss_penalty_ns = (data_bytes / 64.0) * 0.90 * 45.0 / self.host_config.num_cores
        elif access_pattern == "streaming":
            cache_miss_penalty_ns = (data_bytes / 64.0) * 0.85 * 30.0 / self.host_config.num_cores
        else: # reusable
            cache_miss_penalty_ns = (data_bytes / 64.0) * 0.10 * 15.0 / self.host_config.num_cores

        t_host_total_ns = t_xfer_ns + t_host_compute_ns + cache_miss_penalty_ns
        e_host_total_pj = e_xfer_pj + (flops * self.host_config.energy_compute_flop_pj) + (data_bytes * 1.5)

        # 2. Estimate PIM Execution Time and Energy
        pim_peak_gflops = self.pim_config.num_units * self.pim_config.clock_freq_ghz * self.pim_config.flops_per_cycle
        t_pim_compute_ns = (flops / pim_peak_gflops)
        t_pim_tsv_ns = data_bytes / self.memory_config.internal_bandwidth_gb_s
        
        bank_latency_ns = 12.0 if access_pattern == "sequential" else (25.0 if access_pattern == "random" else 18.0)
        t_pim_total_ns = bank_latency_ns + max(t_pim_compute_ns, t_pim_tsv_ns)

        # Small scalar result sync back to host (e.g. 64B status/result flit)
        t_pim_sync_ns = self.interconnect_config.base_latency_ns + (64.0 / self.interconnect_config.bandwidth_gb_s)
        t_pim_total_ns += t_pim_sync_ns

        e_pim_total_pj = (
            (flops * self.pim_config.energy_compute_flop_pj) +
            (data_bytes * self.memory_config.energy_dram_read_per_byte_pj) +
            (data_bytes * 0.2) +
            (64 * 8.0 * self.interconnect_config.energy_per_bit_pj) # sync flit
        )

        # EDP (Energy-Delay Product in pJ * ns)
        edp_host = t_host_total_ns * e_host_total_pj
        edp_pim = t_pim_total_ns * e_pim_total_pj

        return {
            "operational_intensity": operational_intensity,
            "t_host_ns": t_host_total_ns,
            "e_host_pj": e_host_total_pj,
            "edp_host": edp_host,
            "t_pim_ns": t_pim_total_ns,
            "e_pim_pj": e_pim_total_pj,
            "edp_pim": edp_pim,
            "speedup_pim_over_host": t_host_total_ns / max(1e-5, t_pim_total_ns),
            "energy_ratio_pim_to_host": e_pim_total_pj / max(1e-5, e_host_total_pj)
        }

    def decide(
        self,
        policy: PlacementPolicy,
        flops: int,
        data_bytes: int,
        reuse_factor: float,
        access_pattern: str,
        data_residence: str = "memory",
        optimization_metric: str = "edp" # 'edp', 'time', or 'energy'
    ) -> Tuple[PlacementDecision, Dict[str, Any]]:
        """
        Dynamically decide computation placement according to the specified policy.
        Accounts for decision latency and energy overhead.
        """
        self.total_decisions += 1
        
        # Hardware Placement Table (Phase Predictor):
        # Full cost-model evaluation (250 cycles) occurs on phase changes or cache misses.
        # Contiguous chunks in the same execution phase hit the placement buffer in 1 cycle.
        cache_key = (access_pattern, data_residence, int(flops / max(1, data_bytes) * 10))
        is_phase_change = (not hasattr(self, "_last_phase_key")) or (self._last_phase_key != cache_key)
        
        cycles = self.config.decision_latency_cycles if is_phase_change else 1
        decision_energy_pj = self.config.decision_energy_pj if is_phase_change else 5.0
        decision_time_ns = cycles / self.host_config.clock_freq_ghz

        self._last_phase_key = cache_key
        self.total_decision_cycles += cycles
        self.total_decision_time_ns += decision_time_ns
        self.total_decision_energy_pj += decision_energy_pj

        cost_eval = self.evaluate_cost_model(flops, data_bytes, reuse_factor, access_pattern, data_residence)

        reason = ""
        decision = PlacementDecision.HOST

        if policy == PlacementPolicy.ALWAYS_HOST:
            decision = PlacementDecision.HOST
            reason = "Static baseline: forced to Host CPU"

        elif policy == PlacementPolicy.ALWAYS_PIM:
            decision = PlacementDecision.PIM
            reason = "Static baseline: forced to PIM units"

        elif policy == PlacementPolicy.ORACLE:
            # Ideal theoretical placement comparing true costs
            if optimization_metric == "time":
                decision = PlacementDecision.PIM if cost_eval["t_pim_ns"] < cost_eval["t_host_ns"] else PlacementDecision.HOST
            elif optimization_metric == "energy":
                decision = PlacementDecision.PIM if cost_eval["e_pim_pj"] < cost_eval["e_host_pj"] else PlacementDecision.HOST
            else: # edp
                decision = PlacementDecision.PIM if cost_eval["edp_pim"] < cost_eval["edp_host"] else PlacementDecision.HOST
            reason = f"Oracle optimal placement based on minimum {optimization_metric.upper()}"

        elif policy == PlacementPolicy.DYNAMIC_INTELLIGENT:
            # Dynamic heuristic placement with hysteresis
            op_intensity = cost_eval["operational_intensity"]

            # Key architectural intuition:
            # 1. Random access / Pointer-chasing: High host cache miss penalty + high interconnect amplification -> Offload to PIM
            # 2. Streaming (low intensity < 2.0 FLOPs/byte): Memory bandwidth bound, bus bottleneck -> Offload to PIM
            # 3. High Reuse (intensity > 8.0 FLOPs/byte & reuse > 4.0): Host cache effectively captures working set, Host ALUs are 14x faster -> Keep on Host
            # 4. Intermediate: Use cost-model evaluation with hysteresis threshold
            if access_pattern == "random":
                decision = PlacementDecision.PIM
                reason = "Pattern is Random Access: Host cache hit rate is minimal; avoiding CXL bus amplification"
            elif access_pattern == "streaming" and op_intensity < 4.0:
                decision = PlacementDecision.PIM
                reason = f"Streaming with low operational intensity ({op_intensity:.2f} FLOPs/B): Memory-bound; exploiting 1 TB/s internal TSVs"
            elif reuse_factor >= 8.0 and op_intensity >= 8.0:
                decision = PlacementDecision.HOST
                reason = f"High reuse ({reuse_factor:.1f}x) & high intensity ({op_intensity:.1f} FLOPs/B): Host cache hierarchy & 1.84 TFLOPs ALUs superior"
            else:
                # Dynamic cost model comparison with hysteresis
                if optimization_metric == "time":
                    if cost_eval["t_host_ns"] > (cost_eval["t_pim_ns"] * self.config.hysteresis_threshold):
                        decision = PlacementDecision.PIM
                        reason = f"Dynamic Cost Model: PIM is {cost_eval['speedup_pim_over_host']:.2f}x faster"
                    else:
                        decision = PlacementDecision.HOST
                        reason = f"Dynamic Cost Model: Host is faster or within hysteresis margin"
                else: # EDP
                    if cost_eval["edp_host"] > (cost_eval["edp_pim"] * self.config.hysteresis_threshold):
                        decision = PlacementDecision.PIM
                        reason = f"Dynamic Cost Model: PIM reduces EDP by {(1.0 - cost_eval['edp_pim']/cost_eval['edp_host'])*100:.1f}%"
                    else:
                        decision = PlacementDecision.HOST
                        reason = "Dynamic Cost Model: Host achieves better or equivalent EDP"

        if decision == PlacementDecision.HOST:
            self.host_placements += 1
        else:
            self.pim_placements += 1

        decision_info = {
            "decision": decision.value,
            "policy": policy.value,
            "reason": reason,
            "cost_eval": cost_eval,
            "decision_time_ns": decision_time_ns,
            "decision_energy_pj": decision_energy_pj
        }
        self.decision_history.append(decision_info)

        return decision, decision_info

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_decisions": self.total_decisions,
            "host_placements": self.host_placements,
            "pim_placements": self.pim_placements,
            "pim_placement_ratio": self.pim_placements / max(1, self.total_decisions),
            "total_decision_cycles": self.total_decision_cycles,
            "total_decision_time_ns": self.total_decision_time_ns,
            "total_decision_energy_pj": self.total_decision_energy_pj,
            "total_decision_energy_uj": self.total_decision_energy_pj / 1e6
        }
