from fastapi import APIRouter

from app.api.routes import (
    actuators,
    baselines,
    commands,
    diagnoses,
    diagnostics,
    exports,
    features,
    health,
    imports,
    live_telemetry,
    release,
    reports,
    sessions,
    simulator,
    telemetry,
    telemetry_gateway,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(actuators.router)
api_router.include_router(sessions.router)
api_router.include_router(telemetry.router)
api_router.include_router(commands.router)
api_router.include_router(diagnoses.router)
api_router.include_router(imports.router)
api_router.include_router(live_telemetry.router)
api_router.include_router(simulator.router)
api_router.include_router(exports.router)
api_router.include_router(features.router)
api_router.include_router(baselines.router)
api_router.include_router(diagnostics.router)
api_router.include_router(reports.router)
api_router.include_router(telemetry_gateway.router)
api_router.include_router(release.router)
