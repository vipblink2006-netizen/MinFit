from __future__ import annotations

import io
import os
from decimal import Decimal

from PIL import Image, ImageDraw, ImageFont

from explanation_engine import PERSONA_LABELS, build_explanations, format_million
from loan_dti import FinancialProfile, LoanScenario
from project_engine import ProjectAssessment


W, H = 1240, 1754  # A4 portrait at 150 dpi
INK = "#17352f"
MUTED = "#647872"
GREEN = "#1f7a55"
DEEP = "#123f31"
PALE = "#eaf5ed"
LINE = "#dbe8e2"
AMBER = "#d9952f"
RED = "#c95843"
PAPER = "#f5f8f5"


def _font_path(bold: bool = False) -> str:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_font_path(bold), size=size)


def _money_short(value: Decimal) -> str:
    billion = value / Decimal("1000000000")
    if abs(billion) >= 1:
        return f"{billion:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " tỷ"
    return format_million(value)


def _wrapped(draw: ImageDraw.ImageDraw, text: str, box: tuple[int, int, int, int], font, fill=INK, spacing=7, max_lines=None) -> int:
    x1, y1, x2, _ = box
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textbbox((0, 0), trial, font=font)[2] <= x2 - x1:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and draw.textbbox((0, 0), lines[-1] + "…", font=font)[2] > x2 - x1:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    line_h = font.size + spacing
    for index, line in enumerate(lines):
        draw.text((x1, y1 + index * line_h), line, font=font, fill=fill)
    return y1 + len(lines) * line_h


