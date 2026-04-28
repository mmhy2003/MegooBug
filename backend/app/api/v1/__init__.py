from fastapi import APIRouter

from app.api.v1 import auth, users, invites, tokens, projects, issues, stats, notifications

router = APIRouter(prefix="/api/v1")

router.include_router(auth.router, prefix="/auth", tags=["Auth"])
router.include_router(users.router, prefix="/users", tags=["Users"])
router.include_router(invites.router, prefix="/invites", tags=["Invites"])
router.include_router(tokens.router, prefix="/api-tokens", tags=["API Tokens"])
router.include_router(projects.router, prefix="/projects", tags=["Projects"])
router.include_router(issues.router, tags=["Issues & Events"])
router.include_router(stats.router, tags=["Stats"])
router.include_router(notifications.router, tags=["Notifications & Settings & Search"])
