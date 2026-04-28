"""Notification and settings API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, require_admin
from app.models.notification import Notification
from app.models.setting import Setting
from app.models.user import User
from app.logging import get_logger

logger = get_logger("api.notifications")

router = APIRouter()


# ── Notifications ──


@router.get("/notifications")
async def list_notifications(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    unread_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List notifications for the current user."""
    query = select(Notification).where(Notification.user_id == current_user.id)
    count_query = select(func.count(Notification.id)).where(
        Notification.user_id == current_user.id
    )

    if unread_only:
        query = query.where(Notification.is_read == False)
        count_query = count_query.where(Notification.is_read == False)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Unread count (always returned)
    unread_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    unread_count = unread_result.scalar()

    query = query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": str(n.id),
                "type": n.type.value,
                "title": n.title,
                "body": n.body,
                "is_read": n.is_read,
                "issue_id": str(n.issue_id) if n.issue_id else None,
                "project_id": str(n.project_id) if n.project_id else None,
                "created_at": n.created_at.isoformat(),
            }
            for n in items
        ],
        "total": total,
        "unread_count": unread_count,
    }


@router.get("/notifications/unread-count")
async def get_unread_count(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get unread notification count (for badge polling)."""
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    return {"count": result.scalar() or 0}


@router.patch("/notifications/{notification_id}/read")
async def mark_as_read(
    notification_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    await db.flush()
    return {"ok": True}


@router.post("/notifications/read-all")
async def mark_all_read(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Mark all notifications as read."""
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
        .values(is_read=True)
    )
    return {"ok": True}


# ── Settings ──


@router.get("/settings/{key}")
async def get_setting(
    key: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get a setting by key."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting is None:
        return {"key": key, "value": {}}
    return {"key": setting.key, "value": setting.value}


@router.put("/settings/{key}")
async def upsert_setting(
    key: str,
    body: dict,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create or update a setting."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if setting is None:
        setting = Setting(key=key, value=body.get("value", {}))
        db.add(setting)
    else:
        setting.value = body.get("value", {})

    await db.flush()
    return {"key": setting.key, "value": setting.value}


@router.get("/settings")
async def list_settings(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all settings."""
    result = await db.execute(select(Setting).order_by(Setting.key))
    settings_list = result.scalars().all()
    return {
        "settings": [
            {"key": s.key, "value": s.value, "updated_at": s.updated_at.isoformat()}
            for s in settings_list
        ]
    }


@router.post("/settings/smtp/test")
async def test_smtp(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    body: dict | None = None,
):
    """Send a test email using the saved SMTP settings.

    Optionally accepts {"recipient": "user@example.com"} in the request body.
    Falls back to the logged-in user's email if not provided.
    """
    import smtplib
    from email.mime.text import MIMEText

    # Determine recipient
    recipient = current_user.email
    if body and body.get("recipient"):
        recipient = body["recipient"].strip()

    # Load SMTP settings
    result = await db.execute(select(Setting).where(Setting.key == "smtp"))
    setting = result.scalar_one_or_none()

    if setting is None or not setting.value.get("host"):
        return {"ok": False, "error": "SMTP not configured. Save SMTP settings first."}

    cfg = setting.value
    try:
        msg = MIMEText(
            "This is a test email from MegooBug.\n\n"
            "If you received this, your SMTP settings are configured correctly.",
            "plain",
        )
        msg["Subject"] = "MegooBug — SMTP Test"
        msg["From"] = cfg.get("from_email", "noreply@megoobug.local")
        msg["To"] = recipient

        port = int(cfg.get("port", 587))
        with smtplib.SMTP(cfg["host"], port, timeout=10) as server:
            if port == 587:
                server.starttls()
            if cfg.get("username") and cfg.get("password"):
                server.login(cfg["username"], cfg["password"])
            server.sendmail(msg["From"], [recipient], msg.as_string())

        logger.info("Test email sent to %s", recipient)
        return {"ok": True, "message": f"Test email sent to {recipient}"}

    except Exception as e:
        logger.error("SMTP test failed: %s", e)
        return {"ok": False, "error": str(e)}


# ── Search ──


@router.get("/search")
async def global_search(
    q: str = Query("", min_length=1, max_length=200),
    current_user: CurrentUser = None,
):
    """Global search powered by Meilisearch."""
    if not q.strip():
        return {"results": [], "query": q}

    try:
        import meilisearch
        from app.config import settings as app_settings

        client = meilisearch.Client(
            app_settings.MEILISEARCH_URL,
            app_settings.MEILISEARCH_MASTER_KEY,
        )

        results = client.multi_search(
            [
                {
                    "indexUid": "issues",
                    "q": q,
                    "limit": 5,
                    "attributesToRetrieve": [
                        "id", "title", "status", "level", "project_id",
                    ],
                },
                {
                    "indexUid": "projects",
                    "q": q,
                    "limit": 5,
                    "attributesToRetrieve": ["id", "name", "slug", "platform"],
                },
            ]
        )

        formatted = []
        for r in results.get("results", []):
            index = r.get("indexUid", "")
            for hit in r.get("hits", []):
                formatted.append({
                    "type": index,
                    **hit,
                })

        return {"results": formatted, "query": q}

    except Exception as e:
        logger.warning("Search failed: %s", e)
        return {"results": [], "query": q, "error": "Search unavailable"}
