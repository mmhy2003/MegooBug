from fastapi import APIRouter

from app.api.v1 import auth, users, invites

router = APIRouter(prefix="/api/v1")

router.include_router(auth.router, prefix="/auth", tags=["Auth"])
router.include_router(users.router, prefix="/users", tags=["Users"])
router.include_router(invites.router, prefix="/invites", tags=["Invites"])
