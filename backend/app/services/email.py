"""Email service for sending transactional emails.

Uses SMTP settings stored in the database (Settings table, key="smtp").
Falls back to env vars if DB settings are not configured.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.models.setting import Setting
from app.logging import get_logger

logger = get_logger("email")

# MegooBug logo as inline SVG data URI (matches CyberPunk theme)
# A stylized neon cyan bug icon with antennae, eyes, legs, and glow on dark background
LOGO_DATA_URI = (
    "data:image/svg+xml;base64,"
    "PHN2ZyB3aWR0aD0iNDgiIGhlaWdodD0iNDgiIHZpZXdCb3g9IjAgMCA0OCA0OCIg"
    "ZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4K"
    "ICA8cmVjdCB3aWR0aD0iNDgiIGhlaWdodD0iNDgiIHJ4PSIxMiIgZmlsbD0iIzBh"
    "MGEwZiIgc3Ryb2tlPSIjMmEyYTNlIiBzdHJva2Utd2lkdGg9IjEuNSIvPgogIDxn"
    "IHRyYW5zZm9ybT0idHJhbnNsYXRlKDggNikiPgogICAgPCEtLSBBbnRlbm5hZSAt"
    "LT4KICAgIDxwYXRoIGQ9Ik0xMiAxNEw4IDYiIHN0cm9rZT0iIzAwZjBmZiIgc3Ry"
    "b2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIG9wYWNpdHk9IjAu"
    "NyIvPgogICAgPHBhdGggZD0iTTIwIDE0TDI0IDYiIHN0cm9rZT0iIzAwZjBmZiIg"
    "c3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIG9wYWNpdHk9"
    "IjAuNyIvPgogICAgPGNpcmNsZSBjeD0iOCIgY3k9IjUiIHI9IjIiIGZpbGw9IiMw"
    "MGYwZmYiIG9wYWNpdHk9IjAuNSIvPgogICAgPGNpcmNsZSBjeD0iMjQiIGN5PSI1"
    "IiByPSIyIiBmaWxsPSIjMDBmMGZmIiBvcGFjaXR5PSIwLjUiLz4KICAgIDwhLS0g"
    "Qm9keSAtLT4KICAgIDxlbGxpcHNlIGN4PSIxNiIgY3k9IjIzIiByeD0iOSIgcnk9"
    "IjEyIiBmaWxsPSIjMTIxMjFhIiBzdHJva2U9IiMwMGYwZmYiIHN0cm9rZS13aWR0"
    "aD0iMS41IiBvcGFjaXR5PSIwLjkiLz4KICAgIDwhLS0gSGVhZCAtLT4KICAgIDxj"
    "aXJjbGUgY3g9IjE2IiBjeT0iMTQiIHI9IjUiIGZpbGw9IiMxYTFhMmUiIHN0cm9r"
    "ZT0iIzAwZjBmZiIgc3Ryb2tlLXdpZHRoPSIxLjUiLz4KICAgIDwhLS0gRXllcyAt"
    "LT4KICAgIDxjaXJjbGUgY3g9IjE0IiBjeT0iMTMuNSIgcj0iMS41IiBmaWxsPSIj"
    "MDBmMGZmIiBvcGFjaXR5PSIwLjkiLz4KICAgIDxjaXJjbGUgY3g9IjE4IiBjeT0i"
    "MTMuNSIgcj0iMS41IiBmaWxsPSIjMDBmMGZmIiBvcGFjaXR5PSIwLjkiLz4KICAg"
    "IDwhLS0gTGVncyBsZWZ0IC0tPgogICAgPHBhdGggZD0iTTcgMThMMyAxNSIgc3Ry"
    "b2tlPSIjMDBmMGZmIiBzdHJva2Utd2lkdGg9IjEuNSIgc3Ryb2tlLWxpbmVjYXA9"
    "InJvdW5kIiBvcGFjaXR5PSIwLjYiLz4KICAgIDxwYXRoIGQ9Ik03IDIzTDIgMjMi"
    "IHN0cm9rZT0iIzAwZjBmZiIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5l"
    "Y2FwPSJyb3VuZCIgb3BhY2l0eT0iMC42Ii8+CiAgICA8cGF0aCBkPSJNNyAyOEwz"
    "IDMxIiBzdHJva2U9IiMwMGYwZmYiIHN0cm9rZS13aWR0aD0iMS41IiBzdHJva2Ut"
    "bGluZWNhcD0icm91bmQiIG9wYWNpdHk9IjAuNiIvPgogICAgPCEtLSBMZWdzIHJp"
    "Z2h0IC0tPgogICAgPHBhdGggZD0iTTI1IDE4TDI5IDE1IiBzdHJva2U9IiMwMGYw"
    "ZmYiIHN0cm9rZS13aWR0aD0iMS41IiBzdHJva2UtbGluZWNhcD0icm91bmQiIG9w"
    "YWNpdHk9IjAuNiIvPgogICAgPHBhdGggZD0iTTI1IDIzTDMwIDIzIiBzdHJva2U9"
    "IiMwMGYwZmYiIHN0cm9rZS13aWR0aD0iMS41IiBzdHJva2UtbGluZWNhcD0icm91"
    "bmQiIG9wYWNpdHk9IjAuNiIvPgogICAgPHBhdGggZD0iTTI1IDI4TDI5IDMxIiBz"
    "dHJva2U9IiMwMGYwZmYiIHN0cm9rZS13aWR0aD0iMS41IiBzdHJva2UtbGluZWNh"
    "cD0icm91bmQiIG9wYWNpdHk9IjAuNiIvPgogICAgPCEtLSBCb2R5IHNlZ21lbnRz"
    "IC0tPgogICAgPGxpbmUgeDE9IjciIHkxPSIyMCIgeDI9IjI1IiB5Mj0iMjAiIHN0"
    "cm9rZT0iIzAwZjBmZiIgc3Ryb2tlLXdpZHRoPSIwLjgiIG9wYWNpdHk9IjAuMyIv"
    "PgogICAgPGxpbmUgeDE9IjciIHkxPSIyNSIgeDI9IjI1IiB5Mj0iMjUiIHN0cm9r"
    "ZT0iIzAwZjBmZiIgc3Ryb2tlLXdpZHRoPSIwLjgiIG9wYWNpdHk9IjAuMyIvPgog"
    "ICAgPGxpbmUgeDE9IjgiIHkxPSIzMCIgeDI9IjI0IiB5Mj0iMzAiIHN0cm9rZT0i"
    "IzAwZjBmZiIgc3Ryb2tlLXdpZHRoPSIwLjgiIG9wYWNpdHk9IjAuMyIvPgogICAg"
    "PCEtLSBHbG93IGVmZmVjdCAtLT4KICAgIDxjaXJjbGUgY3g9IjE2IiBjeT0iMjMi"
    "IHI9IjYiIGZpbGw9IiMwMGYwZmYiIG9wYWNpdHk9IjAuMDUiLz4KICA8L2c+Cjwv"
    "c3ZnPg=="
)


async def _get_smtp_config(db: AsyncSession) -> dict | None:
    """Load SMTP config from DB settings, falling back to env vars."""
    result = await db.execute(select(Setting).where(Setting.key == "smtp"))
    setting = result.scalar_one_or_none()

    if setting and setting.value.get("host"):
        return setting.value

    # Fallback to env vars
    if app_settings.SMTP_HOST:
        return {
            "host": app_settings.SMTP_HOST,
            "port": app_settings.SMTP_PORT,
            "username": app_settings.SMTP_USERNAME,
            "password": app_settings.SMTP_PASSWORD,
            "from_email": app_settings.SMTP_FROM_EMAIL or "noreply@megoobug.local",
            "use_tls": app_settings.SMTP_USE_TLS,
        }

    return None


def _send(cfg: dict, to: str, subject: str, html_body: str, text_body: str):
    """Synchronous SMTP send (called from async context via thread)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.get("from_email", "noreply@megoobug.local")
    msg["To"] = to

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    port = int(cfg.get("port", 587))
    with smtplib.SMTP(cfg["host"], port, timeout=15) as server:
        if port == 587:
            server.starttls()
        if cfg.get("username") and cfg.get("password"):
            server.login(cfg["username"], cfg["password"])
        server.sendmail(msg["From"], [to], msg.as_string())


