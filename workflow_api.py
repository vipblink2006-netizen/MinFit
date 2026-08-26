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

# 4-Tier Urban Classification (Focus on Hanoi & Northern region, with fallback for other regions)
DISTRICT_TIERS: dict[str, int] = {
    # HÀ NỘI
    "Hoàn Kiếm": 1, "Ba Đình": 1, "Đống Đa": 1, "Hai Bà Trưng": 1,
    "Cầu Giấy": 2, "Thanh Xuân": 2, "Tây Hồ": 2, "Nam Từ Liêm": 2, "Bắc Từ Liêm": 2,
    "Hà Đông": 3, "Hoàng Mai": 3, "Long Biên": 3, "Gia Lâm": 3, "Đông Anh": 3, "Hoài Đức": 3, "Thanh Trì": 3,
    "Sóc Sơn": 4, "Ba Vì": 4, "Mê Linh": 4, "Thạch Thất": 4, "Quốc Oai": 4, "Chương Mỹ": 4, "Đan Phượng": 4, "Thường Tín": 4,
    # MIỀN BẮC LÂN CẬN
    "Văn Giang": 3, "TP. Hưng Yên": 4, "TP. Bắc Ninh": 3, "Từ Sơn": 3, "Yên Phong": 4,
    "TP. Vĩnh Yên": 3, "Phúc Yên": 3, "Hồng Bàng": 2, "Ngô Quyền": 2, "Lê Chân": 2, "Hải An": 2, "Thủy Nguyên": 3,
    # TP. HỒ CHÍ MINH
    "Quận 1": 1, "Quận 3": 1,
    "TP. Thủ Đức": 2, "Quận 7": 2, "Bình Thạnh": 2, "Phú Nhuận": 2, "Tân Bình": 2, "Quận 4": 2, "Quận 5": 2, "Quận 10": 2,
    "Tân Phú": 3, "Gò Vấp": 3, "Quận 6": 3, "Quận 8": 3, "Quận 11": 3, "Quận 12": 3, "Bình Tân": 3, "Huyện Nhà Bè": 3, "Huyện Bình Chánh": 3,
    "Huyện Hóc Môn": 4, "Huyện Củ Chi": 4, "Huyện Cần Giờ": 4,
}

# Base Living Cost by Tier and Persona (Survival Base: Nutrition, Utilities, Basic Needs)
BASE_LIVING_COSTS: dict[int, dict[str, Decimal]] = {
    1: {"single": Decimal("10000000"), "young_couple": Decimal("16000000"), "family_with_children": Decimal("18000000"), "retired": Decimal("12000000")},
    2: {"single": Decimal("8500000"),  "young_couple": Decimal("13500000"), "family_with_children": Decimal("15000000"), "retired": Decimal("10000000")},
    3: {"single": Decimal("7000000"),  "young_couple": Decimal("11000000"), "family_with_children": Decimal("12500000"), "retired": Decimal("8500000")},
    4: {"single": Decimal("5500000"),  "young_couple": Decimal("8500000"),  "family_with_children": Decimal("9500000"),  "retired": Decimal("7000000")},
}

EDUCATION_COST_PER_CHILD: dict[str, Decimal] = {
    "none": Decimal("0"),
    "public": Decimal("2500000"),
    "private": Decimal("6500000"),
    "bilingual": Decimal("15000000"),
    "international": Decimal("30000000"),
}

HEALTHCARE_COSTS: dict[str, Decimal] = {
    "healthy": Decimal("1200000"),
    "toddler": Decimal("2500000"),
    "chronic": Decimal("4500000"),
}

LIFESTYLE_BUFFERS: dict[str, Decimal] = {
    "frugal": Decimal("0"),
    "moderate": Decimal("3000000"),
    "liberal": Decimal("7000000"),
}