def _rounded(draw: ImageDraw.ImageDraw, box, fill="white", outline=LINE, radius=22, width=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _verdict(assessment: ProjectAssessment) -> tuple[str, str, str]:
    a = assessment.analysis
    if a.max_dti <= Decimal("0.36") and a.min_fcf >= Decimal("10000000") and a.survival_months >= Decimal("6"):
        return "PHÙ HỢP ĐỂ XUỐNG TIỀN", "Biên dòng tiền tốt; vẫn cần xác minh pháp lý và bảng giá thực tế.", GREEN
    if a.max_dti <= Decimal("0.45") and a.min_fcf >= 0 and a.survival_months >= Decimal("3"):
        return "CÓ THỂ CÂN NHẮC", "Nên thương lượng giá hoặc tăng vốn tự có để tạo thêm vùng đệm.", AMBER
    return "CHƯA NÊN XUỐNG TIỀN", "Rủi ro dòng tiền cao; cần điều chỉnh cấu trúc vay trước khi đặt cọc.", RED


def _metric(draw, x, y, w, label, value, accent=INK):
    _rounded(draw, (x, y, x + w, y + 104), fill="#ffffff", radius=16)
    draw.text((x + 18, y + 15), label.upper(), font=_font(15, True), fill=MUTED)
    draw.text((x + 18, y + 50), value, font=_font(25, True), fill=accent)


def _chart(draw: ImageDraw.ImageDraw, assessment: ProjectAssessment, box):
    x1, y1, x2, y2 = box
    rows = assessment.analysis.timeline
    sample = list(rows[:: max(1, len(rows) // 80)])
    if sample[-1].month != rows[-1].month:
        sample.append(rows[-1])
    values = [float(r.free_cash_flow / Decimal("1000000")) for r in sample]
    low, high = min(values + [0]), max(values + [0])
    spread = max(high - low, 1)
    zero_y = y2 - (0 - low) / spread * (y2 - y1)
    draw.line((x1, zero_y, x2, zero_y), fill="#c8d6d0", width=2)
    points = []
    for i, value in enumerate(values):
        x = x1 + i / max(len(values) - 1, 1) * (x2 - x1)
        y = y2 - (value - low) / spread * (y2 - y1)
        points.append((x, y))
    draw.line(points, fill=GREEN, width=5, joint="curve")
    draw.text((x1, y1 - 28), f"FCF cao: {max(values):.1f} tr", font=_font(14, True), fill=GREEN)
    right = f"Thấp: {min(values):.1f} tr"
    right_w = draw.textbbox((0, 0), right, font=_font(14, True))[2]
    draw.text((x2 - right_w, y1 - 28), right, font=_font(14, True), fill=RED if min(values) < 3 else MUTED)
    draw.text((x1, y2 + 8), "THÁNG 1", font=_font(12, True), fill=MUTED)
    end = f"THÁNG {rows[-1].month}"
    end_w = draw.textbbox((0, 0), end, font=_font(12, True))[2]
    draw.text((x2 - end_w, y2 + 8), end, font=_font(12, True), fill=MUTED)


def build_a4_report_png(
    assessment: ProjectAssessment,
    persona: str,
    profile: FinancialProfile,
    scenario: LoanScenario,
) -> bytes:
    project, analysis = assessment.project, assessment.analysis
    pros, cons = build_explanations(assessment, persona)
    verdict, verdict_note, verdict_color = _verdict(assessment)
    image = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(image)

    # Hero
    draw.rounded_rectangle((44, 40, W - 44, 302), radius=30, fill=DEEP)
    draw.text((78, 72), "MINFIT  /  INVESTMENT BRIEF", font=_font(17, True), fill="#aee1c1")
    draw.text((78, 112), project.name, font=_font(43, True), fill="white")
    draw.text((78, 169), f"{project.area}  ·  {project.bedrooms}  ·  {project.area_m2:.0f} m²  ·  {assessment.distance_km:.1f} km đến nơi làm việc", font=_font(20), fill="#d3e6dc")
    draw.rounded_rectangle((78, 218, 742, 278), radius=15, fill=verdict_color)
    draw.text((100, 229), verdict, font=_font(23, True), fill="white")
    draw.text((914, 88), f"{assessment.total_score:.0f}", font=_font(68, True), fill="white")
    draw.text((918, 166), "FIT SCORE / 100", font=_font(15, True), fill="#aee1c1")

    # Key facts
    y = 334
    gap, margin = 14, 44
    mw = (W - 2 * margin - 3 * gap) // 4
    _metric(draw, margin, y, mw, "Giá tham chiếu", _money_short(project.price_min_vnd))
    _metric(draw, margin + (mw + gap), y, mw, "Vốn đối ứng", _money_short(assessment.down_payment))
    _metric(draw, margin + 2 * (mw + gap), y, mw, "Khoản vay", _money_short(analysis.initial_loan))
    _metric(draw, margin + 3 * (mw + gap), y, mw, "Dự phòng còn lại", _money_short(assessment.reserve_after_purchase), GREEN)

    # Financial capacity
    y = 462
    _rounded(draw, (44, y, 760, 785), fill="white")
    draw.text((72, y + 24), "SỨC CHỊU DÒNG TIỀN", font=_font(18, True), fill=GREEN)
    facts = [
        ("Thu nhập / tháng", format_million(profile.monthly_income)),
        ("Chi phí thiết yếu", format_million(profile.essential_expenses)),
        ("Nợ hiện hữu", format_million(profile.existing_debt_payment)),
        (f"PMT cao nhất · T{analysis.max_payment_month}", format_million(analysis.max_payment)),
        (f"DTI cao nhất · T{analysis.max_dti_month}", f"{analysis.max_dti * 100:.1f}%"),
        (f"FCF thấp nhất · T{analysis.min_fcf_month}", format_million(analysis.min_fcf)),
    ]
    for i, (label, value) in enumerate(facts):
        cx = 72 + (i % 3) * 224
        cy = y + 76 + (i // 3) * 103
        draw.text((cx, cy), label.upper(), font=_font(13, True), fill=MUTED)
        color = RED if ("DTI" in label and analysis.max_dti > Decimal("0.45")) or ("FCF" in label and analysis.min_fcf < Decimal("3000000")) else INK
        draw.text((cx, cy + 28), value, font=_font(22, True), fill=color)
    draw.text((72, y + 282), f"Quỹ dự phòng chịu được khoảng {analysis.survival_months:.1f} tháng ở kịch bản căng nhất.", font=_font(16, True), fill=GREEN if analysis.survival_months >= 6 else AMBER)

    _rounded(draw, (782, y, W - 44, 785), fill="#fffaf5", outline="#eedfcf")
    draw.text((810, y + 24), "CẤU TRÚC KHOẢN VAY", font=_font(18, True), fill=AMBER)
    loan_lines = [
        f"LTV: {scenario.loan_ratio_percent:.0f}%",
        f"Kỳ hạn: {scenario.term_years} năm",
        f"Ưu đãi: {scenario.phase1_rate_percent:.1f}% / năm · {scenario.phase1_months} tháng",
        f"Sau ưu đãi: {scenario.phase2_rate_percent:.1f}% / năm",
        "Trả nợ: " + ("Gốc đều" if scenario.repayment_method == "equal_principal" else "Gốc lãi đều"),
        "Ân hạn: " + ("Không" if scenario.grace_type == "none" else f"{scenario.grace_months} tháng"),
    ]
    for i, line in enumerate(loan_lines):
        draw.ellipse((812, y + 70 + i * 37, 822, y + 80 + i * 37), fill=AMBER)
        draw.text((836, y + 61 + i * 37), line, font=_font(17), fill=INK)

    # Cash-flow chart
    y = 813
    _rounded(draw, (44, y, W - 44, 1074), fill="white")
    draw.text((72, y + 22), "DÒNG TIỀN TỰ DO TRONG TOÀN KỲ VAY", font=_font(18, True), fill=GREEN)
    draw.text((72, y + 51), "Số tiền còn lại mỗi tháng sau trả góp, nợ hiện hữu, sinh hoạt và phí quản lý · triệu đồng", font=_font(14), fill=MUTED)
    _chart(draw, assessment, (78, y + 119, W - 78, y + 212))

    # Pros / risks
    y = 1102
    col_w = (W - 102) // 2
    _rounded(draw, (44, y, 44 + col_w, 1458), fill="white")
    _rounded(draw, (58 + col_w, y, W - 44, 1458), fill="#fffaf8", outline="#f0ddd6")
    draw.text((72, y + 22), "ƯU ĐIỂM NỔI BẬT", font=_font(18, True), fill=GREEN)
    draw.text((86 + col_w, y + 22), "RỦI RO & ĐIỂM PHẢI KIỂM TRA", font=_font(18, True), fill=RED)
    py = y + 65
    for item in pros[:4]:
        draw.text((72, py), "✓", font=_font(18, True), fill=GREEN)
        py = _wrapped(draw, item, (103, py, 44 + col_w - 25, 1450), _font(15), fill=MUTED, spacing=5, max_lines=2) + 13
    cy = y + 65
    for item in cons[:4]:
        draw.text((86 + col_w, cy), "!", font=_font(18, True), fill=RED)
        cy = _wrapped(draw, item, (117 + col_w, cy, W - 68, 1450), _font(15), fill=MUTED, spacing=5, max_lines=2) + 13

    # Decision footer
    y = 1486
    draw.rounded_rectangle((44, y, W - 44, 1692), radius=24, fill=DEEP)
    draw.text((74, y + 25), "KẾT LUẬN MINFIT", font=_font(15, True), fill="#aee1c1")
    draw.text((74, y + 58), verdict, font=_font(29, True), fill="white")
    _wrapped(draw, verdict_note, (74, y + 100, 710, y + 166), _font(17), fill="#d3e6dc", spacing=5, max_lines=2)
    draw.text((762, y + 25), "TRƯỚC KHI ĐẶT CỌC", font=_font(15, True), fill="#aee1c1")
    checklist = "1. Kiểm tra pháp lý & tiến độ   2. Chốt lãi suất thực   3. Giữ quỹ dự phòng   4. Stress-test thu nhập"
    _wrapped(draw, checklist, (762, y + 58, W - 72, y + 170), _font(16), fill="white", spacing=7, max_lines=4)

    draw.text((44, 1714), f"Chân dung: {PERSONA_LABELS[persona]} · Tiện ích khớp: {len(assessment.matched_amenities)}/3 · Phí quản lý: {format_million(project.monthly_management_fee)}/tháng", font=_font(13), fill=MUTED)
    note = "MinFit là mô phỏng theo dữ liệu đầu vào; không thay thế thẩm định pháp lý, định giá hoặc phê duyệt tín dụng."
    nw = draw.textbbox((0, 0), note, font=_font(11))[2]
    draw.text((W - 44 - nw, 1738), note, font=_font(11), fill="#80908b")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True, dpi=(150, 150))
    return buffer.getvalue()
