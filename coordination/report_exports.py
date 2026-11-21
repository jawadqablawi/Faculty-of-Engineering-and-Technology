"""Workbook exports, using the caller's already-scoped rows."""

from collections.abc import Iterable
from io import BytesIO

from django.http import FileResponse


def workbook_response(
    headers: list[str], rows: Iterable, filename: str, title: str = "Sheet"
) -> FileResponse:
    from openpyxl import Workbook

    book = Workbook(write_only=True)
    sheet = book.create_sheet(title)
    sheet.sheet_view.rightToLeft = True
    sheet.append(headers)
    for row in rows:
        sheet.append(
            [
                "'" + value
                if isinstance(value, str) and value.startswith(("=", "+", "-", "@"))
                else value
                for value in row
            ]
        )
    stream = BytesIO()
    book.save(stream)
    stream.seek(0)
    return FileResponse(stream, as_attachment=True, filename=filename)


def activity_workbook(activities) -> FileResponse:
    headers = [
        "رقم الطلب",
        "النادي",
        "العنوان",
        "النوع",
        "التاريخ",
        "الحالة",
        "الحضور المتوقع",
        "الميزانية",
    ]
    rows = (
        [
            a.number or "",
            a.club.name,
            a.title,
            a.get_kind_display(),
            str(a.date or ""),
            a.get_status_display(),
            a.participants,
            float(a.budget),
        ]
        for a in activities.iterator(chunk_size=250)
    )
    return workbook_response(headers, rows, "etcs-report.xlsx", title="الأنشطة")
