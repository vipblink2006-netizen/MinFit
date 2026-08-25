from __future__ import annotations

from decimal import Decimal

from project_engine import AMENITY_LABELS, ProjectAssessment

PERSONA_LABELS = {
    "single": "Độc thân",
    "young_couple": "Vợ chồng trẻ",
    "family_with_children": "Gia đình có con",
    "retired": "Người lớn tuổi / Hưu trí",
}


def format_vnd(value: Decimal) -> str:
    return f"{value:,.0f}".replace(",", ".") + " đ"


def format_million(value: Decimal) -> str:
    return f"{value / Decimal('1000000'):,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") + " triệu"


def build_explanations(assessment: ProjectAssessment, persona: str) -> tuple[list[str], list[str]]:
    analysis = assessment.analysis
    project = assessment.project
    pros: list[str] = []
    cons: list[str] = []

    if assessment.matched_amenities:
        labels = ", ".join(AMENITY_LABELS[item] for item in assessment.matched_amenities)
        pros.append(f"Đáp ứng {len(assessment.matched_amenities)}/3 tiện ích bắt buộc: {labels}.")
    if assessment.distance_km <= Decimal("5"):
        pros.append(f"Cách nơi làm việc khoảng {assessment.distance_km:.1f} km, phù hợp lịch di chuyển hàng ngày.")
    elif assessment.distance_km <= Decimal("10"):
        pros.append(f"Khoảng cách {assessment.distance_km:.1f} km vẫn nằm trong vùng cân nhắc hợp lý.")
    if analysis.max_dti <= Decimal("0.36"):
        pros.append(f"DTI cao nhất {analysis.max_dti * 100:.1f}% nằm trong vùng an toàn dưới 36%.")
    elif analysis.max_dti <= Decimal("0.45"):
        pros.append(f"DTI cao nhất {analysis.max_dti * 100:.1f}% chưa chạm ngưỡng đỏ 50%.")
    if analysis.min_fcf >= Decimal("10000000"):
        pros.append(f"Tháng căng nhất vẫn còn {format_million(analysis.min_fcf)} dòng tiền tự do.")
    if analysis.survival_months >= Decimal("6"):
        pros.append(f"Quỹ dự phòng sau khi xuống tiền đủ khoảng {analysis.survival_months:.1f} tháng sinh tồn.")

    if assessment.missing_amenities:
        missing_labels = ", ".join(AMENITY_LABELS[item] for item in assessment.missing_amenities)
        cons.append(f"Chưa đáp ứng các tiện ích bắt buộc: {missing_labels}.")
    if assessment.distance_km > Decimal("12"):
        cons.append(f"Khoảng cách {assessment.distance_km:.1f} km có thể làm tăng thời gian và chi phí đi lại.")
    if analysis.max_dti > Decimal("0.45"):
        cons.append(f"DTI đạt {analysis.max_dti * 100:.1f}% tại tháng {analysis.max_dti_month}, rất sát ngưỡng loại 50%.")
    elif analysis.max_dti > Decimal("0.36"):
        cons.append(f"DTI vượt vùng thận trọng 36%, đạt {analysis.max_dti * 100:.1f}% ở tháng {analysis.max_dti_month}.")
    if analysis.min_fcf < Decimal("3000000"):
        if persona == "retired":
            cons.append(f"Với nhóm hưu trí, tháng {analysis.min_fcf_month} chỉ còn {format_million(analysis.min_fcf)} sau trả góp, nợ và phí dịch vụ; biên an toàn rất thấp.")
        else:
            cons.append(f"Dòng tiền tự do thấp nhất chỉ còn {format_million(analysis.min_fcf)} tại tháng {analysis.min_fcf_month}.")
    if analysis.survival_months < Decimal("3"):
        cons.append(f"Quỹ dự phòng chỉ đủ {analysis.survival_months:.1f} tháng, thấp hơn mức thận trọng 3 tháng.")
    elif analysis.survival_months < Decimal("6"):
        cons.append(f"Quỹ dự phòng khoảng {analysis.survival_months:.1f} tháng; nên hướng tới tối thiểu 6 tháng.")
    if analysis.payment_shocks:
        first_shock = analysis.payment_shocks[0]
        if first_shock.increase_ratio is None:
            shock_text = "từ 0 đồng lên " + format_million(first_shock.current_payment)
        else:
            shock_text = f"tăng {first_shock.increase_ratio * 100:.1f}% lên {format_million(first_shock.current_payment)}"
        cons.append(f"Cú sốc thanh toán tại tháng {first_shock.month}: khoản trả {shock_text}.")
    if analysis.illusion_of_safety:
        cons.append("Ảo giác an toàn: DTI tháng đầu dưới 36% nhưng vượt 50% khi bước sang lãi suất thả nổi.")
    if project.monthly_management_fee >= Decimal("2000000"):
        cons.append(f"Phí quản lý khoảng {format_million(project.monthly_management_fee)}/tháng cần được tính cố định vào ngân sách.")

    if persona == "family_with_children" and "school" not in project.amenities:
        cons.append("Chân dung gia đình có con nhưng dự án chưa có lợi thế rõ về trường học.")
    elif persona == "retired" and "hospital" not in project.amenities:
        cons.append("Chân dung lớn tuổi nhưng dự án chưa có lợi thế rõ về tiếp cận bệnh viện.")
    elif persona == "single" and "metro" in project.amenities:
        pros.append("Kết nối metro là điểm cộng lớn cho khách độc thân ưu tiên tính linh hoạt.")
    elif persona == "young_couple" and assessment.reserve_after_purchase > Decimal("500000000"):
        pros.append("Sau vốn đối ứng vẫn còn trên 500 triệu đồng, tạo khoảng đệm cho kế hoạch gia đình.")

    if not cons:
        cons.append("Chưa phát hiện cờ đỏ; vẫn cần kiểm tra bảng giá, pháp lý và lãi suất ngân hàng tại thời điểm ký.")
    return pros, cons


def build_text_report(assessment: ProjectAssessment, persona: str) -> str:
    pros, cons = build_explanations(assessment, persona)
    analysis = assessment.analysis
    project = assessment.project
    lines = [
        "MINFIT · BÁO CÁO THẨM ĐỊNH DÒNG TIỀN",
        f"Chân dung: {PERSONA_LABELS[persona]}",
        f"Dự án: {project.name} ({project.area})",
        f"Giá tham chiếu: {format_vnd(project.price_min_vnd)}",
        f"Vốn đối ứng: {format_vnd(assessment.down_payment)}",
        f"Khoản trả cao nhất: {format_vnd(analysis.max_payment)} tại tháng {analysis.max_payment_month}",
        f"DTI cao nhất: {analysis.max_dti * 100:.2f}% tại tháng {analysis.max_dti_month}",
        f"FCF thấp nhất: {format_vnd(analysis.min_fcf)} tại tháng {analysis.min_fcf_month}",
        f"Số tháng sinh tồn: {analysis.survival_months:.2f}",
        "",
        "ƯU ĐIỂM",
        *[f"✓ {item}" for item in pros],
        "",
        "RỦI RO / ĐIỂM CẦN KIỂM TRA",
        *[f"⚠ {item}" for item in cons],
        "",
        "Lưu ý: Báo cáo dùng dữ liệu dự án mẫu và kịch bản lãi suất do môi giới nhập; không thay thế phê duyệt tín dụng của ngân hàng.",
    ]
    return "\n".join(lines)