def _build_invite_html(
    app_name: str,
    invite_link: str,
    invited_by_name: str,
    role: str,
    expire_hours: int,
) -> str:
    """Build a premium HTML invite email matching the CyberPunk design system."""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>You're invited to {app_name}</title>
    <!--[if mso]>
    <noscript><xml>
    <o:OfficeDocumentSettings>
    <o:PixelsPerInch>96</o:PixelsPerInch>
    </o:OfficeDocumentSettings>
    </xml></noscript>
    <![endif]-->
</head>
<body style="margin:0; padding:0; background-color:#0a0a0f; -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%;">
    <!-- Outer wrapper -->
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
           style="background-color:#0a0a0f; padding:32px 16px;">
        <tr>
            <td align="center">
                <!-- Main card container -->
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                       style="max-width:580px; background-color:#1a1a2e; border-radius:16px; border:1px solid #2a2a3e; box-shadow:0 8px 40px rgba(0,0,0,0.5); overflow:hidden;">

                    <!-- ═══ Header: Logo + Brand ═══ -->
                    <tr>
                        <td style="padding:32px 40px 24px; text-align:center; background:linear-gradient(180deg, rgba(0,240,255,0.06) 0%, transparent 100%); border-bottom:1px solid #2a2a3e;">
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 auto;">
                                <tr>
                                    <td style="vertical-align:middle; padding-right:12px;">
                                        <img src="{LOGO_DATA_URI}" alt="{app_name}" width="48" height="48"
                                             style="display:block; border:0; outline:none;">
                                    </td>
                                    <td style="vertical-align:middle;">
                                        <span style="font-family:'Outfit','Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; font-size:26px; font-weight:700; color:#00f0ff; letter-spacing:0.5px; text-shadow:0 0 20px rgba(0,240,255,0.3);">
                                            {app_name}
                                        </span>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin:12px 0 0; font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif; font-size:13px; color:#555570; letter-spacing:1.5px; text-transform:uppercase;">
                                Team Invitation
                            </p>
                        </td>
                    </tr>

                    <!-- ═══ Body ═══ -->
                    <tr>
                        <td style="padding:36px 40px 32px;">
                            <!-- Greeting -->
                            <p style="margin:0 0 20px; font-family:'Outfit','Inter',-apple-system,BlinkMacSystemFont,sans-serif; font-size:18px; font-weight:600; color:#e0e0ff; line-height:1.5;">
                                You've been invited! 🎉
                            </p>

                            <!-- Invitation details card -->
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                                   style="background:#12121a; border:1px solid #2a2a3e; border-radius:10px; margin-bottom:28px;">
                                <tr>
                                    <td style="padding:20px 24px;">
                                        <p style="margin:0 0 12px; font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif; font-size:15px; color:#8888aa; line-height:1.7;">
                                            <strong style="color:#e0e0ff;">{invited_by_name}</strong> has invited you to join
                                            <strong style="color:#00f0ff;">{app_name}</strong>
                                        </p>
                                        <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                                            <tr>
                                                <td style="padding-right:8px;">
                                                    <span style="font-family:'Inter',sans-serif; font-size:12px; color:#555570; text-transform:uppercase; letter-spacing:0.5px;">Your Role:</span>
                                                </td>
                                                <td>
                                                    <span style="display:inline-block; font-family:'JetBrains Mono','Fira Code',monospace; background:rgba(0,240,255,0.1); color:#00f0ff; padding:3px 12px; border-radius:6px; font-size:13px; font-weight:600; border:1px solid rgba(0,240,255,0.2); text-transform:capitalize;">
                                                        {role}
                                                    </span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            <!-- CTA Button -->
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td align="center" style="padding:4px 0 28px;">
                                        <!--[if mso]>
                                        <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word"
                                                     href="{invite_link}" style="height:52px;v-text-anchor:middle;width:280px;"
                                                     arcsize="15%" strokecolor="#0088cc" fillcolor="#00d4ff">
                                        <w:anchorlock/>
                                        <center style="color:#0a0a0f;font-family:sans-serif;font-size:15px;font-weight:bold;">
                                            Accept Invite &amp; Join
                                        </center>
                                        </v:roundrect>
                                        <![endif]-->
                                        <!--[if !mso]><!-->
                                        <a href="{invite_link}"
                                           style="display:inline-block; padding:15px 40px; background:linear-gradient(135deg, #00f0ff 0%, #0088cc 100%); color:#0a0a0f; font-family:'Outfit','Inter',-apple-system,BlinkMacSystemFont,sans-serif; font-size:15px; font-weight:700; text-decoration:none; border-radius:10px; letter-spacing:0.3px; box-shadow:0 4px 20px rgba(0,240,255,0.35); transition:all 0.2s;">
                                            Accept Invite &amp; Join
                                        </a>
                                        <!--<![endif]-->
                                    </td>
                                </tr>
                            </table>

                            <!-- Fallback link -->
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                                   style="background:#0a0a0f; border:1px solid #2a2a3e; border-radius:8px; margin-bottom:24px;">
                                <tr>
                                    <td style="padding:14px 18px;">
                                        <p style="margin:0 0 6px; font-family:'Inter',sans-serif; font-size:11px; color:#555570; text-transform:uppercase; letter-spacing:0.8px;">
                                            Or copy this link:
                                        </p>
                                        <p style="margin:0; font-family:'JetBrains Mono','Fira Code',monospace; font-size:12px; color:#00f0ff; word-break:break-all; line-height:1.6;">
                                            {invite_link}
                                        </p>
                                    </td>
                                </tr>
                            </table>

                            <!-- Expiry notice -->
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                                   style="background:rgba(255,204,0,0.06); border:1px solid rgba(255,204,0,0.12); border-radius:8px;">
                                <tr>
                                    <td style="padding:12px 18px;">
                                        <p style="margin:0; font-family:'Inter',sans-serif; font-size:13px; color:#8888aa; line-height:1.5;">
                                            ⏳ This invitation expires in <strong style="color:#ffcc00;">{expire_hours} hours</strong>.
                                            After that, the admin will need to send a new invite.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- ═══ Divider ═══ -->
                    <tr>
                        <td style="padding:0 40px;">
                            <div style="height:1px; background:linear-gradient(90deg, transparent, #2a2a3e, rgba(0,240,255,0.15), #2a2a3e, transparent);"></div>
                        </td>
                    </tr>

                    <!-- ═══ Footer ═══ -->
                    <tr>
                        <td style="padding:24px 40px 32px; text-align:center;">
                            <p style="margin:0 0 8px; font-family:'Inter',sans-serif; font-size:12px; color:#555570; line-height:1.6;">
                                If you didn't expect this invite, you can safely ignore this email.
                            </p>
                            <p style="margin:0; font-family:'Inter',sans-serif; font-size:11px; color:#3a3a50;">
                                Sent by <span style="color:#555570;">{app_name}</span> · Self-hosted error tracking
                            </p>
                        </td>
                    </tr>

                </table>

                <!-- Sub-footer branding -->
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:580px;">
                    <tr>
                        <td style="padding:20px 40px; text-align:center;">
                            <p style="margin:0; font-family:'JetBrains Mono',monospace; font-size:10px; color:#3a3a50; letter-spacing:1px;">
                                POWERED BY {app_name.upper()}
                            </p>
                        </td>
                    </tr>
                </table>

            </td>
        </tr>
    </table>
