from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.actuator import Actuator
from app.schemas.actuator import ActuatorCreate, ActuatorRead, ActuatorUpdate

router = APIRouter(prefix="/actuators", tags=["actuators"])


@router.post("", response_model=ActuatorRead, status_code=status.HTTP_201_CREATED)
def create_actuator(payload: ActuatorCreate, db: Session = Depends(get_db)) -> Actuator:
    actuator = Actuator(**payload.model_dump())
    db.add(actuator)
    db.commit()
    db.refresh(actuator)
    return actuator


@router.get("", response_model=list[ActuatorRead])
def list_actuators(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[Actuator]:
    stmt = select(Actuator).order_by(Actuator.created_at.desc()).offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


@router.get("/{actuator_id}", response_model=ActuatorRead)
def get_actuator(actuator_id: str, db: Session = Depends(get_db)) -> Actuator:
    actuator = db.get(Actuator, actuator_id)
    if actuator is None:
        raise HTTPException(status_code=404, detail="Actuator not found")
    return actuator


@router.patch("/{actuator_id}", response_model=ActuatorRead)
def update_actuator(
    actuator_id: str,
    payload: ActuatorUpdate,
    db: Session = Depends(get_db),
) -> Actuator:
    actuator = db.get(Actuator, actuator_id)
    if actuator is None:
        raise HTTPException(status_code=404, detail="Actuator not found")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(actuator, key, value)

    db.add(actuator)
    db.commit()
    db.refresh(actuator)
    return actuator


@router.delete("/{actuator_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_actuator(actuator_id: str, db: Session = Depends(get_db)) -> None:
    actuator = db.get(Actuator, actuator_id)
    if actuator is None:
        raise HTTPException(status_code=404, detail="Actuator not found")

    db.delete(actuator)
    db.commit()