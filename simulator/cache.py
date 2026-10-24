"""
Microarchitectural Set-Associative Cache Model with Explicit LRU Replacement.
Implements tag arrays, set indexing, LRU queue tracking per set,
and a 3-tier hierarchy (L1 D-Cache, L2 Cache, Shared L3 / LLC).
"""

from typing import Dict, Any, Tuple, Optional, List
from collections import OrderedDict
from dataclasses import dataclass

@dataclass
class CacheLine:
    tag: int
    valid: bool = True
    dirty: bool = False
    last_access_cycle: int = 0

class SetAssociativeCache:
    """
    A parameterized set-associative cache with true LRU replacement policy.
    Uses collections.OrderedDict per set to track exact age order of lines.
    """
    def __init__(
        self,
        name: str,
        capacity_bytes: int,
        associativity: int,
        line_size_bytes: int = 64,
        hit_latency_cycles: int = 4,
        access_energy_pj: float = 8.0
    ):
        self.name = name
        self.capacity_bytes = capacity_bytes
        self.associativity = associativity
        self.line_size_bytes = line_size_bytes
        self.hit_latency_cycles = hit_latency_cycles
        self.access_energy_pj = access_energy_pj

        # Calculate geometry
        self.num_lines = capacity_bytes // line_size_bytes
        self.num_sets = max(1, self.num_lines // associativity)

        # Bit masks
        self.offset_bits = (line_size_bytes - 1).bit_length()
        self.set_index_mask = self.num_sets - 1
        self.index_bits = self.set_index_mask.bit_length()

        # Each set is an OrderedDict: tag -> CacheLine (LRU at head, MRU at tail)
        self.sets: List[OrderedDict[int, CacheLine]] = [OrderedDict() for _ in range(self.num_sets)]

        # Telemetry counters
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.writebacks = 0
        self.total_energy_pj = 0.0

    def reset(self):
        for s in self.sets:
            s.clear()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.writebacks = 0
        self.total_energy_pj = 0.0

    def _decompose_address(self, address: int) -> Tuple[int, int, int]:
        """Decomposes a physical byte address into (tag, set_index, offset)."""
        offset = address & (self.line_size_bytes - 1)
        set_index = (address >> self.offset_bits) & self.set_index_mask
        tag = address >> (self.offset_bits + self.index_bits)
        return tag, set_index, offset

    def probe(self, address: int) -> bool:
        """Non-modifying check whether address is currently resident in cache."""
        tag, set_index, _ = self._decompose_address(address)
        return tag in self.sets[set_index]

    def access(self, address: int, is_write: bool = False, current_cycle: int = 0) -> Tuple[bool, Optional[int]]:
        """
        Microarchitectural access with explicit LRU update.
        Returns: (is_hit, evicted_address_if_writeback)
        """
        tag, set_index, _ = self._decompose_address(address)
        cache_set = self.sets[set_index]
        self.total_energy_pj += self.access_energy_pj

        # Case 1: Cache Hit
        if tag in cache_set:
            self.hits += 1
            line = cache_set[tag]
            line.last_access_cycle = current_cycle
            if is_write:
                line.dirty = True
            # Move to end (Most Recently Used)
            cache_set.move_to_end(tag)
            return True, None

        # Case 2: Cache Miss
        self.misses += 1
        evicted_writeback_addr = None

        # Check if set is full (requires LRU eviction)
        if len(cache_set) >= self.associativity:
            # Pop least recently used line (first item in OrderedDict)
            evicted_tag, evicted_line = cache_set.popitem(last=False)
            self.evictions += 1
            if evicted_line.dirty:
                self.writebacks += 1
                # Reconstruct byte address of evicted line
                evicted_writeback_addr = (evicted_tag << (self.offset_bits + self.index_bits)) | (set_index << self.offset_bits)

        # Insert incoming line as MRU
        new_line = CacheLine(tag=tag, valid=True, dirty=is_write, last_access_cycle=current_cycle)
        cache_set[tag] = new_line
        cache_set.move_to_end(tag)

        return False, evicted_writeback_addr

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total) if total > 0 else 0.0

    def get_stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "capacity_kb": self.capacity_bytes // 1024,
            "associativity": self.associativity,
            "sets": self.num_sets,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hit_rate,
            "evictions": self.evictions,
            "writebacks": self.writebacks,
            "total_energy_pj": self.total_energy_pj,
            "total_energy_uj": self.total_energy_pj / 1e6
        }

