"""Thin FastAPI wrapper. All logic lives in the library; this only converts JSON <-> objects.

    GET  /api/v1/scenarios      list of presets with their resolved configuration
    POST /api/v1/simulate       one seed, all three schedulers, one shared workload
    POST /api/v1/experiments    repeated runs (consecutive seeds) with aggregation

Run:  uvicorn acaps.api.app:app --reload
"""

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import ValidationError

from acaps import __version__
from acaps.api.schemas import ExperimentRequest, SimulationRequest, validation_detail
from acaps.api.serializers import config_to_dict, experiment_to_dict, simulation_to_dict
from acaps.config.models import SimulationConfig
from acaps.config.presets import PRESETS, resolve_config
from acaps.experiments.runner import run_experiment, run_simulation

app = FastAPI(
    title="ACAPS Simulation API",
    version=__version__,
    description="Adaptive Context-Aware Packet Scheduling: Phase 1 simulation backend.",
)
# A separate frontend will call this API from another origin.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
# Full simulation responses are large but repetitive (~13 MB raw -> ~1 MB gzipped for a 10 s run).
app.add_middleware(GZipMiddleware, minimum_size=1024)


def _resolve(request: SimulationRequest) -> SimulationConfig:
    try:
        return resolve_config(request.to_config_request())
    except (ValidationError, ValueError) as error:
        raise HTTPException(status_code=422, detail=validation_detail(error)) from error


@app.get("/api/v1/scenarios")
def list_scenarios() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "label": preset.label,
            "description": preset.description,
            "config": config_to_dict(resolve_config({"scenario": name})),
        }
        for name, preset in PRESETS.items()
    ]


@app.post("/api/v1/simulate")
def simulate(request: SimulationRequest) -> dict[str, Any]:
    config = _resolve(request)
    return simulation_to_dict(run_simulation(config))


@app.post("/api/v1/experiments")
def experiments(request: ExperimentRequest) -> dict[str, Any]:
    config = _resolve(request)
    return experiment_to_dict(config, run_experiment(config, request.runs))
