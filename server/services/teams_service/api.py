from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Team, TeamMembership, TeamEvent


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

    db.delete(membership)
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
    if payload.from_team_id:
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

