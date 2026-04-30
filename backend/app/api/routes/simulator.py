from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.imports import ImportSourceFormat
from app.schemas.simulator import (
    SimulationFaultProfileInfo,
    SimulationGenerateRequest,
    SimulationGenerateResponse,
    SimulationImportRequest,
    SimulationImportResponse,
)
from app.services.simulator import FAULT_PROFILE_INFO, simulator
from app.services.telemetry_importer import TelemetryImportError, telemetry_importer

router = APIRouter(prefix="/simulator", tags=["simulator"])


@router.get("/fault-profiles", response_model=list[SimulationFaultProfileInfo])
def list_fault_profiles() -> list[SimulationFaultProfileInfo]:
    return FAULT_PROFILE_INFO


@router.post("/generate", response_model=SimulationGenerateResponse)
def generate_telemetry(payload: SimulationGenerateRequest) -> SimulationGenerateResponse:
    return simulator.generate(payload.config)


@router.post(
    "/generate/import",
    response_model=SimulationImportResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_and_import_telemetry(
    payload: SimulationImportRequest,
    db: Session = Depends(get_db),
) -> SimulationImportResponse:
    generated = simulator.generate(payload.config)
    summary = simulator.summarize(generated.samples)

    try:
        import_result = telemetry_importer.persist_samples(
            db,
            actuator_id=payload.actuator_id,
            session_name=payload.session_name,
            source_format=ImportSourceFormat.SYNTHETIC,
            samples=generated.samples,
            duplicate_strategy=payload.duplicate_strategy,
            source_name="rasentinel-simulator",
            source="synthetic",
            notes=payload.notes,
            tags={
                **payload.tags,
                "simulator_fault_profile": payload.config.fault_profile.value,
                "simulator_seed": payload.config.seed,
            },
            metadata={
                "simulation": generated.metadata.model_dump(mode="json"),
                "summary": summary,
            },
        )
    except TelemetryImportError as exc:
        raise HTTPException(
            status_code=409 if "already exists" in exc.message else 422,
            detail={
                "message": exc.message,
                "errors": [issue.model_dump() for issue in exc.issues],
            },
        ) from exc

    return SimulationImportResponse(
        **import_result.model_dump(),
        metadata=generated.metadata,
    )


@router.post("/export/csv")
def export_generated_csv(payload: SimulationGenerateRequest) -> Response:
    generated = simulator.generate(payload.config)
    content = simulator.export_csv(generated)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=rasentinel-simulated-telemetry.csv"},
    )


@router.post("/export/json")
def export_generated_json(payload: SimulationGenerateRequest) -> Response:
    generated = simulator.generate(payload.config)
    content = simulator.export_json(generated)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=rasentinel-simulated-telemetry.json"},
    )
