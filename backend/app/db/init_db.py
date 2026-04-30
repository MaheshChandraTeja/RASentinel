from app.db.base import Base
from app.db.session import engine

# Import models so SQLAlchemy registers tables before create_all.
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


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
