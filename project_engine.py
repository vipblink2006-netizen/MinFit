from __future__ import annotations

import json
import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from loan_dti import (
    FinancialProfile,
    LoanAnalysis,
    LoanScenario,
    annuity_payment,
    calculate_dti_score,
    calculate_ltv_score,
    decimal_value,
    linear_interpolate,
    simulate_loan,
)

PERSONA_WEIGHTS = {
    "single": {
        "finance": Decimal("0.70"),
        "convenience": Decimal("0.30"),
        "price": Decimal("0.70"),
        "distance": Decimal("0.15"),
        "amenities": Decimal("0.15"),
    },
    "young_couple": {
        "finance": Decimal("0.60"),
        "convenience": Decimal("0.40"),
        "price": Decimal("0.60"),
        "distance": Decimal("0.20"),
        "amenities": Decimal("0.20"),
    },
    "family_with_children": {
        "finance": Decimal("0.50"),
        "convenience": Decimal("0.50"),
        "price": Decimal("0.50"),
        "distance": Decimal("0.25"),
        "amenities": Decimal("0.25"),
    },
    "retired": {
        "finance": Decimal("0.40"),
        "convenience": Decimal("0.60"),
        "price": Decimal("0.40"),
        "distance": Decimal("0.20"),
        "amenities": Decimal("0.40"),
    },
}

AMENITY_LABELS = {
    "school": "Trường học nội khu",
    "park": "Công viên cây xanh",
    "parking": "Chỗ đỗ xe ô tô",
    "quiet": "Không gian yên tĩnh",
    "pool": "Hồ bơi 4 mùa",
    "metro": "Gần metro / xe buýt",
    "hospital": "Bệnh viện / trạm y tế",
    "market": "Chợ / siêu thị",
    "gym": "Phòng gym & thể thao",
}

MUST_HAVE_AMENITIES = {"school", "park", "parking", "hospital", "market"}
NICE_TO_HAVE_AMENITIES = {"pool", "quiet", "metro", "gym"}


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    area: str
    price_min_vnd: Decimal
    area_m2: Decimal
    lat: float
    lng: float
    management_fee_per_m2: Decimal
    bedrooms: str
    amenities: tuple[str, ...]
    developer: str = ""
    price_avg_mil_m2: float = 0.0
    price_min_mil_m2: float = 0.0
    price_max_mil_m2: float = 0.0
    area_min_m2: float = 0.0
    area_max_m2: float = 0.0
    layout_types: str = ""
    raw_amenities: str = ""
    handover_status: str = ""
    handover_year: int = 0
    is_handed_over: bool = False
    payment_policy: str = ""
    grace_period_months: int = 0
    inventory_link: str = ""
    updated_at: str = ""
    risk_note: str = ""
    is_global: int = 1
    created_by_role: str = "admin"
    broker_id: str = ""
    approval_status: str = "approved"
    crawl_url: str = ""
    crawl_frequency: str = "daily"
    links_json: str = "{}"
    units_json: str = "[]"
    raw_source_text: str = ""

    @property
    def monthly_management_fee(self) -> Decimal:
        return self.area_m2 * self.management_fee_per_m2


@dataclass(frozen=True)
class HardFilterItem:
    key: str
    name: str
    value_display: str
    status: Literal["safe", "warning", "reject"]
    threshold_safe: str
    threshold_warning: str
    threshold_reject: str
    note: str


@dataclass(frozen=True)
class ValueForMoney:
    ic_ratio: float
    verdict_label: str
    badge_class: str
    monthly_benefit: Decimal
    monthly_cost: Decimal
    rent_equivalent: Decimal
    commute_saving: Decimal
    amenity_benefit: Decimal
    interest_cost: Decimal
    mgmt_fee: Decimal
    opportunity_cost_equity: Decimal
    tax_monthly: Decimal


@dataclass(frozen=True)
class SmartAmortization:
    has_intro_benefit: bool
    monthly_savings: Decimal
    accumulated_reserve: Decimal
    original_floating_pmt: Decimal
    optimized_floating_pmt: Decimal
    monthly_pmt_reduction: Decimal
    reduction_percent: float
    advice_text: str


