from functools import lru_cache
from pathlib import Path
import os
import sys
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


APPDATA_APP_FOLDER = "rasentinel-desktop"


class Settings(BaseSettings):
    app_name: str = Field(default="RASentinel", alias="RASENTINEL_APP_NAME")
    environment: str = Field(default="development", alias="RASENTINEL_ENV")
    api_prefix: str = Field(default="/api/v1", alias="RASENTINEL_API_PREFIX")

    # Leave this empty by default. When empty, RASentinel stores data in the OS app-data
    # location, not inside the source checkout. This keeps project files clean and makes
    # Electron/dev/backend runs point at the same persistent database.
    database_url: str = Field(default="", alias="RASENTINEL_DATABASE_URL")
    data_dir_override: str = Field(default="", alias="RASENTINEL_DATA_DIR")

    log_level: str = Field(default="INFO", alias="RASENTINEL_LOG_LEVEL")
    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="RASENTINEL_CORS_ORIGINS",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def backend_dir(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def project_root(self) -> Path:
        return self.backend_dir.parent

    @staticmethod
    def _default_app_data_root() -> Path:
        """Return a durable per-user app data location.

        Windows:
            C:\\Users\\<user>\\AppData\\Roaming\\rasentinel-desktop
        macOS:
            ~/Library/Application Support/rasentinel-desktop
        Linux:
            ~/.local/share/rasentinel-desktop
        """
        if sys.platform.startswith("win"):
            roaming = os.environ.get("APPDATA")
            if roaming:
                return Path(roaming) / APPDATA_APP_FOLDER
            return Path.home() / "AppData" / "Roaming" / APPDATA_APP_FOLDER

        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / APPDATA_APP_FOLDER

        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        if xdg_data_home:
            return Path(xdg_data_home) / APPDATA_APP_FOLDER
        return Path.home() / ".local" / "share" / APPDATA_APP_FOLDER

    @property
    def app_data_root(self) -> Path:
        if self.data_dir_override.strip():
            path = Path(self.data_dir_override).expanduser()
            path.mkdir(parents=True, exist_ok=True)
            return path

        path = self._default_app_data_root()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def data_dir(self) -> Path:
        path = self.app_data_root / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def logs_dir(self) -> Path:
        path = self.data_dir / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def reports_dir(self) -> Path:
        path = self.data_dir / "reports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def samples_dir(self) -> Path:
        path = self.data_dir / "samples"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def generated_dir(self) -> Path:
        path = self.data_dir / "generated"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _sqlite_url_from_path(db_path: Path) -> str:
        # SQLAlchemy accepts forward slashes on Windows. This avoids backslash escaping drama,
        # which is how tiny config files become unpaid therapists.
        return f"sqlite:///{db_path.resolve().as_posix()}"

    @property
    def resolved_database_url(self) -> str:
        if not self.database_url.strip():
            db_path = self.data_dir / "rasentinel.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return self._sqlite_url_from_path(db_path)

        if not self.database_url.startswith("sqlite:///"):
            return self.database_url

        raw_path = self.database_url.replace("sqlite:///", "", 1)
        db_path = Path(raw_path).expanduser()

        if not db_path.is_absolute():
            # Relative DB paths are resolved inside the app-data data folder, not the source
            # checkout. This is intentional: the project directory should stay code-only.
            db_path = self.data_dir / db_path

        db_path.parent.mkdir(parents=True, exist_ok=True)
        return self._sqlite_url_from_path(db_path)

    @property
    def cors_origins(self) -> List[str]:
        return [
            origin.strip()
            for origin in self.cors_origins_raw.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
