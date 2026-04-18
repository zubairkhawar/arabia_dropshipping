"""
Human-readable agent schedule lines for customer bot + handoff messages.
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Set

# Convention: 0 = Monday … 6 = Sunday (matches typical admin JSON [0..6]).
_DAY_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_DAY_AR = (
    "الإثنين",
    "الثلاثاء",
    "الأربعاء",
    "الخميس",
    "الجمعة",
    "السبت",
    "الأحد",
)
_DAY_RU = ("Pir", "Mangal", "Budh", "Jumeraat", "Jumma", "Hafta", "Itwar")


def _normalize_day_list(raw: Any) -> Set[int]:
    out: Set[int] = set()
    if raw is None:
        return out
    if isinstance(raw, (list, tuple)):
        for x in raw:
            try:
                d = int(x)
            except (TypeError, ValueError):
                continue
            if 0 <= d <= 6:
                out.add(d)
    return out


def _is_all_week(days: Set[int]) -> bool:
    return len(days) == 7


def _is_24h_window(start: str, end: str) -> bool:
    s = (start or "").strip()
    e = (end or "").strip()
    if not s or not e:
        return False
    sn = re.sub(r"\s", "", s).lower()
    en = re.sub(r"\s", "", e).lower()
    pairs = {
        ("00:00", "23:59"),
        ("00:00", "24:00"),
        ("0:00", "23:59"),
        ("0:00", "24:00"),
    }
    return (sn, en) in pairs or (sn.startswith("00:00") and en in ("23:59", "24:00"))


def _day_list_phrase_en(days: Set[int]) -> str:
    if not days:
        return "days to be confirmed"
    if _is_all_week(days):
        return "every day of the week"
    ordered = [d for d in range(7) if d in days]
    names = [_DAY_EN[d] for d in ordered]
    if len(names) == 1:
        return names[0]
    # consecutive span?
    if len(ordered) >= 2 and ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"{_DAY_EN[ordered[0]]} to {_DAY_EN[ordered[-1]]}"
    return ", ".join(names)


def _day_list_phrase_ar(days: Set[int]) -> str:
    if not days:
        return "أيام العمل غير محددة بعد"
    if _is_all_week(days):
        return "طوال أيام الأسبوع"
    ordered = [d for d in range(7) if d in days]
    names = [_DAY_AR[d] for d in ordered]
    return "، ".join(names)


def _day_list_phrase_ru(days: Set[int]) -> str:
    if not days:
        return "working days abhi confirm nahi"
    if _is_all_week(days):
        return "poora hafta (7 din)"
    ordered = [d for d in range(7) if d in days]
    names = [_DAY_RU[d] for d in ordered]
    return ", ".join(names)


def format_tenant_schedule_for_customer(
    lang: str,
    *,
    working_days: Any,
    start_time: Optional[str],
    end_time: Optional[str],
) -> str:
    """
    One or two sentences describing when human agents are expected to be reachable,
    based on tenant_schedules. No raw JSON lists.
    """
    days = _normalize_day_list(working_days)
    st = (start_time or "").strip() or "09:00"
    et = (end_time or "").strip() or "18:00"
    lang_l = (lang or "english").strip().lower()

    if _is_all_week(days) and _is_24h_window(st, et):
        if lang_l == "arabic":
            return (
                "وكلاء الدعم متاحون على مدار الساعة طوال أيام الأسبوع "
                f"({st}–{et}، حسب إعدادات النظام). يمكنك كتابة \"agent\" أو \"support\" للتواصل مع موظف."
            )
        if lang_l == "roman_urdu":
            return (
                "Hamare support agents 24 ghante, 7 din available hain "
                f"({st} se {et}, system schedule ke mutabiq). Human agent ke liye \"agent\" ya \"support\" likhein."
            )
        return (
            "Our human support agents are available 24 hours a day, 7 days a week "
            f"({st}–{et}, per your workspace schedule). Type \"agent\" or \"support\" to reach someone."
        )

    day_phrase_en = _day_list_phrase_en(days)
    if lang_l == "arabic":
        return (
            f"أيام عمل وكلاء الدعم البشري: {_day_list_phrase_ar(days)}، "
            f"من {st} إلى {et}. يمكنك كتابة \"agent\" أو \"support\" للتواصل مع موظف."
        )
    if lang_l == "roman_urdu":
        return (
            f"Human support agents ke working din: {_day_list_phrase_ru(days)}, "
            f"aur timing {st} se {et} tak hai. Agent ke liye \"agent\" ya \"support\" likhein."
        )
    return (
        f"Our human support agents are scheduled on {day_phrase_en}, "
        f"from {st} to {et}. Type \"agent\" or \"support\" to speak with a person."
    )


def format_tenant_schedule_line_for_handoff(lang: str, working_days: Any, start_time: str, end_time: str) -> str:
    """Single line with clock emoji for handoff_unavailable templates ({schedule} placeholder)."""
    body = format_tenant_schedule_for_customer(
        lang, working_days=working_days, start_time=start_time, end_time=end_time
    )
    first = body.split(".")[0].strip()
    if lang == "arabic":
        return f"🕐 {first}.\n"
    if lang == "roman_urdu":
        return f"🕐 {first}.\n"
    return f"🕐 {first}.\n"
