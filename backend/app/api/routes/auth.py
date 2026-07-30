from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import TokenResponse, UserChangePassword, UserCreate, UserDevResetPassword, UserLogin, UserRead
from app.services.grafana_provisioner import GrafanaProvisioningError, GrafanaProvisioner

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key="platform_access_token",
        value=token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


@router.post("/register", response_model=UserRead)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    existing = db.query(User).filter(or_(User.username == payload.username, User.email == payload.email)).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username or email already exists")

    user = User(
        username=payload.username,
        email=str(payload.email),
        hashed_password=get_password_hash(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    settings = get_settings()
    token = create_access_token(str(user.id), timedelta(minutes=settings.access_token_expire_minutes))
    _set_session_cookie(response, token)
    return TokenResponse(access_token=token)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie("platform_access_token", path="/")
    return {"message": "已退出登录"}


@router.post("/session")
async def refresh_session(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    grafana_ready = True
    if settings.grafana_provisioning_enabled:
        try:
            await GrafanaProvisioner().ensure_user_context(db, current_user)
        except GrafanaProvisioningError:
            db.rollback()
            grafana_ready = False

    token = create_access_token(
        str(current_user.id),
        timedelta(minutes=settings.access_token_expire_minutes),
    )
    _set_session_cookie(response, token)
    return {"ok": True, "grafana_ready": grafana_ready}


@router.get("/grafana-auth")
def grafana_auth(request: Request, db: Session = Depends(get_db)) -> Response:
    token = request.cookies.get("platform_access_token", "")
    if not token:
        token = request.headers.get("Authorization", "")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="平台登录已失效")
    authorization = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    user = get_current_user(authorization=authorization, db=db)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    settings = get_settings()
    response.headers[settings.grafana_auth_proxy_header] = GrafanaProvisioner.grafana_login(user)
    response.headers["X-WEBAUTH-EMAIL"] = user.email
    return response


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/change-password", response_model=UserRead)
def change_password(
    payload: UserChangePassword,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Old password is incorrect")
    current_user.hashed_password = get_password_hash(payload.new_password)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/dev-reset-password", response_model=UserRead)
def dev_reset_password(payload: UserDevResetPassword, db: Session = Depends(get_db)) -> User:
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.hashed_password = get_password_hash(payload.new_password)
    db.commit()
    db.refresh(user)
    return user
