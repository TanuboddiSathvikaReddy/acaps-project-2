"""Workload: the immutable, fingerprinted packet list that is replayed for every scheduler."""

import hashlib
from dataclasses import dataclass
from typing import Iterable

from acaps.core.packet import Packet


def compute_fingerprint(packets: Iterable[Packet], duration_us: int) -> str:
    """SHA-256 over every property of every packet (proof that two runs used the same workload)."""
    digest = hashlib.sha256()
    digest.update(f"duration_us={duration_us}\n".encode())
    for p in packets:
        digest.update(
            (
                f"{p.packet_id}|{p.traffic_class}|{p.arrival_time_us}|{p.size_bytes}|"
                f"{p.source}|{p.destination}|{p.criticality_rank}|{p.delay_budget_us}\n"
            ).encode()
        )
    return digest.hexdigest()


@dataclass(frozen=True)
class Workload:
    packets: tuple[Packet, ...]  # sorted by (arrival_time_us, packet_id)
    duration_us: int  # traffic is generated in [0, duration_us)
    seed: int | None
    fingerprint: str

    @staticmethod
    def from_packets(packets: Iterable[Packet], duration_us: int, seed: int | None = None) -> "Workload":
        """Build a workload from explicit packets (used by tests and hand-made scenarios)."""
        ordered = tuple(sorted(packets, key=lambda p: (p.arrival_time_us, p.packet_id)))
        ids = [p.packet_id for p in ordered]
        if len(set(ids)) != len(ids):
            raise ValueError("packet ids must be unique")
        return Workload(ordered, duration_us, seed, compute_fingerprint(ordered, duration_us))

    def __len__(self) -> int:
        return len(self.packets)
