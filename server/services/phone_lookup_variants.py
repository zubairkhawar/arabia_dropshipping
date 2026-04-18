"""
Normalize mobiles for PK/UAE/KSA and produce all common string forms for API lookup.

Used when matching customers after email verification: the store may index
mobile as local (0321…), international (92321…), with +, or with 00 prefix.
"""
from __future__ import annotations

import re
from typing import List, Optional


def _strip_to_digits(raw: str) -> str:
    s = re.sub(r"[\s\-().]+", "", (raw or "").strip())
    if s.startswith("+"):
        s = s[1:]
    while s.startswith("00"):
        s = s[2:]
    if not s.isdigit():
        return ""
    return s


def normalize_mobile_for_flow(raw: str) -> Optional[str]:
    """
    Same rules as the customer bot: PK → 03… local, UAE/SA → digits starting 971/966.

    Pakistan  → local format  03XXXXXXXXX  (11 digits)
    UAE       → international 971…  (10–12 digits)
    Saudi     → international 966…  (12–13 digits)
    """
    s = _strip_to_digits(raw)
    if not s:
        return None

    if s.startswith("92") and len(s) == 12 and s[2] == "3":
        return "0" + s[2:]
    if s.startswith("03") and len(s) == 11:
        return s
    if s.startswith("3") and len(s) == 10:
        return "0" + s

    if s.startswith("971") and 10 <= len(s) <= 12:
        return s

    if s.startswith("966") and 12 <= len(s) <= 13:
        return s

    return None


def mobile_lookup_variants(raw: str) -> List[str]:
    """
    Deduped list of mobile strings to try against GET /customers?email=&mobile=.
    First entry is always the canonical form from normalize_mobile_for_flow when valid.
    """
    canon = normalize_mobile_for_flow(raw)
    if not canon:
        return []

    d = _strip_to_digits(raw)
    seen: set[str] = set()
    out: List[str] = []

    def add(x: str) -> None:
        t = (x or "").strip()
        if not t or t in seen:
            return
        seen.add(t)
        out.append(t)

    add(canon)

    # Pakistan — local 03XXXXXXXXX
    if canon.startswith("03") and len(canon) == 11 and canon[2] == "3":
        intl = "92" + canon[1:]
        add(intl)
        add(f"+{intl}")
        add(f"00{intl}")
        if d and d != intl:
            add(d)
        ten = canon[1:]
        if len(ten) == 10 and ten.isdigit():
            add(ten)

    elif d.startswith("92") and len(d) == 12 and d[2] == "3":
        add(d)
        add(f"+{d}")
        add(f"00{d}")
        add("0" + d[2:])
        if len(d[2:]) == 10:
            add(d[2:])

    # UAE
    elif canon.startswith("971"):
        add(f"+{canon}")
        add(f"00{canon}")
        national = canon[3:]
        if national.isdigit() and len(national) >= 8 and not national.startswith("0"):
            add("0" + national)

    # Saudi Arabia
    elif canon.startswith("966"):
        add(f"+{canon}")
        add(f"00{canon}")
        national = canon[3:]
        if national.isdigit() and len(national) >= 8 and not national.startswith("0"):
            add("0" + national)

    return out
