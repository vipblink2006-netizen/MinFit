from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from database import SQLITE_PATH, ensure_database, load_projects_from_database, load_persona_weights_from_database
from loan_dti import FinancialProfile, LoanScenario, decimal_value, simulate_loan
from project_engine import Project, assess_project


ROOT = Path(__file__).resolve().parent
PERSONAS = {
    "single": "Độc thân",
    "young_couple": "Vợ chồng trẻ",
    "family_with_children": "Gia đình có con",
    "retired": "Người lớn tuổi / Hưu trí",
}
DEFAULT_TRANSPORT_RATES = {"motorbike": Decimal("1500"), "car": Decimal("4000")}


def dec(value: Any, default: str = "0") -> Decimal:
    try:
        return decimal_value(value if value not in (None, "") else default)
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError(f"Giá trị tài chính không hợp lệ: {value}") from error


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _ensure_workflow_tables() -> None:
    ensure_database()
    with sqlite3.connect(Path(SQLITE_PATH)) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'new',
                profile_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                input_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def _transport_cost(payload: dict[str, Any], distance_km: Decimal) -> Decimal:
    mode = str(payload.get("transport_mode", "motorbike"))
    rate = dec(payload.get("transport_rate_vnd_per_km"), str(DEFAULT_TRANSPORT_RATES.get(mode, Decimal("1500"))))
    workdays = dec(payload.get("workdays_per_month"), "22")
    congestion = dec(payload.get("congestion_factor"), "1")
    return distance_km * Decimal("2") * workdays * rate * congestion


def _cash_equivalent_inflow(payload: dict[str, Any]) -> dict[int, Decimal]:
    inflows: dict[int, Decimal] = {}
    for gift in payload.get("benefits", []):
        if gift.get("type") != "Cash_Equivalent":
            continue
        month = int(gift.get("month", 1))
        inflows[month] = inflows.get(month, Decimal("0")) + dec(gift.get("value"))
    return inflows


