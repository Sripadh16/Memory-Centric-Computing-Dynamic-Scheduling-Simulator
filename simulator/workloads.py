"""
Workload Kernel Definitions and Trace Generators.
Implements the 3 context-mandated workloads:
1. Highly Reusable Dataset (Dense GEMM / 2D Stencil)
2. Streaming Dataset (Vector Add / SAXPY / Stream Filter)
3. Randomly Accessed Dataset (Graph BFS / SpMV / Pointer Chasing)
Plus a 4th Heterogeneous Mixed Pipeline interleaving all 3 access patterns.
"""

from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class ComputeChunk:
    chunk_id: int
    kernel_name: str
    phase_name: str
    flops: int
    data_bytes: int
    reuse_factor: float
    access_pattern: str       # 'reusable', 'streaming', 'random'
    data_residence: str       # 'memory' or 'host_cache'
    output_bytes: int = 64    # Output bytes to return / sync

class WorkloadGenerator:
    """Generates parameterized computational chunks for simulation."""

    @staticmethod
    def create_dense_gemm(matrix_dim: int = 512, tile_size: int = 64) -> List[ComputeChunk]:
        """
        Highly Reusable Dataset: Dense Matrix Multiplication (C = A * B).
        Arithmetic Intensity: High (~2 * N FLOPs per 8 bytes element = N/4).
        Temporal Reuse: Each tile is reused multiple times in cache.
        """
        chunks = []
        num_tiles = matrix_dim // tile_size
        chunk_id = 0

        # Matrix element size = 4 bytes (FP32)
        bytes_per_tile = tile_size * tile_size * 4 # e.g. 64x64x4 = 16 KB

        for i in range(num_tiles):
            for j in range(num_tiles):
                # For each tile (i, j), we accumulate across k tiles
                for k in range(num_tiles):
                    # 2 * tile_size^3 operations
                    flops = 2 * (tile_size ** 3)
                    # Data needed: Tile A (16KB) + Tile B (16KB) + Tile C (16KB)
                    data_bytes = 3 * bytes_per_tile
                    reuse_factor = float(tile_size) # High reuse

                    chunks.append(ComputeChunk(
                        chunk_id=chunk_id,
                        kernel_name="Dense_GEMM",
                        phase_name=f"Tile_{i}_{j}_{k}",
                        flops=flops,
                        data_bytes=data_bytes,
                        reuse_factor=reuse_factor,
                        access_pattern="reusable",
                        data_residence="memory" if k == 0 else "host_cache",
                        output_bytes=bytes_per_tile
                    ))
                    chunk_id += 1

        return chunks

    @staticmethod
    def create_streaming_pipeline(vector_size_elements: int = 4 * 1024 * 1024, chunk_elements: int = 128 * 1024) -> List[ComputeChunk]:
        """
        Streaming Dataset: Vector Scale, Add & Filter (Y = alpha * X + Y, filter > threshold).
        Arithmetic Intensity: Low (~2 FLOPs per 8 bytes = 0.25 FLOPs/byte).
        Temporal Reuse: 1.0 (single-pass streaming, elements accessed once).
        """
        chunks = []
        num_chunks = vector_size_elements // chunk_elements
        bytes_per_chunk = chunk_elements * 4 # FP32

        for i in range(num_chunks):
            # 2 operations per element (multiply + add) + 1 comparison
            flops = chunk_elements * 3
            data_bytes = bytes_per_chunk * 2 # Vector X and Vector Y

            chunks.append(ComputeChunk(
                chunk_id=i,
                kernel_name="Streaming_SAXPY_Filter",
                phase_name=f"StreamChunk_{i}",
                flops=flops,
                data_bytes=data_bytes,
                reuse_factor=1.0,
                access_pattern="streaming",
                data_residence="memory",
                output_bytes=64 # Small scalar count / filtered reduction
            ))

        return chunks

    @staticmethod
    def create_graph_bfs_spmv(num_nodes: int = 250_000, edges_per_node: int = 16, chunk_nodes: int = 25_000) -> List[ComputeChunk]:
        """
        Randomly Accessed Dataset: Graph Breadth-First Search / Sparse Matrix-Vector (SpMV).
        Access Pattern: Indirect pointer chasing (col_idx[row_ptr[i]] -> val[k]).
        Characteristics: Irregular memory access, severe cache misses, bus line amplification.
        """
        chunks = []
        num_chunks = num_nodes // chunk_nodes

        for i in range(num_chunks):
            num_edges = chunk_nodes * edges_per_node
            # ~2 ops per non-zero edge (multiply & accumulate or level update)
            flops = num_edges * 2
            # Indirect index lookups cause memory fetches across random cache lines
            # Cache line amplification: 64B line fetched for 4B value
            data_bytes = int(num_edges * 12) # node indices + edge weights

            chunks.append(ComputeChunk(
                chunk_id=i,
                kernel_name="Graph_BFS_SpMV",
                phase_name=f"GraphFrontier_{i}",
                flops=flops,
                data_bytes=data_bytes,
                reuse_factor=0.2, # Very low spatial/temporal locality
                access_pattern="random",
                data_residence="memory",
                output_bytes=chunk_nodes * 4
            ))

        return chunks

    @staticmethod
    def create_heterogeneous_mixed_pipeline() -> List[ComputeChunk]:
        """
        Realistic Mixed Multi-Phase Pipeline:
        Phase 1: Graph Frontier Filtering (Random access)
        Phase 2: Streaming Signal Normalization (Streaming)
        Phase 3: Dense Feature Projection GEMM (High reuse)
        Phase 4: Streaming Threshold Reduction (Streaming)
        """
        all_chunks = []
        cid = 0

        # Phase 1: 8 random chunks
        for c in WorkloadGenerator.create_graph_bfs_spmv(num_nodes=80_000, edges_per_node=16, chunk_nodes=10_000):
            c.chunk_id = cid
            c.phase_name = f"Phase1_RandomFilter_{cid}"
            all_chunks.append(c)
            cid += 1

        # Phase 2: 12 streaming chunks
        for c in WorkloadGenerator.create_streaming_pipeline(vector_size_elements=1_200_000, chunk_elements=100_000):
            c.chunk_id = cid
            c.phase_name = f"Phase2_StreamNormalize_{cid}"
            all_chunks.append(c)
            cid += 1

        # Phase 3: 16 dense reusable chunks (4x4 tile GEMM)
        for c in WorkloadGenerator.create_dense_gemm(matrix_dim=256, tile_size=64):
            c.chunk_id = cid
            c.phase_name = f"Phase3_DenseGEMM_{cid}"
            all_chunks.append(c)
            cid += 1

        # Phase 4: 8 streaming aggregation chunks
        for c in WorkloadGenerator.create_streaming_pipeline(vector_size_elements=800_000, chunk_elements=100_000):
            c.chunk_id = cid
            c.phase_name = f"Phase4_StreamAggregate_{cid}"
            all_chunks.append(c)
            cid += 1

        return all_chunks
