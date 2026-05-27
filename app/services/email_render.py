"""Worsyn email variable engine.

Supports a tiny Liquid-like subset (NO arbitrary code execution):

  Output:        {{ var }}
                 {{ var.subkey }}
                 {{ var.deeper.nested }}

  Conditional:   {% if var %}…{% endif %}
                 {% if var %}…{% else %}…{% endif %}

Missing variables render as empty strings. Truthiness mirrors Python's
(None / "" / 0 / False / empty list-dict → false).

The full variable catalog is documented in `artifacts/EMAIL-VARIABLES.md`.
This module ONLY exposes:
    render(template_text: str, ctx: dict) -> str
    build_context(*, sender, recipient, organization, service=None) -> dict

`render` is intentionally non-evaluating: no function calls, no filters yet
(planned: `{{ var | upper }}`). Keep it safe-by-default for user-authored
templates.
"""
from __future__ import annotations

import re
from typing import Any

_VAR_RE = re.compile(r"\{\{\s*([\w.?]+)\s*\}\}")
# Non-greedy, non-nested if/else/endif. Multi-line via DOTALL.
_IF_RE = re.compile(
    r"\{%\s*if\s+([\w.?]+)\s*%\}(.*?)(?:\{%\s*else\s*%\}(.*?))?\{%\s*endif\s*%\}",
    re.DOTALL,
)


def _lookup(ctx: dict, dotted: str) -> Any:
    """Walk `ctx` using a dotted key. Trailing `?` is stripped (Liquid-style
    "truthy probe", used e.g. by `to.scheduler_at_all?`)."""
    key = dotted.rstrip("?")
    parts = key.split(".")
    cur: Any = ctx
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif hasattr(cur, p):
            cur = getattr(cur, p)
        else:
            return None
        if cur is None:
            return None
    return cur


def _truthy(v: Any) -> bool:
    return bool(v) and v != ""


def render(template_text: str, ctx: dict) -> str:
    if not template_text:
        return ""
    out = template_text

    # Resolve {% if %}…{% endif %} repeatedly until no more matches (no nesting,
    # but supports multiple ifs in a row). Bound the loop to avoid pathological input.
    for _ in range(50):
        m = _IF_RE.search(out)
        if not m:
            break
        var, then_branch, else_branch = m.group(1), m.group(2), (m.group(3) or "")
        chosen = then_branch if _truthy(_lookup(ctx, var)) else else_branch
        out = out[: m.start()] + chosen + out[m.end():]

    # Substitute {{ var }} occurrences
    def _sub(m: re.Match) -> str:
        v = _lookup(ctx, m.group(1))
        if v is None or v is False:
            return ""
        return str(v)

    out = _VAR_RE.sub(_sub, out)
    return out


# ── Context builder ─────────────────────────────────────────────────────────
# Keep keys/labels consistent with `artifacts/EMAIL-VARIABLES.md`.

_SERVICE_ROLE_ES = {
    "administrator": "Administrador",
    "editor": "Editor",
    "coordinator": "Coordinador",
    "viewer": "Visualizador",
    "scheduled_viewer": "Visualizador Agendado",
}


def _first(name: str | None) -> str:
    if not name: return ""
    return name.split()[0]


def _last(name: str | None) -> str:
    if not name: return ""
    parts = name.split()
    return parts[-1] if len(parts) > 1 else ""


