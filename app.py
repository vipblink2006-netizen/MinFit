from __future__ import annotations

import csv
import html
import io
import time
from decimal import Decimal
import pandas as pd
import streamlit as st

from database import DATABASE_ERRORS, database_status, load_persona_weights_from_database, load_projects_from_database
from explanation_engine import PERSONA_LABELS, build_explanations, build_text_report, format_million, format_vnd
from loan_dti import FinancialProfile, LoanScenario, decimal_value
from project_engine import AMENITY_LABELS, ProjectAssessment, rank_projects
from report_image import build_a4_report_png

AREA_PRESETS = {
    "Bình Thạnh": (10.8106, 106.7091),
    "Quận 1": (10.7769, 106.7009),
    "Thủ Đức": (10.8491, 106.7717),
    "Quận 7": (10.7340, 106.7218),
    "Tân Bình": (10.8015, 106.6527),
    "Gò Vấp": (10.8387, 106.6653),
    "Tân Phú": (10.7916, 106.6273),
    "Nhà Bè": (10.6961, 106.7380),
}

PERSONA_OPTIONS = {label: key for key, label in PERSONA_LABELS.items()}
REPAYMENT_OPTIONS = {"Trả gốc đều": "equal_principal", "Trả gốc lãi đều (Annuity)": "annuity"}
GRACE_OPTIONS = {"Không ân hạn": "none", "Chỉ trả lãi": "interest_only", "Dồn lãi vào dư nợ gốc": "capitalized"}
AMENITY_OPTIONS = {label: key for key, label in AMENITY_LABELS.items()}

st.set_page_config(page_title="MinFit · Thẩm định dòng tiền", page_icon="🏠", layout="wide")

