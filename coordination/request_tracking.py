"""Presentation for the two existing request workflows."""

from django.utils import timezone

NEXT = {
    "draft": ("أرسل الطلب للمراجعة.", "النادي"),
    "review": ("راجع الطلب وحدد الإجراء التالي.", "المنسق أو النائب المخوّل"),
    "changes": ("عدّل الطلب وأعد إرساله.", "النادي"),
    "preliminary": ("ارفع الطلب إلى المجلس.", "المنسق أو النائب المخوّل"),
    "council": ("سجّل قرار المجلس عند وروده.", "المنسق أو النائب المخوّل"),
    "approvals": (
        "استكمل الموافقات الإلزامية وسجّل قرار الجامعة.",
        "المنسق أو النائب المخوّل",
    ),
    "student_approved": (
        "استكمل الموافقات الإلزامية وسجّل الاعتماد الرسمي.",
        "المنسق أو النائب المخوّل",
    ),
    "approved": ("قدّم التقرير الختامي لمراجعته وإغلاق الطلب.", "النادي ثم المنسق"),
    "completed": ("الطلب مكتمل.", ""),
    "rejected": ("توقفت متابعة الطلب بعد الرفض.", ""),
    "cancelled": ("توقفت متابعة الطلب بعد الإلغاء.", ""),
}


def stages_for(activity):
    simple = activity.details.get("simple_request")
    stages = [("submitted", "التقديم"), ("review", "المراجعة")]
    if not simple or activity.status == "preliminary":
        stages.append(("preliminary", "موافقة أولية"))
    stages.append(("council", "المجلس"))
    if simple:
        stages.append(("approvals", "شؤون الطلبة"))
    stages.extend(
        [
            ("student_approved" if simple else "approvals", "الجامعة"),
            ("approved", "الاعتماد الرسمي"),
            ("completed", "الإغلاق"),
        ]
    )
    return stages


def phase(status):
    return {"draft": "submitted", "changes": "review"}.get(status, status)


def compact_progress(activity):
    stages = stages_for(activity)
    current = phase(activity.status)
    for index, (key, _) in enumerate(stages, 1):
        if key == current and activity.status not in {"draft", "changes"}:
            return f"{index}/{len(stages)}"
    return ""


def tracking(activity, show_reason):
    history = list(
        activity.history.order_by("created", "pk").values(
            "previous",
            "status",
            "created",
            "actor__first_name",
            "actor__last_name",
            *("note",) if show_reason else (),
        )
    )
    latest = next(
        (entry for entry in reversed(history) if entry["status"] == activity.status),
        None,
    )
    first_submission = next(
        (entry for entry in history if entry["status"] == "review"), None
    )
    entered = (
        latest["created"]
        if latest
        else (
            activity.created
            if activity.status == "draft"
            else activity.submitted
            if activity.status == "review" and not history
            else None
        )
    )
    age = (
        max(0, (timezone.localdate() - timezone.localdate(entered)).days)
        if entered
        else None
    )
    simple = activity.details.get("simple_request")
    stages = stages_for(activity)
    position = next(
        (
            index
            for index, (key, _) in enumerate(stages)
            if key == phase(activity.status)
        ),
        None,
    )
    terminal = activity.status in {"rejected", "cancelled"}
    previous = phase(latest["previous"]) if latest and terminal else None
    if terminal:
        position = next(
            (index for index, (key, _) in enumerate(stages) if key == previous), None
        )

    milestones = {
        "submitted": first_submission,
        "review": next(
            (
                entry
                for entry in reversed(history)
                if entry["status"] in {"preliminary", "council"}
            ),
            None,
        ),
        "preliminary": next(
            (entry for entry in reversed(history) if entry["status"] == "preliminary"),
            None,
        ),
        "council": next(
            (
                entry
                for entry in reversed(history)
                if entry["previous"] == "council" and entry["status"] == "approvals"
            ),
            None,
        ),
        "approvals": next(
            (
                entry
                for entry in reversed(history)
                if entry["status"] == ("student_approved" if simple else "approved")
            ),
            None,
        ),
        "student_approved": next(
            (entry for entry in reversed(history) if entry["status"] == "approved"),
            None,
        ),
        "approved": next(
            (entry for entry in reversed(history) if entry["status"] == "approved"),
            None,
        ),
        "completed": next(
            (entry for entry in reversed(history) if entry["status"] == "completed"),
            None,
        ),
    }
    rendered = []
    for index, (key, label) in enumerate(stages):
        entry = milestones[key]
        if terminal and index == position:
            state = "stopped"
        elif index == position and activity.status not in {"approved", "completed"}:
            state = "attention" if activity.status == "changes" else "current"
        elif (position is not None and index <= position) or (terminal and entry):
            state = "done"
        else:
            state = "future"
        rendered.append(
            {
                "label": label,
                "state": state,
                "current": index == position and not terminal,
                "date": (
                    entry["created"]
                    if entry
                    else activity.submitted
                    if key == "submitted"
                    else None
                )
                if state == "done"
                else None,
                "actor": " ".join(
                    filter(
                        None, (entry["actor__first_name"], entry["actor__last_name"])
                    )
                )
                if entry and state == "done"
                else "",
            }
        )
    next_step, owner = NEXT[activity.status]
    if activity.status == "review" and simple:
        next_step = "راجع الطلب وأحله إلى المجلس أو اطلب تعديلات."
    elif activity.status == "preliminary" and not simple:
        next_step = "جهّز الكتاب الرسمي ثم ارفع الطلب إلى المجلس."
    elif activity.status == "approvals" and simple:
        next_step = "سجّل موافقة شؤون الطلبة عند ورودها."
    requirements = [
        item
        for item in activity.approval_requirements.all()
        if item.office not in {"مجلس الطلبة", "الجامعة", "شؤون الطلبة"}
    ]
    return {
        "revision": activity.updated.isoformat(),
        "stages": rendered,
        "next_step": next_step,
        "owner": owner,
        "entered": entered,
        "age": age,
        "requirements": requirements,
        "reason": (
            latest.get("note", "")[:300]
            if latest and activity.status in {"changes", "rejected"}
            else ""
        ),
    }
