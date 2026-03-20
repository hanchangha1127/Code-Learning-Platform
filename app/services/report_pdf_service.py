from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from html import escape
from io import BytesIO
import re
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Report, ReportType

_WHITESPACE_RE = re.compile(r"\s+")
_LATEST_REPORT_BATCH_SIZE = 25


def _normalize_text(value: Any, *, limit: int = 220) -> str:
    text = _WHITESPACE_RE.sub(" ", str(value or "").strip())
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 1, 0)].rstrip()}…"


def _normalize_list(value: Any, *, limit: int = 3, item_limit: int = 120) -> list[str]:
    if not isinstance(value, list):
        return []

    rows: list[str] = []
    for item in value:
        text = _normalize_text(item, limit=item_limit)
        if not text or text in rows:
            continue
        rows.append(text)
        if len(rows) >= limit:
            break
    return rows


def _normalize_evidence_items(value: Any, *, limit: int = 3, item_limit: int = 120) -> list[str]:
    if isinstance(value, Mapping):
        rows: list[str] = []
        for key, item in value.items():
            text = _normalize_text(item, limit=item_limit)
            if not text:
                continue
            rows.append(_normalize_text(f"{key}: {text}", limit=item_limit))
            if len(rows) >= limit:
                break
        return rows
    if isinstance(value, list):
        return _normalize_list(value, limit=limit, item_limit=item_limit)

    text = _normalize_text(value, limit=item_limit)
    return [text] if text else []


def _extract_solution_plan(report: Report) -> dict[str, Any]:
    stats = report.stats if isinstance(report.stats, dict) else {}
    solution_plan = stats.get("solutionPlan")
    if isinstance(solution_plan, dict):
        return solution_plan
    return {}


def _extract_metric_snapshot(report: Report) -> dict[str, Any]:
    stats = report.stats if isinstance(report.stats, dict) else {}
    metric_snapshot = stats.get("metricSnapshot")
    if isinstance(metric_snapshot, dict):
        return metric_snapshot
    return {}


