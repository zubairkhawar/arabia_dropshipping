from sqlalchemy.orm import Session

from config import settings
from database import Base, engine, SessionLocal
from models import Tenant, User
from services.auth_service.services import get_password_hash


ADMIN_EMAIL = "arabiadropshipping05@gmail.com"
ADMIN_PASSWORD = "arabia@123"
ADMIN_FULL_NAME = "Arabia Admin"


def main() -> None:
  Base.metadata.create_all(bind=engine)

  db: Session = SessionLocal()
  try:
    tenant = db.query(Tenant).filter(Tenant.id == 1).first()
    if tenant is None:
      tenant = Tenant(id=1, name="Default Tenant", domain=None, is_active=True)
      db.add(tenant)
      db.commit()
      db.refresh(tenant)

    existing = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if existing:
      return

    user = User(
      tenant_id=tenant.id,
      email=ADMIN_EMAIL,
      full_name=ADMIN_FULL_NAME,
      role="admin",
      hashed_password=get_password_hash(ADMIN_PASSWORD),
      is_active=True,
    )
    db.add(user)
    db.commit()
  finally:
    db.close()


if __name__ == "__main__":
  main()

