"""
Host CPU Compute and Microarchitectural Cache Hierarchy Model.
Integrates Out-of-Order cores with explicit 3-Level Set-Associative Caches (L1-L3, LRU).
"""

from typing import Dict, Any, List
from simulator.config import HostConfig
from simulator.cache import ThreeLevelCacheHierarchy

class HostComputeModel:
    def __init__(self, config: HostConfig):
        self.config = config
        self.cache_hierarchy = ThreeLevelCacheHierarchy(
            l1_size_kb=config.l1_size_kb,
            l1_assoc=8,
            l1_latency=config.l1_latency_cycles,
            l1_energy_pj=config.energy_l1_access_pj,
            l2_size_kb=config.l2_size_kb,
            l2_assoc=16,
            l2_latency=config.l2_latency_cycles,
            l2_energy_pj=config.energy_l2_access_pj,
            l3_size_mb=config.l3_size_mb,
            l3_assoc=16,
            l3_latency=config.l3_latency_cycles,
            l3_energy_pj=config.energy_l3_access_pj
        )
        self.total_flops = 0
        self.total_cycles = 0
        self.total_compute_time_ns = 0.0
        self.total_compute_energy_pj = 0.0
        self.total_cache_energy_pj = 0.0
        self.current_cycle = 0

    def reset(self):
        self.cache_hierarchy.reset()
        self.total_flops = 0
        self.total_cycles = 0
        self.total_compute_time_ns = 0.0
        self.total_compute_energy_pj = 0.0
        self.total_cache_energy_pj = 0.0
        self.current_cycle = 0

    @property
    def peak_gflops(self) -> float:
        """Peak theoretical compute throughput across all host cores."""
        return self.config.num_cores * self.config.clock_freq_ghz * self.config.flops_per_cycle

    def _generate_trace_addresses(self, data_bytes: int, reuse_factor: float, access_pattern: str, chunk_base_addr: int = 0x100000) -> List[int]:
        """
        Generates physical block addresses for microarchitectural cache evaluation.
        """
        num_lines = max(1, (data_bytes + 63) // 64)
        sample_count = min(num_lines, 256) # Sample up to 256 representative lines for microarchitecture
        step = max(1, num_lines // sample_count)

        addresses = []
        if access_pattern == "reusable":
            # Tiled block access: addresses repeat according to reuse factor
            tile_span = max(1, int(sample_count / max(1.0, reuse_factor)))
            for i in range(sample_count):
                block_id = (i % tile_span)
                addresses.append(chunk_base_addr + (block_id * 64))

        elif access_pattern == "streaming":
            # Linear contiguous single-pass addresses
            for i in range(sample_count):
                addresses.append(chunk_base_addr + (i * step * 64))

        else: # "random" / pointer chasing
            # Large sparse pseudo-random stride to simulate graph indirect addressing
            large_space = 256 * 1024 * 1024 # 256 MB span
            for i in range(sample_count):
                rand_offset = ((i * 104729 + 17) % (large_space // 64)) * 64
                addresses.append(chunk_base_addr + rand_offset)

        return addresses

    def execute_chunk(
        self,
        flops: int,
        data_bytes: int,
        reuse_factor: float,
        access_pattern: str,
        chunk_id: int = 0
    ) -> Dict[str, Any]:
        """
        Execute computation chunk on the Host processor.
        Simulates pipeline arithmetic latency, probes 3-level set-associative LRU caches,
        and aggregates stall cycles and cache access energy.
        """
        if flops <= 0:
            return {"compute_time_ns": 0.0, "total_energy_pj": 0.0, "cycles": 0}

        cycle_ns = 1.0 / self.config.clock_freq_ghz

        # 1. Pipeline compute latency
        compute_cycles = flops / (self.config.num_cores * self.config.flops_per_cycle)
        self.current_cycle += int(compute_cycles)

        # 2. Probe 3-Level Set-Associative LRU Cache Hierarchy
        base_addr = 0x10000000 + (chunk_id * 0x80000)
        trace_addrs = self._generate_trace_addresses(data_bytes, reuse_factor, access_pattern, base_addr)

        chunk_stall_cycles = 0
        chunk_cache_energy_pj = 0.0
        llc_miss_count = 0

        for addr in trace_addrs:
            res = self.cache_hierarchy.access(addr, is_write=False, current_cycle=self.current_cycle)
            chunk_stall_cycles += res["stall_cycles"]
            chunk_cache_energy_pj += res["energy_pj"]
            if res["is_llc_miss"]:
                llc_miss_count += 1
            self.current_cycle += res["stall_cycles"]

        # Scale sampled cache results to the full chunk size
        num_total_lines = (data_bytes + 63) // 64
        scale_factor = (num_total_lines / max(1, len(trace_addrs)))
        
        effective_stall_cycles = (chunk_stall_cycles * scale_factor) / self.config.num_cores
        effective_cache_energy_pj = chunk_cache_energy_pj * scale_factor
        effective_llc_misses = llc_miss_count * scale_factor

        # Total on-chip execution time
        total_host_time_ns = (compute_cycles * cycle_ns) + (effective_stall_cycles * cycle_ns)
        compute_energy_pj = flops * self.config.energy_compute_flop_pj
        total_energy_pj = compute_energy_pj + effective_cache_energy_pj

        # Accumulate stats
        self.total_flops += flops
        self.total_cycles += int(compute_cycles + effective_stall_cycles)
        self.total_compute_time_ns += total_host_time_ns
        self.total_compute_energy_pj += compute_energy_pj
        self.total_cache_energy_pj += effective_cache_energy_pj

        return {
            "compute_time_ns": total_host_time_ns,
            "pipeline_time_ns": compute_cycles * cycle_ns,
            "cache_stall_time_ns": effective_stall_cycles * cycle_ns,
            "compute_energy_pj": compute_energy_pj,
            "cache_energy_pj": effective_cache_energy_pj,
            "total_energy_pj": total_energy_pj,
            "total_energy_uj": total_energy_pj / 1e6,
            "llc_miss_rate": (llc_miss_count / len(trace_addrs)) if trace_addrs else 0.0,
            "missed_lines": effective_llc_misses
        }

    def get_stats(self) -> Dict[str, Any]:
        total_energy = self.total_compute_energy_pj + self.total_cache_energy_pj
        cache_stats = self.cache_hierarchy.get_stats()
        return {
            "total_flops": self.total_flops,
            "total_cycles": self.total_cycles,
            "total_compute_time_ns": self.total_compute_time_ns,
            "total_compute_energy_pj": self.total_compute_energy_pj,
            "total_cache_energy_pj": self.total_cache_energy_pj,
            "total_energy_pj": total_energy,
            "total_energy_uj": total_energy / 1e6,
            "total_energy_joules": total_energy / 1e12,
            "cache_hierarchy": cache_stats
        }
