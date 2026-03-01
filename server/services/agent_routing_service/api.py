from fastapi import APIRouter

router = APIRouter()


@router.get("/agents")
async def list_agents():
    """List all agents with their status"""
    return {"message": "List agents endpoint"}


@router.post("/agents/{agent_id}/status")
async def update_agent_status(agent_id: int):
    """Update agent status (online, busy, offline)"""
    return {"message": f"Update agent {agent_id} status endpoint"}


@router.post("/assign")
async def assign_conversation():
    """Assign conversation to available agent"""
    return {"message": "Assign conversation endpoint"}


@router.post("/transfer")
async def transfer_conversation():
    """Transfer conversation between agents"""
    return {"message": "Transfer conversation endpoint"}


@router.get("/routing-rules")
async def get_routing_rules():
    """Get conversation routing rules"""
    return {"message": "Get routing rules endpoint"}


@router.post("/routing-rules")
async def create_routing_rule():
    """Create new routing rule"""
    return {"message": "Create routing rule endpoint"}
