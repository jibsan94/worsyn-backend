"""Worsyn SMTP service — single shared SMTP server configured by the platform admin.

Configuration lives in `system_settings` under `email.smtp.*` keys (see
`app/api/v1/endpoints/admin_settings_email.py`). The password is encrypted via
`app.core.crypto.encrypt` and decrypted here.

Send strategy (v1):
  • One SMTP connection per send. No pooling. Fine until ~thousands/day.
  • Called from a FastAPI BackgroundTask after POST /tenant/{slug}/email/messages
    creates queued rows.
  • Each row's status flips to 'sent' (with sent_at) or 'failed' (with error).

From / Reply-To convention:
  • `From: "<from_name>" <from_email>` — always the configured SMTP identity.
    This is the only way Gmail/Workspace will accept the message without SPF/DKIM
    per-tenant. The tenant org NAME may be prefixed, e.g. `"Iglesia X via Worsyn"`.
  • `Reply-To: <sender_member.email>` — replies go back to the actual sender.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt
from app.db.session import AsyncSessionLocal as async_session
from app.models.models import EmailMessage as EmailRow, Organization, OrgMember, SystemSetting

log = logging.getLogger(__name__)

# All settings keys this module touches
CFG_KEYS = [
    "email.smtp.enabled",
    "email.smtp.host",
    "email.smtp.port",
    "email.smtp.username",
    "email.smtp.password",     # encrypted
    "email.smtp.use_tls",      # STARTTLS (port 587)
    "email.smtp.use_ssl",      # implicit TLS (port 465)
    "email.smtp.from_email",
    "email.smtp.from_name",
    "email.smtp.provider",     # gmail | workspace | sendgrid | mailgun | custom — informational
    "email.smtp.reply_to",     # optional override; if blank, uses sender member email
    "email.smtp.timeout",      # seconds, default 20
]


class SmtpConfig:
    def __init__(self, raw: dict[str, str | None]):
        self.enabled  = (raw.get("email.smtp.enabled") or "false").lower() == "true"
        self.host     = raw.get("email.smtp.host") or ""
        self.port     = int(raw.get("email.smtp.port") or 587)
        self.username = raw.get("email.smtp.username") or ""
        self.password_enc = raw.get("email.smtp.password") or ""
        self.use_tls  = (raw.get("email.smtp.use_tls") or "true").lower() == "true"
        self.use_ssl  = (raw.get("email.smtp.use_ssl") or "false").lower() == "true"
        self.from_email = raw.get("email.smtp.from_email") or self.username
        self.from_name  = raw.get("email.smtp.from_name") or "Worsyn"
        self.provider   = raw.get("email.smtp.provider") or "custom"
        self.reply_to_override = raw.get("email.smtp.reply_to") or ""
        self.timeout    = int(raw.get("email.smtp.timeout") or 20)

    def is_configured(self) -> bool:
        return bool(self.enabled and self.host and self.username and self.password_enc and self.from_email)

    @property
    def password(self) -> str:
        return decrypt(self.password_enc) if self.password_enc else ""


async def load_config(db: AsyncSession) -> SmtpConfig:
    rows = (await db.execute(
        select(SystemSetting).where(SystemSetting.key.in_(CFG_KEYS))
    )).scalars().all()
    return SmtpConfig({r.key: r.value for r in rows})


def _open_smtp(cfg: SmtpConfig) -> smtplib.SMTP | smtplib.SMTP_SSL:
    if cfg.use_ssl:
        ctx = ssl.create_default_context()
        s = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=cfg.timeout, context=ctx)
    else:
        s = smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout)
        s.ehlo()
        if cfg.use_tls:
            s.starttls(context=ssl.create_default_context())
            s.ehlo()
    s.login(cfg.username, cfg.password)
    return s


_HTML_SHELL = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#F1F5F9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0F172A;line-height:1.55">
  <div style="max-width:620px;margin:0 auto;padding:24px 16px">
    <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:28px 28px 24px;box-shadow:0 1px 3px rgba(0,0,0,.04)">
      {body}
    </div>
    <div style="text-align:center;color:#94A3B8;font-size:11px;margin-top:14px">
      Enviado desde {org} con <a href="https://worsyn.com" style="color:#4F46E5;text-decoration:none">Worsyn Services</a>
    </div>
  </div>
</body>
</html>"""


def _wrap_html(body: str, subject: str, org_name: str | None) -> str:
    """Wrap the user-authored body fragment in a responsive email shell.

    The body comes from the rich-text editor as inline HTML (no doctype/body).
    We escape only the title (the body is trusted — only admin/leader/coordinator
    can compose, and the variable engine doesn't allow code execution).
    """
    safe_subject = (subject or "").replace("<", "&lt;").replace(">", "&gt;")
    safe_org = (org_name or "tu organización").replace("<", "&lt;").replace(">", "&gt;")
    return _HTML_SHELL.format(subject=safe_subject, body=body or "", org=safe_org)