class ThreeLevelCacheHierarchy:
    """
    3-Level Set-Associative Cache Hierarchy:
    L1 D-Cache (Private) -> L2 Cache (Private) -> L3 Cache (Shared LLC).
    """
    def __init__(
        self,
        l1_size_kb: int = 64,
        l1_assoc: int = 8,
        l1_latency: int = 4,
        l1_energy_pj: float = 8.0,
        l2_size_kb: int = 1024,
        l2_assoc: int = 16,
        l2_latency: int = 14,
        l2_energy_pj: float = 25.0,
        l3_size_mb: int = 64,
        l3_assoc: int = 16,
        l3_latency: int = 45,
        l3_energy_pj: float = 120.0
    ):
        self.l1 = SetAssociativeCache(
            name="L1_Data",
            capacity_bytes=l1_size_kb * 1024,
            associativity=l1_assoc,
            line_size_bytes=64,
            hit_latency_cycles=l1_latency,
            access_energy_pj=l1_energy_pj
        )
        self.l2 = SetAssociativeCache(
            name="L2_Unified",
            capacity_bytes=l2_size_kb * 1024,
            associativity=l2_assoc,
            line_size_bytes=64,
            hit_latency_cycles=l2_latency,
            access_energy_pj=l2_energy_pj
        )
        self.l3 = SetAssociativeCache(
            name="L3_Shared_LLC",
            capacity_bytes=l3_size_mb * 1024 * 1024,
            associativity=l3_assoc,
            line_size_bytes=64,
            hit_latency_cycles=l3_latency,
            access_energy_pj=l3_energy_pj
        )
        self.total_llc_misses = 0
        self.total_stall_cycles = 0

    def reset(self):
        self.l1.reset()
        self.l2.reset()
        self.l3.reset()
        self.total_llc_misses = 0
        self.total_stall_cycles = 0

    def access(self, address: int, is_write: bool = False, current_cycle: int = 0) -> Dict[str, Any]:
        """
        Traverse L1 -> L2 -> L3.
        Returns hit level ('L1', 'L2', 'L3', or 'LLC_MISS'), stall cycles, and energy.
        """
        stall_cycles = self.l1.hit_latency_cycles
        energy_pj = self.l1.access_energy_pj

        # 1. Probe L1
        l1_hit, l1_evicted = self.l1.access(address, is_write, current_cycle)
        if l1_hit:
            return {"hit_level": "L1", "stall_cycles": stall_cycles, "energy_pj": energy_pj, "is_llc_miss": False}

        # Handle L1 writeback to L2 if evicted dirty
        if l1_evicted is not None:
            self.l2.access(l1_evicted, is_write=True, current_cycle=current_cycle)

        # 2. Probe L2
        stall_cycles += self.l2.hit_latency_cycles
        energy_pj += self.l2.access_energy_pj
        l2_hit, l2_evicted = self.l2.access(address, is_write, current_cycle)
        if l2_hit:
            self.total_stall_cycles += stall_cycles
            return {"hit_level": "L2", "stall_cycles": stall_cycles, "energy_pj": energy_pj, "is_llc_miss": False}

        # Handle L2 writeback to L3 if evicted dirty
        if l2_evicted is not None:
            self.l3.access(l2_evicted, is_write=True, current_cycle=current_cycle)

        # 3. Probe L3 (Shared LLC)
        stall_cycles += self.l3.hit_latency_cycles
        energy_pj += self.l3.access_energy_pj
        l3_hit, _ = self.l3.access(address, is_write, current_cycle)
        if l3_hit:
            self.total_stall_cycles += stall_cycles
            return {"hit_level": "L3", "stall_cycles": stall_cycles, "energy_pj": energy_pj, "is_llc_miss": False}

        # 4. LLC Miss (Data must come from DRAM)
        self.total_llc_misses += 1
        self.total_stall_cycles += stall_cycles
        return {"hit_level": "LLC_MISS", "stall_cycles": stall_cycles, "energy_pj": energy_pj, "is_llc_miss": True}

    def get_stats(self) -> Dict[str, Any]:
        total_energy_pj = self.l1.total_energy_pj + self.l2.total_energy_pj + self.l3.total_energy_pj
        return {
            "l1": self.l1.get_stats(),
            "l2": self.l2.get_stats(),
            "l3": self.l3.get_stats(),
            "total_llc_misses": self.total_llc_misses,
            "total_stall_cycles": self.total_stall_cycles,
            "total_cache_energy_pj": total_energy_pj,
            "total_cache_energy_uj": total_energy_pj / 1e6
        }
