"""Server-side unread counts for agent portal sidebar."""

from __future__ import annotations

from typing import Dict

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import (
    Agent,
    Conversation,
    ConversationAgentReadState,
    InternalDmConversation,
    InternalDmMemberReadState,
    InternalDmMessage,
    Message,
    TeamChannelMemberReadState,
    TeamChannelMessage,
    TeamMembership,
)


def _inbox_unread_for_conversation(
    db: Session, tenant_id: int, agent_id: int, conversation_id: int
) -> int:
    st = (
        db.query(ConversationAgentReadState)
        .filter(
            ConversationAgentReadState.tenant_id == tenant_id,
            ConversationAgentReadState.conversation_id == conversation_id,
            ConversationAgentReadState.agent_id == agent_id,
        )
        .first()
    )
    lr = st.last_read_message_id if st else 0
    return (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.sender_type == "customer",
            Message.id > lr,
        )
        .count()
    )


def count_inbox_unread(db: Session, tenant_id: int, agent_id: int) -> int:
    convs = (
        db.query(Conversation)
        .filter(Conversation.tenant_id == tenant_id, Conversation.agent_id == agent_id)
        .all()
    )
    total = 0
    for c in convs:
        total += _inbox_unread_for_conversation(db, tenant_id, agent_id, c.id)
    return total


def count_team_channel_unread(db: Session, tenant_id: int, agent_id: int) -> int:
    mem = (
        db.query(TeamMembership)
        .filter(TeamMembership.tenant_id == tenant_id, TeamMembership.agent_id == agent_id)
        .first()
    )
    if not mem:
        return 0
    st = (
        db.query(TeamChannelMemberReadState)
        .filter(
            TeamChannelMemberReadState.tenant_id == tenant_id,
            TeamChannelMemberReadState.team_id == mem.team_id,
            TeamChannelMemberReadState.agent_id == agent_id,
        )
        .first()
    )
    lr = st.last_read_message_id if st else 0
    return (
        db.query(TeamChannelMessage)
        .filter(
            TeamChannelMessage.tenant_id == tenant_id,
            TeamChannelMessage.team_id == mem.team_id,
            TeamChannelMessage.id > lr,
        )
        .count()
    )


def count_dm_unread(db: Session, tenant_id: int, agent_id: int) -> int:
    convs = (
        db.query(InternalDmConversation)
        .filter(
            InternalDmConversation.tenant_id == tenant_id,
            or_(
                InternalDmConversation.agent_one_id == agent_id,
                InternalDmConversation.agent_two_id == agent_id,
            ),
        )
        .all()
    )
    total = 0
    for c in convs:
        st = (
            db.query(InternalDmMemberReadState)
            .filter(
                InternalDmMemberReadState.tenant_id == tenant_id,
                InternalDmMemberReadState.conversation_id == c.id,
                InternalDmMemberReadState.agent_id == agent_id,
            )
            .first()
        )
        lr = st.last_read_message_id if st else 0
        total += (
            db.query(InternalDmMessage)
            .filter(
                InternalDmMessage.conversation_id == c.id,
                InternalDmMessage.sender_agent_id != agent_id,
                InternalDmMessage.id > lr,
            )
            .count()
        )
    return total


def build_unread_summary_dict(db: Session, tenant_id: int, agent_id: int) -> Dict[str, int]:
    return {
        "inbox": count_inbox_unread(db, tenant_id, agent_id),
        "team_channel": count_team_channel_unread(db, tenant_id, agent_id),
        "dm": count_dm_unread(db, tenant_id, agent_id),
    }


def dm_unread_for_conversation(db: Session, tenant_id: int, agent_id: int, conversation_id: int) -> int:
    st = (
        db.query(InternalDmMemberReadState)
        .filter(
            InternalDmMemberReadState.tenant_id == tenant_id,
            InternalDmMemberReadState.conversation_id == conversation_id,
            InternalDmMemberReadState.agent_id == agent_id,
        )
        .first()
    )
    lr = st.last_read_message_id if st else 0
    return (
        db.query(InternalDmMessage)
        .filter(
            InternalDmMessage.conversation_id == conversation_id,
            InternalDmMessage.sender_agent_id != agent_id,
            InternalDmMessage.id > lr,
        )
        .count()
    )


def resolve_agent_id_for_user(db: Session, tenant_id: int, user_id: int) -> int | None:
    ag = (
        db.query(Agent)
        .filter(Agent.user_id == user_id, Agent.tenant_id == tenant_id)
        .first()
    )
    return ag.id if ag else None
