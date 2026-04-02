from datetime import datetime
from typing import List, Optional, Dict, Any
import base64

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Team, TeamMembership, TeamEvent, Notification, TeamAsset, TeamChannelMessage, Agent, User


router = APIRouter()


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
    sender_agent_id: int
    sender_name: str
    content: str
    created_at: datetime


class TeamChannelMessageCreate(BaseModel):
    tenant_id: int
    sender_agent_id: int
    content: str


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


@router.get("/{team_id}/channel/messages", response_model=List[TeamChannelMessageOut])
async def list_team_channel_messages(
    team_id: int,
    tenant_id: int,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    team = db.query(Team).filter(Team.id == team_id, Team.tenant_id == tenant_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    rows = (
        db.query(TeamChannelMessage)
        .filter(TeamChannelMessage.tenant_id == tenant_id, TeamChannelMessage.team_id == team_id)
        .order_by(TeamChannelMessage.created_at.asc())
        .limit(max(1, min(limit, 1000)))
        .all()
    )
    return [
        TeamChannelMessageOut(
            id=r.id,
            team_id=r.team_id,
            sender_agent_id=r.sender_agent_id,
            sender_name=_agent_name(db, r.sender_agent_id),
            content=r.content,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/{team_id}/channel/messages", response_model=TeamChannelMessageOut, status_code=status.HTTP_201_CREATED)
async def create_team_channel_message(
    team_id: int,
    payload: TeamChannelMessageCreate,
    db: Session = Depends(get_db),
):
    team = db.query(Team).filter(Team.id == team_id, Team.tenant_id == payload.tenant_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required")
    row = TeamChannelMessage(
        tenant_id=payload.tenant_id,
        team_id=team_id,
        sender_agent_id=payload.sender_agent_id,
        content=content,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return TeamChannelMessageOut(
        id=row.id,
        team_id=row.team_id,
        sender_agent_id=row.sender_agent_id,
        sender_name=_agent_name(db, row.sender_agent_id),
        content=row.content,
        created_at=row.created_at,
    )


@router.patch(
    "/{team_id}/channel/messages/{message_id}",
    response_model=TeamChannelMessageOut,
)
async def update_team_channel_message(
    team_id: int,
    message_id: int,
    payload: TeamChannelMessageUpdate,
    db: Session = Depends(get_db),
):
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
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required")
    row.content = content
    db.add(row)
    db.commit()
    db.refresh(row)
    return TeamChannelMessageOut(
        id=row.id,
        team_id=row.team_id,
        sender_agent_id=row.sender_agent_id,
        sender_name=_agent_name(db, row.sender_agent_id),
        content=row.content,
        created_at=row.created_at,
    )

