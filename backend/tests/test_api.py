"""HTTP contract (brief section 35, item 11 and the API section)."""

import pytest
from fastapi.testclient import TestClient

from acaps.api.app import app

client = TestClient(app)
SMALL = {"scenario": "heavyTraffic", "simulationDuration": 1}


def test_scenarios_endpoint_lists_all_presets_with_resolved_configs():
    body = client.get("/api/v1/scenarios").json()
    names = {s["name"] for s in body}
    assert {"normalTraffic", "heavyTraffic", "emergencyBurst", "videoHeavy", "networkOverload",
            "mixedTraffic", "sizeNeutralControl", "custom"} <= names
    heavy = next(s for s in body if s["name"] == "heavyTraffic")
    assert heavy["config"]["linkBandwidthMbps"] == 5.0 and "serviceRate" not in heavy["config"]
    assert heavy["config"]["derived"]["offeredLoad"] == pytest.approx(0.867, abs=0.005)


def test_simulate_returns_the_documented_structure():
    r = client.post("/api/v1/simulate", json=SMALL)
    assert r.status_code == 200
    body = r.json()
    assert body["schemaVersion"] == "1.0"
    assert set(body["schedulers"]) == {"FIFO", "STATIC_PRIORITY", "ACAPS"}
    assert body["workload"]["packetCount"] == len(body["workload"]["packets"]) > 0
    acaps = body["schedulers"]["ACAPS"]
    assert {"metrics", "packets", "queueTimeline", "decisions"} <= set(acaps)
    assert {"overall", "perClass", "queue"} == set(acaps["metrics"])
    assert {"packetLossRate", "deadlineMissRate", "avgWaitingTimeMs", "jitterMs", "starvationCount"} <= set(acaps["metrics"]["overall"])
    packet = acaps["packets"][0]
    assert {"packetId", "outcome", "txStartUs", "waitingTimeUs", "totalDelayUs", "deadlineMissed"} <= set(packet)
    assert {"reasonCode", "details", "queueLength"} <= set(acaps["decisions"][0])
    assert body["comparison"]["baseline"] == "FIFO"
    assert set(body["comparison"]["deltasVsFifo"]["deadlineMissRate"]) == {"STATIC_PRIORITY", "ACAPS"}
    assert body["config"]["derived"]["linkBandwidthBps"] == 5_000_000
    assert "sizeNeutralControl" not in body


def test_request_fields_override_the_preset():
    body = client.post("/api/v1/simulate", json={**SMALL, "linkBandwidthMbps": 3, "incomingRate": 300, "randomSeed": 7}).json()
    cfg = body["config"]
    assert (cfg["linkBandwidthMbps"], cfg["incomingRate"], cfg["randomSeed"]) == (3, 300, 7)
    assert cfg["classes"]["video"]["sizeModel"]["type"] == "uniform"  # preset kept


def test_simulate_is_deterministic_over_http():
    assert client.post("/api/v1/simulate", json=SMALL).json() == client.post("/api/v1/simulate", json=SMALL).json()


def test_optional_outputs_can_be_switched_on_and_off():
    body = client.post("/api/v1/simulate", json={**SMALL, "options": {
        "includeEventLog": True, "includeDecisionCandidates": True, "includeDecisions": True,
        "includeQueueTimeline": False, "includeSizeNeutralControl": True}}).json()
    acaps = body["schedulers"]["ACAPS"]
    assert "events" in acaps and "queueTimeline" not in acaps
    assert "candidates" in acaps["decisions"][0]
    assert "sizeNeutralControl" in body
    assert body["sizeNeutralControl"]["workloadFingerprint"] != body["workload"]["fingerprint"]


def test_timeline_is_downsampled_but_keeps_endpoints():
    body = client.post("/api/v1/simulate", json={**SMALL, "options": {"maxTimelinePoints": 50}}).json()
    timeline = body["schedulers"]["FIFO"]["queueTimeline"]
    assert len(timeline) <= 50 and timeline[0]["timeUs"] == 0


@pytest.mark.parametrize("bad", [
    {"serviceRate": 500},
    {"trafficMix": {"emergency": 0.5}},
    {"queueCapacity": 0},
    {"noSuchField": 1},
    {"scenario": "doesNotExist"},
    {"classes": {"emergency": {"packetSizeBytes": 100}}},
])
def test_invalid_requests_return_422_with_a_message(bad):
    r = client.post("/api/v1/simulate", json={**SMALL, **bad})
    assert r.status_code == 422 and r.json()["detail"]


def test_service_rate_error_message_names_the_replacement():
    r = client.post("/api/v1/simulate", json={"serviceRate": 500})
    assert "linkBandwidthMbps" in str(r.json())


def test_experiments_endpoint_aggregates_over_runs():
    r = client.post("/api/v1/experiments", json={**SMALL, "runs": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["runCount"] == 3 and len(body["runs"]) == 3
    stat = body["aggregate"]["ACAPS"]["overall"]["avgWaitingTimeMs"]
    assert stat["n"] == 3 and stat["mean"] is not None
    assert "ACAPS" in body["pairedDeltasVsFifo"]


def test_experiments_rejects_bad_run_counts():
    assert client.post("/api/v1/experiments", json={**SMALL, "runs": 0}).status_code == 422
    assert client.post("/api/v1/experiments", json={**SMALL, "runs": 10_000}).status_code == 422
