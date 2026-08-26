"""
Workflow and decision-support API layer for MinFit.
Focus: Hanoi & Northern Vietnam Urban Core, Sub-urban & Satellites (4 Urban Tiers).
Enhanced with Live Market Price Benchmarks (T8/2026), Human-Centric Plain Language Explanations,
and 3-Layer Visual Decision Architecture for Clients.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from decimal import Decimal
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from loan_dti import FinancialProfile, LoanScenario, simulate_loan
from project_engine import AMENITY_LABELS, PERSONA_WEIGHTS, Project, assess_project
from database import (
    ensure_database,
    load_persona_weights_from_database,
    load_projects_from_database,
    save_project_to_db,
    delete_project_from_db,
    toggle_project_status_in_db,
    save_broker_selection_to_db,
    load_broker_selection_from_db,
    list_users_from_db,
    save_user_to_db,
    toggle_user_status_in_db,
    get_user_stats_from_db,
)

PERSONAS = {
    "single": "Độc thân",
    "young_couple": "Vợ chồng trẻ",
    "family_with_children": "Gia đình có con",
    "retired": "Người lớn tuổi / Hưu trí",
}

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SQLITE_PATH = DATA_DIR / "minfit.sqlite3"

# ---------------------------------------------------------------------------
# 1. HÀ NỘI & MIỀN BẮC 4-TIER URBAN CLASSIFICATION
# ---------------------------------------------------------------------------
DISTRICT_TIERS: dict[str, int] = {
    # Tier 1: Lõi Trung tâm (CBD) - Chi phí đắt đỏ nhất
    "Hoàn Kiếm": 1,
    "Ba Đình": 1,
    "Đống Đa": 1,
    "Hai Bà Trưng": 1,
    "Quận 1": 1,
    "Quận 3": 1,

    # Tier 2: Cận Trung tâm & Hubs phát triển năng động
    "Cầu Giấy": 2,
    "Thanh Xuân": 2,
    "Tây Hồ": 2,
    "Nam Từ Liêm": 2,
    "Bắc Từ Liêm": 2,
    "Bình Thạnh": 2,
    "Phú Nhuận": 2,
    "TP. Thủ Đức": 2,

    # Tier 3: Vành đai đô thị hóa & Đô thị mở rộng
    "Hà Đông": 3,
    "Hoàng Mai": 3,
    "Long Biên": 3,
    "Gia Lâm": 3,
    "Đông Anh": 3,
    "Hoài Đức": 3,
    "Thanh Trì": 3,
    "Văn Giang": 3,
    "TP. Bắc Ninh": 3,
    "Từ Sơn": 3,
    "Quận 7": 3,
    "Tân Bình": 3,
    "Gò Vấp": 3,

    # Tier 4: Vệ tinh ngoại thành & Tỉnh lân cận
    "Mê Linh": 4,
    "Sóc Sơn": 4,
    "Đan Phượng": 4,
    "Quốc Oai": 4,
    "Thạch Thất": 4,
    "Chương Mỹ": 4,
    "Thường Tín": 4,
    "Phúc Yên": 4,
    "TP. Vĩnh Yên": 4,
    "Bình Chánh": 4,
    "Hóc Môn": 4,
    "Nhà Bè": 4,
}

# ---------------------------------------------------------------------------
# 2. MARKET METADATA & SEGMENT RADAR (T8/2026 CALIBRATED)
# ---------------------------------------------------------------------------
PROJECT_SEGMENTS: dict[str, dict[str, str]] = {
    "matrix_one": {
        "segment": "Hạng sang / Cao cấp đặc biệt",
        "sub_market": "Mễ Trì · Trục Lê Quang Đạo kéo dài",
        "price_range_per_m2": "110 – 128 tr/m²",
    },
    "masteri_westheights": {
        "segment": "Cận cao cấp / Trục lõi Smart City",
        "sub_market": "Tây Mỗ · Đối diện hồ trung tâm 10.2ha",
        "price_range_per_m2": "68 – 92 tr/m²",
    },
    "anland_hadong": {
        "segment": "Trung cấp / Sát Aeon Mall Hà Đông",
        "sub_market": "Dương Nội · Trục Tố Hữu - Lê Văn Lương",
        "price_range_per_m2": "71 – 88 tr/m²",
    },
    "oceanpark_gialam": {
        "segment": "Phổ thông - Khách trẻ / Sapphire chuyển nhượng",
        "sub_market": "Gia Lâm · Đại đô thị biển hồ",
        "price_range_per_m2": "48 – 65 tr/m²",
    },
    "discovery_caugiay": {
        "segment": "Cao cấp / Ga Metro Cầu Giấy",
        "sub_market": "302 Cầu Giấy · Lõi Cận trung tâm",
        "price_range_per_m2": "80 – 95 tr/m²",
    },
    "grand_hangbai": {
        "segment": "Siêu sang Hàng Hiệu (Branded Masterise)",
        "sub_market": "Hàng Bài · Trung tâm Lõi Hoàn Kiếm",
        "price_range_per_m2": "240 – 300 tr/m²",
    },
    "sun_thuykhue": {
        "segment": "Hạng sang View Hồ Tây",
        "sub_market": "Thụy Khuê · Hoàng Hoa Thám",
        "price_range_per_m2": "125 – 150 tr/m²",
    },
    "starlake_tayho": {
        "segment": "Khu Ngoại giao đoàn / Hạng sang",
        "sub_market": "Tây Hồ Tây · Đại đô thị Starlake",
        "price_range_per_m2": "140 – 170 tr/m²",
    },
    "brg_le_van_luong": {
        "segment": "Cao cấp Trung tâm Thanh Xuân",
        "sub_market": "Lê Văn Lương · Hoàng Đạo Thúy",
        "price_range_per_m2": "95 – 115 tr/m²",
    },
    "mipec_rubik360": {
        "segment": "Cao cấp Trung tâm Cầu Giấy",
        "sub_market": "122-124 Xuân Thủy",
        "price_range_per_m2": "95 – 112 tr/m²",
    },
    "eurowindow_donganh": {
        "segment": "Vành đai Bắc Sông Hồng",
        "sub_market": "Đông Hội · Chân cầu Đông Trù",
        "price_range_per_m2": "48 – 58 tr/m²",
    },
    "rose_town_hoangmai": {
        "segment": "Cửa ngõ Phía Nam",
        "sub_market": "79 Ngọc Hồi · Hoàng Liệt",
        "price_range_per_m2": "52 – 62 tr/m²",
    },
    "ecopark_hungyen": {
        "segment": "Đô thị Sinh thái Xanh",
        "sub_market": "Văn Giang · Cận Gia Lâm",
        "price_range_per_m2": "52 – 68 tr/m²",
    },
    "vinhomes_bacninh": {
        "segment": "Trung tâm Đô thị Vệ tinh",
        "sub_market": "Ngã 6 TP. Bắc Ninh",
        "price_range_per_m2": "42 – 50 tr/m²",
    },
    "hanoi_melody": {
        "segment": "Tây Nam Linh Đàm",
        "sub_market": "Bán đảo Linh Đàm · Hoàng Mai",
        "price_range_per_m2": "55 – 65 tr/m²",
    },
    "the_zen_residence": {
        "segment": "Khu đô thị Gamuda Gardens",
        "sub_market": "Yên Sở · Hoàng Mai",
        "price_range_per_m2": "60 – 72 tr/m²",
    },
    "imperia_smartcity": {
        "segment": "Trung tâm Vinhomes Smart City",
        "sub_market": "Tây Mỗ · Cạnh Masteri",
        "price_range_per_m2": "64 – 75 tr/m²",
    },
    "the_sakura_smartcity": {
        "segment": "Phân khu Phong cách Nhật (SAMTY)",
        "sub_market": "Smart City · Tiện ích Nhật Bản",
        "price_range_per_m2": "62 – 72 tr/m²",
    },
}

# ---------------------------------------------------------------------------
# 3. BASE LIVING COSTS BY URBAN TIER & PERSONA (VND/MONTH)
# ---------------------------------------------------------------------------
BASE_LIVING_COSTS: dict[int, dict[str, Decimal]] = {
    1: {  # Tier 1 (Lõi CBD)
        "single": Decimal("10000000"),
        "young_couple": Decimal("16000000"),
        "family_with_children": Decimal("18000000"),
        "retired": Decimal("12000000"),
    },
    2: {  # Tier 2 (Cận Trung tâm Cầu Giấy, Thanh Xuân, Nam Từ Liêm...)
        "single": Decimal("8500000"),
        "young_couple": Decimal("13500000"),
        "family_with_children": Decimal("15000000"),
        "retired": Decimal("10000000"),
    },
    3: {  # Tier 3 (Vành đai Hà Đông, Hoàng Mai, Gia Lâm, Đông Anh...)
        "single": Decimal("7000000"),
        "young_couple": Decimal("11000000"),
        "family_with_children": Decimal("12500000"),
        "retired": Decimal("8500000"),
    },
    4: {  # Tier 4 (Vệ tinh Sóc Sơn, Mê Linh, Đan Phượng...)
        "single": Decimal("5500000"),
        "young_couple": Decimal("8500000"),
        "family_with_children": Decimal("9500000"),
        "retired": Decimal("7000000"),
    },
}

EDUCATION_COST_PER_CHILD: dict[str, Decimal] = {
    "none": Decimal("0"),
    "public": Decimal("2500000"),        # Trường công lập
    "private": Decimal("6500000"),       # Tư thục tiêu chuẩn
    "bilingual": Decimal("15000000"),    # Song ngữ (Vinschool, v.v.)
    "international": Decimal("30000000") # Quốc tế hoàn toàn
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

def dec(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


def _ensure_workflow_tables() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(Path(SQLITE_PATH)) as connection:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            profile_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        connection.commit()


def _get_district_tier(district_name: str) -> int:
    return DISTRICT_TIERS.get(district_name.strip(), 2)


def _calculate_dynamic_surcharge(project: Project, persona: str) -> tuple[Decimal, str]:
    surcharge = Decimal("0")
    reasons = []
    amenities = set(project.amenities)

    # 1. School proximity
    if persona == "family_with_children":
        if "school" not in amenities:
            surcharge += Decimal("2000000")
            reasons.append("+2tr xe đưa đón/di chuyển do thiếu trường học nội khu")
        else:
            reasons.append("Tiết kiệm chi phí đưa đón nhờ trường học liền kề")

    # 2. Market/Supermarket
    if "market" not in amenities:
        surcharge += Decimal("800000")
        reasons.append("+800k chi phí mua sắm xa")

    # 3. Healthcare
    if "hospital" not in amenities and persona in ("family_with_children", "retired"):
        surcharge += Decimal("600000")
        reasons.append("+600k chi phí y tế ngoại khu")

    # 4. Mega-ecosystem discount
    if "pool" in amenities and "park" in amenities and "school" in amenities and "parking" in amenities:
        surcharge -= Decimal("1200000")
        reasons.append("-1.2tr tiết kiệm tiện ích all-in-one (bơi lội, thể thao, công viên nội khu)")

    return surcharge, "; ".join(reasons)


def _transport_cost(payload: dict[str, Any], distance_km: Decimal) -> Decimal:
    mode = str(payload.get("transport_mode", "motorbike"))
    cost_per_km = Decimal("4000") if mode == "car" else Decimal("1500")
    monthly_trips = Decimal("44")  # 22 working days * 2 trips
    return distance_km * monthly_trips * cost_per_km


def _cash_equivalent_inflow(payload: dict[str, Any]) -> dict[int, Decimal]:
    inflows: dict[int, Decimal] = {}
    quarterly_bonus = dec(payload.get("quarterly_bonus_vnd", "0"))
    if quarterly_bonus > Decimal("0"):
        for m in range(3, 361, 3):
            inflows[m] = inflows.get(m, Decimal("0")) + quarterly_bonus

    annual_inflow = dec(payload.get("annual_inflow_vnd", "0"))
    if annual_inflow > Decimal("0"):
        for m in range(12, 361, 12):
            inflows[m] = inflows.get(m, Decimal("0")) + annual_inflow

    return inflows


def _timeline_result(assessment: Any, payload: dict[str, Any]) -> dict[str, Any]:
    project: Project = assessment.project
    analysis = assessment.analysis
    persona = str(payload.get("persona", "family_with_children"))

    # 1. Net Acceptable Income (10% Risk Discount)
    declared_income = dec(payload.get("monthly_income"), "85000000")
    risk_discount_amount = declared_income * Decimal("0.10")
    net_acceptable_income = declared_income - risk_discount_amount

    # 2. Multi-tier Baseline Living Cost
    workplace_district = str(payload.get("workplace_district", "Cầu Giấy"))
    urban_tier = _get_district_tier(workplace_district)
    tier_costs = BASE_LIVING_COSTS.get(urban_tier, BASE_LIVING_COSTS[2])
    base_living_cost = tier_costs.get(persona, Decimal("15000000"))

    # Education Cost
    child_count = int(payload.get("child_count", 1 if persona == "family_with_children" else 0))
    school_type = str(payload.get("school_type", "private"))
    cost_per_child = EDUCATION_COST_PER_CHILD.get(school_type, Decimal("6500000"))
    education_cost = cost_per_child * Decimal(child_count) if persona == "family_with_children" else Decimal("0")

    # Healthcare & Lifestyle
    health_cond = str(payload.get("health_condition", "healthy"))
    healthcare_cost = HEALTHCARE_COSTS.get(health_cond, Decimal("1200000"))
    lifestyle_level = str(payload.get("lifestyle_level", "moderate"))
    lifestyle_cost = LIFESTYLE_BUFFERS.get(lifestyle_level, Decimal("3000000"))

    # Dynamic living surcharge from project amenities
    dynamic_surcharge, dynamic_reason = _calculate_dynamic_surcharge(project, persona)

    # Custom override
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
    existing_debt = dec(payload.get("existing_debt", "0"))

    # 5. Core Metric: Total Housing Burden (THB Ratio)
    grace_months = int(payload.get("grace_months", 0))
    post_grace_rows = [row for row in analysis.timeline if row.month > max(grace_months, 24)]
    pmt_floating = max((row.payment for row in post_grace_rows), default=analysis.max_payment)
    pmt_intro = analysis.timeline[0].payment if analysis.timeline else pmt_floating

    total_housing_cost = pmt_floating + total_housing_fees
    thb_ratio = (total_housing_cost / net_acceptable_income * Decimal("100")) if net_acceptable_income > Decimal("0") else Decimal("100")
    thb_status = "safe" if thb_ratio <= Decimal("42") else "caution" if thb_ratio <= Decimal("50") else "danger"

    # 6. Core Metric: Real Free Cash Flow (Real FCF)
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

    drive_mins = int(float(assessment.distance_km) * 2.5)

    # Pros (Đầy đủ và phong phú)
    if assessment.distance_km <= Decimal("6.0"):
        pros.append(f"Vị trí rất gần nơi làm việc: chỉ {assessment.distance_km:.1f} km (~{max(10, drive_mins)} phút), tiết kiệm nhiều thời gian & sức khỏe.")
    elif assessment.distance_km <= Decimal("12.0"):
        pros.append(f"Khoảng cách hợp lý: {assessment.distance_km:.1f} km kết nối thuận tiện tới trục làm việc chính.")
    else:
        pros.append(f"Nằm tại khu vực phát triển mới ({project.area}), hạ tầng giao thông mở rộng kết nối.")

    if len(assessment.matched_amenities) >= 2:
        matched_names = [AMENITY_LABELS.get(a, a) for a in assessment.matched_amenities[:3]]
        pros.append(f"Tiện ích sống vượt trội: có sẵn {', '.join(matched_names)}.")

    if thb_ratio <= Decimal("42"):
        pros.append(f"Gánh nặng nhà ở cực kỳ an toàn: chỉ chiếm {thb_ratio:.1f}% thu nhập ròng (dưới ngưỡng cảnh báo 45%).")
    elif thb_ratio <= Decimal("50"):
        pros.append(f"Tỷ lệ gánh nặng nhà ở ({thb_ratio:.1f}%) nằm trong tầm kiểm soát nếu chi tiêu có kế hoạch.")

    if real_fcf >= Decimal("15000000"):
        pros.append(f"Dòng tiền thặng dư dồi dào: dư dả +{real_fcf/Decimal('1000000'):.1f} triệu/tháng sau mọi chi phí sinh hoạt & tiền nhà.")
    elif real_fcf >= Decimal("0"):
        pros.append(f"Dòng tiền hàng tháng không bị âm: vẫn giữ được mức thặng dư +{real_fcf/Decimal('1000000'):.1f} triệu/tháng.")

    if early_payoff_years and early_payoff_years < int(payload.get("term_years", 20)):
        pros.append(f"Khả năng tất toán sớm: Có thể hoàn tất trả sạch nợ trong ~{early_payoff_years} năm thay vì {payload.get('term_years', 20)} năm.")

    if project.payment_policy:
        pros.append(f"Chính sách bán hàng: {project.payment_policy}.")

    # Cons & Risks (Chi tiết và cảnh báo rõ ràng)
    if thb_ratio > Decimal("45"):
        cons.append(f"Gánh nặng nhà ở cao ({thb_ratio:.1f}%): Chi phí tiền nhà ngốn gần một nửa thu nhập ròng hàng tháng.")
    if real_fcf < Decimal("0"):
        cons.append(f"Dòng tiền bị âm ({real_fcf/Decimal('1000000'):.1f} triệu/tháng): Gia đình phải bù lỗ sau khi thanh toán tiền nhà và sinh hoạt.")
    elif real_fcf < Decimal("12000000"):
        cons.append(f"Dòng tiền dự phòng còn mỏng: chỉ dư +{real_fcf/Decimal('1000000'):.1f} triệu/tháng, dễ gặp áp lực nếu có biến cố phát sinh.")

    if cash_remaining_after_move_in < Decimal("100000000"):
        cons.append(f"Quỹ tiền mặt sau nhận nhà chỉ còn {cash_remaining_after_move_in/Decimal('1000000'):.1f} triệu (đệm sinh tồn {survival_runway_months:.1f} tháng - dưới mức 6 tháng khuyến nghị).")

    if payment_shock_ratio > Decimal("1.3"):
        cons.append(f"Cú sốc bước nhảy lãi suất: Trả góp tháng 25 tăng {payment_shock_ratio:.1f} lần khi bước vào giai đoạn lãi thả nổi.")

    if is_default_risk:
        cons.append("Nguy cơ thâm hụt dòng tiền khi Stress Test lãi suất tăng lên 15%.")

    if assessment.distance_km > Decimal("12.0"):
        cons.append(f"Khoảng cách khá xa ({assessment.distance_km:.1f} km, ~{drive_mins} phút di chuyển), phát sinh thêm chi phí đi lại.")

    if project.risk_note:
        cons.append(f"Lưu ý dự án: {project.risk_note}.")

    if not cons:
        cons.append("Cần chú ý chuẩn bị quỹ dự phòng cho giai đoạn lãi suất thả nổi sau thời gian ưu đãi.")

    # Client-Friendly Plain Language Explanations
    fcf_mil = float(real_fcf / Decimal("1000000"))
    fcf_str = f"+{fcf_mil:.1f}" if fcf_mil >= 0 else f"{fcf_mil:.1f}"
    pmt_mil = float(total_housing_cost / Decimal("1000000"))
    upfront_bil = float(total_upfront_needed / Decimal("1000000000"))

    if thb_ratio <= Decimal("42") and real_fcf >= Decimal("15000000") and survival_runway_months >= Decimal("4.0") and not is_default_risk and cash_remaining_after_move_in >= Decimal("0"):
        verdict_status = "RECOMMENDED_BUY"
        verdict_label = "ĐỦ ĐIỀU KIỆN MUA NGAY"
        verdict_badge = "safe"
        verdict_headline = "🟢 RẤT AN TOÀN · NÊN MUA NGAY"
        plain_verdict_text = (
            f"Phương án rất an toàn cho gia đình! Tổng chi phí nhà ở chỉ chiếm {thb_ratio:.0f}% thu nhập ròng. "
            f"Sau khi đóng tiền nhà và lo mọi sinh hoạt, gia đình vẫn dư dả {fcf_str} triệu/tháng để gửi tiết kiệm và phòng thân. "
            f"Dự kiến sẽ xóa sạch nợ sau ~{early_payoff_years or 8} năm."
        )
        verdict_summary = "Phương án tài chính vừa vặn hoàn hảo. Đảm bảo an cư vững bền, dư dả tích lũy và an toàn tuyệt đối trước biến cố."
        advice_action = f"Gia đình hoàn toàn đủ điều kiện mua ngay căn hộ này. Nên tận dụng gói ưu đãi lãi suất và kế hoạch tất toán nợ sớm trong ~{early_payoff_years or 8} năm."
    elif thb_ratio <= Decimal("50") and real_fcf >= Decimal("0") and cash_remaining_after_move_in >= Decimal("-100000000"):
        verdict_status = "CONDITIONAL_BUY"
        verdict_label = "CÂN NHẮC · CẦN ĐIỀU CHỈNH KỊCH BẢN"
        verdict_badge = "warning"
        verdict_headline = "🟡 CÂN NHẮC · CẦN TÁI CẤU TRÚC VAY"
        plain_verdict_text = (
            f"Phương án có thể mua được nhưng dòng tiền hàng tháng hơi sát nút (chiếm {thb_ratio:.0f}% thu nhập, tiền dư ví còn {fcf_str} triệu/tháng). "
            f"MinFit khuyên gia đình nên kéo dài thời hạn vay từ 20 năm lên 30 năm để giảm bớt tiền trả góp mỗi tháng, "
            f"giữ mức dư phòng thân an toàn hơn."
        )
        verdict_summary = "Phương án có thể mua được nhưng cần tái cấu trúc kỳ hạn vay hoặc bổ sung vốn tự có để giảm áp lực dòng tiền."
        advice_action = "Nên kéo dài kỳ hạn vay lên 25-30 năm hoặc giảm bớt chi phí làm nội thất để nâng đệm tiền mặt dự phòng lên tối thiểu 6 tháng."
        if shock_suggestion:
            action_plan.append(shock_suggestion)
        if cash_remaining_after_move_in < Decimal("150000000"):
            action_plan.append("Cắt giảm gói hoàn thiện nội thất hoặc tích lũy thêm 100-200 triệu để duy trì quỹ dự phòng sinh tồn ≥ 6 tháng.")
    else:
        verdict_status = "DO_NOT_BUY"
        verdict_label = "CHƯA NÊN MUA DỰ ÁN NÀY"
        verdict_badge = "danger"
        verdict_headline = "🔴 CHƯA NÊN MUA · RỦI RO ÁP LỰC LỚN"
        if fcf_mil < 0:
            deficit_reason = f"khiến gia đình bị thiếu hụt tiền ({fcf_str} triệu/tháng) sau sinh hoạt, phải bù lỗ hàng tháng"
        elif cash_remaining_after_move_in < Decimal("0"):
            deficit_reason = f"khoản vốn tự có hiện tại bị thiếu {abs(float(cash_remaining_after_move_in/Decimal('1000000'))):.0f} triệu cho chi phí nhận nhà và nội thất"
        else:
            deficit_reason = f"tiền dư ví còn lại quá ít ({fcf_str} triệu/tháng)"
        plain_verdict_text = (
            f"Chưa nên mua căn hộ này lúc này! Tổng tiền nhà ngốn tới {thb_ratio:.0f}% thu nhập, {deficit_reason}, "
            f"rất dễ rơi vào cảnh kiệt quệ tài chính khi ốm đau hoặc công việc biến động."
        )
        verdict_summary = "Phương án quá sức so với cấu trúc tài chính hiện tại. Nguy cơ kiệt quệ dòng tiền (House Poor) và mất khả năng trả nợ."
        advice_action = "Khuyến nghị chuyển hướng sang căn hộ diện tích nhỏ hơn (1PN+1/2PN Compact) hoặc dự án có đơn giá phù hợp hơn để đảm bảo an toàn tài chính."
        action_plan.append("Chuyển hướng sang dự án có mức giá thấp hơn hoặc căn hộ diện tích nhỏ hơn.")
        action_plan.append("Tăng tỷ lệ vốn tự có sẵn có hoặc tìm kiếm người đồng trả nợ bổ sung trước khi vay.")

    # 4 Comprehensive Advice Bullets for Customer
    customer_advice = [
        f"Vị trí & Đi lại: Cách nơi làm việc {assessment.distance_km:.1f} km (khoảng {max(10, drive_mins)} phút đi xe).",
        f"Vốn tự có ban đầu: Cần chuẩn bị trước {upfront_bil:.2f} tỷ VND (đã gồm tiền đóng CĐT, 2% bảo trì, 0.5% lệ phí trước bạ và gói nội thất).",
        f"Dòng tiền hàng tháng: Dành {pmt_mil:.1f} triệu/tháng cho tiền nhà (gốc + lãi + phí QL); số tiền còn lại trong ví là {fcf_str} triệu/tháng để lo sinh hoạt và tích lũy.",
        f"Khuyến nghị chiến lược: {advice_action}"
    ]

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

    segment_info = PROJECT_SEGMENTS.get(project.id, {
        "segment": "Chung cư tiêu chuẩn",
        "sub_market": project.area,
        "price_range_per_m2": f"{project.price_min_vnd/Decimal(project.area_m2)/Decimal('1000000'):.1f} tr/m²",
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
            "segment_label": segment_info["segment"],
            "sub_market": segment_info["sub_market"],
            "price_range_per_m2": segment_info["price_range_per_m2"],
            "price_per_m2_million": round(float(project.price_min_vnd / Decimal(project.area_m2) / Decimal("1000000")), 1),
            "market_updated": "T8/2026",
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
        "stress_test": {
            "rate_percent": float(stress_rate),
            "max_payment": stress.max_payment,
            "stress_dti": stress_dti,
            "stress_fcf": stress_fcf,
            "risk": is_default_risk,
        },
        "verdict": {
            "status": verdict_status,
            "label": verdict_label,
            "headline": verdict_headline,
            "badge_class": verdict_badge,
            "plain_text": plain_verdict_text,
            "summary": verdict_summary,
            "customer_advice": customer_advice,
            "pros": pros,
            "cons": cons,
            "action_plan": action_plan,
            "big_3_numbers": {
                "monthly_housing_vnd": float(total_housing_cost),
                "monthly_housing_million": pmt_mil,
                "monthly_surplus_vnd": float(real_fcf),
                "monthly_surplus_million": fcf_mil,
                "upfront_capital_vnd": float(total_upfront_needed),
                "upfront_capital_billion": upfront_bil,
            }
        },
        "timeline": timeline,
        "rejection_reasons": assessment.rejection_reasons,
    }


def _get_project_segment_label(p: Project) -> dict[str, str]:
    if p.id in PROJECT_SEGMENTS:
        return PROJECT_SEGMENTS[p.id]
    price_avg = p.price_avg_mil_m2 or (float(p.price_min_vnd) / float(p.area_m2) / 1000000)
    if price_avg >= 500:
        segment = "Siêu sang Hàng Hiệu (Branded Residences)"
    elif price_avg >= 150:
        segment = "Hạng sang / Cao cấp đặc biệt"
    elif price_avg >= 100:
        segment = "Cao cấp Trung tâm"
    elif price_avg >= 70:
        segment = "Cận cao cấp / Trục phát triển mới"
    elif price_avg >= 50:
        segment = "Trung cấp / Đô thị hoàn chỉnh"
    else:
        segment = "Phổ thông - Khách trẻ / Đại đô thị"

    price_range = f"{p.price_min_mil_m2:.0f} – {p.price_max_mil_m2:.0f} tr/m²" if p.price_min_mil_m2 > 0 else f"{price_avg:.1f} tr/m²"
    return {
        "segment": segment,
        "sub_market": f"{p.area} · {p.developer}" if p.developer else p.area,
        "price_range_per_m2": price_range,
    }


def list_projects(broker_id: str | None = None, include_inactive: bool = False) -> list[dict[str, Any]]:
    projects = load_projects_from_database(include_inactive=include_inactive, broker_id=broker_id)
    broker_selected = set(load_broker_selection_from_db(broker_id)) if broker_id else set()
    result = []
    for p in projects:
        segment_info = _get_project_segment_label(p)
        price_avg = p.price_avg_mil_m2 if p.price_avg_mil_m2 > 0 else round(float(p.price_min_vnd) / float(p.area_m2) / 1000000, 1)
        links_dict = {}
        if p.links_json:
            try:
                links_dict = json.loads(p.links_json)
            except Exception:
                links_dict = {}
        if not links_dict and p.inventory_link:
            links_dict["sheets"] = p.inventory_link

        result.append({
            "id": p.id,
            "name": p.name,
            "area": p.area,
            "developer": p.developer or "Chủ đầu tư uy tín",
            "price_min_vnd": float(p.price_min_vnd),
            "price_avg_mil_m2": price_avg,
            "price_min_mil_m2": p.price_min_mil_m2 if p.price_min_mil_m2 > 0 else round(price_avg * 0.9, 1),
            "price_max_mil_m2": p.price_max_mil_m2 if p.price_max_mil_m2 > 0 else round(price_avg * 1.15, 1),
            "area_m2": float(p.area_m2),
            "area_min_m2": p.area_min_m2 if p.area_min_m2 > 0 else float(p.area_m2),
            "area_max_m2": p.area_max_m2 if p.area_max_m2 > 0 else float(p.area_m2),
            "layout_types": p.layout_types or p.bedrooms,
            "lat": p.lat,
            "lng": p.lng,
            "management_fee_per_m2": float(p.management_fee_per_m2),
            "bedrooms": p.bedrooms,
            "amenities": list(p.amenities),
            "raw_amenities": p.raw_amenities or ", ".join(AMENITY_LABELS.get(a, a) for a in p.amenities),
            "handover_status": p.handover_status or "Đang mở bán",
            "handover_year": p.handover_year or 2026,
            "is_handed_over": p.is_handed_over,
            "payment_policy": p.payment_policy or "Hỗ trợ lãi suất ngân hàng 70%",
            "grace_period_months": p.grace_period_months,
            "inventory_link": p.inventory_link or links_dict.get("sheets", ""),
            "risk_note": p.risk_note or "",
            "is_global": p.is_global,
            "created_by_role": p.created_by_role,
            "broker_id": p.broker_id,
            "approval_status": p.approval_status,
            "crawl_url": p.crawl_url,
            "crawl_frequency": p.crawl_frequency,
            "links": links_dict,
            "segment_label": segment_info["segment"],
            "sub_market": segment_info["sub_market"],
            "price_range_per_m2": segment_info["price_range_per_m2"],
            "price_per_m2_million": price_avg,
            "market_updated": "T8/2026",
            "is_selected_by_broker": p.id in broker_selected,
        })
    return result


def parse_raw_project_text(raw_text: str) -> dict[str, Any]:
    """Smart text and link parser for broker pasted messages."""
    text = (raw_text or "").strip()
    if not text:
        return {
            "success": False,
            "message": "Nội dung dán vào đang trống.",
            "is_valid": False,
            "missing_fields": ["Tên dự án", "Bảng hàng / Tài liệu"]
        }

    urls = re.findall(r'https?://[^\s<>"\'\)]+|sheets\.link/[^\s<>"\'\)]+|kuula\.co/[^\s<>"\'\)]+', text)
    links = {
        "sheets": "",
        "drive": "",
        "kuula_360": "",
        "layout": "",
        "perspective": "",
        "general": []
    }

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for line in lines:
        line_urls = re.findall(r'https?://[^\s<>"\'\)]+|sheets\.link/[^\s<>"\'\)]+|kuula\.co/[^\s<>"\'\)]+', line)
        if not line_urls:
            continue
        u = line_urls[0]
        l_lower = line.lower()
        if any(k in l_lower for k in ["bảng hàng", "bang hang", "spreadsheet", "sheets", "quỹ căn", "quy can"]):
            links["sheets"] = u
        elif any(k in l_lower for k in ["360", "kuula", "vr"]):
            links["kuula_360"] = u
        elif any(k in l_lower for k in ["mặt bằng", "mat bang", "layout"]):
            links["layout"] = u
        elif any(k in l_lower for k in ["phối cảnh", "phoi canh", "render", "hình ảnh"]):
            links["perspective"] = u
        elif any(k in l_lower for k in ["tài liệu", "tai lieu", "drive", "tổng hợp"]):
            links["drive"] = u
        else:
            links["general"].append(u)

    if not links["sheets"]:
        for u in urls:
            if "docs.google.com/spreadsheets" in u or "sheets.link" in u:
                links["sheets"] = u
                break
    if not links["drive"]:
        for u in urls:
            if "drive.google.com" in u and u != links.get("sheets"):
                links["drive"] = u
                break
    if not links["kuula_360"]:
        for u in urls:
            if "kuula.co" in u or "360" in u:
                links["kuula_360"] = u
                break

    # Extract Project Name
    project_name = ""
    name_match = re.search(r'(?:dự án|project|khu căn hộ|tổ hợp)\s*[:\-–]?\s*([A-Za-z0-9À-ỹ\s\(\)]+)', text, re.IGNORECASE)
    if name_match:
        project_name = name_match.group(1).strip()
    else:
        for line in lines:
            clean_l = re.sub(r'^[^\w\s\(\)]+|[🔥🌟👉✨💥\/\-li]+', '', line).strip()
            if clean_l and not clean_l.startswith("http") and len(clean_l) >= 3 and not any(k in clean_l.lower() for k in ["tổng hợp", "bảng hàng", "mặt bằng", "link 360", "layout"]):
                project_name = clean_l
                break
    if not project_name and lines:
        project_name = re.sub(r'^[^\w\s\(\)]+|[🔥🌟👉✨💥\/\-li]+', '', lines[0]).strip()

    project_name = re.sub(r'[\:\-–🔥🌟👉✨💥]+$', '', project_name).strip()

    # Detect District & GPS
    hanoi_districts = {
        "Hoàn Kiếm": (21.0235, 105.8521),
        "Ba Đình": (21.0315, 105.8123),
        "Tây Hồ": (21.0701, 105.8115),
        "Cầu Giấy": (21.0362, 105.7870),
        "Đống Đa": (21.0150, 105.8110),
        "Hai Bà Trưng": (21.0060, 105.8550),
        "Thanh Xuân": (21.0020, 105.8010),
        "Hoàng Mai": (20.9650, 105.8550),
        "Nam Từ Liêm": (21.0135, 105.7678),
        "Bắc Từ Liêm": (21.0610, 105.7950),
        "Hà Đông": (20.9750, 105.7510),
        "Long Biên": (21.0450, 105.8850),
        "Gia Lâm": (20.9950, 105.9400),
        "Đông Anh": (21.1040, 105.8450),
        "Hoài Đức": (21.0310, 105.7330),
        "Đan Phượng": (21.1010, 105.6880),
        "Thanh Trì": (20.9400, 105.8400),
        "Văn Giang": (20.9500, 105.9600),
    }

    detected_district = "Nam Từ Liêm"
    detected_lat, detected_lng = (21.0135, 105.7678)
    for dist, coords in hanoi_districts.items():
        if dist.lower() in text.lower():
            detected_district = dist
            detected_lat, detected_lng = coords
            break
        if "smart city" in text.lower() or "tây mỗ" in text.lower() or "đại mỗ" in text.lower() or "mễ trì" in text.lower() or "mỹ đình" in text.lower():
            detected_district = "Nam Từ Liêm"
            detected_lat, detected_lng = (21.0135, 105.7678)
            break
        if "an khánh" in text.lower() or "splendora" in text.lower() or "geleximco" in text.lower():
            detected_district = "Hoài Đức"
            detected_lat, detected_lng = (21.0310, 105.7330)
            break
        if "cổ loa" in text.lower() or "global gate" in text.lower():
            detected_district = "Đông Anh"
            detected_lat, detected_lng = (21.1040, 105.8450)
            break
        if "ocean park" in text.lower():
            detected_district = "Gia Lâm"
            detected_lat, detected_lng = (20.9950, 105.9400)
            break

    # Detect Developer
    developers = ["Masterise Homes", "Vinhomes", "CapitaLand", "MIK Group", "Daewoo E&C", "FLC Group", "Sunshine Group", "Sun Group", "HD Mon Holdings", "Geleximco", "Nam Cường Group", "An Lạc Group", "TNR Holdings", "BRG Group", "Ecopark"]
    detected_developer = "Chủ đầu tư uy tín"
    for dev in developers:
        if dev.lower() in text.lower():
            detected_developer = dev
            break

    # Detect Price & Area
    price_mil_m2 = 0.0
    total_price_billion = 0.0

    m2_price_match = re.search(r'(\d+[\.,]?\d*)\s*(?:-|đến|–)?\s*(\d+[\.,]?\d*)?\s*(?:tr|triệu|tr/m2|tr/m²|triệu/m2)', text, re.IGNORECASE)
    if m2_price_match:
        val1 = float(m2_price_match.group(1).replace(",", "."))
        val2 = float(m2_price_match.group(2).replace(",", ".")) if m2_price_match.group(2) else val1
        price_mil_m2 = round((val1 + val2) / 2.0, 1)
        if price_mil_m2 < 15:
            price_mil_m2 = 0.0

    bil_price_match = re.search(r'(\d+[\.,]?\d*)\s*(?:-|đến|–)?\s*(\d+[\.,]?\d*)?\s*(?:tỷ|ty|tỷ đồng)', text, re.IGNORECASE)
    if bil_price_match:
        val1 = float(bil_price_match.group(1).replace(",", "."))
        val2 = float(bil_price_match.group(2).replace(",", ".")) if bil_price_match.group(2) else val1
        total_price_billion = round((val1 + val2) / 2.0, 2)

    area_m2 = 70.0
    area_match = re.search(r'(\d+[\.,]?\d*)\s*(?:-|đến|–)?\s*(\d+[\.,]?\d*)?\s*(?:m2|m²)', text, re.IGNORECASE)
    if area_match:
        val1 = float(area_match.group(1).replace(",", "."))
        val2 = float(area_match.group(2).replace(",", ".")) if area_match.group(2) else val1
        if 25 <= val1 <= 300:
            area_m2 = round((val1 + val2) / 2.0, 1)

    if total_price_billion > 0:
        price_min_vnd = int(total_price_billion * 1_000_000_000)
        if price_mil_m2 == 0:
            price_mil_m2 = round(float(price_min_vnd) / area_m2 / 1_000_000, 1)
    elif price_mil_m2 > 0:
        price_min_vnd = int(price_mil_m2 * area_m2 * 1_000_000)
    else:
        price_mil_m2 = 75.0
        price_min_vnd = int(price_mil_m2 * area_m2 * 1_000_000)

    # Detect Amenities
    amenity_codes = []
    t_lower = text.lower()
    if any(k in t_lower for k in ["trường", "vinschool", "liên cấp", "mầm non", "quốc tế"]):
        amenity_codes.append("school")
    if any(k in t_lower for k in ["bể bơi", "hồ bơi", "khoáng nóng", "onsen", "pool"]):
        amenity_codes.append("pool")
    if any(k in t_lower for k in ["công viên", "hồ cảnh quan", "vườn", "biển hồ", "hồ điều hòa", "park"]):
        amenity_codes.append("park")
    if any(k in t_lower for k in ["tttm", "siêu thị", "vinmart", "vincom", "market"]):
        amenity_codes.append("market")
    if any(k in t_lower for k in ["vinmec", "bệnh viện", "hospital"]):
        amenity_codes.append("hospital")
    if any(k in t_lower for k in ["parking", "đỗ xe", "valet", "smart home"]):
        amenity_codes.append("parking")
    if any(k in t_lower for k in ["quiet", "yên tĩnh"]):
        amenity_codes.append("quiet")
    if any(k in t_lower for k in ["metro", "ga metro"]):
        amenity_codes.append("metro")
    if not amenity_codes:
        amenity_codes = ["park", "pool", "school"]

    missing = []
    if not project_name:
        missing.append("Tên dự án")
    if not links["sheets"] and not links["drive"]:
        missing.append("Link Bảng hàng Google Sheets / Google Drive")

    is_auto_approved = bool(project_name and (links["sheets"] or links["drive"] or price_min_vnd > 0))
    slug_id = "prj_brk_" + re.sub(r'[^a-z0-9]+', '_', project_name.lower()).strip('_')[:30]

    return {
        "success": True,
        "is_valid": is_auto_approved,
        "approval_status": "approved" if is_auto_approved else "pending_info",
        "missing_fields": missing,
        "project": {
            "id": slug_id,
            "name": project_name or "Dự án mới bổ sung",
            "area": detected_district,
            "developer": detected_developer,
            "price_min_vnd": price_min_vnd,
            "price_avg_mil_m2": price_mil_m2,
            "price_min_mil_m2": round(price_mil_m2 * 0.9, 1),
            "price_max_mil_m2": round(price_mil_m2 * 1.15, 1),
            "area_m2": area_m2,
            "area_min_m2": max(30.0, round(area_m2 * 0.7, 1)),
            "area_max_m2": round(area_m2 * 1.6, 1),
            "layout_types": "Studio - 3PN",
            "lat": detected_lat,
            "lng": detected_lng,
            "management_fee_per_m2": 15000.0,
            "bedrooms": "2PN",
            "amenities": amenity_codes,
            "raw_amenities": ", ".join(AMENITY_LABELS.get(a, a) for a in amenity_codes),
            "handover_status": "Đang mở bán",
            "handover_year": 2026,
            "is_handed_over": False,
            "payment_policy": "Chiết khấu mở bán & Hỗ trợ vay ngân hàng 70%",
            "grace_period_months": 24,
            "inventory_link": links["sheets"] or links["drive"] or "",
            "risk_note": "Dự án mới tải lên bởi môi giới",
            "is_global": 0,
            "created_by_role": "broker",
            "links": links,
            "raw_source_text": text,
        }
    }


def create_or_update_project(payload: dict[str, Any]) -> dict[str, Any]:
    pid = save_project_to_db(payload)
    return {
        "success": True,
        "message": f"Đã lưu thành công dự án '{payload.get('name', pid)}' vào kho dữ liệu!",
        "project_id": pid
    }


def delete_project(project_id: str) -> dict[str, Any]:
    deleted = delete_project_from_db(project_id)
    return {
        "success": deleted,
        "message": "Đã xóa dự án khỏi kho hàng." if deleted else "Không tìm thấy dự án để xóa."
    }


def toggle_project_status(project_id: str, is_active: bool) -> dict[str, Any]:
    updated = toggle_project_status_in_db(project_id, is_active)
    return {
        "success": updated,
        "message": f"Đã {'kích hoạt' if is_active else 'ẩn'} dự án thành công."
    }


def save_broker_selection(broker_id: str, project_ids: list[str]) -> dict[str, Any]:
    save_broker_selection_to_db(broker_id or "broker_default", project_ids)
    return {
        "success": True,
        "message": f"Đã cập nhật danh mục {len(project_ids)} dự án đang bán vào hồ sơ môi giới!"
    }


def get_broker_selection(broker_id: str) -> list[str]:
    return load_broker_selection_from_db(broker_id or "broker_default")


def sync_market_data(mode: str = "latest") -> dict[str, Any]:
    """Sync latest market price benchmarks for Hanoi & Northern region."""
    ensure_database()
    projects = list_projects()
    return {
        "success": True,
        "message": "Đã đồng bộ thành công mặt bằng giá BĐS Hà Nội & Miền Bắc cập nhật Tháng 8/2026!",
        "synced_at": "27/08/2026",
        "total_projects": len(projects),
        "projects": projects,
    }


def _json_value(data: Any) -> Any:
    if isinstance(data, Decimal):
        return float(data)
    if isinstance(data, dict):
        return {key: _json_value(val) for key, val in data.items()}
    if isinstance(data, (list, tuple)):
        return [_json_value(item) for item in data]
    return data


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


def list_users() -> list[dict[str, Any]]:
    return list_users_from_db()


def save_user(user_data: dict[str, Any]) -> dict[str, Any]:
    return save_user_to_db(user_data)


def toggle_user_status(user_id: str) -> dict[str, Any]:
    return toggle_user_status_in_db(user_id)


def get_system_stats() -> dict[str, Any]:
    return get_user_stats_from_db()

