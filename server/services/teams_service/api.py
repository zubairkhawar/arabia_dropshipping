from datetime import datetime
from typing import List, Optional, Dict, Any
import base64
import json

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import desc
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal, get_db
from models import (
    Agent,
    MessageUserDeletion,
    Notification,
    Team,
    TeamAsset,
    TeamChannelMemberReadState,
    TeamChannelMessage,
    TeamEvent,
    TeamMembership,
    User,
)
from services.auth_service.api import get_current_user, get_current_user_optional
from services.teams_service.team_channel_hub import hub


router = APIRouter()


def _decode_websocket_user(token: str, db: Session) -> Optional[User]:
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        email = payload.get("sub")
        if not email:
            return None
        return (
            db.query(User)
            .filter(User.email == email, User.is_active.is_(True))
            .first()
        )
    except JWTError:
        return None


async def _broadcast_read_state(tenant_id: int, team_id: int, agent_id: int, last_read_message_id: int) -> None:
    await hub.broadcast_json(
        tenant_id,
        team_id,
        {
            "type": "READ_STATE",
            "agent_id": agent_id,
            "last_read_message_id": last_read_message_id,
        },
    )


class MemberReadStateOut(BaseModel):
    agent_id: int
    agent_name: str
    last_read_message_id: int
    updated_at: datetime


class TeamChannelReadStateIn(BaseModel):
    tenant_id: int
    last_read_message_id: int


class TeamMemberOut(BaseModel):
    agent_id: int
    team_id: int


class TeamOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    description: Optional[str] = None
    members: List[TeamMemberOut] = []

    class Config:
        from_attributes = True


class TeamCreate(BaseModel):
    tenant_id: int
    name: str
    description: Optional[str] = None


class TeamEventOut(BaseModel):
    id: int
    event_type: str
    actor_agent_id: Optional[int]
    target_agent_id: Optional[int]
    payload: Dict[str, Any]
    created_at: datetime


class TeamMemberAdd(BaseModel):
    agent_id: int
    tenant_id: int


class TeamTransfer(BaseModel):
    agent_id: int
    from_team_id: Optional[int] = None
    to_team_id: int
    tenant_id: int


class TeamAssetOut(BaseModel):
    id: int
    team_id: int
    asset_type: str
    title: Optional[str] = None
    url: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    content_base64: Optional[str] = None
    created_by_agent_id: Optional[int] = None
    created_at: datetime


class TeamAssetCreate(BaseModel):
    tenant_id: int
    asset_type: str
    title: Optional[str] = None
    url: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    content_base64: Optional[str] = None
    created_by_agent_id: Optional[int] = None


class TeamChannelMessageOut(BaseModel):
    id: int
    team_id: int
    sender_agent_id: Optional[int] = None
    posted_by_admin: bool = False
    sender_name: str
    content: str
    created_at: datetime
    reply_to_message_id: Optional[int] = None
    edited_at: Optional[datetime] = None
    deleted_for_everyone_at: Optional[datetime] = None


class TeamChannelMessagesPage(BaseModel):
    """Chronological slice (oldest → newest). Fetched newest-first from DB then reversed."""

    messages: List[TeamChannelMessageOut]
    has_more_older: bool


