"""
System Interconnect Model (CXL / PCIe / Memory Link).
Simulates packetization, serialization, queueing latency, and energy consumption
for data transfers between Host and Memory Subsystem.
"""

from typing import Dict, Any
from simulator.config import InterconnectConfig

class InterconnectModel:
    def __init__(self, config: InterconnectConfig):
        self.config = config
        self.total_bytes_host_to_mem = 0
        self.total_bytes_mem_to_host = 0
        self.total_packets = 0
        self.total_transfer_time_ns = 0.0
        self.total_energy_pj = 0.0

    def reset(self):
        self.total_bytes_host_to_mem = 0
        self.total_bytes_mem_to_host = 0
        self.total_packets = 0
        self.total_transfer_time_ns = 0.0
        self.total_energy_pj = 0.0

    def transfer(self, num_bytes: int, direction: str = "mem_to_host") -> Dict[str, float]:
        """
        Simulate a transfer across the host-memory interconnect.
        direction: 'mem_to_host' (read) or 'host_to_mem' (write / offload input / sync back).
        Returns dict with latency (ns) and energy (pJ).
        """
        if num_bytes <= 0:
            return {"latency_ns": 0.0, "energy_pj": 0.0, "effective_bandwidth_gb_s": self.config.bandwidth_gb_s}

        # Flit calculation with packet header overhead
        flit_payload = self.config.flit_size_bytes
        num_flits = (num_bytes + flit_payload - 1) // flit_payload
        wire_bytes = num_flits * (flit_payload + self.config.packet_header_overhead_bytes)

        # Serialization time: wire_bytes / Bandwidth
        # 1 GB/s = 1 byte/ns
        serialization_ns = wire_bytes / self.config.bandwidth_gb_s
        total_latency_ns = self.config.base_latency_ns + serialization_ns

        # Energy calculation: wire_bytes * 8 bits * energy_per_bit_pj
        energy_pj = wire_bytes * 8.0 * self.config.energy_per_bit_pj

        # Track statistics
        if direction == "host_to_mem":
            self.total_bytes_host_to_mem += num_bytes
        else:
            self.total_bytes_mem_to_host += num_bytes
            
        self.total_packets += num_flits
        self.total_transfer_time_ns += total_latency_ns
        self.total_energy_pj += energy_pj

        effective_bw = (num_bytes / total_latency_ns) if total_latency_ns > 0 else 0.0

        return {
            "latency_ns": total_latency_ns,
            "serialization_ns": serialization_ns,
            "base_latency_ns": self.config.base_latency_ns,
            "energy_pj": energy_pj,
            "energy_uj": energy_pj / 1e6,
            "wire_bytes": wire_bytes,
            "effective_bandwidth_gb_s": effective_bw
        }

    def get_stats(self) -> Dict[str, Any]:
        total_bytes = self.total_bytes_host_to_mem + self.total_bytes_mem_to_host
        return {
            "total_bytes_transferred": total_bytes,
            "total_mbytes_transferred": total_bytes / (1024 * 1024),
            "bytes_host_to_mem": self.total_bytes_host_to_mem,
            "bytes_mem_to_host": self.total_bytes_mem_to_host,
            "total_packets": self.total_packets,
            "total_transfer_time_ns": self.total_transfer_time_ns,
            "total_energy_pj": self.total_energy_pj,
            "total_energy_uj": self.total_energy_pj / 1e6,
            "total_energy_joules": self.total_energy_pj / 1e12
        }
