import os
from functools import lru_cache

import firebase_admin
from dotenv import load_dotenv
from fastapi import Header, HTTPException
from firebase_admin import auth, credentials
from pydantic import BaseModel


load_dotenv()

AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")


class CurrentUser(BaseModel):
    user_id: str
    email: str | None = None
    name: str | None = None


@lru_cache(maxsize=1)
def initialize_firebase_app() -> None:
    if firebase_admin._apps:
        return

    options = {"projectId": FIREBASE_PROJECT_ID} if FIREBASE_PROJECT_ID else None
    firebase_admin.initialize_app(credentials.ApplicationDefault(), options=options)


async def get_current_user(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> CurrentUser:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            initialize_firebase_app()
            decoded_token = auth.verify_id_token(token)
            return CurrentUser(
                user_id=decoded_token["uid"],
                email=decoded_token.get("email"),
                name=decoded_token.get("name"),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid Firebase ID token: {exc}",
            ) from exc

    if AUTH_REQUIRED:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    return CurrentUser(user_id=x_user_id or "local-dev-user")
