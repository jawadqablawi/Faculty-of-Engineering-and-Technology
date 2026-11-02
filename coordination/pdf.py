"""Arabic PDF exports for both native Linux and serverless Python deployments."""

from django.conf import settings
from django.template.loader import render_to_string
from pathlib import Path


def render_pdf(template, context):
    if settings.ETCS_PDF_BACKEND == "weasyprint":
        from weasyprint import HTML

        return HTML(string=render_to_string(template, context)).write_pdf()
    from fpdf import FPDF

    pdf = FPDF(orientation="P" if "letter_print" in template else "L")
    pdf.add_font("ETCS", fname=str(Path(__file__).parent / "assets" / "DejaVuSans.ttf"))
    pdf.set_font("ETCS", size=11)
    pdf.set_text_shaping(use_shaping_engine=True, direction="rtl")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    def paragraph(text, size=11):
        pdf.set_font("ETCS", size=size)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(
            w=0, h=7, text=str(text), align="R", new_x="LMARGIN", new_y="NEXT"
        )

    if "letter_print" in template:
        letter = context["letter"]
        paragraph("جامعة فلسطين التقنية – خضوري", 16)
        paragraph("كلية الهندسة والتكنولوجيا", 14)
        pdf.ln(6)
        paragraph("مرجع التتبع الداخلي: " + letter.number)
        paragraph("الرقم الرسمي: " + (letter.official_number or "لم يصدر"))
        paragraph("التاريخ: " + letter.created.strftime("%Y-%m-%d"))
        paragraph("إلى: " + letter.recipient)
        paragraph(letter.subject, 14)
        pdf.ln(4)
        paragraph(letter.body)
        paragraph("مرفقات الطلب:")
        for attachment in letter.activity.attachments.filter(deleted=False):
            paragraph("• " + attachment.name)
        pdf.ln(5)
        paragraph("الحالة المسجلة: " + letter.status)
        paragraph("هذه النسخة لا تمثل توقيعاً أو إثبات إرسال رسمي.", 9)
    else:
        if "generic_print" in template:
            title = context["title"]
            headers = context["headers"]
            rows = context["rows"]
        else:
            title = "تقرير أنشطة كلية الهندسة والتكنولوجيا"
            headers = ["رقم الطلب", "النادي", "العنوان", "التاريخ", "الحالة"]
            rows = [
                [
                    a.number or "مسودة",
                    a.club.name,
                    a.title,
                    str(a.date or ""),
                    a.get_status_display(),
                ]
                for a in context["rows"]
            ]
        paragraph(title, 16)
        pdf.ln(5)
        if rows:
            pdf.set_font("ETCS", size=9)
            with pdf.table(
                first_row_as_headings=False, text_align="RIGHT", line_height=7
            ) as table:
                heading = table.row()
                for cell in reversed(headers):
                    heading.cell(str(cell))
                for data in rows:
                    row = table.row()
                    for cell in reversed(data):
                        row.cell(str(cell))
        else:
            paragraph("لا توجد سجلات مطابقة")
    return bytes(pdf.output())
