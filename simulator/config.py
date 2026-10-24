"""
Hardware Architectural Configuration and Parameters.
Defines specifications for Host CPU, Interconnect (CXL/PCIe), PIM Units, and DRAM/HBM Subsystem.
Energy numbers are based on modern post-DDR5 / HBM3 / CXL 3.0 published literature (ISSCC / ISCA / MICRO).
"""

from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class HostConfig:
    num_cores: int = 16
    clock_freq_ghz: float = 3.6        # 3.6 GHz high-performance host core
    simd_width_bits: int = 512          # AVX-512 / wide vector units
    flops_per_cycle: int = 32           # 32 FP32 FLOPs/cycle per core (FMA)
    
    # Cache Hierarchy
    l1_size_kb: int = 64                # Per-core L1 D-Cache
    l1_latency_cycles: int = 4
    l2_size_kb: int = 1024              # Per-core L2 Cache (1 MB)
    l2_latency_cycles: int = 14
    l3_size_mb: int = 64                # Shared LLC (64 MB)
    l3_latency_cycles: int = 45
    
    # Energy model (pJ = picojoules)
    energy_l1_access_pj: float = 8.0    # pJ per 64B line access
    energy_l2_access_pj: float = 25.0
    energy_l3_access_pj: float = 120.0
    energy_compute_flop_pj: float = 4.0 # Host ALU energy per FP32 FLOP

@dataclass
class InterconnectConfig:
    name: str = "CXL_3_0_x16"
    bandwidth_gb_s: float = 64.0        # Bidirectional link bandwidth (GB/s)
    base_latency_ns: float = 75.0       # Link traversal latency (CXL.mem flit protocol)
    flit_size_bytes: int = 64           # Standard flit / cache-line size
    
    # Energy per bit transmitted over external board-level link
    energy_per_bit_pj: float = 18.0     # ~18 pJ/bit (~144 pJ per byte)
    packet_header_overhead_bytes: int = 8

@dataclass
class PIMConfig:
    num_units: int = 16                 # One PIM core per memory vault/channel
    clock_freq_ghz: float = 1.0         # 1.0 GHz energy-efficient near-memory core
    simd_width_bits: int = 256          # 256-bit SIMD vector ALU
    flops_per_cycle: int = 8            # 8 FP32 FLOPs/cycle per unit
    local_sram_kb: int = 32             # Scratchpad / register file per PIM unit
    local_sram_latency_cycles: int = 2
    
    # Energy model
    energy_sram_access_pj: float = 5.0
    energy_compute_flop_pj: float = 2.2 # Simpler, lower-voltage near-memory ALU

@dataclass
class MemorySubsystemConfig:
    technology: str = "HBM3_3D_Stacked"
    num_channels: int = 16              # 16 pseudo-channels/vaults
    internal_bandwidth_gb_s: float = 1024.0 # Internal TSV / crossbar aggregate BW (1 TB/s)
    bank_latency_ns: float = 20.0       # tCAS/tRCD local bank access
    row_buffer_size_kb: int = 2
    
    # Energy
    energy_dram_read_per_byte_pj: float = 12.0 # Internal TSV read to PIM logic die
    energy_dram_write_per_byte_pj: float = 14.0

@dataclass
class DecisionEngineConfig:
    profiler_window_instructions: int = 1024
    decision_latency_cycles: int = 250   # Micro-architectural overhead of dynamic evaluation
    decision_energy_pj: float = 850.0   # Energy consumed by dynamic cost evaluation
    hysteresis_threshold: float = 1.15  # 15% margin required to switch placement (prevent ping-ponging)

@dataclass
class SystemConfig:
    host: HostConfig = field(default_factory=HostConfig)
    interconnect: InterconnectConfig = field(default_factory=InterconnectConfig)
    pim: PIMConfig = field(default_factory=PIMConfig)
    memory: MemorySubsystemConfig = field(default_factory=MemorySubsystemConfig)
    decision_engine: DecisionEngineConfig = field(default_factory=DecisionEngineConfig)
