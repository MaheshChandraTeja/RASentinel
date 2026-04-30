from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.features import FeatureExtractionRequest, FeatureExtractionResponse, FeatureSetRead
from app.services.feature_store import FeatureStore, FeatureStoreError

router = APIRouter(prefix="/sessions/{session_id}/features", tags=["features"])
feature_store = FeatureStore()


@router.post("/extract", response_model=FeatureExtractionResponse, status_code=status.HTTP_201_CREATED)
def extract_features(
    session_id: str,
    payload: FeatureExtractionRequest,
    db: Session = Depends(get_db),
) -> FeatureExtractionResponse:
    try:
        features, feature_set = feature_store.extract_for_session(
            db,
            session_id=session_id,
            smoothing_window=payload.smoothing_window,
            persist=payload.persist,
        )
    except FeatureStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FeatureExtractionResponse(
        session_id=session_id,
        actuator_id=feature_set.actuator_id if feature_set else "",
        persisted=feature_set is not None,
        feature_set_id=feature_set.id if feature_set else None,
        features=features,
    )


@router.get("", response_model=list[FeatureSetRead])
def list_feature_sets(
    session_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return feature_store.list_for_session(db, session_id=session_id, limit=limit)


@router.get("/latest", response_model=FeatureSetRead)
def get_latest_feature_set(session_id: str, db: Session = Depends(get_db)):
    feature_set = feature_store.latest_for_session(db, session_id=session_id)
    if feature_set is None:
        raise HTTPException(status_code=404, detail="Feature set not found")
    return feature_set