st.markdown(
    """
    <style>
    :root { --ink:#15312d; --muted:#70827d; --green:#1f7a55; --deep:#174d3a; --line:#dbe8e2; --paper:#f5f8f5; }
    .stApp { background: #f5f8f5; color: var(--ink); }
    [data-testid="stHeader"] { background: rgba(245,248,245,.88); }
    [data-testid="stToolbar"] { display:none !important; }
    [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label, label[data-testid="stWidgetLabel"] { color:#29433d !important; opacity:1 !important; font-weight:700 !important; }
    [data-testid="stMetric"] { background:#ffffff !important; border-color:#dce8e3 !important; }
    [data-testid="stMetric"] *, [data-testid="stMetricLabel"] *, [data-testid="stMetricValue"] { color:#15312d !important; opacity:1 !important; }
    [data-baseweb="input"] { background:#ffffff !important; border-color:#cbded5 !important; }
    [data-baseweb="input"] input { background:#ffffff !important; color:#15312d !important; -webkit-text-fill-color:#15312d !important; opacity:1 !important; }
    [data-baseweb="select"] > div, [data-baseweb="select"] input, [role="combobox"] { background:#ffffff !important; color:#15312d !important; -webkit-text-fill-color:#15312d !important; }
    [data-testid="stNumberInput"] button { background:#eef5f1 !important; color:#174d3a !important; border-color:#cbded5 !important; }
    [data-testid="stNumberInput"] button * { color:#174d3a !important; }
    [data-testid="stMultiSelect"] [data-baseweb="tag"] { background:#e3f2e8 !important; color:#174d3a !important; }
    [data-testid="stMultiSelect"] [data-baseweb="tag"] * { color:#174d3a !important; }
    [data-testid="stSlider"] p, [data-testid="stSlider"] div { color:#29433d; }
    [data-testid="stMarkdownContainer"] p { opacity:1; }
    .block-container { max-width: 1500px; padding-top: 1.5rem; padding-bottom: 3rem; }
    .hero { background:linear-gradient(135deg,#123f31,#1e7352); border-radius:22px; color:white; padding:32px 36px; margin-bottom:22px; position:relative; overflow:hidden; }
    .hero:after { content:""; position:absolute; width:260px; height:260px; border:1px solid rgba(213,247,226,.22); border-radius:50%; right:-55px; top:-90px; box-shadow:0 0 0 45px rgba(213,247,226,.05),0 0 0 90px rgba(213,247,226,.035); }
    .hero-kicker { color:#bce7ca; font:600 11px monospace; letter-spacing:.12em; text-transform:uppercase; }
    .hero h1 { font-size:42px; letter-spacing:-.055em; line-height:1.03; margin:10px 0 12px; max-width:760px; }
    .hero p { color:#c7ded3; font-size:14px; line-height:1.7; max-width:820px; margin:0; }
    .rule-pill { display:inline-block; margin-top:18px; border:1px solid rgba(205,242,220,.28); border-radius:999px; color:#d4eee0; font:500 10px monospace; padding:8px 11px; }
    .panel-title { font:600 10px monospace; color:#1f7a55; letter-spacing:.12em; text-transform:uppercase; margin-bottom:4px; }
    .project-card { background:#fff; border:1px solid var(--line); border-radius:16px; box-shadow:0 15px 38px rgba(28,78,62,.08); margin:0 0 18px; overflow:hidden; }
    .project-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; padding:20px 22px 16px; }
    .rank { color:#1f7a55; font:600 9px monospace; letter-spacing:.11em; margin-bottom:8px; }
    .project-head h3 { margin:0 0 5px; color:#15312d; font-size:22px; letter-spacing:-.04em; }
    .project-meta { color:#7a8b86; font-size:11px; }
    .fit-score { min-width:72px; text-align:center; background:#e9f5ed; border-radius:12px; color:#17583f; padding:10px; }
    .fit-score strong { display:block; font:400 29px Georgia,serif; line-height:1; }
    .fit-score span { font:600 8px monospace; text-transform:uppercase; }
    .finance-block { background:#f2f5f3; border-top:1px solid #e3ece8; border-bottom:1px solid #e3ece8; padding:16px 22px; }
    .finance-grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; }
    .metric small { color:#778984; display:block; font:500 8px monospace; letter-spacing:.07em; text-transform:uppercase; margin-bottom:5px; }
    .metric b { color:#17352f; font-size:14px; }
    .metric b.danger { color:#b5362e; }
    .dti-track { height:7px; background:#dce5e1; border-radius:99px; overflow:hidden; margin-top:8px; }
    .dti-fill { height:100%; border-radius:99px; }
    .safe { background:#3aa56f; }.watch { background:#e3a43f; }.risk { background:#d45145; }
    .explain-grid { display:grid; grid-template-columns:1fr 1fr; gap:0; }
    .explain { padding:18px 22px 20px; }
    .explain + .explain { border-left:1px solid #e6eee9; background:#fffaf8; }
    .explain h4 { margin:0 0 10px; font-size:11px; letter-spacing:.05em; text-transform:uppercase; }
    .pros h4 { color:#247b56; }.cons h4 { color:#c45e43; }
    .explain ul { list-style:none; padding:0; margin:0; }
    .explain li { color:#526761; font-size:11px; line-height:1.6; margin:7px 0; padding-left:19px; position:relative; }
    .pros li:before { content:"✓"; color:#2f9b69; font-weight:800; left:0; position:absolute; }
    .cons li:before { content:"⚠"; color:#db744f; left:0; position:absolute; }
    .result-summary { background:#eaf5ed; border:1px solid #cfe6d6; border-radius:12px; padding:13px 15px; color:#315e4c; font-size:12px; margin-bottom:16px; }
    .empty { background:#fff; border:1px dashed #c6dcd2; border-radius:14px; padding:34px; text-align:center; color:#71847e; }
    [data-testid="stForm"] { background:#fff; border:1px solid #dce8e3; border-radius:16px; padding:18px 18px 4px; box-shadow:0 15px 35px rgba(28,78,62,.07); }
    div[data-testid="stMetric"] { background:#fff; border:1px solid #dce8e3; border-radius:12px; padding:12px 14px; }
    .stButton button,.stDownloadButton button,.stFormSubmitButton button { background:#ffffff !important; border:1px solid #b9d2c7 !important; border-radius:10px !important; color:#17352f !important; font-weight:800 !important; min-height:2.75rem; opacity:1 !important; white-space:normal !important; }
    .stButton button *,.stDownloadButton button *,.stFormSubmitButton button * { color:inherit !important; opacity:1 !important; visibility:visible !important; }
    .stButton button:hover,.stDownloadButton button:hover { background:#eaf5ed !important; border-color:#65a989 !important; color:#174d3a !important; }
    .stButton button:focus,.stDownloadButton button:focus,.stFormSubmitButton button:focus { box-shadow:0 0 0 3px rgba(47,155,105,.2) !important; }
    .stFormSubmitButton button { background:#174d3a !important; color:#ffffff !important; border-color:#174d3a !important; width:100%; }
    .stFormSubmitButton button:hover { background:#226a4e !important; color:#ffffff !important; }
    .stDownloadButton button:disabled,.stButton button:disabled { background:#eef2f0 !important; color:#61726d !important; opacity:1 !important; }
    details summary { color:#17352f !important; font-weight:700 !important; }
    .db-pill { display:inline-flex; align-items:center; gap:7px; background:#e9f5ed; border:1px solid #cde5d5; border-radius:999px; color:#1c6548; font:600 9px monospace; padding:7px 10px; }
    .db-dot { width:7px; height:7px; border-radius:50%; background:#2f9b69; box-shadow:0 0 0 4px rgba(47,155,105,.12); }
    @media(max-width:900px){.finance-grid{grid-template-columns:repeat(2,1fr)}.explain-grid{grid-template-columns:1fr}.explain+.explain{border-left:0;border-top:1px solid #e6eee9}.hero h1{font-size:32px}}
    </style>
    """,
    unsafe_allow_html=True,
)


