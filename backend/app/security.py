from datetime import timedelta
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import User, now

password_hash = PasswordHash.recommended()
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
DUMMY_HASH = password_hash.hash("nonexistent-account-constant-password")


def issue_token(user):
    return jwt.encode({"sub": user.id, "rev": user.token_revision, "iss": "roadscope",
                       "aud": "roadscope-api", "iat": now(),
                       "exp": now() + timedelta(minutes=settings().access_token_minutes)},
                      settings().jwt_secret, algorithm="HS256")


def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, settings().jwt_secret, algorithms=["HS256"],
                             audience="roadscope-api", issuer="roadscope",
                             options={"require": ["exp", "iat", "sub", "rev"]})
        user = db.get(User, payload["sub"])
        if not user or not user.enabled or user.token_revision != payload["rev"]:
            raise ValueError("revoked")
        return user
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError):
        raise HTTPException(401, "Session expired or invalid", headers={"WWW-Authenticate": "Bearer"})


def require_roles(*roles):
    def check(user=Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(403, "Your role cannot perform this action")
        return user
    return check

