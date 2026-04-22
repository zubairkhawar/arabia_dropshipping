"""
Parse natural-language order/invoice date windows for store API queries.

Shared by customer_bot_flow and ai_orchestrator_service (no circular imports).
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

_MONTH_NAMES: Dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
    "يناير": 1,
    "كانون الثاني": 1,
    "فبراير": 2,
    "شباط": 2,
    "مارس": 3,
    "آذار": 3,
    "اذار": 3,
    "أبريل": 4,
    "ابريل": 4,
    "نيسان": 4,
    "مايو": 5,
    "أيار": 5,
    "ايار": 5,
    "يونيو": 6,
    "حزيران": 6,
    "يوليو": 7,
    "تموز": 7,
    "أغسطس": 8,
    "اغسطس": 8,
    "آب": 8,
    "اب": 8,
    "سبتمبر": 9,
    "أيلول": 9,
    "ايلول": 9,
    "أكتوبر": 10,
    "اكتوبر": 10,
    "تشرين الأول": 10,
    "تشرين الاول": 10,
    "نوفمبر": 11,
    "تشرين الثاني": 11,
    "ديسمبر": 12,
    "كانون الأول": 12,
    "كانون الاول": 12,
}

_MONTH_LABEL_EN = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


def month_bounds(year: int, month: int) -> Tuple[date, date]:
    _, last_day = calendar.monthrange(year, month)
    return date(year, month, 1), date(year, month, last_day)


def parse_iso_date(s: str) -> Optional[date]:
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _resolve_month_name_span(t: str, ref: date) -> Optional[Dict[str, Optional[str]]]:
    """
    English 'from january to march' / 'from jan to mar 2026' (year optional, defaults ref.year).
    """
    low = t.lower()
    if not re.search(r"\bfrom\s+[a-z]", low):
        return None
    m = re.search(
        r"\bfrom\s+([a-z]{3,9})\s+(?:to|until|through|till|-)\s+([a-z]{3,9})(?:\s+(\d{4}))?\b",
        low,
    )
    if not m:
        return None
    a = m.group(1).strip()
    b = m.group(2).strip()
    year = int(m.group(3)) if m.group(3) else ref.year
    ma = _MONTH_NAMES.get(a)
    mb = _MONTH_NAMES.get(b)
    if ma is None or mb is None:
        return None
    if ma > mb:
        ma, mb = mb, ma
    d1, _ = month_bounds(year, ma)
    _, d2 = month_bounds(year, mb)
    return {
        "label": f"{_MONTH_LABEL_EN[ma]} to {_MONTH_LABEL_EN[mb]} {year}",
        "date_from": d1.isoformat(),
        "date_to": d2.isoformat(),
        "month": None,
    }


def parse_date_range_from_message(
    text: str, today: Optional[date] = None
) -> Optional[Dict[str, Optional[str]]]:
    """
    Extract a date window from free-form text.

    Returns None when no period is found, otherwise:
        label, date_from, date_to (YYYY-MM-DD), month (YYYY-MM or None)
    """
    if not (text or "").strip():
        return None
    t = text.lower()
    ref = today or datetime.utcnow().date()

    span = _resolve_month_name_span(t, ref)
    if span:
        return span

    m = re.search(
        r"(\d{4}-\d{2}-\d{2})\s*(?:to|till|until|through|and|-|–|—|:)\s*(\d{4}-\d{2}-\d{2})",
        t,
    )
    if m:
        d1 = parse_iso_date(m.group(1))
        d2 = parse_iso_date(m.group(2))
        if d1 and d2:
            if d1 > d2:
                d1, d2 = d2, d1
            return {
                "label": f"{d1.isoformat()} to {d2.isoformat()}",
                "date_from": d1.isoformat(),
                "date_to": d2.isoformat(),
                "month": None,
            }

    if "this month" in t or "current month" in t or "is month" in t or "هذا الشهر" in t:
        df, dt = month_bounds(ref.year, ref.month)
        return {
            "label": f"{_MONTH_LABEL_EN[ref.month]} {ref.year}",
            "date_from": df.isoformat(),
            "date_to": dt.isoformat(),
            "month": f"{ref.year:04d}-{ref.month:02d}",
        }

    if "last month" in t or "previous month" in t or "pichla mahina" in t or "الشهر الماضي" in t:
        year, month = (ref.year - 1, 12) if ref.month == 1 else (ref.year, ref.month - 1)
        df, dt = month_bounds(year, month)
        return {
            "label": f"{_MONTH_LABEL_EN[month]} {year}",
            "date_from": df.isoformat(),
            "date_to": dt.isoformat(),
            "month": f"{year:04d}-{month:02d}",
        }

    if re.search(r"\btoday\b", t) or "aaj" in t or "اليوم" in t:
        return {
            "label": "today",
            "date_from": ref.isoformat(),
            "date_to": ref.isoformat(),
            "month": None,
        }

    if re.search(r"\byesterday\b", t) or "kal" in t or "أمس" in t or "امس" in t:
        y = ref - timedelta(days=1)
        return {
            "label": "yesterday",
            "date_from": y.isoformat(),
            "date_to": y.isoformat(),
            "month": None,
        }

    # "last N months" → N * 30 calendar days inclusive (product: last 2 months ≈ 60 days)
    m = re.search(r"\b(?:last|past|previous)\s+(\d{1,2})\s+months?\b", t)
    if m:
        n = max(1, min(24, int(m.group(1))))
        span_days = n * 30
        start = ref - timedelta(days=span_days - 1)
        return {
            "label": f"the last {n} months (~{span_days} days)",
            "date_from": start.isoformat(),
            "date_to": ref.isoformat(),
            "month": None,
        }

    m = re.search(r"\b(?:last|past|previous)\s+(\d{1,3})\s+days?\b", t)
    if m:
        n = max(1, min(365, int(m.group(1))))
        start = ref - timedelta(days=n - 1)
        return {
            "label": f"the last {n} days",
            "date_from": start.isoformat(),
            "date_to": ref.isoformat(),
            "month": None,
        }

    if "this week" in t or "current week" in t or "هذا الأسبوع" in t:
        start = ref - timedelta(days=ref.weekday())
        end = start + timedelta(days=6)
        return {
            "label": "this week",
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "month": None,
        }

    if "last week" in t or "previous week" in t or "الأسبوع الماضي" in t:
        this_week_mon = ref - timedelta(days=ref.weekday())
        start = this_week_mon - timedelta(days=7)
        end = start + timedelta(days=6)
        return {
            "label": "last week",
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "month": None,
        }

    for name in sorted(_MONTH_NAMES.keys(), key=len, reverse=True):
        if name in t:
            num = _MONTH_NAMES[name]
            yr_m = re.search(r"\b(\d{4})\b", t)
            year = int(yr_m.group(1)) if yr_m else ref.year
            df, dt = month_bounds(year, num)
            return {
                "label": f"{_MONTH_LABEL_EN[num]} {year}",
                "date_from": df.isoformat(),
                "date_to": dt.isoformat(),
                "month": f"{year:04d}-{num:02d}",
            }

    return None


_ORDERS_IN_PERIOD_MARKERS = (
    "my orders",
    "all my orders",
    "orders in",
    "orders for",
    "orders from",
    "orders last",
    "orders this",
    "orders of",
    "orders during",
    "orders between",
    "mere orders",
    "meray orders",
    "meri orders",
    "meri sales",
    "sales in",
    "sales for",
    "sales from",
    "sales last",
    "sales this",
    "طلباتي",
    "مبيعاتي",
    "الطلبات",
)


def looks_like_orders_in_period_message(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if any(m in t for m in _ORDERS_IN_PERIOD_MARKERS):
        return True
    if re.search(r"\borders\b", t) and parse_date_range_from_message(text):
        return True
    return False


def looks_like_invoices_in_period_message(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    has_invoice_word = ("invoice" in t) or ("فاتور" in t)
    if not has_invoice_word:
        return False
    return parse_date_range_from_message(text) is not None


def message_suggests_store_date_window(text: Optional[str]) -> bool:
    return looks_like_orders_in_period_message(text or "") or looks_like_invoices_in_period_message(
        text or ""
    )
