from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.release_benchmark import BenchmarkConfig, ReleaseBenchmarkRunner

router = APIRouter(prefix="/release", tags=["release-readiness"])
runner = ReleaseBenchmarkRunner()


@router.post("/benchmark")
def run_release_benchmark(
    payload: BenchmarkConfig | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Run the local release-readiness benchmark and return structured metrics."""

    try:
        result = runner.run(db, payload or BenchmarkConfig())
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=500,
            detail={"message": "Release benchmark failed", "error": str(exc)},
        ) from exc

    return result.to_dict()
