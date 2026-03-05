# app/api/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.auth import SignUpRequest, LoginRequest, TokenResponse, RefreshRequest, LogoutRequest
from app.services.auth_service import signup, login, refresh_tokens, logout

router = APIRouter()

@router.post("/signup")
def post_signup(body: SignUpRequest, db: Session = Depends(get_db)):
    try:
        user = signup(db, body.email, body.username, body.password)
        return {"id": user.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login", response_model=TokenResponse)
def post_login(body: LoginRequest, db: Session = Depends(get_db)):
    try:
        access, refresh = login(db, body.username, body.password)
        return TokenResponse(access_token=access, refresh_token=refresh)

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.post("/refresh", response_model=TokenResponse)
def post_refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    try:
        access, refresh = refresh_tokens(db, body.refresh_token)
        return TokenResponse(access_token=access, refresh_token=refresh)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.post("/logout")
def post_logout(body: LogoutRequest, db: Session = Depends(get_db)):
    logout(db, body.refresh_token)
    return {"ok": True}