def dec_million(value: float) -> Decimal:
    return decimal_value(value) * Decimal("1000000")


def dec_billion(value: float) -> Decimal:
    return decimal_value(value) * Decimal("1000000000")


def dti_color(dti: Decimal) -> str:
    if dti <= Decimal("0.36"):
        return "safe"
    if dti <= Decimal("0.45"):
        return "watch"
    return "risk"


def timeline_frame(assessment: ProjectAssessment) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Tháng": row.month,
                "Giai đoạn": row.phase,
                "Lãi suất (%/năm)": float(row.annual_rate_percent),
                "Dư nợ đầu kỳ": float(row.opening_balance),
                "Gốc": float(row.principal),
                "Lãi": float(row.interest),
                "PMT": float(row.payment),
                "DTI (%)": float(row.dti * 100),
                "FCF": float(row.free_cash_flow),
            }
            for row in assessment.analysis.timeline
        ]
    )


def timeline_csv(assessment: ProjectAssessment) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["month", "phase", "annual_rate_percent", "opening_balance", "principal", "interest", "payment", "closing_balance", "dti_percent", "free_cash_flow"])
    for row in assessment.analysis.timeline:
        writer.writerow([row.month, row.phase, row.annual_rate_percent, round(row.opening_balance), round(row.principal), round(row.interest), round(row.payment), round(row.closing_balance), row.dti * 100, round(row.free_cash_flow)])
    return buffer.getvalue().encode("utf-8-sig")