def get_district_tier(district_name: str) -> int:
    for name, tier in DISTRICT_TIERS.items():
        if name.lower() in district_name.lower():
            return tier
    return 2  # Default to Tier 2 if not explicitly listed


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


def _calculate_dynamic_surcharge(project: Project, persona: str) -> tuple[Decimal, str]:
    """Calculate dynamic living surcharge/savings based on project amenity proximity."""
    amenities = set(project.amenities)
    surcharge = Decimal("0")
    reasons = []

    # Check school proximity for family
    if persona == "family_with_children":
        if "school" not in amenities:
            surcharge += Decimal("2000000")
            reasons.append("Thiếu trường học gần: +2.0 tr/tháng (xe đưa đón/xăng xe)")
        else:
            reasons.append("Trường học nội khu: Tiết kiệm thời gian & chi phí đưa đón")

    # Check supermarket / market
    if "market" not in amenities:
        surcharge += Decimal("800000")
        reasons.append("Thiếu chợ/siêu thị gần: +800k/tháng (phí giao hàng/đi chợ xa)")

    # Check healthcare for retired or family
    if persona in ("retired", "family_with_children") and "hospital" not in amenities:
        surcharge += Decimal("600000")
        reasons.append("Cách xa cơ sở y tế: +600k/tháng (phí khám bệnh/di chuyển)")

    # All-in-one ecosystem discount (park + pool + school + parking)
    if {"park", "pool", "school", "parking"}.issubset(amenities):
        surcharge -= Decimal("1200000")
        reasons.append("Hệ sinh thái All-in-One: -1.2 tr/tháng (tiết kiệm vé bơi, gym, công viên)")

    return surcharge, "; ".join(reasons) if reasons else "Hạ tầng tiện ích cân bằng"