def _extract_detail_records(report: Report) -> list[dict[str, Any]]:
    stats = report.stats if isinstance(report.stats, dict) else {}
    detail_records = stats.get("detailRecords")
    if not isinstance(detail_records, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in detail_records:
        if isinstance(item, Mapping):
            rows.append(dict(item))
    return rows


def _format_metric_number(value: Any, *, suffix: str = "") -> str:
    if value is None or value == "":
        return "-"
    return f"{value}{suffix}"


def _short_trend(value: Any) -> str:
    text = _normalize_text(value, limit=80).lower()
    if not text:
        return "데이터 보강 필요"
    if "개선" in text or "improv" in text:
        return "개선"
    if "하락" in text or "감소" in text or "declin" in text:
        return "하락"
    if "안정" in text or "stable" in text:
        return "안정"
    if "부족" in text:
        return "데이터 부족"
    return _normalize_text(value, limit=32)


def _build_summary_text(
    *,
    metric_snapshot: Mapping[str, Any],
    solution_summary: str,
) -> str:
    attempts = metric_snapshot.get("attempts")
    accuracy = metric_snapshot.get("accuracy")
    avg_score = metric_snapshot.get("avgScore")
    trend = _short_trend(metric_snapshot.get("trend"))

    summary_parts: list[str] = []
    metric_bits: list[str] = []

    if attempts not in (None, ""):
        metric_bits.append(f"최근 {attempts}회 학습")
    if accuracy not in (None, ""):
        metric_bits.append(f"정확도 {_format_metric_number(accuracy, suffix='%')}")
    if avg_score not in (None, ""):
        metric_bits.append(f"평균 점수 {_format_metric_number(avg_score)}")

    if metric_bits:
        summary_parts.append(", ".join(metric_bits) + " 기준입니다.")
    if trend and trend not in ("-", ""):
        summary_parts.append(f"현재 추세는 {trend}입니다.")
    if solution_summary:
        summary_parts.append(solution_summary)

    return _normalize_text(" ".join(summary_parts), limit=260) or "최근 학습 기록을 바탕으로 다음 학습 우선순위를 정리했습니다."


def _build_next_steps(
    *,
    focus_actions: list[str],
    learning_habits: list[str],
    checkpoints: list[str],
) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()

    for item in [*focus_actions, *learning_habits, *checkpoints]:
        normalized = _normalize_text(item, limit=120)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        rows.append(normalized)
        if len(rows) >= 3:
            break

    return rows


def _build_study_guide_text(
    *,
    metric_snapshot: Mapping[str, Any],
    focus_actions: list[str],
    learning_habits: list[str],
    checkpoints: list[str],
) -> str:
    trend = _short_trend(metric_snapshot.get("trend"))
    accuracy = metric_snapshot.get("accuracy")

    opener = "다음 학습은 범위를 넓히기보다 지금 흔들리는 포인트를 짧게 반복하는 편이 좋습니다."
    try:
        accuracy_value = float(accuracy) if accuracy not in (None, "") else None
    except (TypeError, ValueError):
        accuracy_value = None

    if trend == "하락":
        opener = "지금은 새 유형을 늘리기보다 최근 오답 유형을 다시 묶어 복기하는 편이 좋습니다."
    elif trend == "개선":
        opener = "지금 흐름이 좋아서 현재 방식은 유지하되 검증 루틴을 더해 안정화하는 편이 좋습니다."
    elif accuracy_value is not None and accuracy_value < 60:
        opener = "정확도가 아직 낮아서 문제 수를 늘리기보다 한 문제당 복기 밀도를 높이는 편이 좋습니다."

    sentences = [opener]
    if focus_actions:
        sentences.append(f"우선순위는 {', '.join(focus_actions[:2])} 순서로 두세요.")
    if learning_habits:
        sentences.append(f"학습 루틴은 {', '.join(learning_habits[:2])} 정도로 가볍게 고정하면 좋습니다.")
    if checkpoints:
        sentences.append(f"다음 확인 기준은 {', '.join(checkpoints[:2])} 입니다.")

    return _normalize_text(" ".join(sentences), limit=300) or opener


def _build_detail_record_header(record: Mapping[str, Any], index: int) -> str:
    title = (
        _normalize_text(record.get("title"), limit=60)
        or _normalize_text(record.get("modeLabel"), limit=60)
        or _normalize_text(record.get("mode"), limit=60)
        or "문제 풀이 기록"
    )
    return f"사례 {index}: {title}"


def _build_detail_record_lines(record: Mapping[str, Any]) -> list[str]:
    question_context = record.get("questionContext") if isinstance(record.get("questionContext"), Mapping) else {}
    evaluation = record.get("evaluation") if isinstance(record.get("evaluation"), Mapping) else {}

    summary_bits = [
        _normalize_text(record.get("result"), limit=24),
        f"점수 {_format_metric_number(record.get('score'))}",
        f"시간 {_format_metric_number(record.get('durationSeconds'), suffix='초')}",
        _normalize_text(record.get("difficulty"), limit=20),
        _normalize_text(record.get("language"), limit=20),
        _normalize_text(evaluation.get("wrongType") or record.get("wrongType"), limit=24),
    ]
    lines = [
        _normalize_text(" · ".join(bit for bit in summary_bits if bit), limit=220),
    ]

    question_bits: list[str] = []
    for value in (
        question_context.get("prompt"),
        question_context.get("scenario"),
        question_context.get("codeOrContext"),
        question_context.get("errorLog"),
    ):
        text = _normalize_text(value, limit=120)
        if text:
            question_bits.append(text)
    option_bits = _normalize_evidence_items(question_context.get("options"), limit=3, item_limit=80)
    commit_bits = _normalize_evidence_items(question_context.get("commits"), limit=3, item_limit=80)
    if question_bits or option_bits or commit_bits:
        lines.append(_normalize_text(f"문제 맥락: {' / '.join([*question_bits, *option_bits, *commit_bits])}", limit=300))

    learner_response = _normalize_text(record.get("learnerResponse"), limit=180)
    expected_answer = _normalize_text(record.get("expectedAnswer"), limit=180)
    if learner_response:
        lines.append(f"작성 답안: {learner_response}")
    if expected_answer:
        lines.append(f"기대 답안: {expected_answer}")

    evaluation_bits: list[str] = []
    for value in (
        evaluation.get("feedbackSummary"),
        evaluation.get("comparison"),
        evaluation.get("referenceExplanation"),
    ):
        text = _normalize_text(value, limit=120)
        if text:
            evaluation_bits.append(text)
    if evaluation_bits:
        lines.append(_normalize_text(f"평가: {' / '.join(evaluation_bits)}", limit=280))

    for label, value in (
        ("강점", evaluation.get("strengths")),
        ("보완", evaluation.get("improvements")),
        ("놓친 포인트", evaluation.get("missedPoints")),
        ("맞춘 포인트", evaluation.get("matchedPoints")),
        ("오답 유형 분포", evaluation.get("wrongTypeCounts")),
        ("선택지 검토", evaluation.get("optionReviews")),
        ("커밋 검토", evaluation.get("commitReviews")),
    ):
        items = _normalize_evidence_items(value, limit=3, item_limit=110)
        if items:
            lines.append(f"{label}: {', '.join(items)}")

    return [line for line in lines if line]


def build_report_brief(
    *,
    solution_plan: Mapping[str, Any] | None,
    metric_snapshot: Mapping[str, Any] | None,
    fallback_title: str = "학습 리포트",
    fallback_summary: str = "",
) -> dict[str, Any]:
    plan = solution_plan if isinstance(solution_plan, Mapping) else {}
    metrics = metric_snapshot if isinstance(metric_snapshot, Mapping) else {}

    title = (
        _normalize_text(plan.get("goal"), limit=90)
        or _normalize_text(fallback_title, limit=90)
        or "학습 리포트"
    )
    solution_summary = (
        _normalize_text(plan.get("solutionSummary"), limit=140)
        or _normalize_text(fallback_summary, limit=140)
    )

    focus_actions = _normalize_list(
        plan.get("priorityActions") or plan.get("recommendations"),
        limit=3,
        item_limit=120,
    )
    learning_habits = _normalize_list(
        plan.get("dailyHabits") or plan.get("focusTopics"),
        limit=3,
        item_limit=120,
    )
    checkpoints = _normalize_list(
        plan.get("checkpoints") or plan.get("metricsToTrack"),
        limit=3,
        item_limit=120,
    )
    next_steps = _build_next_steps(
        focus_actions=focus_actions,
        learning_habits=learning_habits,
        checkpoints=checkpoints,
    )

    headline_source = focus_actions[0] if focus_actions else solution_summary
    headline = _normalize_text(headline_source, limit=100) or "이번 주 학습 우선순위를 정리했습니다."
    summary = _build_summary_text(metric_snapshot=metrics, solution_summary=solution_summary)
    study_guide = _build_study_guide_text(
        metric_snapshot=metrics,
        focus_actions=focus_actions,
        learning_habits=learning_habits,
        checkpoints=checkpoints,
    )

    return {
        "title": title,
        "headline": headline,
        "summary": summary,
        "studyGuide": study_guide,
        "metrics": [
            {
                "label": "시도 수",
                "value": _format_metric_number(metrics.get("attempts"), suffix="회"),
            },
            {
                "label": "정확도",
                "value": _format_metric_number(metrics.get("accuracy"), suffix="%"),
            },
            {
                "label": "평균 점수",
                "value": _format_metric_number(metrics.get("avgScore")),
            },
            {
                "label": "추세",
                "value": _short_trend(metrics.get("trend")),
            },
        ],
        "focusActions": focus_actions,
        "learningHabits": learning_habits,
        "checkpoints": checkpoints,
        "nextSteps": next_steps,
    }


def build_report_brief_from_report(report: Report) -> dict[str, Any]:
    stats = report.stats if isinstance(report.stats, dict) else {}
    cached = stats.get("reportBrief")
    generated = build_report_brief(
        solution_plan=_extract_solution_plan(report),
        metric_snapshot=_extract_metric_snapshot(report),
        fallback_title=report.title,
        fallback_summary=report.summary,
    )
    if isinstance(cached, dict):
        return {**generated, **cached}
    return generated


def _is_latest_milestone_candidate(report: Report | None) -> bool:
    if report is None:
        return False
    stats = report.stats if isinstance(report.stats, dict) else {}
    source = str(stats.get("source") or "").strip().lower()
    return source != "platform"


def _select_latest_milestone_report(reports: list[Report]) -> Report | None:
    for report in reports:
        if _is_latest_milestone_candidate(report):
            return report
    return None


def _load_latest_milestone_report(db: Session, user_id: int) -> Report | None:
    query = (
        db.query(Report)
        .filter(Report.user_id == user_id, Report.report_type == ReportType.milestone)
        .order_by(Report.created_at.desc(), Report.id.desc())
    )
    offset = 0
    while True:
        reports = query.limit(_LATEST_REPORT_BATCH_SIZE).offset(offset).all()
        if not reports:
            return None
        candidate = _select_latest_milestone_report(reports)
        if candidate is not None:
            return candidate
        if len(reports) < _LATEST_REPORT_BATCH_SIZE:
            return None
        offset += _LATEST_REPORT_BATCH_SIZE


def get_latest_report_detail(db: Session, user_id: int) -> dict[str, Any] | None:
    report = _load_latest_milestone_report(db, user_id)
    if report is None:
        return None

    solution_plan = _extract_solution_plan(report)
    metric_snapshot = _extract_metric_snapshot(report)
    brief = build_report_brief_from_report(report)
    goal = _normalize_text(solution_plan.get("goal"), limit=200) or _normalize_text(report.title, limit=200)
    summary = _normalize_text(solution_plan.get("solutionSummary"), limit=400) or _normalize_text(report.summary, limit=400)
    priority_actions = _normalize_list(
        solution_plan.get("priorityActions") or report.recommendations,
        limit=6,
        item_limit=220,
    )
    phase_plan = _normalize_list(solution_plan.get("phasePlan"), limit=6, item_limit=220)
    daily_habits = _normalize_list(solution_plan.get("dailyHabits"), limit=6, item_limit=220)
    focus_topics = _normalize_list(solution_plan.get("focusTopics"), limit=6, item_limit=220)
    metrics_to_track = _normalize_list(solution_plan.get("metricsToTrack"), limit=6, item_limit=220)
    checkpoints = _normalize_list(solution_plan.get("checkpoints"), limit=6, item_limit=220)
    risk_mitigation = _normalize_list(solution_plan.get("riskMitigation"), limit=6, item_limit=220)

    return {
        "reportId": int(report.id),
        "createdAt": report.created_at.isoformat() if report.created_at is not None else None,
        "goal": goal,
        "solutionSummary": summary,
        "priorityActions": priority_actions,
        "phasePlan": phase_plan,
        "dailyHabits": daily_habits,
        "focusTopics": focus_topics,
        "metricsToTrack": metrics_to_track,
        "checkpoints": checkpoints,
        "riskMitigation": risk_mitigation,
        "metricSnapshot": metric_snapshot,
        "reportBrief": brief,
        "pdfDownloadUrl": build_report_pdf_download_url(report.id),
    }


def build_report_pdf_download_url(report_id: int | None) -> str | None:
    if report_id is None:
        return None
    return f"/platform/reports/{int(report_id)}/pdf"


def _format_created_at(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def _load_reportlab_components() -> dict[str, Any]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise RuntimeError("report_pdf_generation_unavailable") from exc

    return {
        "colors": colors,
        "A4": A4,
        "ParagraphStyle": ParagraphStyle,
        "getSampleStyleSheet": getSampleStyleSheet,
        "mm": mm,
        "pdfmetrics": pdfmetrics,
        "UnicodeCIDFont": UnicodeCIDFont,
        "Paragraph": Paragraph,
        "SimpleDocTemplate": SimpleDocTemplate,
        "Spacer": Spacer,
        "Table": Table,
        "TableStyle": TableStyle,
    }


def _ensure_pdf_font(components: Mapping[str, Any]) -> str:
    pdfmetrics = components["pdfmetrics"]
    unicode_cid_font = components["UnicodeCIDFont"]
    candidate_fonts = ("HYGothic-Medium", "HYSMyeongJo-Medium")

    for font_name in candidate_fonts:
        try:
            pdfmetrics.getFont(font_name)
        except KeyError:
            try:
                pdfmetrics.registerFont(unicode_cid_font(font_name))
            except Exception:
                continue
        return font_name

    return "Helvetica"


def build_report_pdf_bytes(report: Report) -> bytes:
    components = _load_reportlab_components()
    colors = components["colors"]
    paragraph_style = components["ParagraphStyle"]
    get_sample_style_sheet = components["getSampleStyleSheet"]
    simple_doc_template = components["SimpleDocTemplate"]
    spacer = components["Spacer"]
    paragraph = components["Paragraph"]
    table = components["Table"]
    table_style = components["TableStyle"]
    a4 = components["A4"]
    mm = components["mm"]

    font_name = _ensure_pdf_font(components)
    brief = build_report_brief_from_report(report)
    solution_plan = _extract_solution_plan(report)
    detail_records = _extract_detail_records(report)
    created_at = _format_created_at(report.created_at)
    styles = get_sample_style_sheet()

    base_style = paragraph_style(
        "ReportBase",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=16,
        textColor=colors.HexColor("#1f2937"),
        spaceAfter=6,
    )
    title_style = paragraph_style(
        "ReportTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=20,
        leading=26,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=10,
    )
    meta_style = paragraph_style(
        "ReportMeta",
        parent=base_style,
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=12,
    )
    section_style = paragraph_style(
        "ReportSection",
        parent=base_style,
        fontName=font_name,
        fontSize=12.5,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=8,
        spaceAfter=6,
    )
    bullet_style = paragraph_style(
        "ReportBullet",
        parent=base_style,
        leftIndent=10,
        bulletIndent=0,
        spaceAfter=4,
    )

    story: list[Any] = [
        paragraph(escape(brief.get("title") or "학습 리포트"), title_style),
        paragraph(
            escape(f"리포트 ID {int(report.id)} · 생성 시각 {created_at}"),
            meta_style,
        ),
        paragraph(escape(brief.get("headline") or ""), section_style),
        paragraph(escape(brief.get("summary") or ""), base_style),
        spacer(1, 5 * mm),
    ]

    story.extend(
        [
            paragraph("학습 가이드", section_style),
            paragraph(escape(_normalize_text(brief.get("studyGuide"), limit=340) or "다음 학습 가이드를 준비 중입니다."), base_style),
            spacer(1, 3 * mm),
        ]
    )

    metric_rows = [["지표", "값"]]
    for item in brief.get("metrics") or []:
        label = _normalize_text(item.get("label"), limit=24)
        value = _normalize_text(item.get("value"), limit=40)
        metric_rows.append([label or "-", value or "-"])

    metrics_table = table(metric_rows, colWidths=[42 * mm, 120 * mm])
    metrics_table.setStyle(
        table_style(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("LEADING", (0, 0), (-1, -1), 14),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.extend(
        [
            paragraph("핵심 지표", section_style),
            metrics_table,
            spacer(1, 4 * mm),
        ]
    )

    plan_sections = (
        (
            "실행 우선순위",
            _normalize_list(solution_plan.get("priorityActions") or report.recommendations, limit=5, item_limit=220),
            "우선 실행 항목이 아직 정리되지 않았습니다.",
        ),
        (
            "단계 계획",
            _normalize_list(solution_plan.get("phasePlan"), limit=5, item_limit=220),
            "단계별 계획이 아직 정리되지 않았습니다.",
        ),
        (
            "하루 루틴",
            _normalize_list(solution_plan.get("dailyHabits"), limit=5, item_limit=220),
            "학습 루틴이 아직 정리되지 않았습니다.",
        ),
        (
            "집중 주제",
            _normalize_list(solution_plan.get("focusTopics"), limit=5, item_limit=220),
            "집중 주제가 아직 정리되지 않았습니다.",
        ),
        (
            "추적 지표",
            _normalize_list(solution_plan.get("metricsToTrack"), limit=5, item_limit=220),
            "추적할 지표가 아직 정리되지 않았습니다.",
        ),
        (
            "체크포인트",
            _normalize_list(solution_plan.get("checkpoints"), limit=5, item_limit=220),
            "확인할 체크포인트가 아직 없습니다.",
        ),
        (
            "리스크 대응",
            _normalize_list(solution_plan.get("riskMitigation"), limit=5, item_limit=220),
            "리스크 대응 전략이 아직 정리되지 않았습니다.",
        ),
    )

    story.append(paragraph("상세 학습 계획", section_style))
    for section_title, section_items, empty_text in plan_sections:
        story.append(paragraph(section_title, section_style))
        if section_items:
            for item in section_items:
                story.append(paragraph(escape(item), bullet_style, bulletText="•"))
        else:
            story.append(paragraph(escape(empty_text), base_style))

    story.append(spacer(1, 3 * mm))

    story.append(paragraph("최근 풀이 사례", section_style))
    if detail_records:
        detail_summary_rows = [["사례", "핵심 요약"]]
        for index, record in enumerate(detail_records[:4], start=1):
            header = _build_detail_record_header(record, index)
            summary_line = _normalize_text(
                " · ".join(line for line in _build_detail_record_lines(record)[:2] if line),
                limit=180,
            )
            detail_summary_rows.append([header, summary_line or "-"])

        detail_summary_table = table(detail_summary_rows, colWidths=[38 * mm, 124 * mm])
        detail_summary_table.setStyle(
            table_style(
                [
                    ("FONTNAME", (0, 0), (-1, -1), font_name),
                    ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                    ("LEADING", (0, 0), (-1, -1), 13),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(detail_summary_table)
        story.append(spacer(1, 3 * mm))

        story.append(paragraph("사례별 세부", section_style))
        for index, record in enumerate(detail_records[:4], start=1):
            story.append(paragraph(escape(_build_detail_record_header(record, index)), section_style))
            for line in _build_detail_record_lines(record):
                story.append(paragraph(escape(line), bullet_style, bulletText="•"))
            story.append(spacer(1, 2 * mm))
    else:
        story.append(paragraph(escape("세부 풀이 기록이 아직 저장되지 않았습니다."), base_style))

    for section_title, section_items, empty_text in (
        ("실행 순서", brief.get("nextSteps") or [], "바로 실행할 단계가 아직 정리되지 않았습니다."),
        ("지금 집중할 것", brief.get("focusActions") or [], "우선 실행 항목이 아직 정리되지 않았습니다."),
        ("학습 루틴", brief.get("learningHabits") or [], "추천 루틴이 아직 정리되지 않았습니다."),
        ("다음 체크포인트", brief.get("checkpoints") or [], "확인할 체크포인트가 아직 없습니다."),
    ):
        story.append(paragraph(section_title, section_style))
        if section_items:
            for item in section_items:
                story.append(paragraph(escape(item), bullet_style, bulletText="•"))
        else:
            story.append(paragraph(escape(empty_text), base_style))

    buffer = BytesIO()
    document = simple_doc_template(
        buffer,
        pagesize=a4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=brief.get("title") or "학습 리포트",
        author="Code Learning Platform",
    )
    document.build(story)
    return buffer.getvalue()


def generate_report_pdf_download(db: Session, user_id: int, report_id: int) -> tuple[str, bytes]:
    report = (
        db.query(Report)
        .filter(Report.id == report_id, Report.user_id == user_id)
        .first()
    )
    if report is None:
        raise LookupError("report_not_found")

    filename = f"learning-report-{int(report.id)}.pdf"
    return filename, build_report_pdf_bytes(report)


def get_latest_report_download_metadata(db: Session, user_id: int) -> dict[str, Any]:
    report = _load_latest_milestone_report(db, user_id)

    if report is None:
        return {
            "available": False,
            "reportId": None,
            "createdAt": None,
            "goal": "",
            "summary": "",
            "pdfDownloadUrl": None,
        }

    brief = build_report_brief_from_report(report)
    return {
        "available": True,
        "reportId": int(report.id),
        "createdAt": report.created_at.isoformat() if report.created_at is not None else None,
        "goal": _normalize_text(brief.get("title"), limit=120) or _normalize_text(report.title, limit=120),
        "summary": _normalize_text(brief.get("summary"), limit=220) or _normalize_text(report.summary, limit=220),
        "pdfDownloadUrl": build_report_pdf_download_url(report.id),
    }