def render_project_card(
    assessment: ProjectAssessment,
    persona: str,
    rank: int,
    profile: FinancialProfile,
    scenario: LoanScenario,
) -> None:
    project = assessment.project
    analysis = assessment.analysis
    pros, cons = build_explanations(assessment, persona)
    fcf_class = "danger" if analysis.min_fcf < Decimal("3000000") else ""
    dti_percent = analysis.max_dti * 100
    dti_width = min(float(dti_percent), 100)
    pros_html = "".join(f"<li>{html.escape(item)}</li>" for item in pros)
    cons_html = "".join(f"<li>{html.escape(item)}</li>" for item in cons)
    card = f"""
    <div class="project-card">
      <div class="project-head">
        <div><div class="rank">TOP {rank:02d} · PHƯƠNG ÁN QUA BỘ LỌC CỨNG</div><h3>{html.escape(project.name)}</h3><div class="project-meta">{html.escape(project.area)} · {html.escape(project.bedrooms)} · {project.area_m2:.0f} m² · Cách nơi làm việc {assessment.distance_km:.1f} km</div></div>
        <div class="fit-score"><strong>{assessment.total_score:.0f}</strong><span>Fit Score</span></div>
      </div>
      <div class="finance-block">
        <div class="finance-grid">
          <div class="metric"><small>Giá tham chiếu</small><b>{format_vnd(project.price_min_vnd)}</b></div>
          <div class="metric"><small>PMT cao nhất · tháng {analysis.max_payment_month}</small><b>{format_million(analysis.max_payment)}</b></div>
          <div class="metric"><small>DTI cao nhất · tháng {analysis.max_dti_month}</small><b>{dti_percent:.1f}%</b><div class="dti-track"><div class="dti-fill {dti_color(analysis.max_dti)}" style="width:{dti_width}%"></div></div></div>
          <div class="metric"><small>FCF thấp nhất · tháng {analysis.min_fcf_month}</small><b class="{fcf_class}">{format_million(analysis.min_fcf)}</b></div>
          <div class="metric"><small>Quỹ dự phòng</small><b>{analysis.survival_months:.1f} tháng</b></div>
        </div>
      </div>
      <div class="explain-grid"><div class="explain pros"><h4>Ưu điểm</h4><ul>{pros_html}</ul></div><div class="explain cons"><h4>Rủi ro cần lưu ý</h4><ul>{cons_html}</ul></div></div>
    </div>
    """
    st.markdown(card, unsafe_allow_html=True)

    button_left, button_right = st.columns(2)
    button_left.download_button(
        "Tải ảnh tư vấn A4",
        data=build_a4_report_png(assessment, persona, profile, scenario),
        file_name=f"minfit-{project.id}-a4.png",
        mime="image/png",
        key=f"report-{project.id}",
        width="stretch",
    )
    button_right.download_button(
        "Tải lịch trả nợ CSV",
        data=timeline_csv(assessment),
        file_name=f"timeline-{project.id}.csv",
        mime="text/csv",
        key=f"timeline-{project.id}",
        width="stretch",
    )

    with st.expander(f"Xem timeline {len(analysis.timeline)} tháng · {project.name}"):
        frame = timeline_frame(assessment)
        chart_frame = frame[["Tháng", "PMT", "FCF"]].copy()
        chart_frame["PMT"] = chart_frame["PMT"] / 1_000_000
        chart_frame["FCF"] = chart_frame["FCF"] / 1_000_000
        st.caption("Đơn vị biểu đồ: triệu đồng/tháng")
        st.line_chart(chart_frame.set_index("Tháng"), color=["#d59a35", "#267a59"])
        st.line_chart(frame.set_index("Tháng")[["DTI (%)"]], color=["#d45145"])
        st.dataframe(
            frame.style.format(
                {
                    "Lãi suất (%/năm)": "{:.2f}",
                    "Dư nợ đầu kỳ": "{:,.0f}",
                    "Gốc": "{:,.0f}",
                    "Lãi": "{:,.0f}",
                    "PMT": "{:,.0f}",
                    "DTI (%)": "{:.2f}",
                    "FCF": "{:,.0f}",
                }
            ),
            width="stretch",
            height=340,
        )


