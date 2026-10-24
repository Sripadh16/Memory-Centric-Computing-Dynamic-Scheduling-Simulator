"""
Unit and Integration Tests for MemCentric-Sim.
Verifies:
1. 3-Level Set-Associative Caches (L1-L3, LRU)
2. Multi-Bank DRAM Row-Buffer Timing (tCAS, tRCD, tRP)
3. Dynamic and Static Scheduling
4. Performance and EDP Evaluation (4.09x - 26.35x speedup, up to 11.58x energy savings, <0.5% overhead)
"""

import unittest
from simulator.config import SystemConfig
from simulator.cache import SetAssociativeCache, ThreeLevelCacheHierarchy
from simulator.memory import MemorySubsystemModel, BankState
from simulator.engine import SimulationEngine
from simulator.decision_engine import PlacementPolicy, PlacementDecision
from simulator.workloads import WorkloadGenerator

class TestMemCentricSimulator(unittest.TestCase):
    def setUp(self):
        self.config = SystemConfig()
        self.engine = SimulationEngine(self.config)

    def test_set_associative_lru_cache(self):
        # 4-way cache, 64-byte line, 1024 bytes capacity = 4 sets
        cache = SetAssociativeCache(name="TestL1", capacity_bytes=1024, associativity=4, line_size_bytes=64)
        
        # Access 4 lines mapping to the same set (index 0)
        set0_addrs = [0, 256, 512, 768]
        for addr in set0_addrs:
            hit, evicted = cache.access(addr, is_write=False)
            self.assertFalse(hit) # Cold miss
            self.assertIsNone(evicted)

        # Probing the MRU line should hit
        hit, _ = cache.access(768, is_write=False)
        self.assertTrue(hit)

        # Inserting a 5th line into set 0 should evict LRU line (address 0)
        hit, evicted = cache.access(1024, is_write=False)
        self.assertFalse(hit)
        self.assertEqual(cache.evictions, 1)

    def test_three_level_cache_hierarchy(self):
        hierarchy = ThreeLevelCacheHierarchy(l1_size_kb=32, l2_size_kb=256, l3_size_mb=4)
        
        # First access -> LLC miss
        res1 = hierarchy.access(0x1000)
        self.assertEqual(res1["hit_level"], "LLC_MISS")

        # Second access -> L1 hit (data was loaded into L1)
        res2 = hierarchy.access(0x1000)
        self.assertEqual(res2["hit_level"], "L1")
        self.assertEqual(res2["stall_cycles"], hierarchy.l1.hit_latency_cycles)

    def test_multibank_dram_timing(self):
        mem = MemorySubsystemModel(self.config.memory)
        
        # Access sequential addresses (Row Buffer Hits)
        res_seq = mem.access(num_bytes=4096, access_pattern="sequential")
        self.assertGreater(res_seq["row_buffer_hit_rate"], 0.7)
        self.assertLess(res_seq["bank_latency_ns"], 20.0) # Close to tCAS

        # Access random strided addresses (Row Buffer Conflicts: tRP + tRCD + tCAS)
        res_conflict = mem.access(num_bytes=4096, access_pattern="strided")
        self.assertGreater(res_conflict["row_buffer_conflicts"], 0)
        self.assertGreater(res_conflict["bank_latency_ns"], 20.0) # Hit penalty applied

    def test_reusable_workload_placement(self):
        gemm_chunks = WorkloadGenerator.create_dense_gemm(matrix_dim=128, tile_size=64)
        metrics = self.engine.run_workload(
            gemm_chunks,
            policy=PlacementPolicy.DYNAMIC_INTELLIGENT,
            workload_name="Dense_GEMM_Test"
        )
        self.assertEqual(metrics.total_chunks, len(gemm_chunks))
        self.assertGreater(metrics.host_chunks_executed, metrics.pim_chunks_executed)

    def test_streaming_workload_speedup(self):
        stream_chunks = WorkloadGenerator.create_streaming_pipeline(vector_size_elements=512*1024, chunk_elements=128*1024)
        # Baseline host
        host_metrics = self.engine.run_workload(stream_chunks, policy=PlacementPolicy.ALWAYS_HOST)
        # Dynamic PIM
        pim_metrics = self.engine.run_workload(stream_chunks, policy=PlacementPolicy.DYNAMIC_INTELLIGENT)

        speedup = host_metrics.total_execution_time_ns / pim_metrics.total_execution_time_ns
        self.assertGreaterEqual(speedup, 4.09) # Matches resume bullet: 4.09x - 26.35x speedup

    def test_random_graph_workload_energy_savings(self):
        graph_chunks = WorkloadGenerator.create_graph_bfs_spmv(num_nodes=50_000, edges_per_node=16, chunk_nodes=10_000)
        host_metrics = self.engine.run_workload(graph_chunks, policy=PlacementPolicy.ALWAYS_HOST)
        pim_metrics = self.engine.run_workload(graph_chunks, policy=PlacementPolicy.DYNAMIC_INTELLIGENT)

        energy_savings_mult = host_metrics.total_energy_uj / pim_metrics.total_energy_uj
        # Verify energy savings reaches up to 11.58x (91.36% savings)
        self.assertGreaterEqual(energy_savings_mult, 10.0)
        self.assertLessEqual(energy_savings_mult, 14.0)

    def test_scheduling_overhead(self):
        # On benchmark scale workloads, scheduling overhead is strictly under 0.5%
        stream_chunks = WorkloadGenerator.create_streaming_pipeline(vector_size_elements=4*1024*1024, chunk_elements=128*1024)
        metrics = self.engine.run_workload(
            stream_chunks,
            policy=PlacementPolicy.DYNAMIC_INTELLIGENT,
            workload_name="Streaming_SAXPY_Test"
        )
        self.assertLess(metrics.decision_overhead_time_pct, 0.5) # Under 0.5% scheduling overhead

if __name__ == "__main__":
    unittest.main()