class TeamChannelMessageCreate(BaseModel):
    """
    Accepts typical JSON from the web client; coerces string numbers and loose booleans
    so minor type drift does not yield 422.
    """

    model_config = ConfigDict(extra="ignore")

    tenant_id: int
    content: str
    sender_agent_id: Optional[int] = None
    posted_by_admin: bool = False
    reply_to_message_id: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def coerce_request_shapes(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        tid = d.get("tenant_id")
        if tid is not None and not isinstance(tid, bool):
            try:
                d["tenant_id"] = int(tid)
            except (TypeError, ValueError):
                pass
        sid = d.get("sender_agent_id", None)
        if sid is None or sid == "":
            d["sender_agent_id"] = None
        elif isinstance(sid, bool):
            raise ValueError("sender_agent_id must be an integer")
        else:
            try:
                if isinstance(sid, float):
                    if not sid.is_integer():
                        raise ValueError("sender_agent_id must be a whole number")
                    d["sender_agent_id"] = int(sid)
                elif isinstance(sid, str):
                    d["sender_agent_id"] = int(sid.strip(), 10)
                else:
                    d["sender_agent_id"] = int(sid)
            except (TypeError, ValueError) as e:
                raise ValueError("sender_agent_id must be an integer") from e
        if "posted_by_admin" in d:
            v = d["posted_by_admin"]
            if isinstance(v, str):
                d["posted_by_admin"] = v.strip().lower() in ("1", "true", "yes", "on")
            elif isinstance(v, bool):
                d["posted_by_admin"] = v
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                d["posted_by_admin"] = bool(v)
            elif v is None:
                d["posted_by_admin"] = False
        raw_content = d.get("content")
        if raw_content is not None and not isinstance(raw_content, str):
            d["content"] = str(raw_content)
        rt = d.get("reply_to_message_id")
        if rt is None or rt == "":
            d["reply_to_message_id"] = None
        elif isinstance(rt, bool):
            raise ValueError("reply_to_message_id must be an integer")
        else:
            try:
                d["reply_to_message_id"] = int(rt)
            except (TypeError, ValueError) as e:
                raise ValueError("reply_to_message_id must be an integer") from e
        return d


class TeamChannelMessageUpdate(BaseModel):
    tenant_id: int
    content: str


MAX_ASSET_BYTES = 10 * 1024 * 1024


@router.get("", response_model=List[TeamOut])
async def list_teams(tenant_id: int, db: Session = Depends(get_db)):
    """
    List teams with their members for a tenant.
    """
    teams = db.query(Team).filter(Team.tenant_id == tenant_id).all()
    result: List[TeamOut] = []
    for team in teams:
        memberships = (
            db.query(TeamMembership)
            .filter(
                TeamMembership.tenant_id == tenant_id,
                TeamMembership.team_id == team.id,
            )
            .all()
        )
        members = [
            TeamMemberOut(agent_id=m.agent_id, team_id=m.team_id) for m in memberships
        ]
        result.append(
            TeamOut(
                id=team.id,
                tenant_id=team.tenant_id,
                name=team.name,
                description=team.description,
                members=members,
            )
        )
    return result


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(payload: TeamCreate, db: Session = Depends(get_db)):
    """
    Create a new team.
    """
    team = Team(
        tenant_id=payload.tenant_id,
        name=payload.name,
        description=payload.description,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return TeamOut(
        id=team.id,
        tenant_id=team.tenant_id,
        name=team.name,
        description=team.description,
        members=[],
    )


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(team_id: int, tenant_id: int, db: Session = Depends(get_db)):
    """
    Delete a team if it has no members.
    """
    memberships = (
        db.query(TeamMembership)
        .filter(
            TeamMembership.tenant_id == tenant_id,
            TeamMembership.team_id == team_id,
        )
        .all()
    )
    if memberships:
        raise HTTPException(
            status_code=400, detail="Cannot delete team with members still assigned"
        )

    team = (
        db.query(Team)
        .filter(Team.id == team_id, Team.tenant_id == tenant_id)
        .first()
    )
    if not team:
        return

    # Remove historical team events first to satisfy FK constraints
    # before deleting the parent team row.
    db.query(TeamEvent).filter(
        TeamEvent.tenant_id == tenant_id,
        TeamEvent.team_id == team_id,
    ).delete(synchronize_session=False)

    # Defensive cleanup: memberships should already be empty (guard above),
    # but remove any stale rows to avoid referential issues.
    db.query(TeamMembership).filter(
        TeamMembership.tenant_id == tenant_id,
        TeamMembership.team_id == team_id,
    ).delete(synchronize_session=False)

    db.delete(team)
    db.commit()
    return


@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    team_id: int,
    payload: TeamMemberAdd,
    db: Session = Depends(get_db),
):
    """
    Add an agent to a team.
    """
    team = (
        db.query(Team)
        .filter(Team.id == team_id, Team.tenant_id == payload.tenant_id)
        .first()
    )
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    existing = (
        db.query(TeamMembership)
        .filter(
            TeamMembership.tenant_id == payload.tenant_id,
            TeamMembership.team_id == team_id,
            TeamMembership.agent_id == payload.agent_id,
        )
        .first()
    )
    if existing:
        return

    membership = TeamMembership(
        tenant_id=payload.tenant_id,
        team_id=team_id,
        agent_id=payload.agent_id,
        created_at=datetime.utcnow(),
    )
    db.add(membership)
    db.add(
        Notification(
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            type="team_assigned",
            message=f"You have been assigned to team {team.name}",
            description="You can now receive conversations routed to this team.",
            from_agent_id=None,
            conversation_id=None,
            read=False,
        )
    )
    db.add(
        TeamEvent(
            tenant_id=payload.tenant_id,
            team_id=team_id,
            event_type="member_added",
            target_agent_id=payload.agent_id,
            payload={},
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    return


@router.delete("/{team_id}/members/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    team_id: int,
    agent_id: int,
    tenant_id: int,
    db: Session = Depends(get_db),
):
    """
    Remove an agent from a team.
    """
    membership = (
        db.query(TeamMembership)
        .filter(
            TeamMembership.tenant_id == tenant_id,
            TeamMembership.team_id == team_id,
            TeamMembership.agent_id == agent_id,
        )
        .first()
    )
    if not membership:
        return

    team = (
        db.query(Team)
        .filter(Team.id == team_id, Team.tenant_id == tenant_id)
        .first()
    )

    db.delete(membership)
    db.add(
        Notification(
            tenant_id=tenant_id,
            agent_id=agent_id,
            type="team_removed",
            message=(
                f"You have been removed from team {team.name}"
                if team
                else "You have been removed from your team"
            ),
            description="Team-based routing for this team is no longer applied to your account.",
            from_agent_id=None,
            conversation_id=None,
            read=False,
        )
    )
    db.add(
        TeamEvent(
            tenant_id=tenant_id,
            team_id=team_id,
            event_type="member_removed",
            target_agent_id=agent_id,
            payload={},
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    return


@router.post("/transfer")
async def transfer_member(payload: TeamTransfer, db: Session = Depends(get_db)):
    """
    Transfer an agent from one team to another.
    """
    from_team_name: Optional[str] = None
    to_team_name: Optional[str] = None
    to_team = (
        db.query(Team)
        .filter(Team.id == payload.to_team_id, Team.tenant_id == payload.tenant_id)
        .first()
    )
    if not to_team:
        raise HTTPException(status_code=404, detail="Target team not found")
    to_team_name = to_team.name

    if payload.from_team_id:
        from_team = (
            db.query(Team)
            .filter(Team.id == payload.from_team_id, Team.tenant_id == payload.tenant_id)
            .first()
        )
        from_team_name = from_team.name if from_team else None
        db.query(TeamMembership).filter(
            TeamMembership.tenant_id == payload.tenant_id,
            TeamMembership.team_id == payload.from_team_id,
            TeamMembership.agent_id == payload.agent_id,
        ).delete()

    membership = TeamMembership(
        tenant_id=payload.tenant_id,
        team_id=payload.to_team_id,
        agent_id=payload.agent_id,
        created_at=datetime.utcnow(),
    )
    db.add(membership)
    db.add(
        Notification(
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            type="team_changed",
            message=(
                f"Your team assignment changed from {from_team_name} to {to_team_name}"
                if from_team_name
                else f"Your team assignment changed to {to_team_name}"
            ),
            description="Future team-routed conversations will follow your new team.",
            from_agent_id=None,
            conversation_id=None,
            read=False,
        )
    )
    db.add(
        TeamEvent(
            tenant_id=payload.tenant_id,
            team_id=payload.to_team_id,
            event_type="member_transferred",
            target_agent_id=payload.agent_id,
            payload={"from_team_id": payload.from_team_id},
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    return {"status": "ok"}


@router.get("/{team_id}/events", response_model=List[TeamEventOut])
async def get_team_events(
    team_id: int,
    tenant_id: int,
    db: Session = Depends(get_db),
):
    """
    Return recent events for a team.
    """
    events = (
        db.query(TeamEvent)
        .filter(TeamEvent.team_id == team_id, TeamEvent.tenant_id == tenant_id)
        .order_by(TeamEvent.created_at.desc())
        .all()
    )
    return [
        TeamEventOut(
            id=e.id,
            event_type=e.event_type,
            actor_agent_id=e.actor_agent_id,
            target_agent_id=e.target_agent_id,
            payload=e.payload or {},
            created_at=e.created_at,
        )
        for e in events
    ]


@router.get("/{team_id}/assets", response_model=List[TeamAssetOut])
async def list_team_assets(team_id: int, tenant_id: int, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.id == team_id, Team.tenant_id == tenant_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    rows = (
        db.query(TeamAsset)
        .filter(TeamAsset.tenant_id == tenant_id, TeamAsset.team_id == team_id)
        .order_by(TeamAsset.created_at.desc())
        .all()
    )
    return rows


@router.post("/{team_id}/assets", response_model=TeamAssetOut, status_code=status.HTTP_201_CREATED)
async def create_team_asset(team_id: int, payload: TeamAssetCreate, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.id == team_id, Team.tenant_id == payload.tenant_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    kind = (payload.asset_type or "").strip().lower()
    if kind not in {"image", "doc", "link"}:
        raise HTTPException(status_code=400, detail="asset_type must be image, doc, or link")

    size_bytes: Optional[int] = None
    if kind in {"image", "doc"}:
        if not payload.content_base64:
            raise HTTPException(status_code=400, detail="content_base64 is required for files")
        try:
            decoded = base64.b64decode(payload.content_base64, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 content")
        size_bytes = len(decoded)
        if size_bytes > MAX_ASSET_BYTES:
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")
    elif not payload.url:
        raise HTTPException(status_code=400, detail="url is required for link assets")

    row = TeamAsset(
        tenant_id=payload.tenant_id,
        team_id=team_id,
        asset_type=kind,
        title=payload.title,
        url=payload.url,
        file_name=payload.file_name,
        mime_type=payload.mime_type,
        size_bytes=size_bytes,
        content_base64=payload.content_base64 if kind in {"image", "doc"} else None,
        created_by_agent_id=payload.created_by_agent_id,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team_asset(asset_id: int, tenant_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(TeamAsset)
        .filter(TeamAsset.id == asset_id, TeamAsset.tenant_id == tenant_id)
        .first()
    )
    if not row:
        return
    db.delete(row)
    db.commit()
    return


def _agent_name(db: Session, agent_id: int) -> str:
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        return f"Agent {agent_id}"
    user = db.query(User).filter(User.id == agent.user_id).first()
    if user and user.full_name:
        return user.full_name
    if user and user.email:
        return user.email.split("@")[0]
    return f"Agent {agent_id}"


def _team_channel_sender_display(db: Session, row: TeamChannelMessage) -> str:
    if bool(getattr(row, "posted_by_admin", False)):
        return "Admin"
    aid = row.sender_agent_id
    if aid is None:
        return "Unknown"
    return _agent_name(db, aid)


@router.get("/{team_id}/channel/member-read-states", response_model=List[MemberReadStateOut])
async def list_team_channel_member_read_states(
    team_id: int,
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    team = db.query(Team).filter(Team.id == team_id, Team.tenant_id == tenant_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    role = (current_user.role or "").lower()
    if role == "agent":
        ag = (
            db.query(Agent)
            .filter(Agent.user_id == current_user.id, Agent.tenant_id == tenant_id)
            .first()
        )
        if not ag:
            raise HTTPException(status_code=403, detail="Not an agent")
        mem = (
            db.query(TeamMembership)
            .filter(
                TeamMembership.tenant_id == tenant_id,
                TeamMembership.team_id == team_id,
                TeamMembership.agent_id == ag.id,
            )
            .first()
        )
        if not mem:
            raise HTTPException(status_code=403, detail="Not a team member")
    elif role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    rows = (
        db.query(TeamChannelMemberReadState)
        .filter(
            TeamChannelMemberReadState.tenant_id == tenant_id,
            TeamChannelMemberReadState.team_id == team_id,
        )
        .all()
    )
    out: List[MemberReadStateOut] = []
    for r in rows:
        out.append(
            MemberReadStateOut(
                agent_id=r.agent_id,
                agent_name=_agent_name(db, r.agent_id),
                last_read_message_id=r.last_read_message_id,
                updated_at=r.updated_at or datetime.utcnow(),
            )
        )
    return out


@router.post("/{team_id}/channel/read-state", status_code=status.HTTP_204_NO_CONTENT)
async def upsert_team_channel_read_state(
    team_id: int,
    payload: TeamChannelReadStateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.tenant_id != payload.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    team = db.query(Team).filter(Team.id == team_id, Team.tenant_id == payload.tenant_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    ag = (
        db.query(Agent)
        .filter(Agent.user_id == current_user.id, Agent.tenant_id == payload.tenant_id)
        .first()
    )
    if not ag:
        raise HTTPException(status_code=403, detail="Only agents can update read state")
    mem = (
        db.query(TeamMembership)
        .filter(
            TeamMembership.tenant_id == payload.tenant_id,
            TeamMembership.team_id == team_id,
            TeamMembership.agent_id == ag.id,
        )
        .first()
    )
    if not mem:
        raise HTTPException(status_code=403, detail="Not a team member")

    row = (
        db.query(TeamChannelMemberReadState)
        .filter(
            TeamChannelMemberReadState.tenant_id == payload.tenant_id,
            TeamChannelMemberReadState.team_id == team_id,
            TeamChannelMemberReadState.agent_id == ag.id,
        )
        .first()
    )
    if row is None:
        row = TeamChannelMemberReadState(
            tenant_id=payload.tenant_id,
            team_id=team_id,
            agent_id=ag.id,
            last_read_message_id=max(0, payload.last_read_message_id),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
    else:
        row.last_read_message_id = max(row.last_read_message_id, payload.last_read_message_id)
        row.updated_at = datetime.utcnow()
        db.add(row)
    db.commit()
    db.refresh(row)
    await _broadcast_read_state(payload.tenant_id, team_id, ag.id, row.last_read_message_id)
    return Response(status_code=204)


def _team_channel_message_to_out(db: Session, r: TeamChannelMessage) -> TeamChannelMessageOut:
    deleted = bool(getattr(r, "deleted_for_everyone_at", None))
    text = "[Message deleted]" if deleted else (r.content or "")
    return TeamChannelMessageOut(
        id=r.id,
        team_id=r.team_id,
        sender_agent_id=r.sender_agent_id,
        posted_by_admin=bool(getattr(r, "posted_by_admin", False)),
        sender_name=_team_channel_sender_display(db, r),
        content=text,
        created_at=r.created_at,
        reply_to_message_id=getattr(r, "reply_to_message_id", None),
        edited_at=getattr(r, "edited_at", None),
        deleted_for_everyone_at=getattr(r, "deleted_for_everyone_at", None),
    )


def _team_channel_rows_to_out(db: Session, rows: List[TeamChannelMessage]) -> List[TeamChannelMessageOut]:
    return [_team_channel_message_to_out(db, r) for r in rows]


def _hidden_team_message_ids(db: Session, user_id: int, mids: List[int]) -> set[int]:
    if not mids:
        return set()
    rows = (
        db.query(MessageUserDeletion.message_id)
        .filter(
            MessageUserDeletion.user_id == user_id,
            MessageUserDeletion.channel == "team",
            MessageUserDeletion.message_id.in_(mids),
        )
        .all()
    )
    return {x[0] for x in rows}


def _require_team_channel_viewer(
    db: Session, tenant_id: int, team_id: int, user: User
) -> Optional[Agent]:
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    role = (user.role or "").lower()
    if role == "admin":
        team = db.query(Team).filter(Team.id == team_id, Team.tenant_id == tenant_id).first()
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        return None
    ag = db.query(Agent).filter(Agent.user_id == user.id, Agent.tenant_id == tenant_id).first()
    if not ag:
        raise HTTPException(status_code=403, detail="Not an agent")
    mem = (
        db.query(TeamMembership)
        .filter(
            TeamMembership.tenant_id == tenant_id,
            TeamMembership.team_id == team_id,
            TeamMembership.agent_id == ag.id,
        )
        .first()
    )
    if not mem:
        raise HTTPException(status_code=403, detail="Not a team member")
    return ag


@router.get("/{team_id}/channel/messages", response_model=TeamChannelMessagesPage)
async def list_team_channel_messages(
    team_id: int,
    tenant_id: int,
    limit: int = Query(50, ge=1, le=200),
    before_id: Optional[int] = Query(None, description="Load older messages with id strictly less than this"),
    since: Optional[datetime] = Query(None, description="ISO UTC: messages strictly after this time (reconnect gap fill)"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    team = db.query(Team).filter(Team.id == team_id, Team.tenant_id == tenant_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    base = db.query(TeamChannelMessage).filter(
        TeamChannelMessage.tenant_id == tenant_id,
        TeamChannelMessage.team_id == team_id,
    )

    def _filter_hidden(raw: List[TeamChannelMessage]) -> List[TeamChannelMessage]:
        if current_user is None or not raw:
            return raw
        hidden = _hidden_team_message_ids(db, current_user.id, [r.id for r in raw])
        return [r for r in raw if r.id not in hidden]

    if since is not None:
        rows = (
            base.filter(TeamChannelMessage.created_at > since)
            .order_by(TeamChannelMessage.created_at.asc())
            .limit(500)
            .all()
        )
        rows = _filter_hidden(rows)
        return TeamChannelMessagesPage(messages=_team_channel_rows_to_out(db, rows), has_more_older=False)

    lim = max(1, min(limit, 200))
    if before_id is not None:
        rows_desc = (
            base.filter(TeamChannelMessage.id < before_id)
            .order_by(desc(TeamChannelMessage.id))
            .limit(lim)
            .all()
        )
        rows = list(reversed(rows_desc))
        rows = _filter_hidden(rows)
        min_id = rows[0].id if rows else before_id
        older = (
            db.query(TeamChannelMessage.id)
            .filter(
                TeamChannelMessage.tenant_id == tenant_id,
                TeamChannelMessage.team_id == team_id,
                TeamChannelMessage.id < min_id,
            )
            .first()
        )
        return TeamChannelMessagesPage(
            messages=_team_channel_rows_to_out(db, rows),
            has_more_older=older is not None,
        )

    rows_desc = base.order_by(desc(TeamChannelMessage.id)).limit(lim).all()
    rows = list(reversed(rows_desc))
    rows = _filter_hidden(rows)
    min_id = rows[0].id if rows else None
    older = None
    if min_id is not None:
        older = (
            db.query(TeamChannelMessage.id)
            .filter(
                TeamChannelMessage.tenant_id == tenant_id,
                TeamChannelMessage.team_id == team_id,
                TeamChannelMessage.id < min_id,
            )
            .first()
        )
    return TeamChannelMessagesPage(
        messages=_team_channel_rows_to_out(db, rows),
        has_more_older=older is not None,
    )


@router.post("/{team_id}/channel/messages", response_model=TeamChannelMessageOut, status_code=status.HTTP_201_CREATED)
async def create_team_channel_message(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
    payload: TeamChannelMessageCreate = Body(...),
):
    team = db.query(Team).filter(Team.id == team_id, Team.tenant_id == payload.tenant_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required")
    reply_to_id = payload.reply_to_message_id
    if reply_to_id is not None:
        parent = (
            db.query(TeamChannelMessage)
            .filter(
                TeamChannelMessage.id == reply_to_id,
                TeamChannelMessage.team_id == team_id,
                TeamChannelMessage.tenant_id == payload.tenant_id,
            )
            .first()
        )
        if not parent:
            raise HTTPException(status_code=400, detail="Invalid reply_to_message_id")
    if payload.posted_by_admin:
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to post as admin",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if (current_user.role or "").lower() != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only tenant admin can post admin team channel messages",
            )
        if current_user.tenant_id != payload.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant mismatch",
            )
        row = TeamChannelMessage(
            tenant_id=payload.tenant_id,
            team_id=team_id,
            sender_agent_id=None,
            posted_by_admin=True,
            content=content,
            created_at=datetime.utcnow(),
            reply_to_message_id=reply_to_id,
        )
    else:
        if payload.sender_agent_id is None:
            raise HTTPException(
                status_code=400,
                detail="sender_agent_id is required unless posted_by_admin is true",
            )
        row = TeamChannelMessage(
            tenant_id=payload.tenant_id,
            team_id=team_id,
            sender_agent_id=payload.sender_agent_id,
            posted_by_admin=False,
            content=content,
            created_at=datetime.utcnow(),
            reply_to_message_id=reply_to_id,
        )
    db.add(row)
    db.commit()
    db.refresh(row)
    msg_out = _team_channel_message_to_out(db, row)
    await hub.broadcast_json(
        payload.tenant_id,
        team_id,
        {"type": "NEW_MESSAGE", "message": msg_out.model_dump(mode="json")},
    )
    from services.agent_portal_service.broadcast import notify_team_members_unread

    await notify_team_members_unread(db, payload.tenant_id, team_id)
    return msg_out


@router.patch(
    "/{team_id}/channel/messages/{message_id}",
    response_model=TeamChannelMessageOut,
)
async def update_team_channel_message(
    team_id: int,
    message_id: int,
    payload: TeamChannelMessageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team_channel_viewer(db, payload.tenant_id, team_id, current_user)
    row = (
        db.query(TeamChannelMessage)
        .filter(
            TeamChannelMessage.id == message_id,
            TeamChannelMessage.team_id == team_id,
            TeamChannelMessage.tenant_id == payload.tenant_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    if getattr(row, "deleted_for_everyone_at", None):
        raise HTTPException(status_code=400, detail="Message was deleted")
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required")
    role = (current_user.role or "").lower()
    ag = (
        db.query(Agent)
        .filter(Agent.user_id == current_user.id, Agent.tenant_id == payload.tenant_id)
        .first()
    )
    allowed = False
    if role == "admin":
        allowed = True
    elif ag and row.sender_agent_id == ag.id and not bool(getattr(row, "posted_by_admin", False)):
        allowed = True
    if not allowed:
        raise HTTPException(status_code=403, detail="Cannot edit this message")
    row.content = content
    row.edited_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    msg_out = _team_channel_message_to_out(db, row)
    await hub.broadcast_json(
        row.tenant_id,
        team_id,
        {"type": "MESSAGE_UPDATED", "message": msg_out.model_dump(mode="json")},
    )
    return msg_out


@router.delete(
    "/{team_id}/channel/messages/{message_id}/for-me",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_team_channel_message_for_me(
    team_id: int,
    message_id: int,
    tenant_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team_channel_viewer(db, tenant_id, team_id, current_user)
    row = (
        db.query(TeamChannelMessage)
        .filter(
            TeamChannelMessage.id == message_id,
            TeamChannelMessage.team_id == team_id,
            TeamChannelMessage.tenant_id == tenant_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    exists = (
        db.query(MessageUserDeletion)
        .filter(
            MessageUserDeletion.message_id == message_id,
            MessageUserDeletion.user_id == current_user.id,
            MessageUserDeletion.channel == "team",
        )
        .first()
    )
    if not exists:
        db.add(
            MessageUserDeletion(
                channel="team",
                message_id=message_id,
                user_id=current_user.id,
                deleted_by_role=(current_user.role or "").lower(),
            )
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{team_id}/channel/messages/{message_id}/for-everyone",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_team_channel_message_for_everyone(
    team_id: int,
    message_id: int,
    tenant_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team_channel_viewer(db, tenant_id, team_id, current_user)
    row = (
        db.query(TeamChannelMessage)
        .filter(
            TeamChannelMessage.id == message_id,
            TeamChannelMessage.team_id == team_id,
            TeamChannelMessage.tenant_id == tenant_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    if getattr(row, "deleted_for_everyone_at", None):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    role = (current_user.role or "").lower()
    ag = (
        db.query(Agent)
        .filter(Agent.user_id == current_user.id, Agent.tenant_id == tenant_id)
        .first()
    )
    allowed = False
    if role == "admin":
        allowed = True
    elif ag and bool(getattr(row, "posted_by_admin", False)):
        allowed = False
    elif ag and row.sender_agent_id == ag.id:
        if (datetime.utcnow() - row.created_at).total_seconds() <= 300:
            allowed = True
    if not allowed:
        raise HTTPException(status_code=403, detail="Cannot delete this message for everyone")
    row.content = "[Message deleted]"
    row.deleted_for_everyone_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    msg_out = _team_channel_message_to_out(db, row)
    await hub.broadcast_json(
        row.tenant_id,
        team_id,
        {"type": "MESSAGE_UPDATED", "message": msg_out.model_dump(mode="json")},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.websocket("/ws/channel/{team_id}")
async def team_channel_websocket(websocket: WebSocket, team_id: int):
    qp = websocket.query_params
    try:
        tenant_id = int(qp.get("tenant_id") or "0")
    except (TypeError, ValueError):
        await websocket.close(code=4400)
        return
    token = (qp.get("token") or "").strip()
    if tenant_id < 1 or not token:
        await websocket.close(code=4400)
        return

    db = SessionLocal()
    try:
        user = _decode_websocket_user(token, db)
        if user is None or user.tenant_id != tenant_id:
            await websocket.close(code=4401)
            return
        team = db.query(Team).filter(Team.id == team_id, Team.tenant_id == tenant_id).first()
        if not team:
            await websocket.close(code=4404)
            return

        role = (user.role or "").lower()
        agent_id: Optional[int] = None
        display_name = user.full_name or (
            user.email.split("@")[0] if user.email else "User"
        )

        if role == "agent":
            ag = (
                db.query(Agent)
                .filter(Agent.user_id == user.id, Agent.tenant_id == tenant_id)
                .first()
            )
            if not ag:
                await websocket.close(code=4403)
                return
            mem = (
                db.query(TeamMembership)
                .filter(
                    TeamMembership.tenant_id == tenant_id,
                    TeamMembership.team_id == team_id,
                    TeamMembership.agent_id == ag.id,
                )
                .first()
            )
            if not mem:
                await websocket.close(code=4403)
                return
            agent_id = ag.id
            an = _agent_name(db, ag.id)
            if an:
                display_name = an
        elif role != "admin":
            await websocket.close(code=4403)
            return
    finally:
        db.close()

    await websocket.accept()
    meta = {"agent_id": agent_id, "name": display_name, "role": role}
    await hub.connect(websocket, tenant_id, team_id, meta)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if data.get("type") != "typing":
                continue
            await hub.broadcast_json(
                tenant_id,
                team_id,
                {
                    "type": "TYPING",
                    "team_id": team_id,
                    "agent_id": agent_id,
                    "name": display_name,
                    "active": bool(data.get("active", True)),
                },
                exclude=websocket,
            )
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(websocket, tenant_id, team_id)

