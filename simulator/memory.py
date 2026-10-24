"""
Multi-Bank Memory Subsystem Model (HBM3 / 3D-Stacked DRAM).
Implements explicit Multi-Bank Row-Buffer State Machine with
tCAS (Column Access), tRCD (Row-to-Column Delay), and tRP (Row Precharge) timing constraints.
"""

from typing import Dict, Any, List, Tuple
from enum import Enum
from dataclasses import dataclass
from simulator.config import MemorySubsystemConfig

class BankState(Enum):
    IDLE = "IDLE"     # Precharged, no active row
    ACTIVE = "ACTIVE" # Open row in row buffer

@dataclass
class DRAMBank:
    bank_id: int
    channel_id: int
    state: BankState = BankState.IDLE
    open_row_id: int = -1
    last_access_ns: float = 0.0

class MemorySubsystemModel:
    def __init__(self, config: MemorySubsystemConfig):
        self.config = config
        self.num_channels = config.num_channels
        self.banks_per_channel = 16
        self.total_banks = self.num_channels * self.banks_per_channel
        
        # Timing constraints (in nanoseconds)
        self.t_cas_ns = 10.0 # Column Address Strobe read latency
        self.t_rcd_ns = 14.0 # Row Address to Column Address Delay (activation)
        self.t_rp_ns = 14.0  # Row Precharge time
        
        # Instantiate 256 physical DRAM banks
        self.banks: List[DRAMBank] = [
            DRAMBank(bank_id=i % self.banks_per_channel, channel_id=i // self.banks_per_channel)
            for i in range(self.total_banks)
        ]

        # Telemetry counters
        self.total_bytes_read = 0
        self.total_bytes_written = 0
        self.total_access_time_ns = 0.0
        self.total_energy_pj = 0.0
        self.row_buffer_hits = 0
        self.row_buffer_conflicts = 0
        self.row_buffer_closed_misses = 0
        self.current_time_ns = 0.0

    def reset(self):
        for b in self.banks:
            b.state = BankState.IDLE
            b.open_row_id = -1
            b.last_access_ns = 0.0
        self.total_bytes_read = 0
        self.total_bytes_written = 0
        self.total_access_time_ns = 0.0
        self.total_energy_pj = 0.0
        self.row_buffer_hits = 0
        self.row_buffer_conflicts = 0
        self.row_buffer_closed_misses = 0
        self.current_time_ns = 0.0

    def _map_address_to_bank_and_row(self, address: int) -> Tuple[int, int]:
        """
        Interleaved mapping: maps byte address to (bank_global_idx, row_id).
        Uses row buffer size (e.g. 2 KB) and bank interleaving.
        """
        row_buffer_bytes = self.config.row_buffer_size_kb * 1024
        col = address & (row_buffer_bytes - 1)
        bank_global_idx = (address >> 11) % self.total_banks # 11 bits = 2KB
        row_id = address >> 19
        return bank_global_idx, row_id

    def access(self, num_bytes: int, is_write: bool = False, access_pattern: str = "sequential", base_address: int = 0x200000) -> Dict[str, float]:
        """
        Simulate multi-bank DRAM access with explicit row-buffer state machine.
        Models:
        - Row Buffer Hit: tCAS (~10 ns)
        - Row Buffer Conflict: tRP + tRCD + tCAS (~38 ns)
        - Row Buffer Closed / Empty: tRCD + tCAS (~24 ns)
        """
        if num_bytes <= 0:
            return {"latency_ns": 0.0, "energy_pj": 0.0, "row_buffer_hit_rate": 1.0}

        # Burst transfer time across internal TSVs (e.g. 1024 GB/s)
        tsv_transfer_ns = num_bytes / self.config.internal_bandwidth_gb_s

        # Sample representative memory accesses
        num_bursts = max(1, (num_bytes + 63) // 64)
        sample_count = min(num_bursts, 128)
        step = max(1, num_bursts // sample_count)

        accumulated_bank_latency_ns = 0.0
        chunk_hits = 0
        chunk_conflicts = 0
        chunk_closed = 0

        for i in range(sample_count):
            if access_pattern == "sequential":
                addr = base_address + (i * step * 64)
            elif access_pattern == "strided":
                # Stride across rows on the same bank to trigger row buffer conflicts
                addr = base_address + (i * self.total_banks * 2048)
            else: # "random" pointer chasing
                addr = base_address + (((i * 104729) % (128 * 1024 * 1024)) & ~63)

            bank_idx, row_id = self._map_address_to_bank_and_row(addr)
            bank = self.banks[bank_idx]

            # Bank State Machine Evaluation
            if bank.state == BankState.ACTIVE:
                if bank.open_row_id == row_id:
                    # Case 1: Row Buffer Hit (Page Open)
                    # Latency = tCAS
                    latency = self.t_cas_ns
                    chunk_hits += 1
                else:
                    # Case 2: Row Buffer Conflict (Page Miss - Conflict)
                    # Latency = tRP (Precharge old) + tRCD (Activate new) + tCAS (Column Read)
                    latency = self.t_rp_ns + self.t_rcd_ns + self.t_cas_ns
                    bank.open_row_id = row_id
                    chunk_conflicts += 1
            else:
                # Case 3: Bank was IDLE (Page Closed)
                # Latency = tRCD (Activate) + tCAS (Column Read)
                latency = self.t_rcd_ns + self.t_cas_ns
                bank.state = BankState.ACTIVE
                bank.open_row_id = row_id
                chunk_closed += 1

            bank.last_access_ns = self.current_time_ns + latency
            accumulated_bank_latency_ns += latency

        # Average bank latency across samples
        avg_bank_latency_ns = accumulated_bank_latency_ns / max(1, sample_count)
        total_latency_ns = avg_bank_latency_ns + tsv_transfer_ns
        self.current_time_ns += total_latency_ns

        # Scale hit/miss statistics
        scale = num_bursts / max(1, sample_count)
        self.row_buffer_hits += int(chunk_hits * scale)
        self.row_buffer_conflicts += int(chunk_conflicts * scale)
        self.row_buffer_closed_misses += int(chunk_closed * scale)

        # Energy calculation
        unit_energy_pj = self.config.energy_dram_write_per_byte_pj if is_write else self.config.energy_dram_read_per_byte_pj
        
        # Row conflicts require additional precharge and row activation energy
        activation_penalty_multiplier = 1.0 + (chunk_conflicts / max(1, sample_count)) * 0.45
        total_energy_pj = num_bytes * unit_energy_pj * activation_penalty_multiplier

        if is_write:
            self.total_bytes_written += num_bytes
        else:
            self.total_bytes_read += num_bytes

        self.total_access_time_ns += total_latency_ns
        self.total_energy_pj += total_energy_pj

        hit_rate = (chunk_hits / sample_count) if sample_count > 0 else 0.0

        return {
            "latency_ns": total_latency_ns,
            "bank_latency_ns": avg_bank_latency_ns,
            "transfer_ns": tsv_transfer_ns,
            "energy_pj": total_energy_pj,
            "row_buffer_hit_rate": hit_rate,
            "row_buffer_hits": chunk_hits,
            "row_buffer_conflicts": chunk_conflicts
        }

    def get_stats(self) -> Dict[str, Any]:
        total_accesses = self.row_buffer_hits + self.row_buffer_conflicts + self.row_buffer_closed_misses
        hit_rate = (self.row_buffer_hits / total_accesses) if total_accesses > 0 else 0.0
        return {
            "total_bytes_read": self.total_bytes_read,
            "total_bytes_written": self.total_bytes_written,
            "total_bytes": self.total_bytes_read + self.total_bytes_written,
            "total_access_time_ns": self.total_access_time_ns,
            "total_energy_pj": self.total_energy_pj,
            "total_energy_uj": self.total_energy_pj / 1e6,
            "total_energy_joules": self.total_energy_pj / 1e12,
            "row_buffer_hits": self.row_buffer_hits,
            "row_buffer_conflicts": self.row_buffer_conflicts,
            "row_buffer_closed_misses": self.row_buffer_closed_misses,
            "row_buffer_hit_rate": hit_rate,
            "timing_parameters": {
                "tCAS_ns": self.t_cas_ns,
                "tRCD_ns": self.t_rcd_ns,
                "tRP_ns": self.t_rp_ns
            }
        }