@dataclass(frozen=True)
class ProjectAssessment:
    project: Project
    analysis: LoanAnalysis
    rank_class: Literal["A", "B", "C"]
    hard_filter_status: Literal["PASS", "WARNING", "REJECT"]
    hard_filters_breakdown: tuple[HardFilterItem, ...]
    down_payment: Decimal
    reserve_after_purchase: Decimal
    distance_km: Decimal
    finance_score: Decimal
    distance_score: Decimal
    amenity_score: Decimal
    convenience_score: Decimal
    total_score: Decimal
    status_label: str
    matched_amenities: tuple[str, ...]
    missing_amenities: tuple[str, ...]
    value_for_money: ValueForMoney
    smart_amortization: SmartAmortization
    rejection_reasons: tuple[str, ...]
    warning_reasons: tuple[str, ...]

    @property
    def is_eligible(self) -> bool:
        return self.rank_class in ("A", "B")


def load_projects(path: str | Path) -> list[Project]:
    raw_projects = json.loads(Path(path).read_text(encoding="utf-8"))
    projects = []
    for item in raw_projects:
        p = Project(
            id=item["id"],
            name=item["name"],
            area=item["area"],
            price_min_vnd=decimal_value(item["price_min_vnd"]),
            area_m2=decimal_value(item["area_m2"]),
            lat=float(item["lat"]),
            lng=float(item["lng"]),
            management_fee_per_m2=decimal_value(item["management_fee_per_m2"]),
            bedrooms=item["bedrooms"],
            amenities=tuple(item.get("amenities", ())),
            developer=item.get("developer", ""),
            price_avg_mil_m2=float(item.get("price_avg_mil_m2", 0.0)),
            price_min_mil_m2=float(item.get("price_min_mil_m2", 0.0)),
            price_max_mil_m2=float(item.get("price_max_mil_m2", 0.0)),
            area_min_m2=float(item.get("area_min_m2", 0.0)),
            area_max_m2=float(item.get("area_max_m2", 0.0)),
            layout_types=item.get("layout_types", ""),
            raw_amenities=item.get("raw_amenities", ""),
            handover_status=item.get("handover_status", ""),
            handover_year=int(item.get("handover_year", 0)),
            is_handed_over=bool(item.get("is_handed_over", False)),
            payment_policy=item.get("payment_policy", ""),
            grace_period_months=int(item.get("grace_period_months", 0)),
            inventory_link=item.get("inventory_link", ""),
            updated_at=item.get("updated_at", ""),
            risk_note=item.get("risk_note", ""),
            is_global=int(item.get("is_global", 1)),
            created_by_role=item.get("created_by_role", "admin"),
            broker_id=item.get("broker_id", ""),
            approval_status=item.get("approval_status", "approved"),
            crawl_url=item.get("crawl_url", ""),
            crawl_frequency=item.get("crawl_frequency", "daily"),
            links_json=json.dumps(item.get("links", {})),
            units_json=json.dumps(item.get("units", [])),
            raw_source_text=item.get("raw_source_text", ""),
        )
        projects.append(p)
    return projects


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> Decimal:
    earth_radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    value = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    distance = earth_radius_km * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))
    return Decimal(str(distance))