def _build_message(cfg: SmtpConfig, *, to_email: str, subject: str, html: str,
                   reply_to: str | None, org_name: str | None) -> EmailMessage:
    msg = EmailMessage()
    display_from = cfg.from_name if not org_name else f"{org_name} vía {cfg.from_name}"
    msg["From"] = formataddr((display_from, cfg.from_email))
    msg["To"] = to_email
    msg["Subject"] = subject or "(sin asunto)"
    rt = cfg.reply_to_override or reply_to
    if rt:
        msg["Reply-To"] = rt
    # Wrap user HTML in a responsive email shell
    full_html = _wrap_html(html or "", subject or "", org_name)
    # Plain-text fallback (very simple — strip HTML tags) + real HTML body
    import re
    plain = re.sub(r"<[^>]+>", "", html or "").strip() or "(sin contenido)"
    msg.set_content(plain)
    msg.add_alternative(full_html, subtype="html")
    return msg


# ── Public single send (used by /admin/settings/email/test) ──────────────────
def send_one(cfg: SmtpConfig, *, to_email: str, subject: str, html: str,
             reply_to: str | None = None, org_name: str | None = None) -> tuple[bool, str | None]:
    """Synchronous single-message send. Returns (ok, error_msg)."""
    if not cfg.is_configured():
        return False, "SMTP no configurado o deshabilitado"
    try:
        msg = _build_message(cfg, to_email=to_email, subject=subject, html=html,
                             reply_to=reply_to, org_name=org_name)
        with _open_smtp(cfg) as s:
            s.send_message(msg)
        return True, None
    except Exception as e:  # noqa: BLE001 — surface any SMTP error to UI
        log.exception("SMTP send failed")
        return False, f"{type(e).__name__}: {e}"


# ── Background dispatch for queued rows ──────────────────────────────────────
async def dispatch_queued(message_ids: list[uuid.UUID]) -> None:
    """Called as a BackgroundTask. Opens its OWN DB session because the request
    session is closed by the time this runs.
    """
    if not message_ids:
        return
    async with async_session() as db:
        cfg = await load_config(db)
        rows = (await db.execute(
            select(EmailRow, Organization)
            .join(Organization, Organization.id == EmailRow.org_id)
            .where(EmailRow.id.in_(message_ids), EmailRow.status == "queued")
        )).all()
        if not cfg.is_configured():
            # Mark all as failed with a clear reason
            for row, _org in rows:
                row.status = "failed"
                row.error = "SMTP no configurado en el panel admin (Configuración → Correo SMTP)"
            await db.commit()
            return

        try:
            with _open_smtp(cfg) as smtp:
                for row, org in rows:
                    reply_to = None
                    if row.sender_member_id is not None:
                        sender = (await db.execute(
                            select(OrgMember).where(OrgMember.id == row.sender_member_id)
                        )).scalar_one_or_none()
                        if sender is not None:
                            reply_to = sender.email
                    try:
                        msg = _build_message(
                            cfg,
                            to_email=row.recipient_email,
                            subject=row.subject,
                            html=row.body_rendered,
                            reply_to=reply_to,
                            org_name=org.name,
                        )
                        smtp.send_message(msg)
                        row.status = "sent"
                        row.sent_at = datetime.now(timezone.utc)
                        row.error = None
                        # Mirror into recipient's "Recibidos" inbox if they are
                        # an org member of THIS org (so they see the same email
                        # both in their Gmail/iCloud AND in Worsyn Servicios).
                        if row.recipient_member_id is not None:
                            mirror = EmailRow(
                                org_id=row.org_id,
                                template_id=row.template_id,
                                sender_member_id=row.sender_member_id,
                                recipient_member_id=row.recipient_member_id,
                                recipient_email=row.recipient_email,
                                sender_email=row.sender_email,
                                direction="received",
                                status="received",
                                subject=row.subject,
                                body_rendered=row.body_rendered,
                                body_template=row.body_template,
                                sent_at=row.sent_at,
                            )
                            db.add(mirror)
                    except Exception as e:  # noqa: BLE001
                        log.exception("SMTP per-row send failed: %s", row.id)
                        row.status = "failed"
                        row.error = f"{type(e).__name__}: {e}"
        except Exception as e:  # noqa: BLE001
            log.exception("SMTP connection failed")
            for row, _org in rows:
                row.status = "failed"
                row.error = f"Conexión SMTP: {type(e).__name__}: {e}"
        await db.commit()
