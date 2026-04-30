import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app

# Import all models so SQLAlchemy registers every table for tests.
from app.models.actuator import Actuator  # noqa: F401
from app.models.baseline import HealthyBaseline  # noqa: F401
from app.models.command import CommandSignal  # noqa: F401
from app.models.diagnosis import DiagnosisResult  # noqa: F401
from app.models.feature_set import FeatureSet  # noqa: F401
from app.models.import_job import ImportJob  # noqa: F401
from app.models.live_telemetry import LiveTelemetrySession  # noqa: F401
from app.models.report_record import ReportRecord  # noqa: F401
from app.models.session_run import SessionRun  # noqa: F401
from app.models.telemetry import TelemetrySample  # noqa: F401


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
