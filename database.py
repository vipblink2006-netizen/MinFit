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
    if platform.system() != "Windows":
        return  # On macOS/Linux, Windows sc.exe service manager does not exist
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
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError) as error:
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
            developer NVARCHAR(200) NULL,
            price_min_vnd DECIMAL(19, 2) NOT NULL,
            price_avg_mil_m2 FLOAT NULL,
            price_min_mil_m2 FLOAT NULL,
            price_max_mil_m2 FLOAT NULL,
            area_m2 DECIMAL(10, 2) NOT NULL,
            area_min_m2 FLOAT NULL,
            area_max_m2 FLOAT NULL,
            layout_types NVARCHAR(100) NULL,
            lat DECIMAL(10, 7) NOT NULL,
            lng DECIMAL(10, 7) NOT NULL,
            management_fee_per_m2 DECIMAL(19, 2) NOT NULL,
            bedrooms NVARCHAR(30) NOT NULL,
            raw_amenities NVARCHAR(500) NULL,
            handover_status NVARCHAR(100) NULL,
            handover_year INT NULL,
            is_handed_over BIT NOT NULL DEFAULT 0,
            payment_policy NVARCHAR(500) NULL,
            grace_period_months INT NOT NULL DEFAULT 0,
            inventory_link NVARCHAR(500) NULL,
            risk_note NVARCHAR(500) NULL,
            is_global BIT NOT NULL DEFAULT 1,
            created_by_role NVARCHAR(30) NOT NULL DEFAULT 'admin',
            broker_id NVARCHAR(50) NULL,
            approval_status NVARCHAR(30) NOT NULL DEFAULT 'approved',
            crawl_url NVARCHAR(500) NULL,
            crawl_frequency NVARCHAR(30) NOT NULL DEFAULT 'daily',
            links_json NVARCHAR(MAX) NULL,
            units_json NVARCHAR(MAX) NULL,
            raw_source_text NVARCHAR(MAX) NULL,
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

    IF OBJECT_ID(N'dbo.BrokerSelectedProjects', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.BrokerSelectedProjects (
            broker_id NVARCHAR(50) NOT NULL,
            project_id NVARCHAR(50) NOT NULL,
            CONSTRAINT PK_BrokerSelected PRIMARY KEY (broker_id, project_id)
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
                SET name=?, area=?, developer=?, price_min_vnd=?, price_avg_mil_m2=?, price_min_mil_m2=?, price_max_mil_m2=?,
                    area_m2=?, area_min_m2=?, area_max_m2=?, layout_types=?, lat=?, lng=?, management_fee_per_m2=?, bedrooms=?,
                    raw_amenities=?, handover_status=?, handover_year=?, is_handed_over=?, payment_policy=?, grace_period_months=?,
                    inventory_link=?, risk_note=?, is_global=1, created_by_role='admin', approval_status='approved',
                    crawl_url=?, crawl_frequency=?, links_json=?, units_json=?, is_active=1, updated_at=SYSUTCDATETIME()
                WHERE id=?;
                IF @@ROWCOUNT = 0
                    INSERT INTO dbo.Projects(id, name, area, developer, price_min_vnd, price_avg_mil_m2, price_min_mil_m2, price_max_mil_m2,
                                             area_m2, area_min_m2, area_max_m2, layout_types, lat, lng, management_fee_per_m2, bedrooms,
                                             raw_amenities, handover_status, handover_year, is_handed_over, payment_policy, grace_period_months,
                                             inventory_link, risk_note, is_global, created_by_role, approval_status, crawl_url, crawl_frequency,
                                             links_json, units_json, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'admin', 'approved', ?, ?, ?, ?, 1);
                """,
                item["name"], item["area"], item.get("developer", ""), item["price_min_vnd"], item.get("price_avg_mil_m2", 0), item.get("price_min_mil_m2", 0), item.get("price_max_mil_m2", 0),
                item["area_m2"], item.get("area_min_m2", 0), item.get("area_max_m2", 0), item.get("layout_types", ""), item["lat"], item["lng"], item["management_fee_per_m2"], item["bedrooms"],
                item.get("raw_amenities", ""), item.get("handover_status", ""), item.get("handover_year", 0), 1 if item.get("is_handed_over") else 0, item.get("payment_policy", ""), item.get("grace_period_months", 0),
                item.get("inventory_link", ""), item.get("risk_note", ""), item.get("crawl_url", ""), item.get("crawl_frequency", "daily"), json.dumps(item.get("links", {})), json.dumps(item.get("units", [])), item["id"],
                item["id"], item["name"], item["area"], item.get("developer", ""), item["price_min_vnd"], item.get("price_avg_mil_m2", 0), item.get("price_min_mil_m2", 0), item.get("price_max_mil_m2", 0),
                item["area_m2"], item.get("area_min_m2", 0), item.get("area_max_m2", 0), item.get("layout_types", ""), item["lat"], item["lng"], item["management_fee_per_m2"], item["bedrooms"],
                item.get("raw_amenities", ""), item.get("handover_status", ""), item.get("handover_year", 0), 1 if item.get("is_handed_over") else 0, item.get("payment_policy", ""), item.get("grace_period_months", 0),
                item.get("inventory_link", ""), item.get("risk_note", ""), item.get("crawl_url", ""), item.get("crawl_frequency", "daily"), json.dumps(item.get("links", {})), json.dumps(item.get("units", [])),
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
        DROP TABLE IF EXISTS ProjectAmenities;
        DROP TABLE IF EXISTS Projects;
        DROP TABLE IF EXISTS Amenities;
        DROP TABLE IF EXISTS PersonaWeights;
        DROP TABLE IF EXISTS BrokerSelectedProjects;
        DROP TABLE IF EXISTS Users;

        CREATE TABLE Projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            area TEXT NOT NULL,
            developer TEXT DEFAULT '',
            price_min_vnd REAL NOT NULL,
            price_avg_mil_m2 REAL DEFAULT 0,
            price_min_mil_m2 REAL DEFAULT 0,
            price_max_mil_m2 REAL DEFAULT 0,
            area_m2 REAL NOT NULL,
            area_min_m2 REAL DEFAULT 0,
            area_max_m2 REAL DEFAULT 0,
            layout_types TEXT DEFAULT '',
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            management_fee_per_m2 REAL NOT NULL,
            bedrooms TEXT NOT NULL,
            raw_amenities TEXT DEFAULT '',
            handover_status TEXT DEFAULT '',
            handover_year INTEGER DEFAULT 0,
            is_handed_over INTEGER DEFAULT 0,
            payment_policy TEXT DEFAULT '',
            grace_period_months INTEGER DEFAULT 0,
            inventory_link TEXT DEFAULT '',
            risk_note TEXT DEFAULT '',
            is_global INTEGER DEFAULT 1,
            created_by_role TEXT DEFAULT 'admin',
            broker_id TEXT DEFAULT NULL,
            approval_status TEXT DEFAULT 'approved',
            crawl_url TEXT DEFAULT '',
            crawl_frequency TEXT DEFAULT 'daily',
            links_json TEXT DEFAULT '{}',
            units_json TEXT DEFAULT '[]',
            raw_source_text TEXT DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE Amenities (
            code TEXT PRIMARY KEY,
            label TEXT NOT NULL
        );

        CREATE TABLE ProjectAmenities (
            project_id TEXT NOT NULL,
            amenity_code TEXT NOT NULL,
            PRIMARY KEY(project_id, amenity_code),
            FOREIGN KEY(project_id) REFERENCES Projects(id) ON DELETE CASCADE,
            FOREIGN KEY(amenity_code) REFERENCES Amenities(code)
        );

        CREATE TABLE BrokerSelectedProjects (
            broker_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            PRIMARY KEY (broker_id, project_id),
            FOREIGN KEY (project_id) REFERENCES Projects(id) ON DELETE CASCADE
        );

        CREATE TABLE Users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            role TEXT NOT NULL DEFAULT 'broker',
            agency TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            clients_count INTEGER DEFAULT 0,
            projects_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_active TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE PersonaWeights (
            persona_code TEXT PRIMARY KEY,
            price_weight REAL NOT NULL,
            distance_weight REAL NOT NULL,
            amenity_weight REAL NOT NULL
        );
        """)

        for code, label in AMENITY_LABELS.items():
            connection.execute("INSERT OR REPLACE INTO Amenities(code,label) VALUES (?,?)", (code, label))

        for item in raw_projects:
            connection.execute(
                """
                INSERT INTO Projects(
                    id, name, area, developer, price_min_vnd, price_avg_mil_m2, price_min_mil_m2, price_max_mil_m2,
                    area_m2, area_min_m2, area_max_m2, layout_types, lat, lng, management_fee_per_m2, bedrooms,
                    raw_amenities, handover_status, handover_year, is_handed_over, payment_policy, grace_period_months,
                    inventory_link, risk_note, is_global, created_by_role, approval_status, crawl_url, crawl_frequency,
                    links_json, units_json, is_active
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                """,
                (
                    item["id"], item["name"], item["area"], item.get("developer", ""),
                    item["price_min_vnd"], item.get("price_avg_mil_m2", 0), item.get("price_min_mil_m2", 0), item.get("price_max_mil_m2", 0),
                    item["area_m2"], item.get("area_min_m2", 0), item.get("area_max_m2", 0), item.get("layout_types", ""),
                    item["lat"], item["lng"], item["management_fee_per_m2"], item["bedrooms"],
                    item.get("raw_amenities", ""), item.get("handover_status", ""), item.get("handover_year", 0), 1 if item.get("is_handed_over") else 0,
                    item.get("payment_policy", ""), item.get("grace_period_months", 0), item.get("inventory_link", ""), item.get("risk_note", ""),
                    item.get("is_global", 1), item.get("created_by_role", "admin"), item.get("approval_status", "approved"),
                    item.get("crawl_url", ""), item.get("crawl_frequency", "daily"), json.dumps(item.get("links", {})), json.dumps(item.get("units", []))
                ),
            )
            for a in item["amenities"]:
                connection.execute("INSERT OR REPLACE INTO ProjectAmenities(project_id, amenity_code) VALUES (?,?)", (item["id"], a))

        for code, weights in PERSONA_WEIGHTS.items():
            connection.execute(
                "INSERT OR REPLACE INTO PersonaWeights VALUES (?,?,?,?)",
                (code, float(weights["price"]), float(weights["distance"]), float(weights["amenities"])),
            )
        connection.commit()
    return _sqlite_status(database_name)


def load_projects_from_database(include_inactive: bool = False, broker_id: str | None = None) -> list[Project]:
    server, database_name, _ = settings()
    if server.lower() == "sqlite":
        _sqlite_ready(database_name)
        condition = "WHERE 1=1"
        params: list[Any] = []
        if not include_inactive:
            condition += " AND p.is_active = 1"
        if broker_id:
            condition += " AND (p.is_global = 1 OR p.broker_id = ?)"
            params.append(broker_id)

        query = f"""
        SELECT p.*, pa.amenity_code
        FROM Projects AS p
        LEFT JOIN ProjectAmenities AS pa ON pa.project_id = p.id
        {condition}
        ORDER BY p.is_global DESC, p.created_at DESC, p.id, pa.amenity_code;
        """
        grouped: dict[str, dict] = {}
        with connect() as connection:
            rows = connection.execute(query, params).fetchall()
        for row in rows:
            r = dict(row)
            amenity = r.pop("amenity_code", None)
            item = grouped.setdefault(
                r["id"],
                {
                    "id": r["id"],
                    "name": r["name"],
                    "area": r["area"],
                    "developer": r.get("developer", ""),
                    "price_min_vnd": Decimal(str(r["price_min_vnd"])),
                    "price_avg_mil_m2": float(r.get("price_avg_mil_m2") or 0),
                    "price_min_mil_m2": float(r.get("price_min_mil_m2") or 0),
                    "price_max_mil_m2": float(r.get("price_max_mil_m2") or 0),
                    "area_m2": Decimal(str(r["area_m2"])),
                    "area_min_m2": float(r.get("area_min_m2") or 0),
                    "area_max_m2": float(r.get("area_max_m2") or 0),
                    "layout_types": r.get("layout_types", ""),
                    "lat": float(r["lat"]),
                    "lng": float(r["lng"]),
                    "management_fee_per_m2": Decimal(str(r["management_fee_per_m2"])),
                    "bedrooms": r["bedrooms"],
                    "raw_amenities": r.get("raw_amenities", ""),
                    "handover_status": r.get("handover_status", ""),
                    "handover_year": int(r.get("handover_year") or 0),
                    "is_handed_over": bool(r.get("is_handed_over", 0)),
                    "payment_policy": r.get("payment_policy", ""),
                    "grace_period_months": int(r.get("grace_period_months") or 0),
                    "inventory_link": r.get("inventory_link", ""),
                    "updated_at": str(r.get("updated_at", "")),
                    "risk_note": r.get("risk_note", ""),
                    "is_global": int(r.get("is_global") or 1),
                    "created_by_role": r.get("created_by_role", "admin"),
                    "broker_id": str(r.get("broker_id") or ""),
                    "approval_status": r.get("approval_status", "approved"),
                    "crawl_url": r.get("crawl_url", ""),
                    "crawl_frequency": r.get("crawl_frequency", "daily"),
                    "links_json": r.get("links_json", "{}"),
                    "units_json": r.get("units_json", "[]"),
                    "raw_source_text": r.get("raw_source_text", ""),
                    "amenities": [],
                },
            )
            if amenity:
                item["amenities"].append(amenity)
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


def save_project_to_db(data: dict[str, Any]) -> str:
    """Save or update project in SQLite database."""
    pid = str(data.get("id") or f"prj_{int(Decimal(str(data.get('price_min_vnd', 1000000000))) % 1000000)}_{abs(hash(data.get('name', '')))%10000}").lower().replace(" ", "_")
    name = str(data.get("name", "")).strip()
    area = str(data.get("area", "Nam Từ Liêm")).strip()
    developer = str(data.get("developer", "")).strip()
    price_min_vnd = float(data.get("price_min_vnd", 4000000000))
    price_avg_mil_m2 = float(data.get("price_avg_mil_m2", 0))
    price_min_mil_m2 = float(data.get("price_min_mil_m2", 0))
    price_max_mil_m2 = float(data.get("price_max_mil_m2", 0))
    area_m2 = float(data.get("area_m2", 70.0))
    area_min_m2 = float(data.get("area_min_m2", 0))
    area_max_m2 = float(data.get("area_max_m2", 0))
    layout_types = str(data.get("layout_types", "2PN")).strip()
    lat = float(data.get("lat", 21.0135))
    lng = float(data.get("lng", 105.7678))
    mgmt_fee = float(data.get("management_fee_per_m2", 15000.0))
    bedrooms = str(data.get("bedrooms", "2PN")).strip()
    raw_amenities = str(data.get("raw_amenities", "")).strip()
    handover_status = str(data.get("handover_status", "Đang mở bán")).strip()
    handover_year = int(data.get("handover_year", 2026))
    is_handed_over = 1 if data.get("is_handed_over") else 0
    payment_policy = str(data.get("payment_policy", "")).strip()
    grace_period_months = int(data.get("grace_period_months", 0))
    inventory_link = str(data.get("inventory_link", "")).strip()
    risk_note = str(data.get("risk_note", "")).strip()
    is_global = int(data.get("is_global", 1 if data.get("created_by_role") == "admin" else 0))
    created_by_role = str(data.get("created_by_role", "broker")).strip()
    broker_id = str(data.get("broker_id", "")).strip()
    approval_status = str(data.get("approval_status", "approved")).strip()
    crawl_url = str(data.get("crawl_url", "")).strip()
    crawl_frequency = str(data.get("crawl_frequency", "daily")).strip()
    links_json = json.dumps(data.get("links", {})) if isinstance(data.get("links"), dict) else str(data.get("links_json", "{}"))
    units_json = json.dumps(data.get("units", [])) if isinstance(data.get("units"), list) else str(data.get("units_json", "[]"))
    raw_source_text = str(data.get("raw_source_text", "")).strip()
    is_active = 1 if data.get("is_active", True) else 0

    with connect() as connection:
        connection.execute(
            """
            INSERT INTO Projects(
                id, name, area, developer, price_min_vnd, price_avg_mil_m2, price_min_mil_m2, price_max_mil_m2,
                area_m2, area_min_m2, area_max_m2, layout_types, lat, lng, management_fee_per_m2, bedrooms,
                raw_amenities, handover_status, handover_year, is_handed_over, payment_policy, grace_period_months,
                inventory_link, risk_note, is_global, created_by_role, broker_id, approval_status, crawl_url,
                crawl_frequency, links_json, units_json, raw_source_text, is_active
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, area=excluded.area, developer=excluded.developer, price_min_vnd=excluded.price_min_vnd,
                price_avg_mil_m2=excluded.price_avg_mil_m2, price_min_mil_m2=excluded.price_min_mil_m2, price_max_mil_m2=excluded.price_max_mil_m2,
                area_m2=excluded.area_m2, area_min_m2=excluded.area_min_m2, area_max_m2=excluded.area_max_m2, layout_types=excluded.layout_types,
                lat=excluded.lat, lng=excluded.lng, management_fee_per_m2=excluded.management_fee_per_m2, bedrooms=excluded.bedrooms,
                raw_amenities=excluded.raw_amenities, handover_status=excluded.handover_status, handover_year=excluded.handover_year,
                is_handed_over=excluded.is_handed_over, payment_policy=excluded.payment_policy, grace_period_months=excluded.grace_period_months,
                inventory_link=excluded.inventory_link, risk_note=excluded.risk_note, is_global=excluded.is_global,
                approval_status=excluded.approval_status, crawl_url=excluded.crawl_url, crawl_frequency=excluded.crawl_frequency,
                links_json=excluded.links_json, units_json=excluded.units_json, raw_source_text=excluded.raw_source_text,
                is_active=excluded.is_active, updated_at=CURRENT_TIMESTAMP
            """,
            (
                pid, name, area, developer, price_min_vnd, price_avg_mil_m2, price_min_mil_m2, price_max_mil_m2,
                area_m2, area_min_m2, area_max_m2, layout_types, lat, lng, mgmt_fee, bedrooms,
                raw_amenities, handover_status, handover_year, is_handed_over, payment_policy, grace_period_months,
                inventory_link, risk_note, is_global, created_by_role, broker_id, approval_status, crawl_url,
                crawl_frequency, links_json, units_json, raw_source_text, is_active
            )
        )
        amenities = data.get("amenities", ["park", "parking"])
        connection.execute("DELETE FROM ProjectAmenities WHERE project_id=?", (pid,))
        for am in amenities:
            connection.execute("INSERT OR REPLACE INTO ProjectAmenities(project_id, amenity_code) VALUES (?,?)", (pid, am))
        connection.commit()
    return pid


def delete_project_from_db(project_id: str) -> bool:
    with connect() as connection:
        res = connection.execute("DELETE FROM Projects WHERE id=?", (project_id,))
        connection.commit()
        return res.rowcount > 0


def toggle_project_status_in_db(project_id: str, is_active: bool) -> bool:
    with connect() as connection:
        res = connection.execute("UPDATE Projects SET is_active=? WHERE id=?", (1 if is_active else 0, project_id))
        connection.commit()
        return res.rowcount > 0


def save_broker_selection_to_db(broker_id: str, project_ids: list[str]) -> None:
    with connect() as connection:
        connection.execute("DELETE FROM BrokerSelectedProjects WHERE broker_id=?", (broker_id,))
        for pid in project_ids:
            connection.execute("INSERT OR IGNORE INTO BrokerSelectedProjects(broker_id, project_id) VALUES (?,?)", (broker_id, pid))
        connection.commit()


def load_broker_selection_from_db(broker_id: str) -> list[str]:
    with connect() as connection:
        rows = connection.execute("SELECT project_id FROM BrokerSelectedProjects WHERE broker_id=?", (broker_id,)).fetchall()
        return [r["project_id"] for r in rows]


DEFAULT_USERS = [
    {
        "id": "admin_01",
        "name": "Chính Chủ (Super Admin)",
        "email": "admin@minfit.vn",
        "phone": "0988.888.888",
        "role": "admin",
        "agency": "MinFit PropTech Headquarter",
        "status": "active",
        "clients_count": 24,
        "projects_count": 27,
        "created_at": "2026-08-01 08:00:00",
        "last_active": "Vừa xong",
    },
    {
        "id": "broker_01",
        "name": "Minh Anh",
        "email": "moigioi@minfit.vn",
        "phone": "0912.345.678",
        "role": "broker",
        "agency": "Đất Xanh Miền Bắc - CN Cầu Giấy",
        "status": "active",
        "clients_count": 8,
        "projects_count": 12,
        "created_at": "2026-08-10 09:30:00",
        "last_active": "10 phút trước",
    },
    {
        "id": "broker_02",
        "name": "Hoàng Nam",
        "email": "nam.vinhomes@gmail.com",
        "phone": "0904.567.890",
        "role": "broker",
        "agency": "Vinhomes Capital Center",
        "status": "active",
        "clients_count": 15,
        "projects_count": 18,
        "created_at": "2026-08-12 14:15:00",
        "last_active": "25 phút trước",
    },
    {
        "id": "broker_03",
        "name": "Thu Trang",
        "email": "trang.cenland@gmail.com",
        "phone": "0977.123.456",
        "role": "broker",
        "agency": "CenLand Tây Hồ",
        "status": "active",
        "clients_count": 6,
        "projects_count": 9,
        "created_at": "2026-08-15 11:20:00",
        "last_active": "1 giờ trước",
    },
    {
        "id": "broker_04",
        "name": "Quang Đức",
        "email": "duc.onehousing@outlook.com",
        "phone": "0936.888.999",
        "role": "broker",
        "agency": "OneHousing Elite Agent",
        "status": "active",
        "clients_count": 11,
        "projects_count": 14,
        "created_at": "2026-08-18 16:45:00",
        "last_active": "Hôm qua",
    },
    {
        "id": "broker_05",
        "name": "Thanh Hương",
        "email": "huong.bds@yahoo.com",
        "phone": "0982.666.777",
        "role": "broker",
        "agency": "Era Vietnam Capital",
        "status": "locked",
        "clients_count": 2,
        "projects_count": 3,
        "created_at": "2026-08-20 10:00:00",
        "last_active": "3 ngày trước",
    },
]


def _ensure_users_table_and_seeds(connection: sqlite3.Connection) -> None:
    connection.execute("""
    CREATE TABLE IF NOT EXISTS Users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        role TEXT NOT NULL DEFAULT 'broker',
        agency TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active',
        clients_count INTEGER DEFAULT 0,
        projects_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_active TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    count = connection.execute("SELECT COUNT(*) FROM Users").fetchone()[0]
    if count == 0:
        for u in DEFAULT_USERS:
            connection.execute(
                """
                INSERT OR REPLACE INTO Users (id, name, email, phone, role, agency, status, clients_count, projects_count, created_at, last_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (u["id"], u["name"], u["email"], u["phone"], u["role"], u["agency"], u["status"], u["clients_count"], u["projects_count"], u["created_at"], u["last_active"])
            )
        connection.commit()


def list_users_from_db() -> list[dict[str, Any]]:
    with connect() as connection:
        _ensure_users_table_and_seeds(connection)
        rows = connection.execute("SELECT * FROM Users ORDER BY role DESC, created_at DESC").fetchall()
        return [dict(r) for r in rows]


def save_user_to_db(user_data: dict[str, Any]) -> dict[str, Any]:
    uid = user_data.get("id") or f"broker_{int(time.time())}"
    name = str(user_data.get("name", "Môi giới mới")).strip()
    email = str(user_data.get("email", "")).strip()
    phone = str(user_data.get("phone", "")).strip()
    role = str(user_data.get("role", "broker")).strip()
    agency = str(user_data.get("agency", "")).strip()
    status = str(user_data.get("status", "active")).strip()

    with connect() as connection:
        _ensure_users_table_and_seeds(connection)
        connection.execute(
            """
            INSERT INTO Users (id, name, email, phone, role, agency, status, clients_count, projects_count, created_at, last_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, CURRENT_TIMESTAMP, 'Vừa xong')
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                email=excluded.email,
                phone=excluded.phone,
                role=excluded.role,
                agency=excluded.agency,
                status=excluded.status,
                last_active='Vừa xong'
            """,
            (uid, name, email, phone, role, agency, status)
        )
        connection.commit()
    return {"id": uid, "name": name, "email": email, "role": role, "status": status}


def toggle_user_status_in_db(user_id: str) -> dict[str, Any]:
    with connect() as connection:
        _ensure_users_table_and_seeds(connection)
        row = connection.execute("SELECT status FROM Users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise ValueError(f"Không tìm thấy user với ID: {user_id}")
        new_status = "locked" if row["status"] == "active" else "active"
        connection.execute("UPDATE Users SET status=? WHERE id=?", (new_status, user_id))
        connection.commit()
        return {"id": user_id, "status": new_status}


def get_user_stats_from_db() -> dict[str, Any]:
    with connect() as connection:
        _ensure_users_table_and_seeds(connection)
        users = [dict(r) for r in connection.execute("SELECT * FROM Users").fetchall()]
        total_users = len(users)
        active_brokers = len([u for u in users if u["role"] == "broker" and u["status"] == "active"])
        total_clients = sum(int(u.get("clients_count") or 0) for u in users)
        total_distribution = sum(int(u.get("projects_count") or 0) for u in users)
        return {
            "total_users": total_users,
            "active_brokers": active_brokers,
            "total_clients": total_clients,
            "total_distribution": total_distribution,
            "total_global_projects": 27,
        }



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