def _timeline_result(assessment, payload: dict[str, Any]) -> dict[str, Any]:
    analysis = assessment.analysis
    rent = dec(payload.get("current_rent_monthly"))
    savings = dec(payload.get("monthly_savings"))
    denominator = rent + savings
    grace_months = int(payload.get("grace_months", 0))
    post_grace_rows = [row for row in analysis.timeline if row.month > grace_months]
    post_grace_payment = max((row.payment for row in post_grace_rows), default=analysis.max_payment)
    payment_shock = post_grace_payment / denominator if denominator > 0 else None
    transport = _transport_cost(payload, assessment.distance_km)
    cash_inflows = _cash_equivalent_inflow(payload)
    timeline = []
    for row in analysis.timeline:
        inflow = cash_inflows.get(row.month, Decimal("0"))
        adjusted_fcf = row.free_cash_flow - transport + inflow
        timeline.append({
            "month": row.month,
            "phase": row.phase,
            "rate_percent": row.annual_rate_percent,
            "opening_balance": row.opening_balance,
            "principal": row.principal,
            "interest": row.interest,
            "payment": row.payment,
            "closing_balance": row.closing_balance,
            "dti": row.dti,
            "free_cash_flow": adjusted_fcf,
            "cash_inflow": inflow,
        })
    adjusted_min_fcf_row = min(timeline, key=lambda row: row["free_cash_flow"])
    shock_level = "unknown" if payment_shock is None else "safe" if payment_shock <= 2 else "danger" if payment_shock <= Decimal("3.5") else "high"
    stress_rate = dec(payload.get("stress_rate_percent"), "12")
    stress = simulate_loan(
        FinancialProfile(
            monthly_income=dec(payload.get("monthly_income"), "100000000") + dec(payload.get("co_borrower_income")),
            available_cash=dec(payload.get("available_cash")),
            existing_debt_payment=dec(payload.get("existing_debt")),
            essential_expenses=dec(payload.get("essential_expenses")) + transport,
        ),
        LoanScenario(
            loan_ratio_percent=dec(payload.get("ltv_percent"), "70"),
            term_years=int(payload.get("term_years", 20)),
            phase1_rate_percent=stress_rate,
            phase1_months=0,
            phase2_rate_percent=stress_rate,
            repayment_method=str(payload.get("repayment_method", "annuity")),
            grace_type=str(payload.get("grace_type", "none")),
            grace_months=int(payload.get("grace_months", 0)),
        ),
        assessment.project.price_min_vnd,
        assessment.project.monthly_management_fee,
        assessment.reserve_after_purchase,
    )
    return {
        "project": {"id": assessment.project.id, "name": assessment.project.name, "area": assessment.project.area, "price": assessment.project.price_min_vnd, "bedrooms": assessment.project.bedrooms, "area_m2": assessment.project.area_m2},
        "distance_km": assessment.distance_km,
        "scores": {"total": assessment.total_score, "price": assessment.price_score, "distance": assessment.distance_score, "amenities": assessment.amenity_score},
        "financial": {"down_payment": assessment.down_payment, "initial_loan": analysis.initial_loan, "max_payment": analysis.max_payment, "max_dti": analysis.max_dti, "min_fcf": adjusted_min_fcf_row["free_cash_flow"], "survival_months": analysis.survival_months},
        "payment_shock": {"ratio": payment_shock, "level": shock_level, "pdf_export_allowed": shock_level not in {"high"}},
        "transport_cost_monthly": transport,
        "stress_test": {"rate_percent": stress_rate, "max_payment": stress.max_payment, "max_dti": stress.max_dti, "min_fcf": stress.min_fcf, "risk": stress.max_dti > Decimal("0.60") or stress.min_fcf < 0},
        "timeline": timeline,
        "non_cash_benefits": [gift for gift in payload.get("benefits", []) if gift.get("type") == "Non_Cash"],
        "rejection_reasons": assessment.rejection_reasons,
    }


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_workflow_tables()
    persona = str(payload.get("persona", "family_with_children"))
    if persona not in PERSONAS:
        raise ValueError("Chân dung khách hàng không hợp lệ.")
    income = dec(payload.get("monthly_income"), "100000000") + dec(payload.get("co_borrower_income"))
    transport_placeholder = Decimal("0")
    profile = FinancialProfile(
        monthly_income=income,
        available_cash=dec(payload.get("available_cash"), "2000000000"),
        existing_debt_payment=dec(payload.get("existing_debt")),
        essential_expenses=dec(payload.get("essential_expenses"), "25000000") + transport_placeholder,
    )
    discount = dec(payload.get("discount_percent")) / Decimal("100")
    scenario = LoanScenario(
        loan_ratio_percent=dec(payload.get("ltv_percent"), "70"),
        term_years=int(payload.get("term_years", 20)),
        phase1_rate_percent=dec(payload.get("intro_rate_percent"), "7.5"),
        phase1_months=int(payload.get("intro_months", 24)),
        phase2_rate_percent=dec(payload.get("floating_rate_percent"), "13.5"),
        repayment_method=str(payload.get("repayment_method", "annuity")),
        grace_type=str(payload.get("grace_type", "none")),
        grace_months=int(payload.get("grace_months", 0)),
    )
    projects = load_projects_from_database()
    selected_ids = payload.get("selected_project_ids") or [project.id for project in projects]
    selected = [project for project in projects if project.id in selected_ids]
    if not selected:
        raise ValueError("Rổ so sánh chưa có dự án hợp lệ.")
    selected = [replace(project, price_min_vnd=project.price_min_vnd * (Decimal("1") - discount)) for project in selected]
    weights = load_persona_weights_from_database()
    results = []
    for project in selected:
        assessment = assess_project(project, profile, scenario, persona, float(payload.get("workplace_lat", 10.8106)), float(payload.get("workplace_lng", 106.7091)), tuple(payload.get("required_amenities", ["school", "park", "parking"])), weights)
        results.append(_timeline_result(assessment, payload))
    results.sort(key=lambda item: item["scores"]["total"], reverse=True)
    return _json_value({"persona": PERSONAS[persona], "project_count": len(results), "results": results})


def list_projects() -> list[dict[str, Any]]:
    _ensure_workflow_tables()
    return _json_value([project.__dict__ for project in load_projects_from_database()])


def create_client(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_workflow_tables()
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Tên khách hàng không được để trống.")
    profile = json.dumps(payload, ensure_ascii=False)
    with sqlite3.connect(Path(SQLITE_PATH)) as connection:
        cursor = connection.execute("INSERT INTO clients(name, email, phone, profile_json) VALUES (?, ?, ?, ?)", (name, payload.get("email", ""), payload.get("phone", ""), profile))
        return {"id": cursor.lastrowid, "name": name, "status": "new"}
