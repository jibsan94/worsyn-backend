# Worsyn — Email Variables & Template Syntax

This is the **canonical catalog** of variables and template syntax available inside any email body or subject in Worsyn. Used by:

- The Compose editor in `Servicios → Personas → Comunicación → + Nuevo`
- The Email Templates manager (4 kinds: `General`, `Programación`, `Hojas de inscripción`, `Bienvenida`)
- The variable picker dropdown in both editors
- The server-side rendering engine ([app/services/email_render.py](../app/services/email_render.py))

When a template is sent, **the server renders ONE message per recipient**: the variable context is built freshly for each `to.*`, so an email to N people produces N personalized copies.

---

## Syntax

### Variable output — `{{ var }}`

Outputs the value, or empty string if missing. Whitespace inside braces is optional.

```
Hola {{ to.first_name }}, te ha invitado {{ from.name }}.
→ "Hola María, te ha invitado Jibsan Rosa."
```

### Nested keys with dots

```
{{ organization.name }}
{{ to.service_role }}
```

### Truthy-probe suffix `?`

Variables ending in `?` are conventional booleans. The trailing `?` is **ignored during lookup** (so `to.scheduler_at_all?` resolves the key `to.scheduler_at_all`) and serves only as a hint that the value is meant for `if` blocks.

```
{% if to.scheduler_at_all? %}…{% endif %}
```

### Conditional blocks — `{% if var %}…{% endif %}` / with else

```
{% if to.has_password %}
Inicia sesión con tu contraseña habitual de Worsyn.
{% else %}
Usa el enlace que recibirás para crear tu contraseña.
{% endif %}
```

Rules:
- The variable is evaluated with Python truthiness (`None`, `""`, `0`, `False`, empty list/dict → false).
- `{% else %}` branch is optional.
- **Nesting is NOT supported in v1** — write flat conditionals.
- Up to 50 conditionals per template (engine bound).

### Comments / escaping

There's no escape sequence yet — if you literally need `{{` or `{%` in the output, send a placeholder you don't intend to render (Phase 3 will add `{% raw %}…{% endraw %}`).

---

## Variable catalog

All values are read at send time. Missing or null → empty string.

### `to.*` — recipient (the person who will receive the email)

| Variable | Type | Example | Description |
|----------|------|---------|-------------|
| `to.name` | str | `María García` | Full name (= `to.full_name`) |
| `to.full_name` | str | `María García` | Same as `to.name`, kept for clarity in long templates |
| `to.first_name` | str | `María` | First whitespace-split token of full name |
| `to.last_name` | str | `García` | Last whitespace-split token; empty if only one word |
| `to.email` | str | `maria@iglesia.com` | Email address |
| `to.prefix` | str | `Sra.` | Honorific (from member profile) |
| `to.ministry` | str | `Alabanza` | Primary ministry assignment |
| `to.service_role` | str | `Administrador` | Spanish label of the person's role in the Servicios module |
| `to.max_plan_permissions_s` | str | `Administrador` | **Alias for compatibility with Planning Center templates.** Identical to `to.service_role` |
| `to.scheduler_at_all?` | bool | `true` | True if `service_role ∈ {administrator, editor, coordinator}` — i.e. can schedule others |
| `to.login_method` | str | `Email + contraseña` | How the person signs in. Today only one mode; future: `Google`, `Apple`, `Microsoft` |
| `to.has_password` | bool | `true` | True if `org_members.hashed_password` is set |

### `from.*` — sender (the logged-in person hitting "Send")

| Variable | Type | Example | Description |
|----------|------|---------|-------------|
| `from.name` | str | `Jibsan Rosa` | Sender's full name |
| `from.first_name` | str | `Jibsan` | First name |
| `from.last_name` | str | `Rosa` | Last name |
| `from.email` | str | `jibsan@iglesia.com` | Sender email (falls back to `organization.email` for system mail) |
| `from.signature` | str | `Jibsan Rosa\nLíder de Alabanza\n…` | Text signature configured by sender. **Renders multi-line** — preserves `\n` |

