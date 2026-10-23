"""Transmission time, bandwidth independence, congestion levels, legacy field rejection."""

import pytest

from acaps.config.presets import resolve_config
from acaps.core.network import NetworkModel, describe_network
from acaps.core.timeunits import mbps_to_bps, transmission_time_us
from helpers import make_config


def test_transmission_time_is_bits_over_bandwidth():
    # 1500 B = 12000 bits; 10 Mbps -> 1200 us (bits / Mbps = us)
    assert transmission_time_us(1500, mbps_to_bps(10)) == 1200
    # 250 B = 2000 bits; 1 Mbps -> 2000 us
    assert transmission_time_us(250, mbps_to_bps(1)) == 2000


def test_transmission_time_rounds_up_and_is_at_least_one_us():
    # 1 byte = 8 bits at 3 Mbps = 2.67 us -> 3 us (ceil)
    assert transmission_time_us(1, mbps_to_bps(3)) == 3
    # 1 byte on a 1000 Mbps link = 0.008 us -> minimum 1 us
    assert transmission_time_us(1, mbps_to_bps(1000)) == 1


def test_transmission_time_scales_linearly_with_size_at_fixed_bandwidth():
    bps = mbps_to_bps(5)
    assert transmission_time_us(2400, bps) == 2 * transmission_time_us(1200, bps)


def test_bandwidth_does_not_change_when_packet_size_changes():
    bandwidths = set()
    for size in (64, 1200, 1500, 9000):
        cfg = resolve_config({"linkBandwidthMbps": 7.5, "packetSize": size})
        bandwidths.add(describe_network(cfg)["linkBandwidthBps"])
    assert bandwidths == {7_500_000}
    # also with per-class size models
    cfg = resolve_config({"scenario": "heavyTraffic", "linkBandwidthMbps": 7.5})
    assert describe_network(cfg)["linkBandwidthBps"] == 7_500_000


def test_service_rate_is_rejected_not_ignored():
    with pytest.raises(ValueError, match="linkBandwidthMbps"):
        resolve_config({"serviceRate": 600})


def test_congestion_level_comes_from_occupancy_thresholds():
    cfg = make_config()
    net = NetworkModel(1.0, 100, cfg.congestion_thresholds)
    assert net.congestion_level(0.0).value == "LOW"
    assert net.congestion_level(0.29).value == "LOW"
    assert net.congestion_level(0.30).value == "MEDIUM"
    assert net.congestion_level(0.69).value == "MEDIUM"
    assert net.congestion_level(0.70).value == "HIGH"
    assert net.congestion_level(1.0).value == "HIGH"


def test_thresholds_are_configurable():
    cfg = make_config(congestionThresholds={"medium": 0.1, "high": 0.2})
    net = NetworkModel(1.0, 100, cfg.congestion_thresholds)
    assert net.congestion_level(0.15).value == "MEDIUM"
    assert net.congestion_level(0.25).value == "HIGH"


def test_offered_load_is_derived_from_rate_size_and_bandwidth():
    cfg = resolve_config({"incomingRate": 500, "packetSize": 1250, "linkBandwidthMbps": 10})
    # 500 pkt/s * 1250 B * 8 = 5 Mbit/s on a 10 Mbps link
    assert describe_network(cfg)["offeredLoad"] == pytest.approx(0.5)


def test_invalid_configurations_are_rejected():
    for bad in (
        {"trafficMix": {"emergency": 0.5, "video": 0.2}},  # does not sum to 1
        {"trafficMix": {"emergency": 1.0, "unknown": 0.0}},  # unknown class
        {"queueCapacity": 0},
        {"linkBandwidthMbps": 0},
        {"packetSize": 0},
        {"classes": {"emergency": {"sizeModel": {"type": "uniform", "minBytes": 500, "maxBytes": 100}}}},
        {"bursts": [{"startTime": 1, "duration": 2, "rateMultiplier": 2},
                    {"startTime": 2, "duration": 1, "rateMultiplier": 2}]},  # overlap
    ):
        with pytest.raises(ValueError):
            resolve_config(bad)
