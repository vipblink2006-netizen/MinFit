from __future__ import annotations

import json
import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from loan_dti import FinancialProfile, LoanAnalysis, LoanScenario, decimal_value, simulate_loan

PERSONA_WEIGHTS = {
    "single": {"price": Decimal("0.30"), "distance": Decimal("0.40"), "amenities": Decimal("0.30")},
    "young_couple": {"price": Decimal("0.35"), "distance": Decimal("0.35"), "amenities": Decimal("0.30")},
    "family_with_children": {"price": Decimal("0.25"), "distance": Decimal("0.30"), "amenities": Decimal("0.45")},
    "retired": {"price": Decimal("0.30"), "distance": Decimal("0.20"), "amenities": Decimal("0.50")},
}

AMENITY_LABELS = {
    "school": "Trường học",
    "park": "Công viên",
    "parking": "Chỗ đỗ xe",
    "quiet": "Không gian yên tĩnh",
    "pool": "Hồ bơi",
    "metro": "Gần metro",
    "hospital": "Bệnh viện",
    "market": "Chợ / siêu thị",
}


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

    @property
    def monthly_management_fee(self) -> Decimal:
        return self.area_m2 * self.management_fee_per_m2


@dataclass(frozen=True)
class ProjectAssessment:
    project: Project
    analysis: LoanAnalysis
    down_payment: Decimal
    reserve_after_purchase: Decimal
    distance_km: Decimal
    price_score: Decimal
    distance_score: Decimal
    amenity_score: Decimal
    total_score: Decimal
    matched_amenities: tuple[str, ...]
    missing_amenities: tuple[str, ...]
    rejection_reasons: tuple[str, ...]

    @property
    def is_eligible(self) -> bool:
        return not self.rejection_reasons


def load_projects(path: str | Path) -> list[Project]:
    raw_projects = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        Project(
            id=item["id"],
            name=item["name"],
            area=item["area"],
            price_min_vnd=decimal_value(item["price_min_vnd"]),
            area_m2=decimal_value(item["area_m2"]),
            lat=float(item["lat"]),
            lng=float(item["lng"]),
            management_fee_per_m2=decimal_value(item["management_fee_per_m2"]),
            bedrooms=item["bedrooms"],
            amenities=tuple(item["amenities"]),
        )
        for item in raw_projects
    ]


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> Decimal:
    earth_radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    value = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    distance = earth_radius_km * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))
    return Decimal(str(distance))


def _clamp(value: Decimal, minimum: Decimal = Decimal("0"), maximum: Decimal = Decimal("100")) -> Decimal:
    return min(maximum, max(minimum, value))


def assess_project(
    project: Project,
    profile: FinancialProfile,
    scenario: LoanScenario,
    persona: str,
    workplace_lat: float,
    workplace_lng: float,
    required_amenities: tuple[str, ...],
    weights_config: dict[str, dict[str, Decimal]] | None = None,
) -> ProjectAssessment:
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

    matched = tuple(item for item in required_amenities if item in project.amenities)
    missing = tuple(item for item in required_amenities if item not in project.amenities)
    amenity_score = Decimal("100") if not required_amenities else Decimal(len(matched)) / Decimal(len(required_amenities)) * Decimal("100")
    distance_km = haversine_distance(workplace_lat, workplace_lng, project.lat, project.lng)
    distance_score = Decimal(str(100 * math.exp(-float(distance_km) / 12)))

    if ltv < Decimal("1") and profile.available_cash > Decimal("0"):
        purchasing_capacity = profile.available_cash / (Decimal("1") - ltv)
        price_load = project.price_min_vnd / purchasing_capacity
        price_score = _clamp(Decimal("100") - price_load * Decimal("55"))
    else:
        price_score = _clamp(Decimal("100") - analysis.max_dti * Decimal("100"))

    weights = (weights_config or PERSONA_WEIGHTS)[persona]
    total_score = (
        price_score * weights["price"]
        + distance_score * weights["distance"]
        + amenity_score * weights["amenities"]
    )

    rejection_reasons = list(analysis.hard_filter_reasons)
    if reserve_after_purchase < Decimal("0"):
        shortfall = abs(reserve_after_purchase)
        rejection_reasons.append(f"Thiếu {shortfall:,.0f} đồng vốn đối ứng.")

    return ProjectAssessment(
        project=project,
        analysis=analysis,
        down_payment=down_payment,
        reserve_after_purchase=reserve_after_purchase,
        distance_km=distance_km,
        price_score=price_score,
        distance_score=distance_score,
        amenity_score=amenity_score,
        total_score=total_score,
        matched_amenities=matched,
        missing_amenities=missing,
        rejection_reasons=tuple(rejection_reasons),
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
) -> tuple[list[ProjectAssessment], list[ProjectAssessment]]:
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
        )
        for project in projects
    ]
    eligible = sorted(
        (item for item in assessments if item.is_eligible),
        key=lambda item: (item.total_score, -item.analysis.max_dti, item.analysis.min_fcf),
        reverse=True,
    )
    rejected = sorted(
        (item for item in assessments if not item.is_eligible),
        key=lambda item: item.total_score,
        reverse=True,
    )
    return eligible, rejected