def assess_project(
    project: Project,
    profile: FinancialProfile,
    scenario: LoanScenario,
    persona: str,
    workplace_lat: float,
    workplace_lng: float,
    required_amenities: tuple[str, ...],
    weights_config: dict[str, dict[str, Decimal]] | None = None,
    client_age: int = 32,
    cic_status: str = "clean",
) -> ProjectAssessment:
    """
    Quy trình Thẩm định 4 Bước Chuẩn mực:
    Bước 1: Lọc Pháp lý & Nhân thân (Hard Legal)
    Bước 2: Lọc Tài chính Cứng (8 Hard Filters)
    Bước 3: Chấm điểm thành phần (Nội suy tuyến tính DTI, LTV, Khoảng cách, Tiện ích, Giá trị I/C)
    Bước 4: Trọng số theo chân dung & Xếp hạng phân lớp Hạng A/B/C
    """
    # ----------------------------------------------------
    # BƯỚC 1: LỌC PHÁP LÝ & NHÂN THÂN
    # ----------------------------------------------------
    legal_reject_reasons: list[str] = []
    if client_age < 18:
        legal_reject_reasons.append("Khách hàng chưa đủ 18 tuổi theo quy định BLDS.")
    end_age = client_age + scenario.term_years
    if end_age > 70:
        legal_reject_reasons.append(f"Độ tuổi kết thúc vay ({end_age} tuổi) vượt quá trần quy định (≤ 70 tuổi).")
    if cic_status != "clean":
        legal_reject_reasons.append("Lịch sử tín dụng CIC có nợ chú ý/nợ xấu trong 12 tháng qua.")

    # ----------------------------------------------------
    # MÔ PHỎNG DÒNG TIỀN (LOAN SIMULATION)
    # ----------------------------------------------------
    ltv = scenario.loan_ratio_percent / Decimal("100")
    down_payment = project.price_min_vnd * (Decimal("1") - ltv)
    reserve_after_purchase = profile.available_cash - down_payment
    analysis = simulate_loan(
        profile=profile,
        scenario=scenario,
        project_price=project.price_min_vnd,
        monthly_management_fee=project.monthly_management_fee,
        liquid_reserve_after_purchase=max(reserve_after_purchase, Decimal("0")),
    )

    # ----------------------------------------------------
    # BƯỚC 2: 8 HARD FINANCIAL FILTERS
    # ----------------------------------------------------
    hard_items: list[HardFilterItem] = []
    financial_rejects: list[str] = []
    financial_warnings: list[str] = []

    # 1. LTV Filter
    ltv_pct = float(scenario.loan_ratio_percent)
    if ltv_pct <= 80.0:
        ltv_status = "safe"
        ltv_note = "Tỷ lệ vay trong ngưỡng an toàn chuẩn ngân hàng."
    elif ltv_pct <= 90.0:
        ltv_status = "warning"
        ltv_note = "Tỷ lệ vay 80-90% khá cao, đòi hỏi đòn bẩy lớn."
        financial_warnings.append(f"Tỷ lệ vay LTV ({ltv_pct:.0f}%) thuộc vùng cảnh báo (80-90%).")
    else:
        ltv_status = "reject"
        ltv_note = "Tỷ lệ vay vượt 90%, ngân hàng không hỗ trợ."
        financial_rejects.append(f"LTV vượt 90% ({ltv_pct:.0f}%).")

    hard_items.append(HardFilterItem(
        key="ltv",
        name="Tỷ lệ vay LTV",
        value_display=f"{ltv_pct:.0f}%",
        status=ltv_status,
        threshold_safe="≤ 80%",
        threshold_warning="80% – 90%",
        threshold_reject="> 90%",
        note=ltv_note
    ))

    # 2. DTI Hiện tại & Max DTI
    max_dti_pct = float(analysis.max_dti * 100)
    if max_dti_pct <= 50.0:
        dti_status = "safe"
        dti_note = f"DTI cao nhất đạt {max_dti_pct:.1f}%, gia đình hoàn toàn kiểm soát được nợ."
    elif max_dti_pct <= 60.0:
        dti_status = "warning"
        dti_note = f"DTI chạm mức {max_dti_pct:.1f}% tại tháng {analysis.max_dti_month} (vùng cảnh báo 50-60%)."
        financial_warnings.append(f"DTI cao ({max_dti_pct:.1f}%) tại tháng {analysis.max_dti_month}.")
    else:
        dti_status = "reject"
        dti_note = f"DTI chạm {max_dti_pct:.1f}% tại tháng {analysis.max_dti_month}, vượt ngưỡng trần 60%."
        financial_rejects.append(f"DTI vượt 60% ({max_dti_pct:.1f}%) tại tháng {analysis.max_dti_month}.")

    hard_items.append(HardFilterItem(
        key="dti",
        name="Tỷ lệ nợ / Thu nhập (DTI)",
        value_display=f"{max_dti_pct:.1f}%",
        status=dti_status,
        threshold_safe="≤ 50%",
        threshold_warning="50% – 60%",
        threshold_reject="> 60%",
        note=dti_note
    ))

    # 3. FCF (Dư địa sống hàng tháng)
    fcf_ratio = float((analysis.min_fcf / profile.monthly_income) * 100) if profile.monthly_income > 0 else 0.0
    fcf_val_mil = float(analysis.min_fcf / Decimal("1000000"))
    if fcf_ratio >= 30.0:
        fcf_status = "safe"
        fcf_note = f"Dư địa tiền tự do đạt +{fcf_val_mil:.1f} tr/tháng ({fcf_ratio:.1f}% thu nhập)."
    elif fcf_ratio >= 15.0:
        fcf_status = "warning"
        fcf_note = f"Dư địa sinh tồn còn +{fcf_val_mil:.1f} tr/tháng ({fcf_ratio:.1f}%), cần chi tiêu tiết kiệm."
        financial_warnings.append(f"Dư địa sống mỏng ({fcf_ratio:.1f}% thu nhập, +{fcf_val_mil:.1f} tr/tháng).")
    else:
        fcf_status = "reject"
        fcf_note = f"Dòng tiền tự do quá thấp hoặc âm ({fcf_val_mil:.1f} tr/tháng, {fcf_ratio:.1f}%)."
        financial_rejects.append(f"Dòng tiền tự do nguy hiểm ({fcf_val_mil:.1f} tr/tháng, {fcf_ratio:.1f}% thu nhập).")

    hard_items.append(HardFilterItem(
        key="fcf",
        name="Dư địa sống (FCF / Thu nhập)",
        value_display=f"{fcf_ratio:.1f}% (+{fcf_val_mil:.1f} tr)",
        status=fcf_status,
        threshold_safe="≥ 30%",
        threshold_warning="15% – 30%",
        threshold_reject="< 15%",
        note=fcf_note
    ))

    # 4. Vốn tự có đối ứng (Equity)
    equity_ratio = float((profile.available_cash / project.price_min_vnd) * 100) if project.price_min_vnd > 0 else 0.0
    if reserve_after_purchase >= Decimal("0"):
        if equity_ratio >= 20.0:
            equity_status = "safe"
            equity_note = f"Vốn tự có sẵn có đạt {equity_ratio:.1f}% giá trị nhà, đủ đóng đối ứng an toàn."
        elif equity_ratio >= 10.0:
            equity_status = "warning"
            equity_note = f"Vốn tự có {equity_ratio:.1f}% ở mức sát nút, cần kiểm soát chi phí nhận nhà."
            financial_warnings.append(f"Vốn tự có ({equity_ratio:.1f}%) sát ngưỡng tối thiểu 20%.")
        else:
            equity_status = "reject"
            equity_note = f"Vốn tự có quá thấp ({equity_ratio:.1f}%)."
            financial_rejects.append(f"Vốn tự có quá thấp ({equity_ratio:.1f}% < 10%).")
    else:
        shortfall = abs(reserve_after_purchase)
        shortfall_mil = float(shortfall / Decimal("1000000"))
        if equity_ratio >= 10.0:
            equity_status = "warning"
            equity_note = f"Thiếu {shortfall_mil:.0f} triệu vốn đối ứng (đạt {equity_ratio:.1f}%), cần huy động thêm từ người thân."
            financial_warnings.append(f"Thiếu {shortfall_mil:.0f} triệu vốn đối ứng, cần vay người thân.")
        else:
            equity_status = "reject"
            equity_note = f"Thiếu {shortfall_mil:.0f} triệu vốn đối ứng (vốn tự có chỉ có {equity_ratio:.1f}%)."
            financial_rejects.append(f"Thiếu {shortfall_mil:.0f} triệu vốn đối ứng ban đầu.")

    hard_items.append(HardFilterItem(
        key="equity",
        name="Vốn tự có ban đầu",
        value_display=f"{equity_ratio:.1f}%",
        status=equity_status,
        threshold_safe="≥ 20%",
        threshold_warning="10% – 20%",
        threshold_reject="< 10%",
        note=equity_note
    ))

    # 5. Stress Test DTI (+3% Lãi suất)
    stress_rate = scenario.phase2_rate_percent + Decimal("3.0")
    stress_pmt = annuity_payment(analysis.initial_loan, stress_rate, scenario.term_months)
    stress_dti = (stress_pmt + profile.existing_debt_payment) / profile.monthly_income if profile.monthly_income > Decimal("0") else Decimal("1.0")
    stress_dti_pct = float(stress_dti * 100)
    if stress_dti_pct <= 55.0:
        stress_status = "safe"
        stress_note = f"Khi lãi suất thị trường tăng thêm +3% ({stress_rate}%), DTI vẫn an toàn ở mức {stress_dti_pct:.1f}%."
    elif stress_dti_pct <= 65.0:
        stress_status = "warning"
        stress_note = f"Khi lãi suất tăng +3%, DTI tăng lên {stress_dti_pct:.1f}% (vùng cảnh báo 55-65%)."
        financial_warnings.append(f"Stress Test lãi suất (+3%): DTI nhảy lên {stress_dti_pct:.1f}%.")
    else:
        stress_status = "reject"
        stress_note = f"Khi lãi suất tăng +3%, DTI vọt lên {stress_dti_pct:.1f}%, nguy cơ vỡ nợ cao."
        financial_rejects.append(f"Stress Test lãi suất (+3%): DTI vượt 65% ({stress_dti_pct:.1f}%).")

    hard_items.append(HardFilterItem(
        key="stress_dti",
        name="Stress DTI (Lãi +3%)",
        value_display=f"{stress_dti_pct:.1f}%",
        status=stress_status,
        threshold_safe="≤ 55%",
        threshold_warning="55% – 65%",
        threshold_reject="> 65%",
        note=stress_note
    ))

    # 6. Tuổi kết thúc khoản vay
    if end_age <= 65:
        age_status = "safe"
        age_note = f"Đáo hạn ở tuổi {end_age}, trước tuổi nghỉ hưu phổ biến."
    elif end_age <= 70:
        age_status = "warning"
        age_note = f"Đáo hạn ở tuổi {end_age} (65-70 tuổi), cần nguồn thu ổn định tuổi xế chiều."
        financial_warnings.append(f"Độ tuổi kết thúc vay ({end_age} tuổi) chạm vùng cảnh báo (65-70).")
    else:
        age_status = "reject"
        age_note = f"Đáo hạn ở tuổi {end_age} vượt trần 70 tuổi."
        financial_rejects.append(f"Độ tuổi kết thúc vay ({end_age} tuổi) vượt quá 70 tuổi.")

    hard_items.append(HardFilterItem(
        key="end_age",
        name="Tuổi kết thúc vay",
        value_display=f"{end_age} tuổi",
        status=age_status,
        threshold_safe="≤ 65 tuổi",
        threshold_warning="65 – 70 tuổi",
        threshold_reject="> 70 tuổi",
        note=age_note
    ))

    # 7. Payment Shock (Điều kiện kép)
    phase1_months = scenario.phase1_months
    grace_months = scenario.effective_grace_months
    transition_month = max(phase1_months, grace_months)
    pmt_intro = analysis.timeline[0].payment if analysis.timeline else analysis.max_payment
    post_transition_rows = [r for r in analysis.timeline if r.month > transition_month]
    pmt_floating = max((r.payment for r in post_transition_rows), default=analysis.max_payment)

    if pmt_intro > Decimal("0"):
        shock_pct = float(((pmt_floating - pmt_intro) / pmt_intro) * 100)
    else:
        shock_pct = 100.0 if pmt_floating > Decimal("0") else 0.0

    dti_floating = (pmt_floating + profile.existing_debt_payment) / profile.monthly_income if profile.monthly_income > Decimal("0") else Decimal("1.0")

    if shock_pct <= 20.0:
        shock_status = "safe"
        shock_note = f"Bước nhảy trả góp nhẹ ({shock_pct:.0f}%), không gây áp lực dòng tiền."
    elif shock_pct <= 50.0:
        shock_status = "warning"
        shock_note = f"Tiền trả góp tăng {shock_pct:.0f}% khi hết ưu đãi (từ {float(pmt_intro/Decimal('1000000')):.1f} tr lên {float(pmt_floating/Decimal('1000000')):.1f} tr)."
        financial_warnings.append(f"Sốc thanh toán {shock_pct:.0f}% khi chuyển sang lãi thả nổi.")
    else:
        # Dual condition check
        if dti_floating > Decimal("0.50") or fcf_ratio < 15.0:
            shock_status = "reject"
            shock_note = f"Tiền nhà tăng {shock_pct:.0f}% và DTI thả nổi vọt lên {float(dti_floating*100):.1f}%, vượt sức chịu đựng."
            financial_rejects.append(f"Sốc thanh toán {shock_pct:.0f}% kèm DTI thả nổi cao ({float(dti_floating*100):.1f}%).")
        else:
            shock_status = "warning"
            shock_note = f"Tiền nhà tăng {shock_pct:.0f}% (ân hạn gốc) nhưng DTI thả nổi vẫn kiểm soát được ({float(dti_floating*100):.1f}%)."
            financial_warnings.append(f"Sốc thanh toán {shock_pct:.0f}% (do hết ân hạn gốc), cần chuẩn bị quỹ dự phòng.")

    hard_items.append(HardFilterItem(
        key="payment_shock",
        name="Sốc thanh toán (Payment Shock)",
        value_display=f"+{shock_pct:.0f}%",
        status=shock_status,
        threshold_safe="≤ 20%",
        threshold_warning="20% – 50%",
        threshold_reject="> 50% & DTI>50%",
        note=shock_note
    ))

    # 8. Pháp lý & Hiện trạng tài sản
    risk_note_lower = project.risk_note.lower()
    if "tranh chấp" in risk_note_lower or "kê biên" in risk_note_lower:
        legal_asset_status = "reject"
        legal_asset_note = f"Cảnh báo pháp lý nghiêm trọng: {project.risk_note}."
        financial_rejects.append(f"Pháp lý dự án có tranh chấp: {project.risk_note}.")
    elif project.approval_status != "approved" or "chú ý" in risk_note_lower:
        legal_asset_status = "warning"
        legal_asset_note = f"Cần thẩm định pháp lý: {project.risk_note or 'Đang chờ phê duyệt hồ sơ'}."
        financial_warnings.append(f"Cần kiểm tra kỹ hồ sơ pháp lý dự án ({project.risk_note}).")
    else:
        legal_asset_status = "safe"
        legal_asset_note = "Pháp lý hoàn chỉnh, đủ điều kiện giao dịch và thế chấp ngân hàng."

    hard_items.append(HardFilterItem(
        key="asset_legal",
        name="Pháp lý dự án",
        value_display="Chuẩn chỉnh" if legal_asset_status == "safe" else "Cần thẩm định",
        status=legal_asset_status,
        threshold_safe="Đầy đủ Sổ/HĐMB",
        threshold_warning="Cần kiểm tra",
        threshold_reject="Tranh chấp/Kê biên",
        note=legal_asset_note
    ))

    # ----------------------------------------------------
    # XẾP HẠNG PHÂN LỚP (RANKING CLASS A / B / C)
    # ----------------------------------------------------
    all_rejects = tuple(legal_reject_reasons + financial_rejects)
    all_warnings = tuple(financial_warnings)

    if legal_reject_reasons or len(financial_rejects) >= 1 or len(financial_warnings) >= 4:
        rank_class: Literal["A", "B", "C"] = "C"
        hard_filter_status: Literal["PASS", "WARNING", "REJECT"] = "REJECT"
    elif len(financial_warnings) >= 1:
        rank_class = "B"
        hard_filter_status = "WARNING"
    else:
        rank_class = "A"
        hard_filter_status = "PASS"

    # ----------------------------------------------------
    # BƯỚC 3: CHẤM ĐIỂM THÀNH PHẦN (NỘI SUY LIÊN TỤC)
    # ----------------------------------------------------
    score_dti = calculate_dti_score(analysis.max_dti)
    score_ltv = calculate_ltv_score(scenario.loan_ratio_percent / Decimal("100"))
    finance_score = round(score_dti * Decimal("0.60") + score_ltv * Decimal("0.40"), 2)

    distance_km = haversine_distance(workplace_lat, workplace_lng, project.lat, project.lng)
    distance_score = Decimal(str(round(100 * math.exp(-float(distance_km) / 12), 2)))

    # Amenity Score with Must-Have (20 pts) & Nice-To-Have (5 pts) Weighting
    matched = tuple(item for item in required_amenities if item in project.amenities)
    missing = tuple(item for item in required_amenities if item not in project.amenities)

    if not required_amenities:
        amenity_score = Decimal("100")
    else:
        must_req = [a for a in required_amenities if a in MUST_HAVE_AMENITIES]
        nice_req = [a for a in required_amenities if a not in MUST_HAVE_AMENITIES]
        must_matched = [a for a in must_req if a in project.amenities]
        nice_matched = [a for a in nice_req if a in project.amenities]

        pts_num = len(must_matched) * 20 + len(nice_matched) * 5
        pts_den = len(must_req) * 20 + len(nice_req) * 5
        amenity_score = Decimal(str(round((pts_num / pts_den) * 100, 2))) if pts_den > 0 else Decimal("100")

    convenience_score = round(distance_score * Decimal("0.50") + amenity_score * Decimal("0.50"), 2)

    # ----------------------------------------------------
    # BƯỚC 4: TRỌNG SỐ THEO CHÂN DUNG & TỔNG ĐIỂM
    # ----------------------------------------------------
    weights = (weights_config or PERSONA_WEIGHTS).get(persona, PERSONA_WEIGHTS["family_with_children"])
    if "finance" in weights and "convenience" in weights:
        total_score = round(
            finance_score * weights["finance"] + convenience_score * weights["convenience"],
            1
        )
    else:
        w_price = weights.get("price", Decimal("0.50"))
        w_distance = weights.get("distance", Decimal("0.25"))
        w_amenities = weights.get("amenities", Decimal("0.25"))
        total_score = round(
            finance_score * w_price + distance_score * w_distance + amenity_score * w_amenities,
            1
        )

    if total_score >= Decimal("85.0"):
        status_label = "RẤT KHẢ THI"
    elif total_score >= Decimal("70.0"):
        status_label = "KHẢ THI"
    elif total_score >= Decimal("50.0"):
        status_label = "CÂN NHẮC"
    else:
        status_label = "KHÔNG KHUYẾN NGHỊ"

    # ----------------------------------------------------
    # TỰ ĐỘNG HÓA CHỈ SỐ ĐÁNG TIỀN (VALUE FOR MONEY - I/C)
    # ----------------------------------------------------
    # Lợi ích hàng tháng (I):
    # 1. Tiền thuê tương đương (~4.5% giá trị căn hộ/năm)
    rent_equiv = round(project.price_min_vnd * Decimal("0.045") / Decimal("12"), 0)

    # 2. Tiết kiệm di chuyển theo khoảng cách thực tế
    dist_val = float(distance_km)
    if dist_val <= 6.0:
        commute_saving = Decimal("3500000")
    elif dist_val <= 12.0:
        commute_saving = Decimal("1800000")
    else:
        commute_saving = Decimal("500000")

    # 3. Tiết kiệm tiện ích theo bảng đặc tả 5.2.B
    amenity_value_map = {
        "school": Decimal("5000000"),
        "market": Decimal("1500000"),
        "hospital": Decimal("1500000"),
        "metro": Decimal("2000000"),
        "park": Decimal("800000"),
        "pool": Decimal("800000"),
        "gym": Decimal("600000"),
        "parking": Decimal("1200000"),
        "quiet": Decimal("500000"),
    }
    amenity_benefit = sum((amenity_value_map.get(a, Decimal("400000")) for a in matched), Decimal("0"))
    monthly_benefit = rent_equiv + commute_saving + amenity_benefit

    # Chi phí thực tế hàng tháng (C):
    # Lãi vay bình quân suốt vòng đời khoản vay
    if scenario.term_months > 0:
        effective_rate = (
            (scenario.phase1_rate_percent * Decimal(scenario.phase1_months) +
             scenario.phase2_rate_percent * Decimal(max(0, scenario.term_months - scenario.phase1_months)))
            / Decimal(scenario.term_months)
        )
    else:
        effective_rate = scenario.phase2_rate_percent
    avg_loan_balance = analysis.initial_loan * Decimal("0.65")
    interest_cost = round(avg_loan_balance * (effective_rate / Decimal("1200")), 0)

    mgmt_fee = project.monthly_management_fee
    opp_cost_equity = round(down_payment * (Decimal("0.055") / Decimal("12")), 0)  # 5.5% chi phí cơ hội tiền gửi
    tax_monthly = round(project.price_min_vnd * (Decimal("0.0005") / Decimal("12")), 0)
    monthly_cost = interest_cost + mgmt_fee + opp_cost_equity + tax_monthly

    ic_ratio = float(round(monthly_benefit / monthly_cost, 2)) if monthly_cost > Decimal("0") else 1.0
    if ic_ratio >= 1.2:
        vfm_label = "RẤT ĐÁNG TIỀN MUA"
        vfm_badge = "safe"
    elif ic_ratio >= 0.8:
        vfm_label = "TRUNG BÌNH · CÂN NHẮC KỸ"
        vfm_badge = "warning"
    else:
        vfm_label = "KHÔNG ĐÁNG TIỀN · NÊN THUÊ"
        vfm_badge = "danger"

    value_for_money = ValueForMoney(
        ic_ratio=ic_ratio,
        verdict_label=vfm_label,
        badge_class=vfm_badge,
        monthly_benefit=monthly_benefit,
        monthly_cost=monthly_cost,
        rent_equivalent=rent_equiv,
        commute_saving=commute_saving,
        amenity_benefit=amenity_benefit,
        interest_cost=interest_cost,
        mgmt_fee=mgmt_fee,
        opportunity_cost_equity=opp_cost_equity,
        tax_monthly=tax_monthly,
    )

    # ----------------------------------------------------
    # TÍNH NĂNG SMART AMORTIZATION (TÍCH LŨY ÂN HẠN GỐC)
    # ----------------------------------------------------
    has_intro_benefit = scenario.phase1_months > 0 and pmt_floating > pmt_intro
    if has_intro_benefit:
        monthly_savings = pmt_floating - pmt_intro
        accumulated_reserve = monthly_savings * Decimal(scenario.phase1_months)
        remaining_months = max(1, scenario.term_months - scenario.phase1_months)
        # Giả sử dùng quỹ tích lũy trả bớt nợ gốc ở tháng kết thúc ưu đãi
        est_balance_after_intro = analysis.timeline[min(len(analysis.timeline)-1, scenario.phase1_months-1)].closing_balance
        new_balance = max(Decimal("0"), est_balance_after_intro - accumulated_reserve)
        optimized_floating_pmt = annuity_payment(new_balance, scenario.phase2_rate_percent, remaining_months)
        pmt_reduction = max(Decimal("0"), pmt_floating - optimized_floating_pmt)
        reduction_pct = float(round((pmt_reduction / pmt_floating) * 100, 1)) if pmt_floating > Decimal("0") else 0.0
        advice_text = (
            f"Trong {scenario.phase1_months} tháng ưu đãi (tiết kiệm được {float(monthly_savings/Decimal('1000000')):.1f} tr/tháng), "
            f"nếu gia đình kỷ luật tích lũy {float(accumulated_reserve/Decimal('1000000')):.0f} triệu vào quỹ trả bớt gốc ở tháng {scenario.phase1_months + 1}, "
            f"tiền trả góp thả nổi sẽ giảm vĩnh viễn từ {float(pmt_floating/Decimal('1000000')):.1f} tr xuống chỉ còn {float(optimized_floating_pmt/Decimal('1000000')):.1f} tr/tháng "
            f"(giảm {reduction_pct}%), triệt tiêu hoàn toàn cú sốc lãi suất!"
        )
    else:
        monthly_savings = Decimal("0")
        accumulated_reserve = Decimal("0")
        optimized_floating_pmt = pmt_floating
        pmt_reduction = Decimal("0")
        reduction_pct = 0.0
        advice_text = "Khoản vay áp dụng trả góp đều ngay từ đầu, duy trì dòng tiền ổn định không có sốc bước nhảy."

    smart_amortization = SmartAmortization(
        has_intro_benefit=has_intro_benefit,
        monthly_savings=monthly_savings,
        accumulated_reserve=accumulated_reserve,
        original_floating_pmt=pmt_floating,
        optimized_floating_pmt=optimized_floating_pmt,
        monthly_pmt_reduction=pmt_reduction,
        reduction_percent=reduction_pct,
        advice_text=advice_text,
    )

    return ProjectAssessment(
        project=project,
        analysis=analysis,
        rank_class=rank_class,
        hard_filter_status=hard_filter_status,
        hard_filters_breakdown=tuple(hard_items),
        down_payment=down_payment,
        reserve_after_purchase=reserve_after_purchase,
        distance_km=distance_km,
        finance_score=finance_score,
        distance_score=distance_score,
        amenity_score=amenity_score,
        convenience_score=convenience_score,
        total_score=total_score,
        status_label=status_label,
        matched_amenities=matched,
        missing_amenities=missing,
        value_for_money=value_for_money,
        smart_amortization=smart_amortization,
        rejection_reasons=all_rejects,
        warning_reasons=all_warnings,
    )


