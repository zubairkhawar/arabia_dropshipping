from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_tenants():
    """List all tenants (admin only)"""
    return {"message": "List tenants endpoint"}


@router.post("/")
async def create_tenant():
    """Create a new tenant"""
    return {"message": "Create tenant endpoint"}


@router.get("/{tenant_id}")
async def get_tenant(tenant_id: int):
    """Get tenant details"""
    return {"message": f"Get tenant {tenant_id} endpoint"}


@router.put("/{tenant_id}")
async def update_tenant(tenant_id: int):
    """Update tenant"""
    return {"message": f"Update tenant {tenant_id} endpoint"}


@router.delete("/{tenant_id}")
async def delete_tenant(tenant_id: int):
    """Delete tenant"""
    return {"message": f"Delete tenant {tenant_id} endpoint"}