def _timeline_result(assessment, payload: dict[str, Any]) -> dict[str, Any]:
    project = assessment.project
    analysis = assessment.analysis
    persona = str(payload.get("persona", "family_with_children"))

    # Geographic Tier
    workplace_district = str(payload.get("workplace_district", "Cầu Giấy"))
    urban_tier = get_district_tier(workplace_district)

    # 1. Income calculation (Net Acceptable Income with 10% risk discount)
    declared_income = dec(payload.get("monthly_income"), "85000000") + dec(payload.get("co_borrower_income", "0"))
    net_acceptable_income = declared_income * Decimal("0.90")
    risk_discount_amount = declared_income * Decimal("0.10")

    # 2. Living Costs Breakdown
    tier_costs = BASE_LIVING_COSTS.get(urban_tier, BASE_LIVING_COSTS[2])
    base_living_cost = tier_costs.get(persona, tier_costs["family_with_children"])

    # Education cost
    if persona == "family_with_children":
        child_count = int(payload.get("child_count", 1))
        school_type = str(payload.get("school_type", "private"))
        education_cost = Decimal(child_count) * EDUCATION_COST_PER_CHILD.get(school_type, Decimal("6500000"))
    else:
        child_count = 0
        school_type = "none"
        education_cost = Decimal("0")

    # Healthcare & Lifestyle
    health_cond = str(payload.get("health_condition", "healthy"))
    healthcare_cost = HEALTHCARE_COSTS.get(health_cond, Decimal("1200000"))
    lifestyle_level = str(payload.get("lifestyle_level", "moderate"))
    lifestyle_cost = LIFESTYLE_BUFFERS.get(lifestyle_level, Decimal("3000000"))

    # Dynamic living surcharge from project amenities
    dynamic_surcharge, dynamic_reason = _calculate_dynamic_surcharge(project, persona)

    # Allow custom essential expenses override if explicitly provided and greater
    custom_expenses = dec(payload.get("essential_expenses", "0"))
    calculated_total_living = base_living_cost + education_cost + healthcare_cost + lifestyle_cost + dynamic_surcharge
    total_living_cost = max(custom_expenses, calculated_total_living)

    # 3. Building Housing Fees
    building_mgmt_fee = project.monthly_management_fee
    parking_fee = Decimal("300000")  # 2 motorbikes
    if declared_income >= Decimal("75000000"):
        parking_fee += Decimal("1500000")  # 1 car
    total_housing_fees = building_mgmt_fee + parking_fee

    # 4. Commute Cost
    commute_cost = _transport_cost(payload, assessment.distance_km)

    # Existing Debt
    existing_debt = dec(payload.get("existing_debt", "0"))

    # 5. Core Metric: Total Housing Burden (THB Ratio)
    # Floating Period Monthly Payment (Month 25+)
    grace_months = int(payload.get("grace_months", 0))
    post_grace_rows = [row for row in analysis.timeline if row.month > max(grace_months, 24)]
    pmt_floating = max((row.payment for row in post_grace_rows), default=analysis.max_payment)
    pmt_intro = analysis.timeline[0].payment if analysis.timeline else pmt_floating

    total_housing_cost = pmt_floating + total_housing_fees
    thb_ratio = (total_housing_cost / net_acceptable_income * Decimal("100")) if net_acceptable_income > Decimal("0") else Decimal("100")
    thb_status = "safe" if thb_ratio <= Decimal("42") else "caution" if thb_ratio <= Decimal("50") else "danger"

    # 6. Core Metric: Real Free Cash Flow (Real FCF - Continuous Spectrum)
    total_monthly_outflow = total_housing_cost + total_living_cost + commute_cost + existing_debt
    real_fcf = net_acceptable_income - total_monthly_outflow
    if real_fcf >= Decimal("15000000"):
        fcf_status = "safe"
        fcf_remark = "Dư dả an toàn: Tự tin phòng ngừa biến cố & tích lũy đầu tư."
    elif real_fcf >= Decimal("0"):
        fcf_status = "caution"
        fcf_remark = "Vùng đệm vừa vặn: Cần quản lý chi tiêu chặt chẽ, đề phòng viện phí."
    else:
        fcf_status = "danger"
        fcf_remark = "Âm dòng tiền: Nguy cơ thiếu hụt thanh khoản, phải vay bù hàng tháng."

    # 7. Move-in Initial Capex & Survival Runway
    project_price = project.price_min_vnd
    maintenance_fund_2pct = project_price * Decimal("0.02")
    registration_tax_05pct = project_price * Decimal("0.005")
    interior_furnishing = project.area_m2 * Decimal("2800000")  # ~2.8tr/m2 basic fit-out
    initial_move_in_capex = maintenance_fund_2pct + registration_tax_05pct + interior_furnishing

    down_payment = assessment.down_payment
    total_upfront_needed = down_payment + initial_move_in_capex
    available_cash = dec(payload.get("available_cash"), "2200000000")
    cash_remaining_after_move_in = available_cash - total_upfront_needed

    survival_runway_months = Decimal("0")
    if total_monthly_outflow > Decimal("0") and cash_remaining_after_move_in > Decimal("0"):
        survival_runway_months = round(cash_remaining_after_move_in / total_monthly_outflow, 1)

    # 8. Payment Shock & Auto-Suggestion
    pmt_m24 = analysis.timeline[min(23, len(analysis.timeline) - 1)].payment if len(analysis.timeline) >= 24 else pmt_intro
    pmt_m25 = analysis.timeline[min(24, len(analysis.timeline) - 1)].payment if len(analysis.timeline) >= 25 else pmt_floating
    payment_shock_ratio = (pmt_m25 / pmt_m24) if pmt_m24 > Decimal("0") else Decimal("1.0")

    shock_level = "safe" if payment_shock_ratio <= Decimal("1.4") else "caution" if payment_shock_ratio <= Decimal("1.8") else "danger"
    shock_suggestion = ""
    if payment_shock_ratio > Decimal("1.8"):
        term_years = int(payload.get("term_years", 20))
        suggested_term = 30 if term_years < 30 else 35
        # Estimate lower PMT with 30-year term
        suggested_pmt = round((pmt_m25 * Decimal(term_years) / Decimal(suggested_term)) / Decimal("1000000"), 1)
        shock_suggestion = f"Cú sốc thả nổi tháng 25 tăng vọt {payment_shock_ratio:.1f} lần (từ {pmt_m24/Decimal('1000000'):.1f} tr lên {pmt_m25/Decimal('1000000'):.1f} tr). Đề xuất: Kéo dài thời hạn vay từ {term_years} năm lên {suggested_term} năm để hạ PMT xuống ~{suggested_pmt} triệu/tháng."

    # 9. Stress Test at 15.0% Floating Rate (Default Risk Evaluation)
    stress_rate = Decimal("15.0")
    stress_profile = FinancialProfile(
        monthly_income=net_acceptable_income,
        available_cash=available_cash,
        existing_debt_payment=existing_debt,
        essential_expenses=total_living_cost + commute_cost + total_housing_fees,
    )
    stress_scenario = LoanScenario(
        loan_ratio_percent=dec(payload.get("ltv_percent"), "70"),
        term_years=int(payload.get("term_years", 20)),
        phase1_rate_percent=stress_rate,
        phase1_months=0,
        phase2_rate_percent=stress_rate,
        repayment_method=str(payload.get("repayment_method", "annuity")),
        grace_type=str(payload.get("grace_type", "none")),
        grace_months=int(payload.get("grace_months", 0)),
    )
    stress = simulate_loan(stress_profile, stress_scenario, project.price_min_vnd, project.monthly_management_fee, max(cash_remaining_after_move_in, Decimal("0")))
    stress_dti = (stress.max_payment + existing_debt) / net_acceptable_income if net_acceptable_income > Decimal("0") else Decimal("1.0")
    stress_fcf = net_acceptable_income - stress.max_payment - total_housing_fees - total_living_cost - commute_cost - existing_debt
    is_default_risk = (stress_dti > Decimal("0.70")) or (stress_fcf < Decimal("0"))

    # 10. Early Payoff Horizon
    early_payoff_years = None
    if real_fcf >= Decimal("10000000"):
        annual_prepay_pool = real_fcf * Decimal("0.70") * Decimal("12")
        initial_loan = analysis.initial_loan
        term_years = int(payload.get("term_years", 20))
        effective_annual_payoff = annual_prepay_pool + (initial_loan / Decimal(term_years))
        if effective_annual_payoff > Decimal("0"):
            early_payoff_years = round(float(initial_loan / effective_annual_payoff), 1)

    # 11. Final Purchase Verdict (6-Pillar Framework)
    pros = []
    cons = []
    action_plan = []

    # Pros
    if assessment.distance_km <= Decimal("6.0"):
        pros.append(f"Khoảng cách đến nơi làm việc rất gần: {assessment.distance_km:.1f} km (tiết kiệm ~30-45 phút di chuyển/ngày).")
    if len(assessment.matched_amenities) >= 3:
        pros.append(f"Khớp {len(assessment.matched_amenities)}/{len(payload.get('required_amenities', []))} tiện ích ưu tiên hàng đầu.")
    if thb_ratio <= Decimal("40"):
        pros.append(f"Gánh nặng nhà ở chỉ chiếm {thb_ratio:.1f}% thu nhập ròng (vùng cực kỳ an toàn).")
    if real_fcf >= Decimal("15000000"):
        pros.append(f"Dòng tiền thặng dư thực tế dồi dào: +{real_fcf/Decimal('1000000'):.1f} triệu/tháng sau mọi chi phí sinh hoạt.")
    if early_payoff_years and early_payoff_years < int(payload.get("term_years", 20)):
        pros.append(f"Khả năng tất toán sớm: Có thể trả hết nợ trong ~{early_payoff_years} năm thay vì {payload.get('term_years', 20)} năm.")

    # Cons & Risks
    if thb_ratio > Decimal("48"):
        cons.append(f"Gánh nặng nhà ở cao ({thb_ratio:.1f}%): Chi phí nhà ở ngốn gần một nửa thu nhập ròng.")
    if cash_remaining_after_move_in < Decimal("100000000"):
        cons.append(f"Quỹ tiền mặt sau nhận nhà chỉ còn {cash_remaining_after_move_in/Decimal('1000000'):.1f} triệu (đệm sinh tồn {survival_runway_months:.1f} tháng - khá mỏng).")
    if payment_shock_ratio > Decimal("1.8"):
        cons.append(f"Cú sốc trả góp tháng 25 tăng {payment_shock_ratio:.1f} lần khi bước vào giai đoạn lãi thả nổi.")
    if is_default_risk:
        cons.append("Nguy cơ vỡ nợ khi Stress Test 15%: Nếu lãi suất thị trường tăng lên 15%, gia đình sẽ bị âm dòng tiền.")
    if assessment.distance_km > Decimal("12.0"):
        cons.append(f"Khoảng cách khá xa nơi làm việc ({assessment.distance_km:.1f} km), phát sinh thời gian & xăng xe.")

    # Determine Verdict
    if thb_ratio <= Decimal("42") and real_fcf >= Decimal("15000000") and survival_runway_months >= Decimal("4.0") and not is_default_risk and cash_remaining_after_move_in >= Decimal("0"):
        verdict_status = "RECOMMENDED_BUY"
        verdict_label = "ĐỦ ĐIỀU KIỆN MUA NGAY"
        verdict_badge = "safe"
        verdict_summary = "Phương án tài chính vừa vặn hoàn hảo. Đảm bảo an cư vững bền, dư dả tích lũy và an toàn tuyệt đối trước biến cố."
    elif thb_ratio <= Decimal("50") and real_fcf >= Decimal("0") and cash_remaining_after_move_in >= Decimal("-100000000"):
        verdict_status = "CONDITIONAL_BUY"
        verdict_label = "CÂN NHẮC · CẦN ĐIỀU CHỈNH KỊCH BẢN"
        verdict_badge = "warning"
        verdict_summary = "Phương án có thể mua được nhưng cần tái cấu trúc kỳ hạn vay hoặc bổ sung vốn tự có để giảm áp lực dòng tiền."
        if shock_suggestion:
            action_plan.append(shock_suggestion)
        if cash_remaining_after_move_in < Decimal("150000000"):
            action_plan.append("Cắt giảm gói hoàn thiện nội thất hoặc tích lũy thêm 100-200 triệu để duy trì quỹ dự phòng sinh tồn ≥ 6 tháng.")
    else:
        verdict_status = "DO_NOT_BUY"
        verdict_label = "CHƯA NÊN MUA DỰ ÁN NÀY"
        verdict_badge = "danger"
        verdict_summary = "Phương án quá sức so với cấu trúc tài chính hiện tại. Nguy cơ kiệt quệ dòng tiền (House Poor) và mất khả năng trả nợ."
        action_plan.append("Chuyển hướng sang dự án có mức giá thấp hơn hoặc căn hộ diện tích nhỏ hơn.")
        action_plan.append("Tăng tỷ lệ vốn tự có sẵn có hoặc tìm kiếm người đồng trả nợ bổ sung trước khi vay.")

    # Timeline adjusted
    cash_inflows = _cash_equivalent_inflow(payload)
    timeline = []
    for row in analysis.timeline:
        inflow = cash_inflows.get(row.month, Decimal("0"))
        adjusted_fcf = net_acceptable_income - (row.payment + total_housing_fees + total_living_cost + commute_cost + existing_debt) + inflow
        timeline.append({
            "month": row.month,
            "phase": row.phase,
            "rate_percent": row.annual_rate_percent,
            "opening_balance": row.opening_balance,
            "principal": row.principal,
            "interest": row.interest,
            "payment": row.payment,
            "closing_balance": row.closing_balance,
            "dti": (row.payment + existing_debt) / net_acceptable_income if net_acceptable_income > Decimal("0") else row.dti,
            "free_cash_flow": adjusted_fcf,
            "cash_inflow": inflow,
        })

    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "area": project.area,
            "price": project.price_min_vnd,
            "bedrooms": project.bedrooms,
            "area_m2": project.area_m2,
            "amenities": project.amenities,
            "management_fee_per_m2": project.management_fee_per_m2,
            "monthly_management_fee": building_mgmt_fee,
        },
        "urban_tier": urban_tier,
        "distance_km": assessment.distance_km,
        "matched_amenities": assessment.matched_amenities,
        "missing_amenities": assessment.missing_amenities,
        "scores": {
            "total": assessment.total_score,
            "price": assessment.price_score,
            "distance": assessment.distance_score,
            "amenities": assessment.amenity_score
        },
        "financial_breakdown": {
            "declared_income": declared_income,
            "net_acceptable_income": net_acceptable_income,
            "risk_discount_amount": risk_discount_amount,
            "pmt_floating": pmt_floating,
            "pmt_intro": pmt_intro,
            "building_management_fee": building_mgmt_fee,
            "parking_fee": parking_fee,
            "total_housing_fees": total_housing_fees,
            "total_housing_cost": total_housing_cost,
            "thb_ratio": thb_ratio,
            "thb_status": thb_status,
            "base_living_cost": base_living_cost,
            "education_cost": education_cost,
            "healthcare_cost": healthcare_cost,
            "lifestyle_cost": lifestyle_cost,
            "dynamic_living_surcharge": dynamic_surcharge,
            "dynamic_reason": dynamic_reason,
            "total_living_cost": total_living_cost,
            "commute_cost": commute_cost,
            "existing_debt": existing_debt,
            "total_monthly_outflow": total_monthly_outflow,
            "real_fcf": real_fcf,
            "fcf_status": fcf_status,
            "fcf_remark": fcf_remark,
            "down_payment": down_payment,
            "initial_loan": analysis.initial_loan,
            "maintenance_fund_2pct": maintenance_fund_2pct,
            "registration_tax_05pct": registration_tax_05pct,
            "interior_furnishing": interior_furnishing,
            "initial_move_in_capex": initial_move_in_capex,
            "total_upfront_needed": total_upfront_needed,
            "cash_remaining_after_move_in": cash_remaining_after_move_in,
            "survival_runway_months": survival_runway_months,
            "early_payoff_years": early_payoff_years,
        },
        "financial": {
            "down_payment": down_payment,
            "initial_loan": analysis.initial_loan,
            "max_payment": pmt_floating,
            "max_dti": (pmt_floating + existing_debt) / net_acceptable_income,
            "min_fcf": real_fcf,
            "survival_months": survival_runway_months,
        },
        "payment_shock": {
            "ratio": payment_shock_ratio,
            "level": shock_level,
            "suggestion": shock_suggestion,
        },
        "stress_test_15": {
            "rate_percent": stress_rate,
            "max_payment": stress.max_payment,
            "dti": stress_dti,
            "fcf": stress_fcf,
            "is_default_risk": is_default_risk,
        },
        "verdict": {
            "status": verdict_status,
            "label": verdict_label,
            "badge_class": verdict_badge,
            "summary": verdict_summary,
            "pros": pros,
            "cons": cons,
            "action_plan": action_plan,
        },
        "timeline": timeline,
        "rejection_reasons": assessment.rejection_reasons,
    }