def build_context(
    *,
    sender_member=None,        # OrgMember of who sent it (may be None for system)
    sender_signature: str | None = None,  # RAW signature template (may contain {{ to.* }} / {{ organization.* }})
    sender_signature_image: str | None = None,  # data: URL base64 of the signature image (optional)
    recipient_member,           # OrgMember (mandatory — one msg per recipient)
    recipient_service_role: str | None = None,  # 'administrator' | … | None
    recipient_has_password: bool = False,
    organization,               # Organization model
    service: dict | None = None,  # {day, name, scheduled_at} or None
    team: dict | None = None,     # {name, color, positions:[str], leaders:[{full_name,email}], recipient_positions:[str]} or None
    sender_team_role: str | None = None,  # "Líder de equipo" / "Administrador" / role label
) -> dict:
    """Build the variable context for a SINGLE recipient. When sending to many
    people, call this per-recipient and render once each.

    `sender_signature` is treated as a *template*: it gets rendered with the
    recipient's `to.*` and `organization.*` context BEFORE being exposed as
    `{{ from.signature }}`. This lets people personalize their sign-off
    (e.g. "Saludos a {{ to.first_name }} · {{ organization.name }}").
    `{{ from.* }}` is intentionally NOT available inside a signature.
    """
    to_full = (recipient_member.full_name or recipient_member.email or "").strip()
    from_full = (sender_member.full_name if sender_member else None) or "Worsyn"
    svc_role_label = _SERVICE_ROLE_ES.get(recipient_service_role or "", "Visualizador")
    is_scheduler = recipient_service_role in ("administrator", "editor", "coordinator")
    login_method = "Email + contraseña"  # only mode supported today; future: 'Google', 'Apple', 'Microsoft'

    to_dict = {
        "name": to_full,
        "full_name": to_full,
        "first_name": _first(to_full),
        "last_name": _last(to_full),
        "email": recipient_member.email,
        "prefix": getattr(recipient_member, "prefix", None) or "",
        "ministry": getattr(recipient_member, "ministry", None) or "",
        "service_role": svc_role_label,
        # Planning-Center-compatible alias
        "max_plan_permissions_s": svc_role_label,
        "scheduler_at_all?": is_scheduler,
        "login_method": login_method,
        "has_password": recipient_has_password,
    }
    org_dict = {
        "name": organization.name,
        "alias": organization.alias or "",
        "email": organization.email or "",
        "slug": organization.slug,
        "phone": organization.phone or "",
        "website": organization.website or "",
        "city": organization.city or "",
        "country": organization.country or "",
    }
    # Pre-render the signature with the same to/org buckets (no `from.*` allowed inside)
    rendered_signature_text = render(sender_signature or "", {"to": to_dict, "organization": org_dict})
    # Build the HTML signature: text with newlines→<br> + optional image embedded
    # as a data URL (max 1 MB enforced upstream). `{{ from.signature }}` is
    # substituted into an HTML body, so this needs to be HTML-safe.
    sig_html_parts: list[str] = []
    if rendered_signature_text:
        sig_html_parts.append(rendered_signature_text.replace("\n", "<br>"))
    if sender_signature_image:
        sig_html_parts.append(
            f'<br><img src="{sender_signature_image}" alt="firma" '
            f'style="max-width:240px;height:auto;display:block;margin-top:8px"/>'
        )
    rendered_signature = "".join(sig_html_parts)

    # Team context (optional) — emitted as HTML strings ready to drop in templates
    team_dict: dict = {"name": "", "color": "", "positions": "", "leaders": "", "recipient_positions": ""}
    if team:
        positions = team.get("positions") or []
        leaders = team.get("leaders") or []
        rp = team.get("recipient_positions") or []
        team_dict = {
            "name": team.get("name") or "",
            "color": team.get("color") or "",
            "positions": (
                "<ul>" + "".join(f"<li>{p}</li>" for p in positions) + "</ul>"
            ) if positions else "<p><em>—</em></p>",
            "leaders": (
                "<ul>" + "".join(
                    f"<li>{(l.get('full_name') or l.get('email') or '').strip()}"
                    + (f" · <a href=\"mailto:{l['email']}\">{l['email']}</a>" if l.get('email') else "")
                    + "</li>"
                    for l in leaders
                ) + "</ul>"
            ) if leaders else "<p><em>—</em></p>",
            "recipient_positions": (
                "<ul>" + "".join(f"<li>{p}</li>" for p in rp) + "</ul>"
            ) if rp else "<p><em>—</em></p>",
        }

    return {
        "to": to_dict,
        "from": {
            "name": from_full,
            "first_name": _first(from_full),
            "last_name": _last(from_full),
            "email": (sender_member.email if sender_member else (organization.email or "")) or "",
            "signature": rendered_signature,
            "signature_image": sender_signature_image or "",
            "team_role": sender_team_role or "",
        },
        "organization": org_dict,
        "service": service or {},
        "team": team_dict,
    }