> The signature **image** (`signature_image`) is attached separately as an HTML inline image — not exposed as a `{{ from.signature_image }}` variable yet. Phase 3 will inject it via the HTML renderer.

#### Signature is itself a template

`signature_text` is rendered **before** being exposed as `{{ from.signature }}`. The signature can use:
- `{{ to.* }}` (the email's recipient — useful for greetings: `Saludos a {{ to.first_name }}`)
- `{{ organization.* }}` (the church)

`{{ from.* }}` is **intentionally not available** inside a signature (no self-reference). The compose / signature editor's variable picker enforces this by hiding non-allowed groups.

### `organization.*` — the tenant church

| Variable | Type | Example | Description |
|----------|------|---------|-------------|
| `organization.name` | str | `Comunidad Cristiana de Camarma` | Display name |
| `organization.alias` | str | `ccc` | Short URL alias |
| `organization.slug` | str | `comunidad-cristiana-de-camarma` | Path slug |
| `organization.email` | str | `contacto@ccc.com` | Contact email |
| `organization.phone` | str | `+34 912 345 678` | Phone |
| `organization.website` | str | `https://ccc.com` | Website URL |
| `organization.city` | str | `Camarma de Esteruelas` | City |
| `organization.country` | str | `España` | Country |

### `service.*` — service plan context (only present in `schedule` templates)

| Variable | Type | Notes |
|----------|------|-------|
| `service.day` | str | Date label, e.g. `Domingo 31 de mayo` |
| `service.name` | str | Service type name, e.g. `Servicio Dominical` |
| `service.scheduled_at` | str | ISO 8601 datetime |

`service.*` is empty for `general` / `welcome` / `signup` templates. Phase 3 will populate it automatically when the email is triggered from a plan view.

---

## Example templates

### Welcome email (parity with Planning Center)

```
Hola {{ to.name }},

¡{{ from.name }} te ha invitado a usar la cuenta de Services de {{ organization.name }}!

Services es una herramienta en línea que ayuda a las iglesias a organizar a su
equipo y planificar los próximos servicios. Con tus permisos de
{{ to.max_plan_permissions_s }}, podrás iniciar sesión en cualquier momento.

Cómo iniciar sesión:
- Tu método de inicio de sesión es: {{ to.login_method }}
{% if to.has_password %}
- Inicia sesión con tu contraseña habitual de Worsyn.
{% else %}
- Usa ese método de inicio de sesión para crear tu contraseña.
{% endif %}

{% if to.scheduler_at_all? %}
Con tus permisos de {{ to.max_plan_permissions_s }}, también podrás gestionar
equipos y programar personas en los planes.
{% endif %}

{{ from.signature }}
```

### Schedule / request

```
Hola {{ to.first_name }},

Se ha solicitado tu participación en uno o varios servicios. Revisa la
planificación y responde con el botón al final.

{{ from.signature }}
```

### General announcement

```
Asunto: Recordatorio de ensayo — {{ organization.name }}

Hola {{ to.first_name }},

Recuerda que el ensayo es esta semana. ¡Te esperamos!

{{ from.signature }}
```

---

## Render guarantees

- **Deterministic**: same `template + recipient` → same rendered output.
- **Safe**: no arbitrary expressions, no Python eval, no shell. Unknown variables → empty string.
- **One row per recipient**: `email_messages` stores both `body_template` (raw) and `body_rendered` (final). Subject is rendered too.
- **Idempotent retries**: SMTP worker (Phase 3) re-reads the rendered body — no re-rendering on send, so customer text doesn't drift.

## Adding new variables

1. Add the key/value in `app.services.email_render.build_context` (or extend the `service.*` branch when adding plan context).
2. Add a row to the right table in **this** file.
3. If the variable should appear in the picker dropdown, add it to `VARIABLE_GROUPS` in `worsyn-dashboard/src/tenant/pages/Servicios.tsx`.
4. Bump the file's "last updated" date below.

---

_Last updated: 2026-05-23 · catalog v1.0_