def list_projects() -> list[dict[str, Any]]:
    projects = load_projects_from_database()
    return [
        {
            "id": p.id,
            "name": p.name,
            "area": p.area,
            "price_min_vnd": float(p.price_min_vnd),
            "area_m2": float(p.area_m2),
            "lat": p.lat,
            "lng": p.lng,
            "management_fee_per_m2": float(p.management_fee_per_m2),
            "bedrooms": p.bedrooms,
            "amenities": list(p.amenities),
        }
        for p in projects
    ]


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_workflow_tables()
    persona = str(payload.get("persona", "family_with_children"))
    if persona not in PERSONAS:
        raise ValueError("Chân dung khách hàng không hợp lệ.")

    income = dec(payload.get("monthly_income"), "85000000") + dec(payload.get("co_borrower_income", "0"))
    transport_placeholder = Decimal("0")
    profile = FinancialProfile(
        monthly_income=income,
        available_cash=dec(payload.get("available_cash"), "2200000000"),
        existing_debt_payment=dec(payload.get("existing_debt", "0")),
        essential_expenses=dec(payload.get("essential_expenses"), "25000000") + transport_placeholder,
    )
    discount = dec(payload.get("discount_percent", "0")) / Decimal("100")
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
    selected_ids = payload.get("selected_project_ids") or [project.id for project in projects[:5]]
    selected = [project for project in projects if project.id in selected_ids]
    if not selected:
        selected = projects[:5]

    selected = [replace(project, price_min_vnd=project.price_min_vnd * (Decimal("1") - discount)) for project in selected]
    weights = load_persona_weights_from_database()

    # Default to Hanoi GPS (Cầu Giấy: 21.0362, 105.7906)
    workplace_lat = float(payload.get("workplace_lat", 21.0362))
    workplace_lng = float(payload.get("workplace_lng", 105.7906))

    results = []
    for project in selected:
        assessment = assess_project(
            project,
            profile,
            scenario,
            persona,
            workplace_lat,
            workplace_lng,
            tuple(payload.get("required_amenities", ["school", "park", "parking"])),
            weights,
        )
        results.append(_timeline_result(assessment, payload))

    results.sort(key=lambda item: item["scores"]["total"], reverse=True)
    return _json_value({
        "persona": PERSONAS[persona],
        "market_segment": payload.get("market_segment", "primary"),
        "address": {
            "city": payload.get("address_city", "Hà Nội"),
            "district": payload.get("address_district", "Cầu Giấy"),
            "ward": payload.get("address_ward", "Phường Dịch Vọng Hậu"),
            "detail": payload.get("address_detail", ""),
        },
        "workplace": {
            "city": payload.get("workplace_city", "Hà Nội"),
            "district": payload.get("workplace_district", "Cầu Giấy"),
            "ward": payload.get("workplace_ward", "Phường Dịch Vọng Hậu"),
            "detail": payload.get("workplace_detail", ""),
            "lat": workplace_lat,
            "lng": workplace_lng,
        },
        "project_count": len(results),
        "results": results,
    })


def create_client(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_workflow_tables()
    name = str(payload.get("name", "Khách hàng mới")).strip()
    email = str(payload.get("email", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    profile = json.dumps(payload.get("profile", {}), ensure_ascii=False)
    with sqlite3.connect(Path(SQLITE_PATH)) as connection:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO clients (name, email, phone, status, profile_json) VALUES (?, ?, ?, 'new', ?)",
            (name, email, phone, profile),
        )
        client_id = cursor.lastrowid
        connection.commit()
    return {"id": client_id, "name": name, "status": "saved"}


def list_clients() -> list[dict[str, Any]]:
    _ensure_workflow_tables()
    with sqlite3.connect(Path(SQLITE_PATH)) as connection:
        cursor = connection.cursor()
        rows = cursor.execute(
            "SELECT id, name, email, phone, status, profile_json, created_at FROM clients ORDER BY id DESC"
        ).fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "email": r[2],
                "phone": r[3],
                "status": r[4],
                "profile": json.loads(r[5]) if r[5] else {},
                "created_at": r[6],
            }
            for r in rows
        ]
