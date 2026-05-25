from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.models import Portfolio
from app.utils.json_tools import parse_json_list, parse_json_object
from app.services.portfolio_service import normalize_education_entries, normalize_skill_categories


def build_resume_pdf(portfolio: Portfolio) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=LETTER, topMargin=32, bottomMargin=32)
    styles = getSampleStyleSheet()

    education_entries = normalize_education_entries(parse_json_list(portfolio.education_json), portfolio.education_text)
    skill_categories = normalize_skill_categories(parse_json_list(portfolio.skills_json), portfolio.skills_text)

    content = [
        Paragraph(f"<b>{portfolio.full_name}</b>", styles["Title"]),
        Paragraph(portfolio.title_tagline, styles["Heading3"]),
        Spacer(1, 8),
        Paragraph(portfolio.bio or "", styles["BodyText"]),
        Spacer(1, 12),
        Paragraph("<b>Skills</b>", styles["Heading2"]),
        Paragraph(
            " | ".join(
                f"{category['category_name']}: {', '.join(category['skills'])}"
                for category in skill_categories
            ),
            styles["BodyText"],
        ),
        Spacer(1, 12),
        Paragraph("<b>Education</b>", styles["Heading2"]),
    ]

    for entry in education_entries:
        content.append(
            Paragraph(
                " - ".join(
                    part
                    for part in [
                        entry["course_name"],
                        entry["specialization"],
                        entry["institution_name"],
                    ]
                    if part
                ),
                styles["Heading4"],
            )
        )
        meta = " | ".join(
            part
            for part in [
                entry["custom_type"] if entry["education_type"] == "Custom" else entry["education_type"],
                entry["university"],
                entry["start_year"],
                entry["end_year"],
                entry["score"],
            ]
            if part
        )
        if meta:
            content.append(Paragraph(meta, styles["BodyText"]))
        if entry["description"]:
            content.append(Paragraph(entry["description"], styles["BodyText"]))

    experiences = parse_json_list(portfolio.experiences_json)
    if experiences:
        content.extend([Spacer(1, 12), Paragraph("<b>Experience</b>", styles["Heading2"])])
        for item in experiences:
            line = f"{item.get('role', '')} | {item.get('company', '')} | {item.get('duration', '')}"
            content.append(Paragraph(line.strip(" |"), styles["Heading4"]))
            content.append(Paragraph(item.get("description", ""), styles["BodyText"]))

    if portfolio.projects:
        content.extend([Spacer(1, 12), Paragraph("<b>Projects</b>", styles["Heading2"])])
        for project in portfolio.projects:
            content.append(Paragraph(project.title, styles["Heading4"]))
            content.append(Paragraph(project.description, styles["BodyText"]))

    certificates = parse_json_list(portfolio.certificates_json)
    if certificates:
        content.extend([Spacer(1, 12), Paragraph("<b>Certificates</b>", styles["Heading2"])])
        for item in certificates:
            line = f"{item.get('name', '')} - {item.get('issuer', '')} {item.get('year', '')}".strip()
            content.append(Paragraph(line, styles["BodyText"]))

    contact = parse_json_object(portfolio.contact_data)
    contact_parts = [value for value in contact.values() if isinstance(value, str) and value.startswith(("http", "+", "@"))]
    if contact_parts:
        content.extend([Spacer(1, 12), Paragraph("<b>Contact</b>", styles["Heading2"])])
        content.append(Paragraph(" | ".join(contact_parts), styles["BodyText"]))

    document.build(content)
    return buffer.getvalue()
