from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User

authorization_header = APIKeyHeader(name="Authorization", auto_error=True)


def get_current_user(
    authorization: str = Depends(authorization_header),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()
    token = authorization.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        subject = payload.get("sub")
        if subject is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user = db.get(User, int(subject))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user

def require_root_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "root":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Root privileges required")
    return current_user
