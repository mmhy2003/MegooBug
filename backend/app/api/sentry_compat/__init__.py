from fastapi import APIRouter

from app.api.sentry_compat import organizations, projects, issues

router = APIRouter(prefix="/api/0")

router.include_router(organizations.router, tags=["Sentry Compat - Orgs"])
router.include_router(projects.router, tags=["Sentry Compat - Projects"])
router.include_router(issues.router, tags=["Sentry Compat - Issues"])
