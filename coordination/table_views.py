from django.core.paginator import Paginator

REQUEST_SORT = {
    "title": ("الطلب / النشاط", "title"),
    "club": ("النادي", "club__name"),
    "date": ("النوع والموعد", "date"),
    "status": ("الحالة", "status"),
}
AUDIT_SORT = {
    "date": ("التاريخ", "created"),
    "actor": ("المستخدم", "actor__email"),
    "action": ("الإجراء", "action"),
    "record": ("السجل", "record"),
    "note": ("الملاحظات", "note"),
}
LETTER_SORT = {
    "reference": ("مرجع التتبع", "pk"),
    "number": ("الرقم الرسمي", "official_number"),
    "subject": ("الموضوع والنادي", "subject"),
    "status": ("الحالة", "status"),
    "follow_up": ("المتابعة", "follow_up"),
}


def page_context(request, queryset, columns, default_order, per_page):
    sort = request.GET.get("sort", "")
    descending = request.GET.get("direction") == "desc"
    ordering = default_order
    if sort in columns:
        field = columns[sort][1]
        ordering = "-" + field if descending else field
    else:
        sort = ""
    return {
        "page": Paginator(queryset.order_by(ordering, "pk"), per_page).get_page(
            request.GET.get("page")
        ),
        "table_columns": columns,
        "table_sort": sort,
        "table_direction": "desc" if descending else "asc",
    }
