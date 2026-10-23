"""Unit system and conversions.

Simulation time is an INTEGER number of microseconds (us). Integers make event
ordering and ties exact, and make tests exact.

Conventions (all documented in docs/ASSUMPTIONS.md):
    1 s      = 1_000_000 us
    1 ms     = 1_000 us
    1 byte   = 8 bits
    1 Mbps   = 1_000_000 bit/s   (decimal, the networking convention)
"""

US_PER_S = 1_000_000
US_PER_MS = 1_000
BITS_PER_BYTE = 8
BPS_PER_MBPS = 1_000_000


def seconds_to_us(seconds: float) -> int:
    return round(seconds * US_PER_S)


def ms_to_us(milliseconds: float) -> int:
    return round(milliseconds * US_PER_MS)


def us_to_ms(microseconds: float) -> float:
    return microseconds / US_PER_MS


def mbps_to_bps(mbps: float) -> int:
    return round(mbps * BPS_PER_MBPS)


def transmission_time_us(size_bytes: int, bandwidth_bps: int) -> int:
    """Serialization time of one packet on the link, in whole microseconds.

        transmissionTime = packetSizeBits / linkBandwidthBps

    Rounded UP (ceiling) because a packet cannot finish before its last bit has
    been sent. Minimum 1 us so that every transmission takes positive time.
    Pure integer arithmetic: no floating-point error.

    Shortcut worth remembering: bits / Mbps = microseconds.
        1500 B on 10 Mbps -> 12000 / 10 = 1200 us
    """
    bits = size_bytes * BITS_PER_BYTE
    return max(1, -(-bits * US_PER_S // bandwidth_bps))