def rank_projects(
    projects: list[Project],
    profile: FinancialProfile,
    scenario: LoanScenario,
    persona: str,
    workplace_lat: float,
    workplace_lng: float,
    required_amenities: tuple[str, ...],
    weights_config: dict[str, dict[str, Decimal]] | None = None,
    client_age: int = 32,
    cic_status: str = "clean",
) -> tuple[list[ProjectAssessment], list[ProjectAssessment], list[ProjectAssessment]]:
    """
    Xếp hạng rổ dự án trả về 3 danh sách riêng biệt:
    - class_a: Hạng A (Khả thi an toàn)
    - class_b: Hạng B (Cần thẩm định đặc cách)
    - class_c: Hạng C (Loại trừ)
    """
    assessments = [
        assess_project(
            project=project,
            profile=profile,
            scenario=scenario,
            persona=persona,
            workplace_lat=workplace_lat,
            workplace_lng=workplace_lng,
            required_amenities=required_amenities,
            weights_config=weights_config,
            client_age=client_age,
            cic_status=cic_status,
        )
        for project in projects
    ]

    class_a = sorted(
        [item for item in assessments if item.rank_class == "A"],
        key=lambda item: item.total_score,
        reverse=True,
    )
    class_b = sorted(
        [item for item in assessments if item.rank_class == "B"],
        key=lambda item: item.total_score,
        reverse=True,
    )
    class_c = sorted(
        [item for item in assessments if item.rank_class == "C"],
        key=lambda item: item.total_score,
        reverse=True,
    )

    return class_a, class_b, class_c
