"""Team channel @mentions: resolve display names (including spaces) and merge payload + text."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from models import Agent, TeamMembership, User

TEAM_MSG_PREFIX = "__TEAM_MSG_JSON__"


def _decode_team_payload(raw: str) -> Dict[str, Any]:
    if isinstance(raw, str) and raw.startswith(TEAM_MSG_PREFIX):
        try:
            obj = json.loads(raw[len(TEAM_MSG_PREFIX) :])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return {"text": raw if isinstance(raw, str) else str(raw)}


def _agent_display_name(db: Session, agent_id: int) -> str:
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        return f"Agent {agent_id}"
    user = db.query(User).filter(User.id == agent.user_id).first()
    if user and user.full_name:
        return user.full_name.strip()
    if user and user.email:
        return user.email.split("@")[0]
    return f"Agent {agent_id}"


def team_member_roster(db: Session, tenant_id: int, team_id: int) -> List[Tuple[int, str]]:
    rows = (
        db.query(TeamMembership)
        .filter(TeamMembership.tenant_id == tenant_id, TeamMembership.team_id == team_id)
        .all()
    )
    out: List[Tuple[int, str]] = []
    for m in rows:
        name = _agent_display_name(db, m.agent_id).strip()
        if name:
            out.append((m.agent_id, name))
    return out


def _boundary_ok(next_ch: Optional[str]) -> bool:
    if next_ch is None:
        return True
    if next_ch.isspace():
        return True
    # Do not treat combining marks as "continuing" the mention (names are normalized).
    cat = unicodedata.category(next_ch)
    if cat.startswith("M"):
        return True
    if next_ch.isalnum() or next_ch == "_":
        return False
    return True


def parse_mention_agent_ids_from_text(text: str, roster: List[Tuple[int, str]]) -> Set[int]:
    """Longest roster name match after each @ (case-insensitive), including spaces in names."""
    if not text or not roster:
        return set()
    by_len = sorted(roster, key=lambda x: len(x[1]), reverse=True)
    found: Set[int] = set()
    i = 0
    n = len(text)
    while i < n:
        at = text.find("@", i)
        if at < 0:
            break
        rest = text[at + 1 :]
        matched_len = 0
        matched_id: Optional[int] = None
        for aid, name in by_len:
            if not name or len(rest) < len(name):
                continue
            chunk = rest[: len(name)]
            if chunk.lower() != name.lower():
                continue
            nxt = rest[len(name)] if len(rest) > len(name) else None
            if not _boundary_ok(nxt):
                continue
            matched_len = len(name)
            matched_id = aid
            break
        if matched_id is not None:
            found.add(matched_id)
            i = at + 1 + matched_len
        else:
            i = at + 1
    return found


def collect_mention_targets_for_message(
    db: Session,
    tenant_id: int,
    team_id: int,
    raw_content: str,
    sender_agent_id: Optional[int],
) -> List[int]:
    """
    Mentioned agent ids from JSON `mentions` plus @Name spans in `text`.
    Excludes the sender (agent messages only).
    """
    obj = _decode_team_payload(raw_content)
    text = obj.get("text")
    if not isinstance(text, str):
        text = ""
    roster = team_member_roster(db, tenant_id, team_id)
    ids: Set[int] = parse_mention_agent_ids_from_text(text, roster)
    raw_mentions = obj.get("mentions")
    if isinstance(raw_mentions, list):
        for x in raw_mentions:
            try:
                aid = int(x)
                if aid >= 1:
                    ids.add(aid)
            except (TypeError, ValueError):
                continue
    member_ids = {m[0] for m in roster}
    ids = {a for a in ids if a in member_ids}
    if sender_agent_id is not None and sender_agent_id >= 1:
        ids.discard(sender_agent_id)
    return sorted(ids)