</body>
</html>"""


async def send_invite_email(
    db: AsyncSession,
    to_email: str,
    invite_token: str,
    role: str,
    invited_by_name: str,
):
    """Send an invite email with a registration link."""
    cfg = await _get_smtp_config(db)
    if cfg is None:
        logger.warning("Cannot send invite email to %s — SMTP not configured", to_email)
        return False

    app_url = app_settings.APP_URL.rstrip("/")
    invite_link = f"{app_url}/register?token={invite_token}"
    app_name = app_settings.APP_NAME
    expire_hours = app_settings.INVITE_TOKEN_EXPIRE_HOURS

    subject = f"You've been invited to {app_name}"

    text_body = (
        f"Hi,\n\n"
        f"{invited_by_name} has invited you to join {app_name} as a {role}.\n\n"
        f"Click the link below to create your account:\n"
        f"{invite_link}\n\n"
        f"This link expires in {expire_hours} hours.\n\n"
        f"If you didn't expect this invite, you can safely ignore this email.\n\n"
        f"— {app_name}"
    )

    html_body = _build_invite_html(
        app_name=app_name,
        invite_link=invite_link,
        invited_by_name=invited_by_name,
        role=role,
        expire_hours=expire_hours,
    )

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send, cfg, to_email, subject, html_body, text_body)
        logger.info("Invite email sent to %s", to_email)
        return True
    except Exception as e:
        logger.error("Failed to send invite email to %s: %s", to_email, e)
        return False


# ── Issue Notification Email ──


_LEVEL_COLORS = {
    "fatal": ("#ff3366", "rgba(255,51,102,0.1)", "rgba(255,51,102,0.25)"),
    "error": ("#ff3366", "rgba(255,51,102,0.1)", "rgba(255,51,102,0.25)"),
    "warning": ("#ffcc00", "rgba(255,204,0,0.1)", "rgba(255,204,0,0.25)"),
    "info": ("#00f0ff", "rgba(0,240,255,0.1)", "rgba(0,240,255,0.25)"),
}


def _build_issue_notification_html(
    app_name: str,
    project_name: str,
    issue_title: str,
    issue_level: str,
    issue_link: str,
    is_regression: bool,
    event_count: int,
    environment: str,
) -> str:
    """Build a premium HTML issue notification email matching the CyberPunk design system."""
    color, bg, border = _LEVEL_COLORS.get(issue_level, _LEVEL_COLORS["error"])
    type_label = "Regression" if is_regression else "New Issue"
    type_emoji = "🔄" if is_regression else "🚨"
    # Truncate title for email display
    display_title = issue_title[:200] + ("…" if len(issue_title) > 200 else "")
    env_row = ""
    if environment:
        env_row = f"""
                                        <tr>
                                            <td style="padding:6px 0; font-family:'Inter',sans-serif; font-size:13px; color:#555570; width:110px;">Environment</td>
                                            <td style="padding:6px 0; font-family:'JetBrains Mono',monospace; font-size:13px; color:#e0e0ff;">{environment}</td>
                                        </tr>"""

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>{type_label} in {project_name}</title>
    <!--[if mso]>
    <noscript><xml>
    <o:OfficeDocumentSettings>
    <o:PixelsPerInch>96</o:PixelsPerInch>
    </o:OfficeDocumentSettings>
    </xml></noscript>
    <![endif]-->
</head>
<body style="margin:0; padding:0; background-color:#0a0a0f; -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
           style="background-color:#0a0a0f; padding:32px 16px;">
        <tr>
            <td align="center">
                <!-- Main card -->
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                       style="max-width:580px; background-color:#1a1a2e; border-radius:16px; border:1px solid #2a2a3e; box-shadow:0 8px 40px rgba(0,0,0,0.5); overflow:hidden;">

                    <!-- ═══ Header ═══ -->
                    <tr>
                        <td style="padding:32px 40px 24px; text-align:center; background:linear-gradient(180deg, {bg} 0%, transparent 100%); border-bottom:1px solid #2a2a3e;">
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 auto;">
                                <tr>
                                    <td style="vertical-align:middle; padding-right:12px;">
                                        <img src="{LOGO_DATA_URI}" alt="{app_name}" width="48" height="48"
                                             style="display:block; border:0; outline:none;">
                                    </td>
                                    <td style="vertical-align:middle;">
                                        <span style="font-family:'Outfit','Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; font-size:26px; font-weight:700; color:#00f0ff; letter-spacing:0.5px; text-shadow:0 0 20px rgba(0,240,255,0.3);">
                                            {app_name}
                                        </span>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin:12px 0 0; font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif; font-size:13px; color:#555570; letter-spacing:1.5px; text-transform:uppercase;">
                                {type_emoji} {type_label} Detected
                            </p>
                        </td>
                    </tr>

                    <!-- ═══ Body ═══ -->
                    <tr>
                        <td style="padding:36px 40px 32px;">
                            <!-- Project badge -->
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:20px;">
                                <tr>
                                    <td>
                                        <span style="display:inline-block; font-family:'Inter',sans-serif; background:rgba(0,240,255,0.08); color:#00f0ff; padding:4px 14px; border-radius:6px; font-size:12px; font-weight:600; border:1px solid rgba(0,240,255,0.15); letter-spacing:0.3px;">
                                            {project_name}
                                        </span>
                                    </td>
                                </tr>
                            </table>

                            <!-- Issue title card -->
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                                   style="background:#12121a; border:1px solid {border}; border-left:4px solid {color}; border-radius:10px; margin-bottom:24px;">
                                <tr>
                                    <td style="padding:20px 24px;">
                                        <!-- Level badge -->
                                        <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:12px;">
                                            <tr>
                                                <td>
                                                    <span style="display:inline-block; font-family:'JetBrains Mono',monospace; background:{bg}; color:{color}; padding:3px 12px; border-radius:6px; font-size:11px; font-weight:700; border:1px solid {border}; text-transform:uppercase; letter-spacing:1px;">
                                                        {issue_level}
                                                    </span>
                                                </td>
                                            </tr>
                                        </table>
                                        <!-- Title -->
                                        <p style="margin:0; font-family:'JetBrains Mono','Fira Code',monospace; font-size:14px; color:#e0e0ff; line-height:1.6; word-break:break-word;">
                                            {display_title}
                                        </p>
                                    </td>
                                </tr>
                            </table>

                            <!-- Details table -->
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                                   style="background:#12121a; border:1px solid #2a2a3e; border-radius:10px; margin-bottom:28px;">
                                <tr>
                                    <td style="padding:16px 24px;">
                                        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                                            <tr>
                                                <td style="padding:6px 0; font-family:'Inter',sans-serif; font-size:13px; color:#555570; width:110px;">Project</td>
                                                <td style="padding:6px 0; font-family:'Inter',sans-serif; font-size:13px; color:#e0e0ff; font-weight:600;">{project_name}</td>
                                            </tr>
                                            <tr>
                                                <td style="padding:6px 0; font-family:'Inter',sans-serif; font-size:13px; color:#555570;">Events</td>
                                                <td style="padding:6px 0; font-family:'JetBrains Mono',monospace; font-size:13px; color:#e0e0ff;">{event_count}</td>
                                            </tr>{env_row}
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            <!-- CTA Button -->
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td align="center" style="padding:4px 0 16px;">
                                        <!--[if mso]>
                                        <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word"
                                                     href="{issue_link}" style="height:52px;v-text-anchor:middle;width:280px;"
                                                     arcsize="15%" strokecolor="#0088cc" fillcolor="#00d4ff">
                                        <w:anchorlock/>
                                        <center style="color:#0a0a0f;font-family:sans-serif;font-size:15px;font-weight:bold;">
                                            View Issue Details
                                        </center>
                                        </v:roundrect>
                                        <![endif]-->
                                        <!--[if !mso]><!-->
                                        <a href="{issue_link}"
                                           style="display:inline-block; padding:15px 40px; background:linear-gradient(135deg, #00f0ff 0%, #0088cc 100%); color:#0a0a0f; font-family:'Outfit','Inter',-apple-system,BlinkMacSystemFont,sans-serif; font-size:15px; font-weight:700; text-decoration:none; border-radius:10px; letter-spacing:0.3px; box-shadow:0 4px 20px rgba(0,240,255,0.35);">
                                            View Issue Details →
                                        </a>
                                        <!--<![endif]-->
                                    </td>
                                </tr>
                            </table>

                            <!-- Fallback link -->
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                                   style="background:#0a0a0f; border:1px solid #2a2a3e; border-radius:8px;">
                                <tr>
                                    <td style="padding:14px 18px;">
                                        <p style="margin:0 0 6px; font-family:'Inter',sans-serif; font-size:11px; color:#555570; text-transform:uppercase; letter-spacing:0.8px;">
                                            Or open in browser:
                                        </p>
                                        <p style="margin:0; font-family:'JetBrains Mono','Fira Code',monospace; font-size:12px; color:#00f0ff; word-break:break-all; line-height:1.6;">
                                            {issue_link}
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- ═══ Divider ═══ -->
                    <tr>
                        <td style="padding:0 40px;">
                            <div style="height:1px; background:linear-gradient(90deg, transparent, #2a2a3e, rgba(0,240,255,0.15), #2a2a3e, transparent);"></div>
                        </td>
                    </tr>

                    <!-- ═══ Footer ═══ -->
                    <tr>
                        <td style="padding:24px 40px 32px; text-align:center;">
                            <p style="margin:0 0 8px; font-family:'Inter',sans-serif; font-size:12px; color:#555570; line-height:1.6;">
                                You're receiving this because you're a member of <strong style="color:#8888aa;">{project_name}</strong>.
                            </p>
                            <p style="margin:0; font-family:'Inter',sans-serif; font-size:11px; color:#3a3a50;">
                                Sent by <span style="color:#555570;">{app_name}</span> · Self-hosted error tracking
                            </p>
                        </td>
                    </tr>

                </table>

                <!-- Sub-footer -->
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:580px;">
                    <tr>
                        <td style="padding:20px 40px; text-align:center;">
                            <p style="margin:0; font-family:'JetBrains Mono',monospace; font-size:10px; color:#3a3a50; letter-spacing:1px;">
                                POWERED BY {app_name.upper()}
                            </p>
                        </td>
                    </tr>
                </table>

            </td>
        </tr>
    </table>
</body>
</html>"""


