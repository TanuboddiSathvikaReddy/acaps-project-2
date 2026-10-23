"""Traffic generator: produces the workload from the user's network CONDITIONS.

What randomness is used for (and ONLY this):
    * arrival gaps          (stream "arrivals")  - Poisson arrivals
    * traffic-class choice  (stream "classes")   - according to the traffic mix
    * packet size           (stream "sizes")     - according to the class size model

It is NEVER used for waiting time, latency, congestion or urgency: those emerge from the
queue. The three streams are independent, so:
    * changing a size model does not move arrival times or the class sequence;
    * the same seed always gives the same workload (only random() is used, whose output for a
      given seed is stable across Python versions).
Exactly ONE draw is consumed per packet from the class stream and from the size stream, in
packet order, whatever the class or size model.
"""

import hashlib
import math
import random

from acaps.config.models import ArrivalModel, RateSegment, SimulationConfig
from acaps.core.packet import Packet
from acaps.traffic.workload import Workload


def _stream(seed: int, name: str) -> random.Random:
    digest = hashlib.sha256(f"acaps:{seed}:{name}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


class TrafficGenerator:
    def __init__(self, config: SimulationConfig) -> None:
        self.config = config

    def generate(self) -> Workload:
        config = self.config
        arrivals = self._arrival_times()
        class_rng = _stream(config.random_seed, "classes")
        size_rng = _stream(config.random_seed, "sizes")
        segments = config.rate_segments()
        cumulative_by_segment = [self._cumulative_mix(seg) for seg in segments]

        packets: list[Packet] = []
        for index, (arrival_us, segment_index) in enumerate(arrivals, start=1):
            name = self._draw_class(class_rng.random(), cumulative_by_segment[segment_index])
            cls = config.classes[name]
            size = cls.size_model.sample(size_rng.random())
            packets.append(
                Packet(
                    packet_id=index,
                    traffic_class=name,
                    arrival_time_us=arrival_us,
                    size_bytes=size,
                    source=cls.source or f"{name}-src",
                    destination=cls.destination,
                    criticality_rank=cls.criticality_rank,
                    delay_budget_us=cls.delay_budget_us,
                )
            )
        return Workload.from_packets(packets, config.duration_us, config.random_seed)

    # ---- arrivals -----------------------------------------------------------

    def _arrival_times(self) -> list[tuple[int, int]]:
        """(arrival_time_us, segment_index) for every packet, in non-decreasing time order."""
        rng = _stream(self.config.random_seed, "arrivals")
        arrivals: list[tuple[int, int]] = []
        for index, seg in enumerate(self.config.rate_segments()):
            if seg.rate_pps <= 0:
                continue
            if self.config.arrival_model is ArrivalModel.CONSTANT:
                arrivals += [(t, index) for t in self._constant_times(seg)]
            else:
                arrivals += [(t, index) for t in self._poisson_times(seg, rng)]
        return arrivals

    @staticmethod
    def _poisson_times(seg: RateSegment, rng: random.Random) -> list[int]:
        """Exponential gaps -ln(1-U)/rate. Restarting at each segment boundary is exact
        because the exponential distribution is memoryless."""
        times: list[int] = []
        t = float(seg.start_us)
        while True:
            t += -math.log1p(-rng.random()) / seg.rate_pps * 1e6
            if t >= seg.end_us:
                return times
            times.append(int(t))

    @staticmethod
    def _constant_times(seg: RateSegment) -> list[int]:
        """Evenly spaced; first packet at the segment start. k*1e6/rate avoids drift."""
        times: list[int] = []
        k = 0
        while True:
            t = seg.start_us + k * 1e6 / seg.rate_pps
            if t >= seg.end_us:
                return times
            times.append(int(t))
            k += 1

    # ---- class choice ---------------------------------------------------------

    @staticmethod
    def _cumulative_mix(seg: RateSegment) -> list[tuple[float, str]]:
        """Canonical (alphabetical) class order so dict key order can never change the workload."""
        total = 0.0
        cumulative: list[tuple[float, str]] = []
        for name in sorted(seg.mix):
            if seg.mix[name] > 0:
                total += seg.mix[name]
                cumulative.append((total, name))
        return cumulative

    @staticmethod
    def _draw_class(u: float, cumulative: list[tuple[float, str]]) -> str:
        for bound, name in cumulative:
            if u < bound:
                return name
        return cumulative[-1][1]  # guards float rounding of the cumulative sum
