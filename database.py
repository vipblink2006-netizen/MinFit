from __future__ import annotations

import json
import os
import re
import subprocess
import sqlite3
import platform
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    import pyodbc
except ImportError:  # macOS local fallback
    pyodbc = None

DATABASE_ERRORS: tuple[type[BaseException], ...] = (ValueError, ConnectionError, sqlite3.Error)
if pyodbc is not None:
    DATABASE_ERRORS += (pyodbc.Error,)

from project_engine import AMENITY_LABELS, PERSONA_WEIGHTS, Project

BASE_DIR = Path(__file__).resolve().parent
PROJECTS_JSON = BASE_DIR / "data" / "projects.json"
DEFAULT_SERVER = r".\MINH"
DEFAULT_DATABASE = "MinFitLocal"
DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"
SQLITE_PATH = BASE_DIR / "data" / "minfit.sqlite3"


class _SQLiteConnection(sqlite3.Connection):
    """Make ``with connect()`` close SQLite connections like pyodbc ones."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


@dataclass(frozen=True)
class DatabaseStatus:
    server: str
    database: str
    project_count: int
    persona_count: int


def settings() -> tuple[str, str, str]:
    server = os.getenv("MINFIT_SQL_SERVER", "sqlite" if platform.system() != "Windows" else DEFAULT_SERVER).strip()
    database = os.getenv("MINFIT_SQL_DATABASE", DEFAULT_DATABASE).strip()
    driver = os.getenv("MINFIT_SQL_DRIVER", DEFAULT_DRIVER).strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", database):
        raise ValueError("Tên database không hợp lệ.")
    if server.lower() == "sqlite":
        return server, database, driver
    local_hosts = (".", "(local)", "localhost", "127.0.0.1")
    if not server.lower().startswith(local_hosts):
        raise ValueError("MinFit chỉ cho phép kết nối SQL Server local.")
    return server, database, driver



def _assert_sql_service_running(server: str) -> None:
    normalized = server.strip().lower()
    if "\\" in normalized:
        instance = normalized.split("\\", 1)[1]
        service_name = "MSSQL$" + instance.upper()
    else:
        service_name = "MSSQLSERVER"
    try:
        result = subprocess.run(
            ["sc.exe", "query", service_name],
            capture_output=True,
            text=True,
            timeout=2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ConnectionError(f"Không kiểm tra được SQL Server service {service_name}.") from error
    if result.returncode != 0 or "RUNNING" not in result.stdout.upper():
        raise ConnectionError(f"SQL Server service {service_name} chưa chạy hoặc không tồn tại.")


def connection_string(database: str | None = None) -> str:
    server, configured_database, driver = settings()
    target_database = database or configured_database
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={target_database};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
        "Encrypt=no;"
        "Connection Timeout=5;"
    )


def connect(database: str | None = None, autocommit: bool = False) -> Any:
    server, _, _ = settings()
    if server.lower() == "sqlite":
        sqlite_path = Path(os.getenv("MINFIT_SQLITE_PATH", str(SQLITE_PATH))).expanduser()
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            sqlite_path,
            isolation_level=None if autocommit else "",
            factory=_SQLiteConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    if pyodbc is None:
        raise ConnectionError("Thiếu pyodbc hoặc ODBC Driver để kết nối SQL Server. Hãy dùng SQLite trên macOS.")
    _assert_sql_service_running(server)
    return pyodbc.connect(connection_string(database), autocommit=autocommit, timeout=3)


def ensure_database() -> DatabaseStatus:
    server, database_name, _ = settings()
    if server.lower() == "sqlite":
        return _ensure_sqlite_database(database_name)
    with connect("master", autocommit=True) as master:
        master.execute(f"IF DB_ID(N'{database_name}') IS NULL CREATE DATABASE [{database_name}]")

    schema_sql = """
    IF OBJECT_ID(N'dbo.Projects', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.Projects (
            id NVARCHAR(50) NOT NULL PRIMARY KEY,
            name NVARCHAR(200) NOT NULL,
            area NVARCHAR(100) NOT NULL,
            price_min_vnd DECIMAL(19, 2) NOT NULL,
            area_m2 DECIMAL(10, 2) NOT NULL,
            lat DECIMAL(10, 7) NOT NULL,
            lng DECIMAL(10, 7) NOT NULL,
            management_fee_per_m2 DECIMAL(19, 2) NOT NULL,
            bedrooms NVARCHAR(30) NOT NULL,
            is_active BIT NOT NULL CONSTRAINT DF_Projects_IsActive DEFAULT 1,
            updated_at DATETIME2 NOT NULL CONSTRAINT DF_Projects_UpdatedAt DEFAULT SYSUTCDATETIME()
        );
    END;

    IF OBJECT_ID(N'dbo.Amenities', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.Amenities (
            code NVARCHAR(30) NOT NULL PRIMARY KEY,
            label NVARCHAR(100) NOT NULL
        );
    END;

    IF OBJECT_ID(N'dbo.ProjectAmenities', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.ProjectAmenities (
            project_id NVARCHAR(50) NOT NULL,
            amenity_code NVARCHAR(30) NOT NULL,
            CONSTRAINT PK_ProjectAmenities PRIMARY KEY (project_id, amenity_code),
            CONSTRAINT FK_ProjectAmenities_Project FOREIGN KEY (project_id) REFERENCES dbo.Projects(id) ON DELETE CASCADE,
            CONSTRAINT FK_ProjectAmenities_Amenity FOREIGN KEY (amenity_code) REFERENCES dbo.Amenities(code)
        );
    END;

    IF OBJECT_ID(N'dbo.PersonaWeights', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.PersonaWeights (
            persona_code NVARCHAR(40) NOT NULL PRIMARY KEY,
            price_weight DECIMAL(6, 4) NOT NULL,
            distance_weight DECIMAL(6, 4) NOT NULL,
            amenity_weight DECIMAL(6, 4) NOT NULL,
            CONSTRAINT CK_PersonaWeights_Total CHECK (price_weight + distance_weight + amenity_weight = 1)
        );
    END;
    """

    raw_projects = json.loads(PROJECTS_JSON.read_text(encoding="utf-8"))
    with connect() as connection:
        cursor = connection.cursor()
        cursor.execute(schema_sql)

        for code, label in AMENITY_LABELS.items():
            cursor.execute(
                """
                UPDATE dbo.Amenities SET label = ? WHERE code = ?;
                IF @@ROWCOUNT = 0 INSERT INTO dbo.Amenities(code, label) VALUES (?, ?);
                """,
                label,
                code,
                code,
                label,
            )

        for item in raw_projects:
            cursor.execute(
                """
                UPDATE dbo.Projects
                SET name=?, area=?, price_min_vnd=?, area_m2=?, lat=?, lng=?, management_fee_per_m2=?, bedrooms=?, is_active=1, updated_at=SYSUTCDATETIME()
                WHERE id=?;
                IF @@ROWCOUNT = 0
                    INSERT INTO dbo.Projects(id, name, area, price_min_vnd, area_m2, lat, lng, management_fee_per_m2, bedrooms, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                """,
                item["name"], item["area"], item["price_min_vnd"], item["area_m2"], item["lat"], item["lng"], item["management_fee_per_m2"], item["bedrooms"], item["id"],
                item["id"], item["name"], item["area"], item["price_min_vnd"], item["area_m2"], item["lat"], item["lng"], item["management_fee_per_m2"], item["bedrooms"],
            )
            cursor.execute("DELETE FROM dbo.ProjectAmenities WHERE project_id = ?", item["id"])
            for amenity in item["amenities"]:
                cursor.execute("INSERT INTO dbo.ProjectAmenities(project_id, amenity_code) VALUES (?, ?)", item["id"], amenity)

        for persona_code, weights in PERSONA_WEIGHTS.items():
            cursor.execute(
                """
                UPDATE dbo.PersonaWeights SET price_weight=?, distance_weight=?, amenity_weight=? WHERE persona_code=?;
                IF @@ROWCOUNT = 0
                    INSERT INTO dbo.PersonaWeights(persona_code, price_weight, distance_weight, amenity_weight) VALUES (?, ?, ?, ?);
                """,
                weights["price"], weights["distance"], weights["amenities"], persona_code,
                persona_code, weights["price"], weights["distance"], weights["amenities"],
            )
        connection.commit()
    return database_status()


def _sqlite_status(database_name: str) -> DatabaseStatus:
    with connect() as connection:
        project_count = connection.execute("SELECT COUNT(*) FROM Projects WHERE is_active=1").fetchone()[0]
        persona_count = connection.execute("SELECT COUNT(*) FROM PersonaWeights").fetchone()[0]
    return DatabaseStatus(server="sqlite", database=database_name, project_count=int(project_count), persona_count=int(persona_count))


def _sqlite_ready(database_name: str) -> None:
    """Create and seed SQLite automatically when the app is launched directly."""
    sqlite_path = Path(os.getenv("MINFIT_SQLITE_PATH", str(SQLITE_PATH))).expanduser()
    if not sqlite_path.exists():
        _ensure_sqlite_database(database_name)
        return
    with connect() as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='Projects'"
        ).fetchone()
    if table is None:
        _ensure_sqlite_database(database_name)


def _ensure_sqlite_database(database_name: str) -> DatabaseStatus:
    raw_projects = json.loads(PROJECTS_JSON.read_text(encoding="utf-8"))
    with connect() as connection:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS Projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, area TEXT NOT NULL,
          price_min_vnd REAL NOT NULL, area_m2 REAL NOT NULL, lat REAL NOT NULL, lng REAL NOT NULL,
          management_fee_per_m2 REAL NOT NULL, bedrooms TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS Amenities (code TEXT PRIMARY KEY, label TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ProjectAmenities (project_id TEXT NOT NULL, amenity_code TEXT NOT NULL,
          PRIMARY KEY(project_id, amenity_code), FOREIGN KEY(project_id) REFERENCES Projects(id) ON DELETE CASCADE,
          FOREIGN KEY(amenity_code) REFERENCES Amenities(code));
        CREATE TABLE IF NOT EXISTS PersonaWeights (persona_code TEXT PRIMARY KEY, price_weight REAL NOT NULL,
          distance_weight REAL NOT NULL, amenity_weight REAL NOT NULL);
        """)
        for code, label in AMENITY_LABELS.items():
            connection.execute("INSERT OR REPLACE INTO Amenities(code,label) VALUES (?,?)", (code, label))
        for item in raw_projects:
            connection.execute("INSERT OR REPLACE INTO Projects(id,name,area,price_min_vnd,area_m2,lat,lng,management_fee_per_m2,bedrooms,is_active) VALUES (?,?,?,?,?,?,?,?,?,1)",
                (item["id"],item["name"],item["area"],item["price_min_vnd"],item["area_m2"],item["lat"],item["lng"],item["management_fee_per_m2"],item["bedrooms"]))
            connection.execute("DELETE FROM ProjectAmenities WHERE project_id=?", (item["id"],))
            connection.executemany("INSERT INTO ProjectAmenities(project_id,amenity_code) VALUES (?,?)", [(item["id"], a) for a in item["amenities"]])
        for code, weights in PERSONA_WEIGHTS.items():
            connection.execute("INSERT OR REPLACE INTO PersonaWeights VALUES (?,?,?,?)", (code,float(weights["price"]),float(weights["distance"]),float(weights["amenities"])))
        connection.commit()
    return _sqlite_status(database_name)


def load_projects_from_database() -> list[Project]:
    server, _, _ = settings()
    if server.lower() == "sqlite":
        _sqlite_ready(settings()[1])
        query = """
        SELECT p.id, p.name, p.area, p.price_min_vnd, p.area_m2, p.lat, p.lng,
               p.management_fee_per_m2, p.bedrooms, pa.amenity_code
        FROM Projects AS p
        LEFT JOIN ProjectAmenities AS pa ON pa.project_id = p.id
        WHERE p.is_active = 1
        ORDER BY p.id, pa.amenity_code;
        """
        grouped: dict[str, dict] = {}
        with connect() as connection:
            rows = connection.execute(query).fetchall()
        for row in rows:
            item = grouped.setdefault(
                row["id"],
                {
                    "id": row["id"], "name": row["name"], "area": row["area"],
                    "price_min_vnd": Decimal(str(row["price_min_vnd"])), "area_m2": Decimal(str(row["area_m2"])),
                    "lat": float(row["lat"]), "lng": float(row["lng"]),
                    "management_fee_per_m2": Decimal(str(row["management_fee_per_m2"])), "bedrooms": row["bedrooms"],
                    "amenities": [],
                },
            )
            if row["amenity_code"]:
                item["amenities"].append(row["amenity_code"])
        return [Project(**{**item, "amenities": tuple(item["amenities"])}) for item in grouped.values()]

    query = """
    SELECT p.id, p.name, p.area, p.price_min_vnd, p.area_m2, p.lat, p.lng,
           p.management_fee_per_m2, p.bedrooms, pa.amenity_code
    FROM dbo.Projects AS p
    LEFT JOIN dbo.ProjectAmenities AS pa ON pa.project_id = p.id
    WHERE p.is_active = 1
    ORDER BY p.id, pa.amenity_code;
    """
    grouped: dict[str, dict] = {}
    with connect() as connection:
        for row in connection.cursor().execute(query):
            item = grouped.setdefault(
                row.id,
                {
                    "id": row.id, "name": row.name, "area": row.area,
                    "price_min_vnd": Decimal(str(row.price_min_vnd)), "area_m2": Decimal(str(row.area_m2)),
                    "lat": float(row.lat), "lng": float(row.lng),
                    "management_fee_per_m2": Decimal(str(row.management_fee_per_m2)), "bedrooms": row.bedrooms,
                    "amenities": [],
                },
            )
            if row.amenity_code:
                item["amenities"].append(row.amenity_code)
    return [Project(**{**item, "amenities": tuple(item["amenities"])}) for item in grouped.values()]



def load_persona_weights_from_database() -> dict[str, dict[str, Decimal]]:
    server, database_name, _ = settings()
    if server.lower() == "sqlite":
        _sqlite_ready(database_name)
        weights: dict[str, dict[str, Decimal]] = {}
        with connect() as connection:
            rows = connection.execute(
                "SELECT persona_code, price_weight, distance_weight, amenity_weight FROM PersonaWeights"
            ).fetchall()
        for row in rows:
            weights[row["persona_code"]] = {
                "price": Decimal(str(row["price_weight"])),
                "distance": Decimal(str(row["distance_weight"])),
                "amenities": Decimal(str(row["amenity_weight"])),
            }
        return weights

    weights: dict[str, dict[str, Decimal]] = {}
    with connect() as connection:
        rows = connection.cursor().execute(
            "SELECT persona_code, price_weight, distance_weight, amenity_weight FROM dbo.PersonaWeights"
        ).fetchall()
    for row in rows:
        weights[row.persona_code] = {
            "price": Decimal(str(row.price_weight)), "distance": Decimal(str(row.distance_weight)),
            "amenities": Decimal(str(row.amenity_weight)),
        }
    return weights


def database_status() -> DatabaseStatus:
    server, database_name, _ = settings()
    if server.lower() == "sqlite":
        _sqlite_ready(database_name)
        return _sqlite_status(database_name)
    with connect() as connection:
        cursor = connection.cursor()
        project_count = cursor.execute("SELECT COUNT(*) FROM dbo.Projects WHERE is_active=1").fetchval()
        persona_count = cursor.execute("SELECT COUNT(*) FROM dbo.PersonaWeights").fetchval()
    return DatabaseStatus(server=server, database=database_name, project_count=int(project_count), persona_count=int(persona_count))


if __name__ == "__main__":
    status = ensure_database()
    print(f"database={status.database}")
    print(f"server={status.server}")
    print(f"projects={status.project_count}")
    print(f"personas={status.persona_count}")