st.markdown(
    """
    <section class="hero">
      <div class="hero-kicker">Công cụ thẩm định cho môi giới bất động sản</div>
      <h1>MinFit — biết chính xác tháng nào dòng tiền căng nhất.</h1>
      <p>MinFit mô phỏng từng tháng trong toàn bộ kỳ vay, áp dụng bộ lọc LTV, DTI và FCF trước khi xếp hạng dự án theo chân dung khách hàng.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

control_column, output_column = st.columns([0.36, 0.64], gap="large")

with control_column:
    st.markdown('<div class="panel-title">Bảng điều khiển môi giới</div>', unsafe_allow_html=True)
    with st.form("assessment_form"):
        st.subheader("1. Chân dung khách hàng")
        persona_label = st.selectbox("Nhóm khách hàng", list(PERSONA_OPTIONS), index=2)
        monthly_income_million = st.number_input("Tổng thu nhập / tháng (triệu đồng)", min_value=10.0, max_value=1000.0, value=100.0, step=5.0)
        available_cash_billion = st.number_input("Tiền mặt sẵn có (tỷ đồng)", min_value=0.1, max_value=100.0, value=2.0, step=0.1)
        existing_debt_million = st.number_input("Khoản trả nợ hiện hữu / tháng (triệu đồng)", min_value=0.0, max_value=500.0, value=0.0, step=1.0)
        essential_expenses_million = st.number_input("Chi phí sinh hoạt thiết yếu / tháng (triệu đồng)", min_value=1.0, max_value=500.0, value=25.0, step=1.0)

        st.subheader("2. Vị trí & tiện ích")
        area_preset = st.selectbox("Khu vực làm việc tham khảo", list(AREA_PRESETS), index=0)
        preset_lat, preset_lng = AREA_PRESETS[area_preset]
        workplace_lat = st.number_input("Vĩ độ nơi làm việc (Lat)", min_value=-90.0, max_value=90.0, value=preset_lat, format="%.6f")
        workplace_lng = st.number_input("Kinh độ nơi làm việc (Lng)", min_value=-180.0, max_value=180.0, value=preset_lng, format="%.6f")
        amenity_labels = st.multiselect("Chọn đúng 3 tiện ích bắt buộc", list(AMENITY_OPTIONS), default=["Trường học", "Công viên", "Chỗ đỗ xe"], max_selections=3)

        st.subheader("3. Cấu hình khoản vay")
        loan_ratio = st.slider("Tỷ lệ vay / giá tài sản (LTV)", min_value=0, max_value=90, value=70, step=5, format="%d%%")
        term_years = st.slider("Thời hạn vay", min_value=10, max_value=30, value=20, step=1, format="%d năm")
        phase1_rate = st.number_input("Lãi suất ưu đãi (%/năm)", min_value=0.0, max_value=30.0, value=7.5, step=0.1)
        phase1_months = st.number_input("Thời gian ưu đãi (tháng)", min_value=0, max_value=359, value=24, step=1)
        phase2_rate = st.number_input("Lãi suất thả nổi giả định (%/năm)", min_value=0.0, max_value=30.0, value=13.5, step=0.1)
        repayment_label = st.selectbox("Phương pháp trả nợ", list(REPAYMENT_OPTIONS), index=0)
        grace_label = st.selectbox("Kịch bản ân hạn", list(GRACE_OPTIONS), index=0)
        grace_months = st.number_input("Số tháng ân hạn", min_value=0, max_value=120, value=0, step=1)
        st.form_submit_button("Phân tích an toàn với MinFit", width="stretch")

persona = PERSONA_OPTIONS[persona_label]
required_amenities = tuple(AMENITY_OPTIONS[label] for label in amenity_labels)

with output_column:
    st.markdown('<div class="panel-title">Kết quả thẩm định</div>', unsafe_allow_html=True)
    if len(required_amenities) != 3:
        st.error("Cần chọn đúng 3 tiện ích bắt buộc để áp dụng ma trận chấm điểm.")
        st.stop()
    if phase1_months >= term_years * 12:
        st.error("Thời gian lãi suất ưu đãi phải ngắn hơn tổng thời hạn vay.")
        st.stop()
    effective_grace = 0 if GRACE_OPTIONS[grace_label] == "none" else grace_months
    if effective_grace >= term_years * 12:
        st.error("Thời gian ân hạn phải ngắn hơn tổng thời hạn vay.")
        st.stop()

    profile = FinancialProfile(
        monthly_income=dec_million(monthly_income_million),
        available_cash=dec_billion(available_cash_billion),
        existing_debt_payment=dec_million(existing_debt_million),
        essential_expenses=dec_million(essential_expenses_million),
    )
    scenario = LoanScenario(
        loan_ratio_percent=decimal_value(loan_ratio),
        term_years=term_years,
        phase1_rate_percent=decimal_value(phase1_rate),
        phase1_months=int(phase1_months),
        phase2_rate_percent=decimal_value(phase2_rate),
        repayment_method=REPAYMENT_OPTIONS[repayment_label],
        grace_type=GRACE_OPTIONS[grace_label],
        grace_months=int(grace_months),
    )

    start_time = time.perf_counter()
    try:
        db_info = database_status()
        database_projects = load_projects_from_database()
        database_weights = load_persona_weights_from_database()
    except DATABASE_ERRORS as error:
        st.error("Không thể kết nối cơ sở dữ liệu local. Hãy kiểm tra cấu hình database.")
        st.code(str(error))
        st.stop()

    eligible, rejected = rank_projects(
        projects=database_projects,
        profile=profile,
        scenario=scenario,
        persona=persona,
        workplace_lat=workplace_lat,
        workplace_lng=workplace_lng,
        required_amenities=required_amenities,
        weights_config=database_weights,
    )
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    top_projects = eligible[:3]

    summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
    summary_col1.metric("Dự án qua bộ lọc", f"{len(eligible)}/{db_info.project_count}")
    summary_col2.metric("Dự án bị loại", len(rejected))
    summary_col3.metric("Thời gian xử lý", f"{elapsed_ms:.0f} ms")
    db_label = "SQLite" if db_info.server.lower() == "sqlite" else "SQL Server"
    summary_col4.markdown(f'<span class="db-pill"><span class="db-dot"></span>{db_label} · {html.escape(db_info.database)}</span>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="result-summary"><b>{html.escape(persona_label)}</b> · {repayment_label} · LTV {loan_ratio}% · Lãi suất {phase1_rate:.1f}% trong {phase1_months} tháng, sau đó {phase2_rate:.1f}%.</div>',
        unsafe_allow_html=True,
    )

    if not top_projects:
        st.markdown('<div class="empty"><b>Không có dự án nào vượt qua bộ lọc cứng.</b><br>Hãy giảm tỷ lệ vay, tăng vốn đối ứng hoặc điều chỉnh cấu trúc chi tiêu.</div>', unsafe_allow_html=True)
    else:
        summary_report = "\n\n".join(build_text_report(item, persona) for item in top_projects)
        st.download_button("Tải báo cáo tổng hợp Top 3", summary_report.encode("utf-8-sig"), "minfit-top-3.txt", "text/plain", width="stretch")
        for rank, assessment in enumerate(top_projects, start=1):
            render_project_card(assessment, persona, rank, profile, scenario)

    with st.expander(f"Xem {len(rejected)} dự án bị loại bởi bộ lọc cứng"):
        if not rejected:
            st.success("Không có dự án nào bị loại trong kịch bản hiện tại.")
        else:
            rejected_rows = [
                {
                    "Dự án": item.project.name,
                    "Giá": format_vnd(item.project.price_min_vnd),
                    "DTI max": f"{item.analysis.max_dti * 100:.1f}%",
                    "FCF min": format_million(item.analysis.min_fcf),
                    "Lý do loại": " ".join(item.rejection_reasons),
                }
                for item in rejected
            ]
            st.dataframe(pd.DataFrame(rejected_rows), width="stretch", hide_index=True)

st.caption("Dữ liệu dự án được đọc từ cơ sở dữ liệu local. Trên macOS MinFit dùng SQLite; trên Windows có thể dùng SQL Server MinFitLocal. MinFit không lưu hồ sơ thu nhập, khoản nợ hoặc chi phí của khách hàng xuống ổ cứng.")