async def send_issue_notification_email(
    db: AsyncSession,
    to_email: str,
    project_name: str,
    project_slug: str,
    issue_id: str,
    issue_title: str,
    issue_level: str,
    is_regression: bool = False,
    event_count: int = 1,
    environment: str = "",
):
    """Send an issue notification email to a project member."""
    cfg = await _get_smtp_config(db)
    if cfg is None:
        logger.debug("Cannot send issue email — SMTP not configured")
        return False

    app_url = app_settings.APP_URL.rstrip("/")
    app_name = app_settings.APP_NAME
    issue_link = f"{app_url}/projects/{project_slug}/issues/{issue_id}"
    type_label = "Regression" if is_regression else "New Issue"

    subject = f"[{project_name}] {type_label}: {issue_title[:100]}"

    text_body = (
        f"{type_label} in {project_name}\n\n"
        f"Level: {issue_level.upper()}\n"
        f"Title: {issue_title}\n"
        f"Events: {event_count}\n"
        + (f"Environment: {environment}\n" if environment else "")
        + f"\nView issue: {issue_link}\n\n"
        f"— {app_name}"
    )

    html_body = _build_issue_notification_html(
        app_name=app_name,
        project_name=project_name,
        issue_title=issue_title,
        issue_level=issue_level,
        issue_link=issue_link,
        is_regression=is_regression,
        event_count=event_count,
        environment=environment,
    )

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send, cfg, to_email, subject, html_body, text_body)
        logger.info("Issue notification email sent to %s (issue=%s)", to_email, issue_id[:8])
        return True
    except Exception as e:
        logger.error("Failed to send issue notification email to %s: %s", to_email, e)
        return False

