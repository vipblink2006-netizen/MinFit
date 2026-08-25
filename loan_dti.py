from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Literal

getcontext().prec = 32

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
TWELVE_HUNDRED = Decimal("1200")

RepaymentMethod = Literal["equal_principal", "annuity"]
GraceType = Literal["none", "interest_only", "capitalized"]


def decimal_value(value: Decimal | int | float | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(frozen=True)
class FinancialProfile:
    monthly_income: Decimal
    available_cash: Decimal
    existing_debt_payment: Decimal
    essential_expenses: Decimal


@dataclass(frozen=True)
class LoanScenario:
    loan_ratio_percent: Decimal
    term_years: int
    phase1_rate_percent: Decimal
    phase1_months: int
    phase2_rate_percent: Decimal
    repayment_method: RepaymentMethod
    grace_type: GraceType
    grace_months: int

    @property
    def term_months(self) -> int:
        return self.term_years * 12

    @property
    def effective_grace_months(self) -> int:
        return 0 if self.grace_type == "none" else self.grace_months


@dataclass(frozen=True)
class TimelineRow:
    month: int
    phase: str
    annual_rate_percent: Decimal
    opening_balance: Decimal
    interest: Decimal
    principal: Decimal
    payment: Decimal
    closing_balance: Decimal
    dti: Decimal
    free_cash_flow: Decimal


@dataclass(frozen=True)
class PaymentShock:
    month: int
    previous_payment: Decimal
    current_payment: Decimal
    increase_ratio: Decimal | None


@dataclass(frozen=True)
class LoanAnalysis:
    initial_loan: Decimal
    ltv: Decimal
    timeline: tuple[TimelineRow, ...]
    max_payment: Decimal
    max_payment_month: int
    max_dti: Decimal
    max_dti_month: int
    min_fcf: Decimal
    min_fcf_month: int
    survival_months: Decimal
    payment_shocks: tuple[PaymentShock, ...]
    illusion_of_safety: bool
    hard_filter_reasons: tuple[str, ...]

    @property
    def is_eligible(self) -> bool:
        return not self.hard_filter_reasons


def annuity_payment(balance: Decimal, annual_rate_percent: Decimal, remaining_months: int) -> Decimal:
    if remaining_months <= 0 or balance <= ZERO:
        return ZERO
    monthly_rate = annual_rate_percent / TWELVE_HUNDRED
    if monthly_rate == ZERO:
        return balance / Decimal(remaining_months)
    growth = (ONE + monthly_rate) ** remaining_months
    return balance * monthly_rate * growth / (growth - ONE)


def _validate(profile: FinancialProfile, scenario: LoanScenario, project_price: Decimal) -> None:
    if profile.monthly_income <= ZERO:
        raise ValueError("Thu nhập hàng tháng phải lớn hơn 0.")
    if project_price <= ZERO:
        raise ValueError("Giá dự án phải lớn hơn 0.")
    if not 0 <= scenario.loan_ratio_percent <= 100:
        raise ValueError("Tỷ lệ vay phải nằm trong khoảng 0-100%.")
    if not 10 <= scenario.term_years <= 30:
        raise ValueError("Thời hạn vay phải nằm trong khoảng 10-30 năm.")
    if not 0 <= scenario.phase1_months < scenario.term_months:
        raise ValueError("Thời gian lãi suất ưu đãi phải ngắn hơn thời hạn vay.")
    if not 0 <= scenario.effective_grace_months < scenario.term_months:
        raise ValueError("Thời gian ân hạn phải ngắn hơn thời hạn vay.")
    if scenario.phase1_rate_percent < ZERO or scenario.phase2_rate_percent < ZERO:
        raise ValueError("Lãi suất không được âm.")


def simulate_loan(
    profile: FinancialProfile,
    scenario: LoanScenario,
    project_price: Decimal,
    monthly_management_fee: Decimal,
    liquid_reserve_after_purchase: Decimal,
) -> LoanAnalysis:
    project_price = decimal_value(project_price)
    monthly_management_fee = decimal_value(monthly_management_fee)
    liquid_reserve_after_purchase = max(decimal_value(liquid_reserve_after_purchase), ZERO)
    _validate(profile, scenario, project_price)

    ltv = scenario.loan_ratio_percent / HUNDRED
    initial_loan = project_price * ltv
    balance = initial_loan
    grace_months = scenario.effective_grace_months
    rows: list[TimelineRow] = []
    fixed_principal: Decimal | None = None
    current_annuity: Decimal | None = None

    for month in range(1, scenario.term_months + 1):
        opening_balance = balance
        annual_rate = scenario.phase1_rate_percent if month <= scenario.phase1_months else scenario.phase2_rate_percent
        phase = "Ưu đãi" if month <= scenario.phase1_months else "Thả nổi"
        monthly_rate = annual_rate / TWELVE_HUNDRED
        interest = opening_balance * monthly_rate
        principal = ZERO
        payment = ZERO

        if month <= grace_months:
            if scenario.grace_type == "interest_only":
                payment = interest
            elif scenario.grace_type == "capitalized":
                balance = opening_balance + interest
        else:
            remaining_months = scenario.term_months - month + 1
            if scenario.repayment_method == "equal_principal":
                if fixed_principal is None:
                    fixed_principal = opening_balance / Decimal(remaining_months)
                principal = min(fixed_principal, opening_balance)
                payment = principal + interest
                balance = opening_balance - principal
            else:
                rate_changed = month == scenario.phase1_months + 1
                grace_ended = month == grace_months + 1
                if current_annuity is None or rate_changed or grace_ended:
                    current_annuity = annuity_payment(opening_balance, annual_rate, remaining_months)
                payment = current_annuity
                principal = min(max(payment - interest, ZERO), opening_balance)
                payment = principal + interest
                balance = opening_balance - principal

        if month == scenario.term_months and abs(balance) < Decimal("0.01"):
            balance = ZERO

        dti = (payment + profile.existing_debt_payment) / profile.monthly_income
        free_cash_flow = profile.monthly_income - (
            payment
            + profile.existing_debt_payment
            + profile.essential_expenses
            + monthly_management_fee
        )
        rows.append(
            TimelineRow(
                month=month,
                phase=phase,
                annual_rate_percent=annual_rate,
                opening_balance=opening_balance,
                interest=interest,
                principal=principal,
                payment=payment,
                closing_balance=balance,
                dti=dti,
                free_cash_flow=free_cash_flow,
            )
        )

    max_payment_row = max(rows, key=lambda row: row.payment)
    max_dti_row = max(rows, key=lambda row: row.dti)
    min_fcf_row = min(rows, key=lambda row: row.free_cash_flow)
    monthly_survival_cost = (
        profile.essential_expenses
        + profile.existing_debt_payment
        + monthly_management_fee
        + max_payment_row.payment
    )
    survival_months = liquid_reserve_after_purchase / monthly_survival_cost if monthly_survival_cost > ZERO else Decimal("999")

    shocks: list[PaymentShock] = []
    for previous, current in zip(rows, rows[1:]):
        if current.payment <= previous.payment:
            continue
        if previous.payment == ZERO:
            shocks.append(PaymentShock(current.month, previous.payment, current.payment, None))
            continue
        increase_ratio = (current.payment - previous.payment) / previous.payment
        if increase_ratio > Decimal("0.05"):
            shocks.append(PaymentShock(current.month, previous.payment, current.payment, increase_ratio))

    phase2_rows = [row for row in rows if row.month > scenario.phase1_months]
    illusion_of_safety = bool(
        phase2_rows
        and rows[0].dti < Decimal("0.36")
        and max(row.dti for row in phase2_rows) > Decimal("0.50")
    )

    reasons: list[str] = []
    if ltv > Decimal("0.80"):
        reasons.append("LTV vượt 80%.")
    if max_dti_row.dti > Decimal("0.50"):
        reasons.append(f"DTI vượt 50% tại tháng {max_dti_row.month}.")
    if min_fcf_row.free_cash_flow < ZERO:
        reasons.append(f"Dòng tiền tự do âm tại tháng {min_fcf_row.month}.")

    return LoanAnalysis(
        initial_loan=initial_loan,
        ltv=ltv,
        timeline=tuple(rows),
        max_payment=max_payment_row.payment,
        max_payment_month=max_payment_row.month,
        max_dti=max_dti_row.dti,
        max_dti_month=max_dti_row.month,
        min_fcf=min_fcf_row.free_cash_flow,
        min_fcf_month=min_fcf_row.month,
        survival_months=survival_months,
        payment_shocks=tuple(shocks),
        illusion_of_safety=illusion_of_safety,
        hard_filter_reasons=tuple(reasons),
    )
