"""Sentry-compatible teams endpoint under /api/0/.

MegooBug doesn't have a native teams concept, so we return a single
default team to satisfy the Sentry MCP's TeamListSchema validation.

TeamSchema requires:
  - id: z.union([z.string(), z.number()])
  - slug: z.string()
  - name: z.string()
"""
from fastapi import APIRouter

from app.config import settings
from app.dependencies import CurrentUser

router = APIRouter()


@router.get("/organizations/{org}/teams/")
async def list_teams(org: str, current_user: CurrentUser):
    """List teams. Returns a single default team."""
    return [
        {
            "id": "1",
            "slug": "default",
            "name": "Default",
            "dateCreated": None,
            "isMember": True,
            "memberCount": 1,
            "avatar": {"avatarType": "letter_avatar"},
        }
    ]


@router.get("/teams/{org}/{team_slug}/")
async def get_team(org: str, team_slug: str, current_user: CurrentUser):
    """Get team detail."""
    return {
        "id": "1",
        "slug": "default",
        "name": "Default",
        "dateCreated": None,
        "isMember": True,
        "memberCount": 1,
        "avatar": {"avatarType": "letter_avatar"},
        "organization": {"id": "1", "slug": "megoobug", "name": settings.APP_NAME},
    }
