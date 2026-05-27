# Worsyn API Documentation

**Base URL:** `http://<host>:8000/api/v1`
**OpenAPI spec:** `GET /api/openapi.json` · **Swagger UI:** `GET /api/docs`
**Auth:** Bearer JWT (`Authorization: Bearer <access_token>`)
**Content-Type:** `application/json` (except `/auth/login` → `application/x-www-form-urlencoded`)

---

## 📱 Mobile / Desktop Integration Guide (Phase 3 / 4)

This API is the **single source of truth** for every Worsyn surface: the admin web panel (this repo), the upcoming mobile apps (iOS + Android, Phase 3), and the desktop client (Electron or native, Phase 4). Every public endpoint below works equally well via web cookies **or** Bearer header — native clients must use the Bearer flow.

### 1. Two API surfaces

| Surface | Base path | Audience |
|---------|-----------|----------|
| **Platform / Admin** | `/api/v1/admin/*`, `/api/v1/organizations/*`, `/api/v1/auth/*` | Internal Worsyn operators only — `system_users` table. Not exposed to mobile apps. |
| **Tenant Portal**    | `/api/v1/tenant/*`, `/api/v1/tenant/{slug}/*` | All church members. **This is the API every mobile/desktop client consumes.** |

A tenant-side `OrgMember` cannot authenticate against the platform API and vice-versa. The tokens are different types (`access` for admins vs `tenant_access` / `org_select` for tenant) and the server rejects mismatches with 401.

### 2. Versioning & lifecycle

- Path prefix `v1` — never breaking changes. Additive only.
- Each tenant endpoint emits a stable JSON shape with `id` as a UUID string and all timestamps as ISO 8601 UTC (`2026-05-23T10:00:00+00:00`).
- Deprecations announced 90 days before removal via a `Deprecation` header — clients should log it.
- Future `v2` will live at `/api/v2/*` in parallel.

### 3. Auth flow for native apps (mobile + desktop)

Cookies are **not** usable from native clients. Every native client must use the Bearer header.

```
1. POST   /api/v1/tenant/auth/login           { email, password }
   → 200  { partial_token, orgs: [{slug, name, icon}] }
        (partial_token is a JWT of type 'org_select', 10-min expiry)

2. POST   /api/v1/tenant/auth/select          { partial_token, slug }
   → 200  { access_token, refresh_token?, member: {...} }

3. Every subsequent call:
   Authorization: Bearer <access_token>

4. When the server returns 401:
   • Refresh via /api/v1/tenant/auth/refresh (Phase 3 — pending) OR
   • Re-login (steps 1+2)
```

The `access_token` is a JWT of type `tenant_access`. Payload (read-only):

```json
{
  "sub": "<org_member uuid>",
  "type": "tenant_access",
  "org_id": "<uuid>",
  "org_slug": "iglesia-x",
  "exp": 1748000000,
  "impersonating": false
}
```

It does **not** carry the org role, the service role or the list of accessible modules. Always fetch those from `GET /tenant/{slug}/auth/me` after authentication — see §6 below.

### 4. Standard error envelope

All errors return JSON with a single `detail` string (FastAPI default):

```json
{ "detail": "Solo administradores pueden eliminar personas" }
```

For validation errors (Pydantic) the envelope is `{ "detail": [{ "loc": [...], "msg": "...", "type": "..." }] }`. Clients should display either form.

| Status | Meaning |
|--------|---------|
| 200    | OK |
| 201    | Created |
| 204    | No Content (typically DELETE) |
| 400    | Bad request — malformed body, invalid date, invalid enum |
| 401    | No autenticado · Token inválido · Sesión inválida |
| 403    | Permiso insuficiente (rol) |
| 404    | Recurso no encontrado |
| 409    | Conflicto (duplicado: email, slug, etc.) |
| 422    | Pydantic validation error |
| 500    | Bug del servidor — reportar |

### 5. JSON & data conventions

- IDs: **UUID v4 as string** — never integers.
- Timestamps: **ISO 8601** with timezone (`2026-05-23T10:00:00+00:00`). Dates: `YYYY-MM-DD`. Times: `HH:MM`.
- Money: stored as **integer cents** with explicit `currency` (e.g. `amount_cents: 12345, currency: "EUR"`).
- Avatars & small files: **base64 data URLs** (member avatar ≤ 3 MB, org icon ≤ 1 MB).
- Large files (member attachments): **multipart/form-data**, capped at 10 MB. Returned base64 only on explicit `/data` endpoint.
- Booleans, never `0/1`. Enums, never untyped strings — every enum is documented per-endpoint.
- Empty lists return `[]`, never `null`. Missing optional fields return `null`.

### 6. Module access — `GET /tenant/{slug}/auth/me`

Mobile clients use this to know which modules to render. The response includes:

```json
{
  "id": "...", "email": "...", "full_name": "...", "role": "admin|leader|member",
  "org_id": "...", "org_name": "...", "org_slug": "...", "avatar": null,
  "accessible_modules": ["servicios", "miembros", "..."],
  "service_role": "administrator|editor|coordinator|viewer|scheduled_viewer|null",
  "impersonating": false
}
```

Resolution rules: org admin/leader → all modules. Org member with `service_members` row → `["servicios","perfil"]`. Otherwise → `["perfil"]`. Impersonation → all modules.

### 7. File uploads (member attachments)

```
POST /api/v1/tenant/{slug}/members/{member_id}/attachments
Content-Type: multipart/form-data
fields:
  file:  <binary>     (max 10 MB)
  label: "Pasaporte"  (string)
```

Returns `{ id, label, original_name, mime_type, size_bytes, uploaded_at }`. The bytes themselves are fetched separately via `GET .../attachments/{id}/data`, which returns a base64-encoded `file_data` field plus `mime_type` so the client can build a `data:<mime>;base64,<data>` URL for preview/download.

### 8. Real-time & notifications (Phase 3+)

- **WebSocket**: not yet implemented. Planned at `/api/v1/tenant/{slug}/ws` for plan updates, attendance ticks, blockout sync.
- **Push notifications**: planned via Apple APNs + Firebase FCM. The tokens will be registered via `POST /tenant/{slug}/auth/devices` (not yet implemented).
- **Polling**: until those land, mobile apps can safely poll `/auth/me`, `/services/people`, `/services/occurrences` every 60–300 s.

### 9. Pagination & filtering (current state)

Most listing endpoints currently return the full collection (typically ≤ a few hundred rows per org). Phase 3 will introduce `?cursor=&limit=` query params on:

- `GET /tenant/{slug}/members`
- `GET /tenant/{slug}/services/plans`
- `GET /tenant/{slug}/songs`
- `GET /tenant/{slug}/media`
- `GET /tenant/{slug}/finance/transactions`

Until then, clients should assume "small enough to fetch fully".

### 10. Endpoint index (tenant portal)

| Module | Path prefix | State | CRUD |
|--------|-------------|-------|------|
| Auth (unified)       | `/tenant/auth/*`                         | Stable    | login, select, switch-options |
| Auth (per-slug)      | `/tenant/{slug}/auth/*`                  | Stable    | login, me, profile, logout, switch-options |
| Settings (org)       | `/tenant/{slug}/settings`                | Stable    | GET, PATCH |
| Members              | `/tenant/{slug}/members`                 | Stable    | GET, POST, PUT, DELETE + attachments CRUD |
| Services · Types     | `/tenant/{slug}/services/types`          | Stable    | GET, POST, PATCH, DELETE |
| Services · Plans     | `/tenant/{slug}/services/plans`          | Stable    | GET, POST |
| Services · Occurrences | `/tenant/{slug}/services/occurrences` | Stable    | GET (projection) |
| Services · People    | `/tenant/{slug}/services/people`         | Stable    | GET, POST, PATCH, DELETE + welcome + reset-password (test) |
| Services · Blockouts | `/tenant/{slug}/services/people/{id}/blockouts` | Stable | GET, POST, PATCH, DELETE |
| Teams                | `/tenant/{slug}/teams`                   | Stable    | GET, POST, PATCH, DELETE + memberships |
| Email · Templates    | `/tenant/{slug}/email/templates`         | Stable    | GET, POST, PATCH, DELETE (4 kinds) |
| Email · Messages     | `/tenant/{slug}/email/messages`          | Stable    | GET, POST (queues for SMTP), GET /{id} + /preview |
| Email · Per-person   | `/tenant/{slug}/services/people/{id}/messages` | Stable | GET (mailbox: sent ∪ received for the person) |
| Auth · Reset password| `/tenant/auth/reset-password/{token}`    | Stable    | GET (token info, public), POST (set new pwd, public) |
| Songs                | `/tenant/{slug}/songs`                   | **Stub**  | GET only (POST/PATCH/DELETE pending — Phase 3) |
| Media                | `/tenant/{slug}/media`                   | **Stub**  | GET only |
| Scores               | `/tenant/{slug}/scores`                  | **Stub**  | GET only |
| Events               | `/tenant/{slug}/events`                  | **Stub**  | GET only |
| Rehearsals           | `/tenant/{slug}/rehearsals`              | **Stub**  | GET only |
| Calendar             | `/tenant/{slug}/calendar`                | **Stub**  | GET unified feed (events + rehearsals + plans) |
| Finance              | `/tenant/{slug}/finance/*`               | **Stub**  | GET transactions + summary |

**Stub** = read-only; write endpoints will land as each module's UI is built. Mobile/desktop clients can already list these resources but cannot mutate them yet.

---

## Two user types

| Type | Table | Description |
|------|-------|-------------|
| `AdminUser` | `system_users` | Worsyn platform operators — access to this panel |
| `OrgMember` | `org_members` | Members of a tenant church organization — no panel access |

---

## Role access matrix

| Role    | Auth | Organizations | Org Members | Admin Users (system_users) | Settings (read) | Settings (write) | Health |
|---------|------|---------------|-------------|----------------------------|-----------------|------------------|--------|
| —       | ✅   | ❌            | ❌          | ❌                         | ❌              | ❌               | ✅     |
| `user`  | ✅   | ✅ read       | ✅ read     | ❌                         | ❌              | ❌               | ✅     |
| `admin` | ✅   | ✅ write      | ✅ write    | ✅ (no owners)             | ✅              | ❌               | ✅     |
| `owner` | ✅   | ✅ write+del  | ✅ write    | ✅ (all)                   | ✅              | ✅               | ✅     |

---

## System

### GET /health
Check API + database connectivity.

**Auth required:** No

**Response 200**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "db": "ok"
}
```

---

## Auth

### POST /auth/login
Authenticate with username and password. Returns JWT tokens.

**Auth required:** No  
**Content-Type:** `application/x-www-form-urlencoded`

**Form fields**

| Field      | Type   | Required |
|------------|--------|----------|
| `username` | string | ✅       |
| `password` | string | ✅       |

**Response 200 — no 2FA**
```json
{
  "requires_2fa": false,
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "must_change_password": true,
  "role": "owner"
}
```

**Response 200 — user has 2FA enabled**
```json
{
  "requires_2fa": true,
  "partial_token": "eyJ...",
  "access_token": null,
  "refresh_token": null,
  "token_type": "bearer",
  "must_change_password": false,
  "role": "owner"
}
```

> If `requires_2fa: true`, the frontend must call `POST /auth/2fa/complete` with the `partial_token` and a TOTP code to obtain full tokens.

**Errors**

| Code | Detail |
|------|--------|
| 401  | Invalid credentials |
| 403  | Account disabled |

---

### POST /auth/2fa/complete
Complete login for users who have 2FA enabled. Called after `POST /auth/login` returns `requires_2fa: true`.

**Auth required:** No

**Request body**
```json
{
  "partial_token": "eyJ...",
  "totp_code": "123456"
}
```

**Response 200**
```json
{
  "requires_2fa": false,
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "must_change_password": false,
  "role": "owner"
}
```

**Errors**

| Code | Detail |
|------|--------|
| 401  | Token inválido o expirado |
| 400  | Código 2FA incorrecto |

---

### GET /auth/2fa/setup
Generate a new TOTP secret for the authenticated user. Returns a QR code (base64 PNG) to scan with an authenticator app. The secret is stored in Redis for 5 minutes pending verification via `POST /auth/2fa/enable`.

**Auth required:** Yes (any role)

**Response 200**
```json
{
  "secret": "BASE32SECRET",
  "qr_code": "<base64 PNG string>",
  "uri": "otpauth://totp/Worsyn%20Admin:user@example.com?secret=...&issuer=Worsyn%20Admin"
}
```

---

### POST /auth/2fa/enable
Verify a TOTP code against the pending setup secret in Redis and persist 2FA to the user account. Must be called while the Redis session from `GET /auth/2fa/setup` is still alive.

**Auth required:** Yes (any role)

**Request body**
```json
{ "totp_code": "123456" }
```

**Response 200**
```json
{ "status": "enabled" }
```

**Errors**

| Code | Detail |
|------|--------|
| 400  | Sesión expirada (Redis TTL elapsed) |
| 400  | Código incorrecto |

---

### POST /auth/2fa/disable
Disable 2FA for the current user. Requires current TOTP code as confirmation.

**Auth required:** Yes (any role)

**Request body**
```json
{ "totp_code": "123456" }
```

**Response 200**
```json
{ "status": "disabled" }
```

**Errors**

| Code | Detail |
|------|--------|
| 400  | 2FA no está activado |
| 400  | Código incorrecto |

---

### GET /auth/me
Return the currently authenticated user.

**Auth required:** Yes (any role)

**Response 200**
```json
{
  "id": "uuid",
  "username": "admin",
  "email": "admin@worsyn.local",
  "full_name": "Worsyn Owner",
  "role": "owner",
  "is_active": true,
  "must_change_password": false,
  "created_at": "2026-05-11T13:16:03.583827+00:00",
  "last_login_at": "2026-05-11T13:16:11.246295+00:00"
}
```

**Errors**

| Code | Detail |
|------|--------|
| 401  | Missing or invalid token |

---

### POST /auth/change-credentials
Change username and/or password. Used from the **Perfil** page (`/profile`).  
On success sets `must_change_password = false`.

**Auth required:** Yes (any role)

**Request body**
```json
{
  "current_password": "worsyn",
  "new_username": "admin",
  "new_password": "SecureP@ss123"
}
```

| Field              | Type   | Required | Rules |
|--------------------|--------|----------|-------|
| `current_password` | string | ✅       | Must match current password |
| `new_username`     | string | ❌       | Min 3 chars, no spaces, must be unique |
| `new_password`     | string | ❌       | Min 8 chars |

> At least one of `new_username` or `new_password` must be provided.

**Response 200**
```json
{
  "status": "ok",
  "username": "admin"
}
```

**Errors**

| Code | Detail |
|------|--------|
| 400  | Current password incorrect |
| 400  | new_username or new_password required |
| 400  | Username min 3 chars / Password min 8 chars |
| 409  | Username already taken |

---

## Admin User Management (`system_users`)

All endpoints require role `admin` or `owner`.  
**Rule:** An `admin` can never delete or modify users with role `owner`.  
**Rule:** An `admin` cannot create users with role `owner`.  
**Rule:** An `admin` cannot promote a user to role `owner`.  
**Rule:** No user can delete their own account.

---

### GET /admin/users
List all platform users.

**Auth required:** admin, owner

**Response 200** — array of `AdminUserRead`
```json
[
  {
    "id": "uuid",
    "username": "operator1",
    "email": "op1@worsyn.local",
    "full_name": "Operator One",
    "role": "admin",
    "is_active": true,
    "must_change_password": true,
    "avatar": null,
    "created_at": "2026-05-11T14:00:00+00:00",
    "last_login_at": null
  }
]
```

---

### POST /admin/users
Create a new platform user. New users always start with `must_change_password: true`.

**Auth required:** admin, owner

**Request body**
```json
{
  "username": "operator1",
  "email": "op1@worsyn.local",
  "password": "InitialP@ss1",
  "full_name": "Operator One",
  "role": "admin"
}
```

| Field       | Type   | Required | Rules |
|-------------|--------|----------|-------|
| `username`  | string | ✅       | Unique |
| `email`     | string | ✅       | Unique, must contain `@` |
| `password`  | string | ✅       | — |
| `full_name` | string | ❌       | — |
| `role`      | string | ✅       | `user`, `admin`, `owner` (admin cannot set `owner`) |

**Response 201** — `AdminUserRead`

**Errors**

| Code | Detail |
|------|--------|
| 403  | Admins cannot create owner accounts |
| 409  | Username already taken |
| 409  | Email already registered |

---

### GET /admin/users/{user_id}
Get a single platform user by UUID.

**Auth required:** admin, owner

**Response 200** — `AdminUserRead`

**Errors**

| Code | Detail |
|------|--------|
| 404  | User not found |

---

### PUT /admin/users/{user_id}
Update a platform user. Admin cannot modify owner accounts.  
If `password` is provided, `must_change_password` is reset to `true`.

**Auth required:** admin, owner

**Request body** (all fields optional)
```json
{
  "username": "newname",
  "email": "new@worsyn.local",
  "full_name": "New Name",
  "role": "admin",
  "is_active": true,
  "password": "NewP@ss123"
}
```

**Response 200** — `AdminUserRead`

**Errors**

| Code | Detail |
|------|--------|
| 403  | Admins cannot modify or delete owner accounts |
| 403  | Admins cannot assign the owner role |
| 404  | User not found |
| 409  | Username already taken |
| 409  | Email already registered |

---

### PUT /admin/users/{user_id}/avatar
Update or remove the avatar for a platform user.
- Any authenticated user can update **their own** avatar.
- Admin/owner can update other users' avatars (with owner-protection rule).

**Auth required:** any authenticated user (own avatar); admin/owner (others)

**Request body**
```json
{ "avatar": "data:image/jpeg;base64,/9j/4AA..." }
```
Set `avatar` to `null` to remove the current avatar.

| Field    | Type          | Notes |
|----------|---------------|-------|
| `avatar` | string\|null  | Base64 data URL. Max ~450 KB encoded. |

**Response 200** — `AdminUserRead`

**Errors**

| Code | Detail |
|------|--------|
| 403  | Insufficient permissions |
| 404  | User not found |
| 413  | Avatar too large (max ~450 KB) |

---

### DELETE /admin/users/{user_id}
Delete a platform user. Admin cannot delete owner accounts. No user can delete themselves.

**Auth required:** admin, owner

**Response 204** — No content

**Errors**

| Code | Detail |
|------|--------|
| 400  | Cannot delete your own account |
| 403  | Admins cannot modify or delete owner accounts |
| 404  | User not found |

---

### PUT /admin/users/{user_id}/2fa
Toggle 2FA on/off for **own account only**. Any authenticated user can manage their own.

**Auth required:** any authenticated user (only own account)

**Response 200** — returns updated `AdminUserRead`

**Errors**

| Code | Detail |
|------|--------|
| 403  | You can only manage your own 2FA |
| 404  | User not found |

---

### DELETE /admin/users/{user_id}/2fa
Reset (disable) 2FA for a user. **Owner only.**

**Auth required:** owner

**Response 204** — No content

**Errors**

| Code | Detail |
|------|--------|
| 403  | Insufficient permissions |
| 404  | User not found |

---

## Organizations

### GET /organizations
List all organizations with `member_count`.

**Auth required:** any role

**Response 200**
```json
[
  {
    "id": "uuid",
    "name": "Iglesia Gracia",
    "slug": "iglesia-gracia",
    "alias": "gracia",
    "email": "info@iglesiagracia.es",
    "plan": "pro",
    "status": "active",
    "country": "ES",
    "city": "Madrid",
    "phone": "+34 600 000 000",
    "website": "https://iglesiagracia.es",
    "created_at": "2026-05-11T00:00:00+00:00",
    "member_count": 12
  }
]
```

---

### POST /organizations
Create a new organization. **Automatically provisions a tenant PostgreSQL container** in the background (`worsyn-tenant-{slug}-db` on port 6001+).

**Auth required:** admin, owner

**Request body**
```json
{
  "name": "Iglesia Gracia",
  "slug": "iglesia-gracia",
  "alias": "gracia",
  "email": "info@iglesiagracia.es",
  "plan": "free",
  "status": "active",
  "country": "ES",
  "city": "Madrid"
}
```

**Response 201** — `OrganizationRead`  
> Tenant provisioning runs async. Poll `GET /organizations/{id}/tenant` to check status.

---

### GET /organizations/slug/{slug}
**PUBLIC — no auth required.** Returns basic org info by slug. Used by TenantPortal.

**Response 200**
```json
{ "id": "uuid", "name": "Iglesia Gracia", "slug": "iglesia-gracia", "alias": "gracia", "plan": "pro" }
```

**Response 404** if org not found.

---

### GET /organizations/{org_id}
Get a single organization with `member_count`.

**Auth required:** any role  
**Response 200** — `OrganizationRead`

---

### PATCH /organizations/{org_id}
Update organization fields (partial update). Supports `email` and `alias`.

**Auth required:** admin, owner  
**Response 200** — `OrganizationRead`

---

### DELETE /organizations/{org_id}
Delete an organization and all its members. Also destroys the tenant container.

**Auth required:** owner only  
**Response 204** — No content

---

## Tenant Management

Each organization has exactly one tenant: an isolated PostgreSQL container.

### GET /organizations/{org_id}/tenant
Get tenant info for an organization.

**Auth required:** admin, owner

**Response 200**
```json
{
  "org_id": "uuid",
  "status": "running",
  "db_port": 6001,
  "container_name": "worsyn-tenant-iglesia-gracia-db",
  "compose_dir": "/mnt/tenants/iglesia-gracia",
  "provisioned_at": "2026-05-13T20:00:00+00:00",
  "error_msg": null,
  "updated_at": "2026-05-13T20:00:00+00:00"
}
```

Tenant statuses: `provisioning` | `running` | `stopped` | `error`

---

### POST /organizations/{org_id}/impersonate
**Support mode** — issues a 1-hour `tenant_access` cookie that lets an admin/owner enter the org portal with synthetic super-admin permissions (role = `admin`, all writes allowed). The portal `/auth/me` endpoint detects the `impersonating: true` JWT flag and returns a synthetic profile (`<admin_username>@worsyn.support`).

**Auth required:** admin, owner

**Response 200**
```json
{ "slug": "lifeboat", "org_name": "LifeBoat", "expires_in": 3600 }
```

Side effect: sets cookie `tenant_access` (httpOnly, 1h). Logged via `org.impersonate` audit event.

---

### POST /organizations/{org_id}/tenant/start
Start a stopped tenant container.

**Auth required:** admin, owner  
**Response 200** — `TenantRead`

---

### POST /organizations/{org_id}/tenant/stop
Stop a running tenant container.

**Auth required:** admin, owner  
**Response 200** — `TenantRead`

---

### POST /organizations/{org_id}/tenant/refresh
Sync tenant status with actual Docker container state.

**Auth required:** admin, owner  
**Response 200** — `TenantRead`

---

### DELETE /organizations/{org_id}/tenant
**Destroy** the tenant container (removes it from Docker). The org record is kept. Sets tenant status to `stopped`. Use `POST /provision` to create a new container.

**Auth required:** admin, owner  
**Response 204** — No content

---

### POST /organizations/{org_id}/tenant/provision
(Re-)provision the tenant container. Creates a new PostgreSQL Docker container. Used after destroying a tenant or if initial provisioning failed.

**Auth required:** admin, owner  
**Response 200** — `TenantRead` (status = `provisioning`, completes async)

---

## Members (global — across all organizations)

Used by the admin Users page to view and manage org members regardless of their organization.

### GET /members/
List all org members with optional filters. Includes `org_name` and `org_slug` from the parent organization.

**Auth required:** any role  
**Query params:** `org_id` (UUID), `role` (admin|leader), `is_active` (bool), `search` (string — matches name or email), `skip`, `limit`

**Response 200**
```json
[
  {
    "id": "uuid", "org_id": "uuid", "org_name": "Comunidad Cristiana", "org_slug": "comunidad-cristiana",
    "email": "pastor@iglesia.com", "full_name": "Pastor Juan", "phone": null,
    "role": "admin", "is_active": true, "joined_at": "...", "updated_at": "..."
  }
]
```

---

### GET /members/{member_id}
Get a single org member by ID (any org).

**Auth required:** any role  
**Response 200** — `OrgMemberWithOrg`

---

### PATCH /members/{member_id}
Update an org member (partial). Supports: `full_name`, `email`, `phone`, `role`, `is_active`, `password`.

**Auth required:** admin, owner  
**Response 200** — `OrgMemberWithOrg`

---

### DELETE /members/{member_id}
Delete an org member.

**Auth required:** admin, owner  
**Response 204** — No content

---

## Org Roles

Manages the configurable roles available for org members. Stored in `org_roles` table.
System roles (`is_system=true`) cannot be deleted. Custom roles can be deleted if no members are assigned.

### GET /org-roles/
List all org roles ordered by `sort_order`. Includes `member_count` per role.

**Auth required:** any role

**Response 200**
```json
[
  { "id": "uuid", "slug": "admin", "name": "Administrador de Organización", "description": "...", "is_system": true, "sort_order": 0, "member_count": 3, "created_at": "...", "updated_at": "..." },
  { "id": "uuid", "slug": "leader", "name": "Líder", "is_system": true, "sort_order": 1, "member_count": 7, ... },
  { "id": "uuid", "slug": "member", "name": "Miembro", "is_system": true, "sort_order": 2, "member_count": 42, ... }
]
```

### POST /org-roles/
Create a new custom role. Slug must be unique, lowercase, letters/numbers/hyphens/underscores only.

**Auth required:** admin, owner  
**Body:** `{ slug, name, description?, sort_order? }`  
**Response 201** — `OrgRoleRead`

### PATCH /org-roles/{id}
Update role metadata (`name`, `description`, `sort_order`). Works for all roles including system ones.

**Auth required:** admin, owner  
**Response 200** — `OrgRoleRead`

### DELETE /org-roles/{id}
Delete a custom role. Fails if `is_system=true` or if any members have this role.

**Auth required:** owner only  
**Response 204** — No content

---

## Org Members

### Schema — OrgMemberRead

```json
{
  "id": "uuid",
  "org_id": "uuid",
  "email": "pastor@church.com",
  "full_name": "Juan Pastor",
  "phone": "+34 600 000 000",
  "role": "member",
  "is_active": true,
  "joined_at": "2026-05-20T00:00:00+00:00",
  "updated_at": "2026-05-20T00:00:00+00:00",
  "prefix": "Rvdo.",
  "gender": "M",
  "birthdate": "1980-05-15",
  "anniversary": "2005-06-20",
  "ministry": "Alabanza",
  "org_roles": ["Predicador", "Pastor o Anciano"]
}
```

`password` is optional on create. Stored as null until portal login is implemented.

---

### Admin panel endpoints (require AdminUser JWT)

Nested under `/organizations/{org_id}/members`:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/organizations/{org_id}/members` | any | List members |
| POST   | `/organizations/{org_id}/members` | admin, owner | Create member |
| GET    | `/organizations/{org_id}/members/{id}` | any | Get member |
| PUT    | `/organizations/{org_id}/members/{id}` | admin, owner | Update member |
| DELETE | `/organizations/{org_id}/members/{id}` | admin, owner | Delete member |

---

### Tenant portal endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/tenant/{slug}/members` | none | List org members |
| POST   | `/tenant/{slug}/members` | none | Create member |
| PUT    | `/tenant/{slug}/members/{id}` | none | Update member |
| DELETE | `/tenant/{slug}/members/{id}` | none | Delete member |
| GET    | `/tenant/{slug}/members/{id}/attachments` | JWT or cookie | List attachments (metadata only) |
| POST   | `/tenant/{slug}/members/{id}/attachments` | JWT or cookie (admin/leader) | Upload attachment — multipart: `file` + `label` (max 10 MB) |
| GET    | `/tenant/{slug}/members/{id}/attachments/{att_id}/data` | JWT or cookie (admin/leader) | Get base64 file_data + mime_type for preview/download |
| DELETE | `/tenant/{slug}/members/{id}/attachments/{att_id}` | JWT or cookie (admin/leader) | Delete attachment |
| POST   | `/tenant/auth/login` | none | **Unified login** — email+password → matching orgs + partial_token (10 min) |
| POST   | `/tenant/auth/select` | none | **Org selection** — partial_token + slug → tenant_access cookie |
| GET    | `/tenant/{slug}/auth/switch-options` | JWT or cookie | **Account switch** — returns other orgs for this member + new partial_token (10 min) |
| POST   | `/tenant/{slug}/auth/login` | none | Per-slug login (legacy / direct access) → 7-day cookie |
| GET    | `/tenant/{slug}/auth/me` | JWT or cookie | Validate session / get member info (incl. avatar) |
| POST   | `/tenant/{slug}/auth/logout` | none | Clear `tenant_access` cookie |
| PATCH  | `/tenant/{slug}/auth/profile` | JWT or cookie | Self-update own profile + avatar (max 3 MB base64) |
| GET    | `/tenant/{slug}/settings` | none | Get org settings (incl. ministries, roles, icon) |
| PATCH  | `/tenant/{slug}/settings` | JWT or cookie (admin role) | Update org settings |
| GET    | `/tenant/{slug}/settings/defaults` | none | Get platform default ministries and roles |

**GET /tenant/{slug}/auth/switch-options — Response**
```json
{
  "orgs": [
    { "slug": "org-b", "name": "Iglesia Beta", "icon": null }
  ],
  "partial_token": "<10-min org_select JWT>"
}
```
- `orgs` excludes the current org. Empty array if member only belongs to one org or is impersonating.
- Frontend shows "Cambiar de cuenta" in topbar dropdown only when `orgs.length > 0`.
- If 1 other org → auto-switch with loading screen. If 2+ → picker modal.
- Then calls `POST /tenant/auth/select` with the returned `partial_token` + target `slug`.

**PATCH /tenant/{slug}/settings — Request body (all fields optional)**
```json
{
  "name": "Mi Iglesia",
  "alias": "mi-iglesia",
  "icon": "data:image/png;base64,...",
  "ministries": ["Alabanza", "Pastoral", "Jóvenes"],
  "member_roles": ["Vocalista", "Pianista", "Guitarrista"],
  "require_2fa_admins": false
}
```

**Errors**

| Code | Detail |
|------|--------|
| 401  | Token inválido / No autenticado |
| 403  | Se requiere rol de admin |
| 409  | Ese alias ya está en uso |

**POST /tenant/{slug}/members — Request body**
```json
{
  "email": "miembro@iglesia.com",
  "full_name": "María García",
  "phone": "+34 612 345 678",
  "prefix": "Sra.",
  "gender": "F",
  "birthdate": "1990-03-10",
  "anniversary": null,
  "ministry": "Alabanza",
  "org_roles": ["Vocalista", "Líder de Adoración"],
  "role": "member"
}
```

**Errors**

| Code | Detail |
|------|--------|
| 404  | Org slug not found |
| 409  | Email already exists in this org |

---

## Tenant · Services

All endpoints require a valid `tenant_access` cookie or `Authorization: Bearer <tenant_access>` header. Mutations require `role = admin | leader` on the org. Impersonation tokens behave as `admin`. The role is **read from the DB at request time**, not from the JWT (the tenant_access JWT does not carry `org_role`).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/tenant/{slug}/services/types` | JWT or cookie | List service types (with nested times + team_ids) |
| POST   | `/tenant/{slug}/services/types` | admin/leader | Create service type + nested times + team picks |
| PATCH  | `/tenant/{slug}/services/types/{type_id}` | admin/leader | Update fields and/or replace nested `times` / `team_ids` |
| DELETE | `/tenant/{slug}/services/types/{type_id}` | admin/leader | Cascade-deletes service_times + service_teams (FK ON DELETE CASCADE) |
| GET    | `/tenant/{slug}/services/plans` | JWT or cookie | List concrete plan instances (ordered by scheduled_at DESC, NULLS LAST) |
| POST   | `/tenant/{slug}/services/plans` | admin/leader | Create a one-off plan instance |
| GET    | `/tenant/{slug}/services/occurrences?range_from=YYYY-MM-DD&range_to=YYYY-MM-DD` | JWT or cookie | Project ServiceTime templates forward into concrete date+time occurrences. Default window: today → today+90d |

### Recurrence values

`none` (one-shot, no projection) · `random` (single anchor, no projection) · `daily` · `weekly` · `weekdays` (Mon–Fri) · `biweekly` · `monthly` (same day-of-month, clamped to last day if shorter)

### POST /tenant/{slug}/services/types — Request body

```json
{
  "name": "Servicio Dominical",
  "color": "#4F46E5",
  "recurrence": "weekly",
  "description": null,
  "sort_order": 0,
  "times": [
    { "starts_on": "2026-05-24", "start_time": "09:00", "end_time": "10:15" },
    { "starts_on": "2026-05-24", "start_time": "11:00", "end_time": "12:15" }
  ],
  "team_ids": ["<team-uuid-1>", "<team-uuid-2>"]
}
```

Notes:
- `times[]` is required and must contain at least one entry. Each row creates a `service_times` record.
- `starts_on` is the **first occurrence date** — its weekday is derived server-side. Recurrence rules project from here.
- `team_ids[]` are validated against the org; unknown IDs are silently dropped.
- The default `starts_on` exposed by the wizard UI is **the next Sunday** following today.

### Response 201 — fully hydrated ServiceType

```json
{
  "id": "uuid",
  "name": "Servicio Dominical",
  "color": "#4F46E5",
  "sort_order": 0,
  "recurrence": "weekly",
  "description": null,
  "times": [
    { "id": "uuid", "starts_on": "2026-05-24", "start_time": "09:00", "end_time": "10:15", "weekday": 6, "sort_order": 0 },
    { "id": "uuid", "starts_on": "2026-05-24", "start_time": "11:00", "end_time": "12:15", "weekday": 6, "sort_order": 1 }
  ],
  "team_ids": ["uuid-1", "uuid-2"]
}
```

`weekday`: 0=Monday … 6=Sunday (Python `date.weekday()` convention).

### PATCH /tenant/{slug}/services/types/{type_id}

All fields optional. If `times` or `team_ids` is supplied, the existing rows are **replaced** in full.

### GET /tenant/{slug}/services/occurrences — Response

```json
[
  {
    "service_type_id": "uuid",
    "service_type_name": "Servicio Dominical",
    "color": "#4F46E5",
    "date": "2026-05-24",
    "start_time": "09:00",
    "end_time": "10:15"
  }
]
```

Ordered by `(date, start_time)`. Frontend mini-calendar uses this to render day dots and the Calendario Maestro modal uses it for the month grid.

### POST /tenant/{slug}/services/plans — Request body

```json
{
  "title": "Servicio 24 mayo",
  "scheduled_at": "2026-05-24T11:00:00",
  "service_type_id": "uuid-or-null",
  "status": "draft",
  "notes": null
}
```

### Errors

| Code | Detail |
|------|--------|
| 400  | El nombre es obligatorio · Recurrencia inválida · Debes definir al menos un horario · Hora inválida · Fecha inválida · scheduled_at inválido |
| 401  | No autenticado · Token inválido · Miembro no encontrado |
| 403  | Solo administradores y líderes |
| 404  | Tipo no encontrado · Org no encontrada |

---

## Tenant · Service People

Manages who has access to the Services module and at what level. Inspired by Planning Center: per-area roles, per-service-type overrides, file-access flags, and welcome flow.

**Auto-provisioning**: on first GET, any `org_member` with org-role `admin` that lacks a `service_members` row is inserted as `service_role='administrator'` (idempotent). This guarantees existing org admins always appear here as service administrators.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/tenant/{slug}/services/people` | JWT or cookie (any service_member or org admin/leader) | List service members with permissions |
| POST   | `/tenant/{slug}/services/people` | service administrator OR org admin/leader | Add person (existing org_member or new) with permissions; optional welcome |
| PATCH  | `/tenant/{slug}/services/people/{sm_id}` | service administrator OR org admin/leader | Update roles / file_access / per-type overrides |
| DELETE | `/tenant/{slug}/services/people/{sm_id}` | service administrator OR org admin/leader | Remove from Services module (does NOT delete from org_members). **Self-delete guard**: rejects `403` if the target is the caller themselves AND has `org_role == 'admin'` — another org admin must do it. Impersonation tokens bypass this guard. |
| POST   | `/tenant/{slug}/services/people/{sm_id}/welcome` | service administrator OR org admin/leader | Generate a temp password (if member has none) + mark `welcomed_at`. Returns temp password ONCE |

### Role enum

`service_role`  →  `administrator | editor | coordinator | viewer | scheduled_viewer`

| Role | Permissions in Servicios |
|------|--------------------------|
| `administrator` | Full control — add/edit/delete people, types, plans |
| `editor` | Edit services, types, plans. **No delete people**, **no add people** |
| `coordinator` | Coordinate plans within a type. **No add/modify types**, can manage (not delete) plans |
| `viewer` | Read-only across all services |
| `scheduled_viewer` | Read-only of *assigned* services only |

`songs_role` and `media_role` use the same enum **without** `coordinator`:
`administrator | editor | viewer | scheduled_viewer`

### POST /tenant/{slug}/services/people — Request body

Either `member_id` (existing org member) **or** `new_member` (create new):

```json
{
  "member_id": "<uuid>",
  "service_role": "editor",
  "songs_role": "viewer",
  "media_role": "viewer",
  "file_access": { "plans": true, "songs": true, "media": false },
  "type_permissions": [
    { "service_type_id": "<uuid>", "role": null },
    { "service_type_id": "<uuid>", "role": "administrator" }
  ],
  "send_welcome": true
}
```

```json
{
  "new_member": {
    "full_name": "Jorge Perez",
    "email": "jorge@iglesia.com",
    "phone": "+34 612 345 678"
  },
  "service_role": "viewer",
  "songs_role": "viewer", "media_role": "viewer",
  "file_access": { "plans": true, "songs": true, "media": true },
  "type_permissions": [],
  "send_welcome": true
}
```

Notes:
- `type_permissions[].role`: `null` means **same as parent** (inherit from `service_role`). Absent entries also inherit.
- `send_welcome: true`: if the member has no `hashed_password`, generates a 12-char temp password and stores it hashed. `welcomed_at` is stamped. The plaintext is returned **once** in the response as `temp_password` — admin shares manually until SMTP is wired.
- **Org admins are skipped**: if the resolved `OrgMember.role == 'admin'`, the server silently ignores `send_welcome` (no password gen, no `welcomed_at`). The dedicated `POST .../welcome` endpoint returns `400` for the same reason — admins already authenticate with their tenant-level password.

### Scheduling preferences (caps for the Phase-3 scheduler)

`ServiceMember` carries two soft caps consumed by the future cuadrante / scheduler:

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `scheduling.max_per_month` | `int \| null` | `null` (unlimited) | Max number of plans this person can be scheduled into per calendar month |
| `scheduling.max_per_day`   | `int \| null` | `null` (unlimited) | Max plans per day — useful when a church runs 2–4 services the same Sunday |

Update via `PATCH /tenant/{slug}/services/people/{sm_id}` body:

```json
{ "scheduling": { "max_per_month": 1, "max_per_day": 1 } }
```

Either value can be omitted (no change), `null`, `0`, or `""` (all interpreted as "unlimited"). Range is 1–31. The list/get response always includes `"scheduling": { "max_per_month": ..., "max_per_day": ... }`.

### Email signature

`ServiceMember` carries an optional signature used by outgoing tenant emails (once SMTP is wired in Phase 3).

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `signature.text`  | `string \| null` | `null` | Multi-line text (≤ 16 000 chars). Saved verbatim, displayed `pre-wrap`. |
| `signature.image` | `string \| null` | `null` | **Base64 data URL** (`data:image/*;base64,...`). Decoded size capped at **1 MB**. Use `null` to clear. |

**Permission**: signature is self-editable — the person can update their own without admin rights. Admin/leader (or impersonation) can update any. Other PATCH fields (`service_role`, `scheduling`, `file_access`, etc.) still require admin/leader.

Update via `PATCH /tenant/{slug}/services/people/{sm_id}`:

```json
{ "signature": {
    "text":  "Jibsan Rosa\nLíder de Alabanza\nComunidad Cristiana de Camarma",
    "image": "data:image/png;base64,iVBORw0KGgoAAA…"
} }
```

Send only the fields you want to change. Send `"image": null` to remove the current image without touching the text.

#### Errors

| Code | Detail |
|------|--------|
| 400  | Imagen inválida (debe ser data URL base64 de tipo image/*) · Imagen inválida (base64 corrupto) · Imagen demasiado grande (máx. 1 MB) · Firma de texto demasiado larga (máx. 16 000 caracteres) |
| 403  | Sin permiso para editar la firma |

### Plan assignments (scheduling summary)

Each row links one `org_member` to one `service_plan` with a status. Powers the "Resumen de programación" donut + upcoming-plans list on the person detail.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/tenant/{slug}/services/people/{sm_id}/assignments?range_from&range_to` | any member view-perm OR self | Summary + items in date range |
| POST   | `/tenant/{slug}/services/people/{sm_id}/assignments` | admin/leader/coord/svc-editor | Create assignment |
| PATCH  | `/tenant/{slug}/services/people/{sm_id}/assignments/{assignment_id}` | admin/coord OR the assigned person (self) | Update status (auto-stamps `responded_at` when changing to confirmed/declined) |
| DELETE | `/tenant/{slug}/services/people/{sm_id}/assignments/{assignment_id}` | admin/leader/coord/svc-editor | Unassign |

Status enum: `pending | confirmed | declined`.

#### GET response

```json
{
  "range": { "from": "2026-04-26", "to": null },
  "summary": { "confirmed": 1, "pending": 1, "declined": 1, "total": 3 },
  "items": [
    {
      "id": "uuid", "plan_id": "uuid",
      "plan_title": "Servicio Dominical",
      "service_type_id": "uuid", "service_type_name": "Servicio Dominical", "service_type_color": "#4F46E5",
      "scheduled_at": "2026-06-02T09:00:00+00:00",
      "team_id": "uuid", "team_name": "Equipo de Adoración", "team_color": "#4F46E5",
      "position": "Piano",
      "status": "pending",
      "requested_at": "...", "responded_at": null, "decline_reason": null
    }
  ]
}
```

Range presets the frontend uses: `upcoming` (today→∞), `1m/3m/6m/12m` (T-N months→today), `custom` (user-picked). Both ends optional — omit `range_from` for "since forever" or `range_to` for "into the future".

#### POST body

```json
{
  "service_plan_id": "uuid",
  "team_id": "uuid",        // optional
  "position": "Piano",
  "status": "pending"       // default
}
```

#### PATCH body

```json
{ "status": "confirmed" }
// or
{ "status": "declined", "decline_reason": "Estaré de viaje" }
```

`responded_at` is auto-stamped server-side when status flips to `confirmed` or `declined`. Self can update their own; admin/coord can update anyone's.

Phase 3 producer: the cuadrante/scheduler will INSERT these rows automatically based on `service_times` + `service_teams` + each member's `scheduling.max_per_*` caps + `service_member_blockouts`.

### Teams of a person

| Method | Path | Description |
|--------|------|-------------|
| GET | `/tenant/{slug}/services/people/{sm_id}/teams` | Teams this person belongs to (joins `team_memberships` → `teams` via `org_members.id`) |

Returns `[ { membership_id, team_id, team_name, team_color, role } ]`. To add/remove use the existing `/tenant/{slug}/teams/{team_id}/members` endpoints with `member_id` = the person's `member_id` (not their service_member id).

### Person blockouts (unavailability)

Per-ServiceMember unavailability ranges with optional recurrence. All endpoints scoped to a person.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/tenant/{slug}/services/people/{sm_id}/blockouts` | JWT or cookie (any member) | List blockouts ordered by `start_date DESC` |
| POST   | `/tenant/{slug}/services/people/{sm_id}/blockouts` | admin/leader/coordinator OR self | Create blockout |
| PATCH  | `/tenant/{slug}/services/people/{sm_id}/blockouts/{blockout_id}` | admin/leader/coordinator OR self | Update blockout |
| DELETE | `/tenant/{slug}/services/people/{sm_id}/blockouts/{blockout_id}` | admin/leader/coordinator OR self | Delete blockout |

#### Recurrence

`repeat_kind` ∈ `none | day | week | month | year` · `repeat_interval` 1–12 (`Cada`, `Cada dos`, …) · `repeat_until` ISO date or `null` (forever).

#### POST/PATCH body

```json
{
  "start_date": "2026-05-31",
  "end_date": "2026-06-02",
  "all_day": true,
  "repeat_kind": "week",
  "repeat_interval": 2,
  "repeat_until": "2026-08-31",
  "reason": "Vacaciones"
}
```

`end_date` defaults to `start_date` when omitted. For `repeat_kind: "none"`, the server forces `repeat_interval=1` and `repeat_until=null`.

#### Response

```json
{
  "id": "uuid",
  "start_date": "2026-05-31",
  "end_date": "2026-06-02",
  "all_day": true,
  "repeat_kind": "week",
  "repeat_interval": 2,
  "repeat_until": "2026-08-31",
  "reason": "Vacaciones",
  "created_at": "2026-05-23T10:00:00+00:00"
}
```

#### Errors

| Code | Detail |
|------|--------|
| 400  | Fecha inválida · `end_date < start_date` · `repeat_kind` inválido · `repeat_interval` fuera de rango (1–12) · `repeat_until` < `start_date` |
| 401  | No autenticado · Token inválido |
| 403  | Sin permiso para editar bloqueos |
| 404  | Persona no encontrada · Bloqueo no encontrado |

---

### ⚠ TEST-ONLY: `debug_password` field + reset-password endpoint

For local QA the server temporarily stores the plaintext of every generated password in `service_members.debug_password` and exposes it both in the list response and via a force-reset endpoint. **Remove before going to production** — see `CONTEXT.md → "Para quitar antes de producción"` for the full checklist.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/tenant/{slug}/services/people/{sm_id}/reset-password` | TEST-ONLY. Force-regenerates a member's password, stores plaintext in `debug_password`, updates the bcrypt hash on `org_members.hashed_password`, and stamps `welcomed_at`. Returns `{ id, email, debug_password }`. Rejects (400) for `org_role == 'admin'`. |

The GET list response includes `debug_password` (may be `null` for entries created before the column existed or for org admins).

### Response

```json
{
  "id": "<service_member uuid>",
  "member_id": "<org_member uuid>",
  "full_name": "Jorge Perez", "email": "jorge@iglesia.com", "avatar": null,
  "org_role": "member",
  "service_role": "viewer",
  "songs_role": "viewer", "media_role": "viewer",
  "file_access": { "plans": true, "songs": true, "media": true },
  "type_permissions": [
    { "service_type_id": "<uuid>", "role": null }
  ],
  "welcomed_at": "2026-05-22T20:00:00+00:00",
  "password_set": true,
  "created_at": "2026-05-22T20:00:00+00:00",
  "temp_password": "Ab12CdEf34Gh"
}
```

### Errors

| Code | Detail |
|------|--------|
| 400  | Email inválido · Nombre requerido · service_role inválido · songs_role inválido · media_role inválido · Indica member_id o new_member |
| 401  | No autenticado · Token inválido · Miembro no encontrado |
| 403  | Sin acceso al módulo de Servicios · Solo administradores |
| 404  | Persona no encontrada · Org no encontrada |
| 409  | Esta persona ya pertenece a Servicios · Ese email ya existe en la organización |

### Sidebar / module access (impact on `/tenant/{slug}/auth/me`)

`GET /tenant/{slug}/auth/me` now returns two additional fields used by the
frontend to filter the module dropdown:

```json
{
  "...": "...existing fields...",
  "accessible_modules": ["servicios", "perfil"],
  "service_role": "viewer"
}
```

Resolution rules:
- Org admin / leader → all modules.
- Else if `service_members` row exists for this member → `["servicios","perfil"]` + `service_role` = the row's value.
- Else → `["perfil"]` only.
- Impersonation token → all modules + `service_role: administrator`.

The frontend redirects (`replace`) to the first accessible module when the URL targets one that is forbidden.

---

## Tenant · Teams

A Team groups org_members for service assignments (Adoración, Audio/Visual, Recibo, Desayunos, etc.). Linked to ServiceType via `service_teams` M2M, leaders via `team_leaders` M2M. Same auth/role rules as Services.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/tenant/{slug}/teams` | JWT or cookie | List teams + `member_count` + flags + `leader_member_ids[]` + `service_type_ids[]` |
| POST   | `/tenant/{slug}/teams` | admin/leader | Create team (auto-adds caller as leader if `leader_member_ids` omitted/empty) |
| PATCH  | `/tenant/{slug}/teams/{team_id}` | admin/leader | Update name/color/description/flags + settings (default_status, notify_on_prepare, replies_to, gap_alerts_enabled, last_scheduled_date_rule, scheduled_viewer_access, signup_sheets_auto_enable, reschedule_on_decline); **replaces** `leader_member_ids[]`, `service_type_ids[]`, `related_team_ids[]` when provided |
| DELETE | `/tenant/{slug}/teams/{team_id}` | admin/leader | Cascade-deletes memberships, leaders, service_teams links |
| POST   | `/tenant/{slug}/teams/{team_id}/leaders` | admin/leader | Add ONE leader. Body: `{ member_id }`. Idempotent. |
| DELETE | `/tenant/{slug}/teams/{team_id}/leaders/{member_id}` | admin/leader | Remove ONE leader. **409** if team would be left without leaders; the caller cannot self-remove when last. |
| GET    | `/tenant/{slug}/teams/{team_id}/members` | JWT or cookie | List memberships (joins `org_members` for name/email) |
| POST   | `/tenant/{slug}/teams/{team_id}/members` | admin/leader | Add a member to the team — body: `{ member_id, role? }` |
| DELETE | `/tenant/{slug}/teams/{team_id}/members/{member_id}` | admin/leader | Remove member from team |

### POST /tenant/{slug}/teams — Request body

```json
{
  "name": "Equipo de Adoración",
  "color": "#4F46E5",
  "description": "Cantantes, instrumentistas, dirección musical",
  "is_rehearsal": true,
  "is_secure": false,
  "is_split": false,
  "leader_member_ids": ["uuid-of-leader-1", "uuid-of-leader-2"],
  "service_type_ids": ["uuid-of-service-type"]
}
```

`leader_member_ids` and `service_type_ids` are optional. If `leader_member_ids` is missing or empty, the **caller is auto-added** as the first leader (matches PCO UX). Unknown IDs are silently dropped (same-org guard).

### Flags

| Flag | Meaning |
|------|---------|
| `is_rehearsal` | Equipo de ensayo. Acceso a canciones, partituras y media del servicio asignado. |
| `is_secure` | Equipo seguro. Sólo personas con verificación de antecedentes pueden ser asignadas. (Por ahora sólo se guarda el flag; la verificación real con un check-provider llega en Fase 3.) |
| `is_split` | Equipo dividido. Permite distintas personas por franja cuando hay varios servicios el mismo día. |

### Settings fields (PATCH)

Persistidos en BD hoy; comportamiento real llega con módulo Servicios completo
(ver `artifacts/SERVICES-INTEGRATION-NOTES.md`).

| Field | Type | Values | Phase |
|-------|------|--------|-------|
| `default_status` | str | `unconfirmed` · `confirmed` | Fase 3 |
| `notify_on_prepare` | bool | true / false | Fase 3 |
| `replies_to` | str | `all_leaders` · `service_type_leaders` · `no_one` | Fase 3 |
| `gap_alerts_enabled` | bool | true / false | Fase 3 |
| `last_scheduled_date_rule` | str | `same_as_service_type` · `last_used_anywhere` · `last_used_in_team` · `last_used_in_position` | Fase 3 |
| `scheduled_viewer_access` | str | `full_plan` · `limited` · `none` | Fase 3 |
| `signup_sheets_auto_enable` | bool | true / false | Fase 3 |
| `reschedule_on_decline` | str | `none` · `manual` · `volunteer` · `auto` · `signup_sheet` | Fase 3 |
| `related_team_ids[]` | str[] | UUIDs de equipos del mismo org (replace-all, no-self) | Hoy (UI activa) |

PATCH dropea silently: ids no-UUID, ids de otro org, y `team_id` propio en
`related_team_ids`. UNIQUE pair en `team_related` evita duplicados.

**`service_type_ids` mínimo 1.** Si el body envía `service_type_ids` y tras
filtrar UUIDs válidos del mismo org queda 0, devuelve `400 — "Selecciona al
menos un tipo de servicio."` Frontend bloquea el botón Guardar y deshabilita el
× del último chip restante.

**PATCH /services/people/{sm_id} acepta `is_active`** (bool, admin-only):
deshabilita o reactiva al `org_member` ligado. Una persona deshabilitada no
podrá hacer login ni recibir correos hasta ser reactivada. Self-disable
bloqueada (`400 — "No puedes deshabilitarte a ti mismo"`). Serialize de
Services incluye `is_active`.

**Admin · settings · seguridad — TTL del enlace de recuperación.** Nueva clave
`security.password_reset_ttl_minutes` (default `10`, clamp aplicado en runtime
a [1, 1440]). Endpoints `GET/POST /admin/settings/security` aceptan el campo
`password_reset_ttl_minutes` (int). `tenant_email._resolve_reset_ttl_minutes`
es la única fuente al construir `send_password_reset_email` → la duración del
botón "Restablece tu contraseña" se controla desde el panel admin.

### Response

```json
{
  "id": "uuid",
  "name": "Equipo de Adoración",
  "color": "#4F46E5",
  "description": "...",
  "member_count": 0,
  "is_rehearsal": true,
  "is_secure": false,
  "is_split": false,
  "default_status": "unconfirmed",          // unconfirmed | confirmed
  "notify_on_prepare": true,
  "replies_to": "all_leaders",              // all_leaders | service_type_leaders | no_one
  "gap_alerts_enabled": false,
  "last_scheduled_date_rule": "same_as_service_type", // same_as_service_type | last_used_anywhere | last_used_in_team | last_used_in_position
  "scheduled_viewer_access": "full_plan",   // full_plan | limited | none
  "signup_sheets_auto_enable": false,
  "reschedule_on_decline": "manual",        // none | manual | volunteer | auto | signup_sheet
  "leaders": [
    { "member_id": "uuid", "full_name": "Jibsan Rosa", "email": "jibsan@ccc.com" }
  ],
  "leader_member_ids": ["uuid"],
  "service_type_ids": ["uuid"],
  "related_team_ids": ["uuid", "uuid"]
}
```

### Errors

| Code | Detail |
|------|--------|
| 400  | Nombre requerido · member_id inválido |
| 401  | No autenticado · Token inválido · Miembro no encontrado |
| 403  | Solo administradores y líderes |
| 404  | Equipo no encontrado · Miembro no encontrado · Pertenencia no encontrada |
| 409  | Ya está en el equipo |

### Team detail + Positions (PCO-style)

Used by the team detail view in the tenant portal. Positions are named roles inside a team (Piano, Bajo, Guitarra Acústica…). Members are assigned to a position via `team_position_members`. The "all team members" view is the DISTINCT union across all position assignments.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/tenant/{slug}/teams/{team_id}/detail` | JWT or cookie | Full detail payload: `{ team, leaders, positions, all_members }`. Each person includes `preferences` (max_per_month/day from `service_members` if present, else null). |
| POST   | `/tenant/{slug}/teams/{team_id}/positions` | admin/leader | Create a position. Body: `{ name }`. 409 on duplicate name within the same team. |
| PATCH  | `/tenant/{slug}/teams/{team_id}/positions/{pos_id}` | admin/leader | Rename or reorder. Body: `{ name?, sort_order? }`. |
| DELETE | `/tenant/{slug}/teams/{team_id}/positions/{pos_id}` | admin/leader | Cascade-deletes all `team_position_members` for the position. |
| POST   | `/tenant/{slug}/teams/{team_id}/positions/{pos_id}/members` | admin/leader | Bulk-add. Body: `{ member_ids: [...] }`. Idempotent — already-present pairs go to `skipped`, unknown ids are dropped. **Auto-enrolls** any member_id without a `service_members` row (default viewer permissions; org admins skipped). Returns `{ added, skipped, newly_enrolled }`. |
| DELETE | `/tenant/{slug}/teams/{team_id}/positions/{pos_id}/members/{member_id}` | admin/leader | Remove a single person from a position. |

#### GET /tenant/{slug}/teams/{team_id}/detail — Response

```json
{
  "team": { "id": "...", "name": "Equipo de Adoración", "is_rehearsal": true, ... },
  "leaders": [
    { "member_id": "...", "full_name": "Jibsan Rosa", "email": "jibsan@ccc.com",
      "avatar": null, "preferences": { "max_per_month": null, "max_per_day": null } }
  ],
  "positions": [
    {
      "id": "...", "name": "Piano", "sort_order": 1, "member_count": 2,
      "members": [ { "member_id": "...", "full_name": "...", "email": "...", "avatar": null, "preferences": { ... } } ]
    }
  ],
  "all_members": [ /* DISTINCT union of all position members */ ]
}
```

#### POST /tenant/{slug}/teams/{team_id}/positions/{pos_id}/members — Request / Response

```json
// Request
{ "member_ids": ["uuid-1", "uuid-2", "uuid-3"] }

// Response
{
  "added":   ["uuid-1", "uuid-2"],
  "skipped": ["uuid-3"],          // uuid-3 was already in this position; unknown ids silently dropped
  "newly_enrolled": [              // members auto-enrolled into Services (no service_members row before)
    { "member_id": "uuid-2", "service_member_id": "sm-uuid", "full_name": "...", "email": "..." }
  ]
}
```

---

## Tenant · Email

**Template kinds:** `general` · `schedule` · `signup` · `welcome` · `password_reset` · `team_welcome`.
The `team_welcome` template is auto-seeded per org and used when a member already in Services is added to a new team. Variables: `{{ team.name }}`, `{{ team.recipient_positions }}` (HTML `<ul>` of the recipient's positions in that team), `{{ team.leaders }}` (HTML `<ul>` mailto-linked), `{{ team.positions }}` (HTML `<ul>` of all team positions), `{{ from.team_role }}` (Líder de equipo / Administrador).

**Permission gate for team-scoped sends:** `POST /messages` and `/messages/preview` accept an optional `team_id` in the body. When provided, the caller MUST be an `admin` of the org OR a leader of that team (`team_leaders` row) — otherwise HTTP 403. The endpoint then computes `team.recipient_positions` per-recipient (positions of that member inside the team) and exposes `sender_team_role` based on the caller.


Per-org templates + message log + send-rendered. SMTP is **not wired yet** — new sends are persisted with `status="queued"` so the future worker (worsyn-integrations) can flush them. The variable engine is documented at length in [`EMAIL-VARIABLES.md`](./EMAIL-VARIABLES.md).

### Templates

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/tenant/{slug}/email/templates?kind=…` | JWT or cookie | List per-org templates. Optional `kind` filter |
| POST   | `/tenant/{slug}/email/templates` | admin/leader/coordinator/svc-editor | Create template |
| PATCH  | `/tenant/{slug}/email/templates/{tpl_id}` | admin/leader/coordinator/svc-editor | Update fields |
| DELETE | `/tenant/{slug}/email/templates/{tpl_id}` | admin/leader/coordinator/svc-editor | Delete template |

`kind` ∈ `general | schedule | signup | welcome`.

#### POST body

```json
{
  "kind": "welcome",
  "name": "Bienvenida Equipo de Adoración",
  "subject": "¡Bienvenido(a) a {{ organization.name }}!",
  "body": "Hola {{ to.first_name }},\n\n…",
  "is_default": false
}
```

#### Response

```json
{
  "id": "uuid", "kind": "welcome", "name": "...",
  "subject": "...", "body": "...",
  "is_default": false,
  "created_at": "...", "updated_at": "..."
}
```

### Messages (sent + received log)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/tenant/{slug}/email/messages?direction=sent|received&limit=100` | admin/leader/coordinator/svc-editor | Org-wide log. Personal mailbox uses the per-person endpoint |
| GET    | `/tenant/{slug}/email/messages/{msg_id}` | sender / recipient / admin | Single message detail |
| POST   | `/tenant/{slug}/email/messages` | admin/leader/coordinator/svc-editor | "Send" — renders + stores one row per recipient (`status="queued"`) |
| POST   | `/tenant/{slug}/email/messages/preview` | admin/leader/coordinator/svc-editor | Render against a specific recipient WITHOUT sending |
| GET    | `/tenant/{slug}/services/people/{sm_id}/messages?direction=…` | self / admin / leader / svc-admin | Per-person mailbox (sent ∪ received) |

#### POST /messages — send

```json
{
  "recipient_member_ids": ["<org_member uuid>", "..."],
  "template_id": "<uuid or null>",
  "subject": "Hola {{ to.first_name }}",
  "body": "..."
}
```

- 1–50 recipient IDs (capped server-side). One `EmailMessage` row created per resolved recipient.
- `template_id` is optional metadata — the server doesn't auto-merge it; submit the resolved subject/body yourself (the compose UI does this).
- Subject + body run through the variable engine **per recipient** (`to.*` is freshly built each time).
- Status is `queued` until the SMTP worker (Phase 3) dispatches.

#### POST /messages/preview

```json
{ "recipient_member_id": "<uuid>", "subject": "...", "body": "..." }
```

Returns `{ "subject": "<rendered>", "body": "<rendered>", "context_keys_used": [] }`. Use this to power "Vista previa" in the compose UI.

#### Message row response

```json
{
  "id": "uuid",
  "direction": "sent",
  "status": "queued|sent|delivered|failed|received",
  "subject": "...",
  "body": "<rendered body>",
  "recipient_email": "maria@iglesia.com",
  "sender_email": "jibsan@iglesia.com",
  "recipient_member_id": "uuid|null",
  "sender_member_id": "uuid|null",
  "template_id": "uuid|null",
  "sent_at": "ISO|null",
  "created_at": "ISO",
  "error": null,
  "counterparty_name": "María García"
}
```

`counterparty_name`: the "other side" (recipient name for sent rows, sender name for received).

### Retention

`organizations.email_retention_months` (default `3`, max `12`) controls how long rows live in `email_messages`. The cleanup cron is **not wired yet** — see `CONTEXT.md → Para quitar antes de producción / TODOs` for the scheduled deletion task. Surfaced in org settings UI (Phase 3).

### Notification preference (per person)

`PATCH /tenant/{slug}/services/people/{sm_id}` accepts a self-editable `preferred_notif_app`:

```json
{ "preferred_notif_app": "servicios" }
```

Values: `servicios` (default — this module's portal + future mobile app) or `worsyn` (reserved for future Worsyn app; client should disable in UI for now). The GET response always exposes `preferred_notif_app`.

### Errors

| Code | Detail |
|------|--------|
| 400  | kind inválido · Nombre requerido · Nombre vacío · Asunto requerido · Cuerpo requerido · Debes indicar al menos un destinatario · Máximo 50 destinatarios por envío · recipient_member_ids contiene IDs inválidos · Plantilla no encontrada · preferred_notif_app inválido |
| 401  | No autenticado · Token inválido · Miembro no encontrado |
| 403  | Sin permiso · Sin permiso para enviar correos |
| 404  | Plantilla no encontrada · Mensaje no encontrado · Persona no encontrada · Destinatario no encontrado |

### Welcome flow + magic link (set-password)

When a tenant admin adds a new `service_person` with `send_welcome=true`, the backend:

1. Issues a fresh URL-safe token (32 bytes) → stored in `org_members.password_reset_token` with 7-day expiry
2. Auto-seeds the default Welcome template if the org has none (`kind=welcome`, `is_default=true`)
3. Renders the welcome template with `{{ to.welcome_url }}` = `{general.app_url}/set-password/{token}`
4. Queues an email_messages row + schedules SMTP dispatch (BackgroundTask)
5. The recipient clicks the link → frontend `/set-password/:token` page

Two public endpoints (no auth — the token IS the auth):

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/tenant/auth/reset-password/{token}` | Returns `{ email, full_name, org_name, org_slug, expires_at }` or 404 if invalid/used, 410 if expired |
| POST   | `/tenant/auth/reset-password/{token}` body `{ password }` | Sets the new password, marks token used. Returns `{ org_slug, email }` for the "Ir a Servicios" redirect |

Token rules:
- Minimum 8 characters server-side (`MIN_PASSWORD_LEN`)
- Rejects obvious commons: `password`, `12345678`, `contraseña`, `worsyn`
- Single-use: cleared on successful POST
- Reissuing welcome (via POST `/services/people/{sm_id}/welcome`) **rotates the token** — the previous one becomes invalid

When SMTP is **not** configured, the welcome falls back to the legacy temp-password path (returns `temp_password` ONCE in the response so the admin can share manually).

### Auto-mirror sent → received

When a sent message's recipient is an `org_member` of the same org, the SMTP dispatcher creates a mirror row with `direction='received'`, `status='received'`. The recipient sees it in their Worsyn "Recibidos" tab AND in their real email inbox.

### Delete message

| Method | Path | Description |
|--------|------|-------------|
| DELETE | `/tenant/{slug}/email/messages/{msg_id}` | Removes the Worsyn record ONLY. Does NOT touch the user's external inbox (Gmail/iCloud). Allowed: admin/leader/coord/svc-editor for any row · sender/recipient for their own |

### Variable engine

See [`EMAIL-VARIABLES.md`](./EMAIL-VARIABLES.md) for the full catalog. TL;DR:

- `{{ var }}` substitutes values; missing → empty string
- `{% if var %}…{% else %}…{% endif %}` for branching (no nesting in v1)
- Context buckets: `to.*` (recipient), `from.*` (sender, incl. `from.signature`), `organization.*`, `service.*` (plan context, empty for now)

---

## Tenant · Songs (stub — read-only, Phase 3)

Song library (lyrics, chords, metadata). Schema-stable, full CRUD pending.

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/tenant/{slug}/songs` | List songs ordered by title |

### Response

```json
[
  { "id": "uuid", "title": "Aleluya", "author": "Anónimo", "key": "G", "tempo": 84, "ccli": null, "tags": ["adoración"] }
]
```

### Planned (Phase 3)

`POST`, `PATCH`, `DELETE` for `/songs`; `GET /songs/{id}` returning full lyrics + chords (JSON), audio refs (`media_id`), and `arrangements[]`; bulk import via ChordPro.

---

## Tenant · Media (stub — read-only)

Media assets (image, video, audio, doc). Currently external `url`; upload pipeline + base64 path pending.

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/tenant/{slug}/media` | List media ordered by `uploaded_at DESC` |

### Response

```json
[
  { "id": "uuid", "name": "Portada Domingo", "kind": "image", "url": "https://...", "size_bytes": 124000, "mime": "image/jpeg", "uploaded_at": "..." }
]
```

`kind` ∈ `image | video | audio | doc`.

### Planned (Phase 3)

`POST` multipart upload (with S3 or local-disk backend), `DELETE`, signed download URLs, thumbnails.

---

## Tenant · Scores (stub — read-only)

Sheet music per instrument, optionally linked to a `song_id`.

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/tenant/{slug}/scores` | List scores ordered by title |

### Response

```json
[
  { "id": "uuid", "title": "Cuán Grande es Él (Piano)", "key": "C", "instrument": "piano", "file_url": "https://...", "song_id": "uuid" }
]
```

### Planned (Phase 3)

`POST`/`DELETE`, PDF upload, transpose helper endpoint, per-instrument filtering.

---

## Tenant · Events (stub — read-only)

One-off events (camps, retreats, conferences). Distinct from recurring `service_plans`.

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/tenant/{slug}/events` | List events ordered by `starts_at DESC NULLS LAST` |

### Response

```json
[
  { "id": "uuid", "name": "Retiro de Jóvenes", "location": "Sierra de Madrid",
    "starts_at": "2026-07-15T08:00:00+00:00", "ends_at": "2026-07-17T18:00:00+00:00",
    "description": "Tres días de comunión" }
]
```

### Planned (Phase 3)

CRUD, RSVP endpoint, registrations, cost tracking via Finance.

---

## Tenant · Rehearsals (stub — read-only)

Practice sessions, optionally linked to a `service_plan_id`.

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/tenant/{slug}/rehearsals` | List rehearsals ordered by `scheduled_at DESC NULLS LAST` |

### Response

```json
[
  { "id": "uuid", "location": "Sala principal", "notes": "Repasar coros",
    "scheduled_at": "2026-05-30T19:00:00+00:00", "service_plan_id": "uuid-or-null" }
]
```

### Planned (Phase 3)

CRUD + attendance + reminders.

---

## Tenant · Calendar (stub — unified read-only feed)

Composes events + rehearsals + service plans into one feed for calendar UIs. Does not own a table.

| Method | Path | Query | Description |
|--------|------|-------|-------------|
| GET    | `/tenant/{slug}/calendar` | `from`, `to` (ISO 8601 datetime, optional) | Unified feed |

### Response

Each item carries a `kind` discriminator:

```json
[
  { "kind": "event",   "id": "uuid", "title": "Retiro de Jóvenes", "starts_at": "...", "ends_at": "...", "location": "...", "description": "..." },
  { "kind": "rehearsal", "id": "uuid", "title": "Ensayo Equipo Alabanza", "scheduled_at": "...", "location": "...", "service_plan_id": "uuid" },
  { "kind": "plan",    "id": "uuid", "title": "Servicio Dominical 31 mayo", "scheduled_at": "...", "service_type_id": "uuid", "status": "draft" }
]
```

Mobile/desktop clients should sort and group client-side. Service occurrences from the `services` module are **not** included here — use `GET /tenant/{slug}/services/occurrences` for the recurring projection. Phase 3 will merge both feeds.

---

## Tenant · Finance (stub — read-only)

Income / expense ledger for the org. Stored as integer cents.

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/tenant/{slug}/finance/transactions` | List transactions ordered by `occurred_on DESC NULLS LAST` |
| GET    | `/tenant/{slug}/finance/summary` | Monthly aggregates (sum by `kind`) |

### Transactions response

```json
[
  { "id": "uuid", "amount_cents": 12500, "currency": "EUR",
    "kind": "tithe", "description": "Diezmo dominical",
    "category": "diezmos", "occurred_on": "2026-05-17" }
]
```

`kind` ∈ `income | expense | tithe | offering`.

### Summary response

```json
{ "totals_by_kind": { "tithe": 250000, "offering": 80000, "expense": 145000 }, "currency": "EUR" }
```

### Planned (Phase 3)

CRUD, monthly reports, CSV/PDF export, integration with payment gateways (Stripe / Bizum).

---

## Settings

### Email · SMTP (shared by all tenants)

The Worsyn platform admin (owner only) configures **one SMTP server** that every tenant uses when its members send emails from Services. Password is encrypted at rest with Fernet (key from env `WORSYN_SETTINGS_KEY`). Returned password is always masked (`••••••••`).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/admin/settings/email` | admin/owner (read) | Returns config (password masked) |
| POST   | `/admin/settings/email` | **owner only** | Save config. Password: empty → clear · `••••••••` → keep existing · anything else → encrypt and store |
| POST   | `/admin/settings/email/test` | admin/owner | Send a test email using saved config (or `override`) |

#### GET response

```json
{
  "enabled": true, "host": "smtp.gmail.com", "port": 587,
  "username": "notificaciones@worsyn.com", "password": "••••••••", "has_password": true,
  "use_tls": true, "use_ssl": false,
  "from_email": "notificaciones@worsyn.com", "from_name": "Worsyn",
  "provider": "gmail", "reply_to": "", "timeout": 20,
  "readonly": false
}
```

#### POST body

Same shape as GET (minus `has_password` / `readonly`). For `password`: send `"••••••••"` to keep the saved value, `""` to clear, or a new plaintext to replace+encrypt.

#### POST /test body

```json
{
  "to": "tu-cuenta@ejemplo.com",
  "override": { "host": "...", "port": 587, "username": "...", "password": "••••••••",
                "use_tls": true, "use_ssl": false, "from_email": "...", "from_name": "..." }
}
```

`override` is optional. With it the test uses form-state values without saving; without it the saved config is used. Returns `{ "status": "ok", "to": "..." }` or `502 { "detail": "Envío falló: <SMTP error>" }`.

#### Provider enum

`provider` ∈ `gmail | workspace | outlook | sendgrid | mailgun | custom`. Informational — the UI uses it to prefill `host`/`port`/`use_tls`.

#### Errors

| Code | Detail |
|------|--------|
| 400  | Provider inválido · Puerto inválido · No actives STARTTLS y SSL al mismo tiempo · Configuración SMTP incompleta · Email destino inválido |
| 403  | Solo el owner puede modificar |
| 502  | Envío falló: `<SMTP error>` |

### Tenant email dispatch (queued → sent/failed)

When a tenant member calls `POST /tenant/{slug}/email/messages`, the server:

1. Renders subject + body **per recipient**
2. Stores rows with `status="queued"`
3. Returns 201 with the created rows
4. Schedules `dispatch_queued()` as a **FastAPI BackgroundTask** — opens its own DB session, loads `SmtpConfig`, opens ONE SMTP connection per batch, iterates rows:
   - Success → `status='sent'`, `sent_at=<now>`, `error=null`
   - Failure → `status='failed'`, `error="<ExceptionType>: <msg>"`
5. If SMTP isn't configured/disabled → all rows marked `failed` with reason `"SMTP no configurado en el panel admin"`

**From / Reply-To convention** (matches Gmail/Workspace requirements):
- `From` = `"<org_name> vía <smtp.from_name>" <smtp.from_email>` (the SMTP-authenticated identity)
- `Reply-To` = sender member's email (replies route back to the actual person)
- `email.smtp.reply_to` overrides if you want all replies to a single mailbox

Worker (Phase 3): swap BackgroundTasks for a Redis queue + dedicated worker once volume exceeds ~1k/day.

See [`EMAIL-VARIABLES.md`](./EMAIL-VARIABLES.md) for the template variable catalog and the [`worsyn-smtp`](../../.claude/skills/worsyn-smtp/SKILL.md) agent skill for provider setup + debugging.

---

### GET /admin/settings/database
Get current database configuration.  
`readonly: true` is returned for `admin` role — they cannot write.

**Auth required:** admin, owner

**Response 200**
```json
{
  "engine": "postgresql",
  "host": "worsyn-db",
  "port": 5432,
  "database": "worsyn",
  "username": "worsyn",
  "ssl": false,
  "pool_min": 2,
  "pool_max": 10,
  "readonly": false
}
```

---

### POST /admin/settings/database
Update database configuration.

**Auth required:** owner only  
**Response 200** — updated config

---

### POST /admin/settings/database/test
Test a database connection with given config.

**Auth required:** admin, owner  
**Response 200** — `{ "status": "ok" }`

---

## Two user types

| Type | Table | Description |
|------|-------|-------------|
| `AdminUser` | `admin_users` | Worsyn platform operators — access to this panel |
| `OrgMember` | `org_members` | Members of a tenant church organization — no panel access |

---

## Role access matrix

| Role    | Auth | Organizations | Org Members | Admin Users | Settings (read) | Settings (write) | Health |
|---------|------|---------------|-------------|-------------|-----------------|------------------|--------|
| —       | ✅   | ❌            | ❌          | ❌          | ❌              | ❌               | ✅     |
| `user`  | ✅   | ✅ read       | ✅ read     | ❌          | ❌              | ❌               | ✅     |
| `admin` | ✅   | ✅ write      | ✅ write    | ✅ (no owners) | ✅           | ❌               | ✅     |
| `owner` | ✅   | ✅ write+del  | ✅ write    | ✅ (all)    | ✅              | ✅               | ✅     |

---

## System

### GET /health
Check API + database connectivity.

**Auth required:** No

**Response 200**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "db": "ok"
}
```

---

## Auth

### POST /auth/login
Authenticate with username and password. Returns JWT tokens.

**Auth required:** No  
**Content-Type:** `application/x-www-form-urlencoded`

**Form fields**

| Field      | Type   | Required |
|------------|--------|----------|
| `username` | string | ✅       |
| `password` | string | ✅       |

**Response 200**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "must_change_password": true,
  "role": "owner"
}
```

> If `must_change_password` is `true`, the client **must** redirect to the credential change flow before allowing any other action.

**Errors**

| Code | Detail |
|------|--------|
| 401  | Invalid credentials |
| 403  | Account disabled |

---

### GET /auth/me
Return the currently authenticated user.

**Auth required:** Yes (any role)

**Response 200**
```json
{
  "id": "uuid",
  "username": "admin",
  "email": "admin@worsyn.local",
  "full_name": "Worsyn Owner",
  "role": "owner",
  "is_active": true,
  "must_change_password": false,
  "two_factor_enabled": false,
  "avatar": null,
  "created_at": "2026-05-11T13:16:03.583827+00:00",
  "last_login_at": "2026-05-11T13:16:11.246295+00:00"
}
```

**Errors**

| Code | Detail |
|------|--------|
| 401  | Missing or invalid token |

---

### POST /auth/change-credentials
Change username and/or password. Required on first login (`must_change_password: true`).

**Auth required:** Yes (any role)

**Request body**
```json
{
  "current_password": "worsyn",
  "new_username": "admin",
  "new_password": "SecureP@ss123"
}
```

| Field              | Type   | Required | Rules |
|--------------------|--------|----------|-------|
| `current_password` | string | ✅       | Must match current password |
| `new_username`     | string | ❌       | Min 3 chars, no spaces, must be unique |
| `new_password`     | string | ❌       | Min 8 chars |

> At least one of `new_username` or `new_password` must be provided.

**Response 200**
```json
{
  "status": "ok",
  "username": "admin"
}
```

**Errors**

| Code | Detail |
|------|--------|
| 400  | Current password incorrect |
| 400  | new_username or new_password required |
| 400  | Username min 3 chars / Password min 8 chars |
| 409  | Username already taken |

---

## Admin User Management

All endpoints require role `admin` or `owner`.  
**Rule:** An `admin` can never delete or modify users with role `owner`.  
**Rule:** An `admin` cannot create users with role `owner`.  
**Rule:** An `admin` cannot promote a user to role `owner`.

---

### GET /admin/users
List all platform users.

**Auth required:** admin, owner

**Response 200** — array of `AdminUserRead`
```json
[
  {
    "id": "uuid",
    "username": "operator1",
    "email": "op1@worsyn.local",
    "full_name": "Operator One",
    "role": "admin",
    "is_active": true,
    "must_change_password": true,
    "avatar": null,
    "created_at": "2026-05-11T14:00:00+00:00",
    "last_login_at": null
  }
]
```

---

### POST /admin/users
Create a new platform user. New users always start with `must_change_password: true`.

**Auth required:** admin, owner

**Request body**
```json
{
  "username": "operator1",
  "email": "op1@worsyn.local",
  "password": "InitialP@ss1",
  "full_name": "Operator One",
  "role": "admin"
}
```

| Field       | Type   | Required | Rules |
|-------------|--------|----------|-------|
| `username`  | string | ✅       | Unique, no spaces, lowercased |
| `email`     | string | ✅       | Valid email, unique |
| `password`  | string | ✅       | Min 8 chars |
| `full_name` | string | ❌       | — |
| `role`      | string | ❌       | `user` \| `admin` \| `owner`. Admin cannot create `owner` |

**Response 201** — `AdminUserRead`

**Errors**

| Code | Detail |
|------|--------|
| 403  | Admins cannot create owner accounts |
| 409  | Username already taken |
| 409  | Email already registered |

---

### GET /admin/users/{user_id}
Get a single platform user by ID.

**Auth required:** admin, owner

**Path param:** `user_id` (UUID)

**Response 200** — `AdminUserRead`

**Errors**

| Code | Detail |
|------|--------|
| 404  | User not found |

---

### PUT /admin/users/{user_id}
Update a platform user. Partial updates supported (all fields optional).  
Setting a new `password` automatically sets `must_change_password: true`.

**Auth required:** admin, owner

**Path param:** `user_id` (UUID)

**Request body** (all fields optional)
```json
{
  "username": "newname",
  "email": "new@worsyn.local",
  "full_name": "New Name",
  "role": "user",
  "is_active": false,
  "password": "NewP@ss123"
}
```

**Response 200** — `AdminUserRead`

**Errors**

| Code | Detail |
|------|--------|
| 403  | Admins cannot modify owner accounts |
| 403  | Admins cannot assign the owner role |
| 404  | User not found |
| 409  | Username / Email already taken |

---

### DELETE /admin/users/{user_id}
Delete a platform user permanently.

**Auth required:** admin, owner

**Path param:** `user_id` (UUID)

**Response 204** — No content

**Errors**

| Code | Detail |
|------|--------|
| 400  | Cannot delete your own account |
| 403  | Admins cannot delete owner accounts |
| 404  | User not found |

---

## Settings

### GET /admin/settings/database
Return the current database configuration (password masked).

**Auth required:** admin, owner

**Response 200**
```json
{
  "engine": "postgresql",
  "host": "db",
  "port": 5432,
  "name": "worsyn",
  "user": "worsyn_admin",
  "password": "***",
  "ssl": true,
  "readonly": false
}
```

> `readonly: true` when the requesting user has role `admin` (cannot save changes).

---

### POST /admin/settings/database
Persist the database configuration.

**Auth required:** owner only

**Request body**
```json
{
  "engine": "postgresql",
  "host": "db",
  "port": 5432,
  "name": "worsyn",
  "user": "worsyn_admin",
  "password": "secret"
}
```

| Field      | Type    | Required | Rules |
|------------|---------|----------|-------|
| `engine`   | string  | ✅       | `postgresql` \| `mysql` \| `mariadb` |
| `host`     | string  | ✅       | — |
| `port`     | integer | ✅       | — |
| `name`     | string  | ✅       | Database name |
| `user`     | string  | ✅       | — |
| `password` | string  | ✅       | — |

**Response 200**
```json
{
  "status": "saved",
  "engine": "postgresql"
}
```

**Errors**

| Code | Detail |
|------|--------|
| 403  | Insufficient permissions (admin trying to write) |
| 422  | Unsupported engine |

---

### POST /admin/settings/database/test
Test a database connection without saving the configuration.

**Auth required:** admin, owner

**Request body** — same as `POST /admin/settings/database`

**Response 200**
```json
{
  "status": "ok",
  "latency_ms": 12
}
```

---

### GET /admin/settings/general
Return general platform config.

**Auth required:** Yes — `admin` or `owner` (read) · `owner` only (write)

**Response 200**
```json
{
  "platform_name": "Worsyn",
  "support_email": "soporte@worsyn.com",
  "timezone": "Europe/Madrid",
  "maintenance_mode": false,
  "maintenance_message": "El sistema está en mantenimiento. Vuelve pronto.",
  "readonly": false
}
```

---

### POST /admin/settings/general
Persist general config. Owner only. Keys stored under `general.*` in `system_settings`.

**Auth required:** Yes — `owner`

**Request body**
```json
{
  "platform_name": "Worsyn",
  "support_email": "soporte@worsyn.com",
  "timezone": "Europe/Madrid",
  "maintenance_mode": false,
  "maintenance_message": "El sistema está en mantenimiento."
}
```

**Response 200** `{ "status": "saved" }`

---

### GET /admin/settings/security
Return current security config.

**Auth required:** Yes — `admin` or `owner`

**Response 200**
```json
{
  "password_min_length": 8,
  "password_require_uppercase": false,
  "password_require_numbers": false,
  "password_require_special": false,
  "password_max_age_days": 0,
  "session_access_token_minutes": 30,
  "session_refresh_token_days": 7,
  "max_sessions_per_user": 0,
  "two_factor_enabled": false,
  "readonly": false
}
```
`readonly: true` when caller is `admin` (not `owner`).

---

### POST /admin/settings/security
Persist security config to `system_settings` table.

**Auth required:** Yes — `owner` only

**Request body**
```json
{
  "password_min_length": 10,
  "password_require_uppercase": true,
  "password_require_numbers": true,
  "password_require_special": false,
  "password_max_age_days": 90,
  "session_access_token_minutes": 60,
  "session_refresh_token_days": 14,
  "max_sessions_per_user": 3,
  "two_factor_enabled": false
}
```

**Response 200**
```json
{ "status": "saved" }
```

Settings stored as `security.*` keys in `system_settings` (e.g. `security.password_min_length`).

---

## Organizations

All organization endpoints require authentication. Write operations (create/update/delete) require `admin` or `owner`.

### GET /organizations/
List all organizations (paginated). Includes `member_count`.

**Auth required:** any role  
**Query params:** `skip` (default 0), `limit` (default 50)

**Response 200** — array of `OrganizationRead`
```json
[
  {
    "id": "uuid",
    "name": "Iglesia Vida Nueva",
    "slug": "vida-nueva",
    "plan": "pro",
    "status": "active",
    "country": "Colombia",
    "city": "Bogotá",
    "phone": "+57 1 234 5678",
    "website": "https://vidanueva.com",
    "created_at": "2026-05-11T00:00:00+00:00",
    "updated_at": "2026-05-11T00:00:00+00:00",
    "member_count": 12
  }
]
```

---

### GET /organizations/count
Return total number of organizations.

**Auth required:** any role

**Response 200**
```json
{ "count": 42 }
```

---

### GET /organizations/{org_id}
Get a single organization by ID.

**Auth required:** any role

**Response 200** — `OrganizationRead`  
**Errors:** 404 Organization not found

---

### POST /organizations/
Create a new organization.

**Auth required:** admin, owner

**Request body**
```json
{
  "name": "Iglesia Vida Nueva",
  "slug": "vida-nueva",
  "plan": "free",
  "status": "active",
  "country": "Colombia",
  "city": "Bogotá",
  "phone": "+57 1 234 5678",
  "website": "https://vidanueva.com"
}
```

| Field     | Type   | Required | Values |
|-----------|--------|----------|--------|
| `name`    | string | ✅       | — |
| `slug`    | string | ✅       | Unique, URL-safe |
| `plan`    | string | ❌       | `free` \| `pro` \| `teams` |
| `status`  | string | ❌       | `active` \| `trial` \| `suspended` \| `cancelled` |
| `country` | string | ❌       | — |
| `city`    | string | ❌       | — |
| `phone`   | string | ❌       | — |
| `website` | string | ❌       | — |

**Response 201** — `OrganizationRead`  
**Errors:** 409 Slug already in use

---

### PATCH /organizations/{org_id}
Partially update an organization.

**Auth required:** admin, owner  
**Request body** — all fields optional (same as create, excluding `slug`)

**Response 200** — `OrganizationRead`  
**Errors:** 404

---

### DELETE /organizations/{org_id}
Delete an organization and all its members (cascade).

**Auth required:** owner only

**Response 204** — No content  
**Errors:** 404

---

## Org Members

Members of a tenant organization. Completely separate from `AdminUser`.  
All endpoints are nested under `/organizations/{org_id}/members`.

### GET /organizations/{org_id}/members
List all members of an organization.

**Auth required:** any role  
**Query params:** `skip` (default 0), `limit` (default 100)

**Response 200** — array of `OrgMemberRead`
```json
[
  {
    "id": "uuid",
    "org_id": "uuid",
    "email": "pastor@vidanueva.com",
    "full_name": "Carlos García",
    "phone": "+57 310 000 0000",
    "role": "owner",
    "is_active": true,
    "joined_at": "2026-05-11T00:00:00+00:00",
    "updated_at": "2026-05-11T00:00:00+00:00"
  }
]
```

**Errors:** 404 Organization not found

---

### POST /organizations/{org_id}/members
Add a new member to an organization. Email must be unique within the org.

**Auth required:** admin, owner

**Request body**
```json
{
  "email": "pastor@vidanueva.com",
  "password": "SecureP@ss",
  "full_name": "Carlos García",
  "phone": "+57 310 000 0000",
  "role": "member"
}
```

| Field       | Type   | Required | Rules |
|-------------|--------|----------|-------|
| `email`     | string | ✅       | Unique within org |
| `password`  | string | ✅       | Min 8 chars |
| `full_name` | string | ❌       | — |
| `phone`     | string | ❌       | — |
| `role`      | string | ❌       | `owner` \| `admin` \| `member` \| `viewer` |

**Response 201** — `OrgMemberRead`  
**Errors:** 404 Org not found, 409 Email already in org

---

### GET /organizations/{org_id}/members/{member_id}
Get a single org member.

**Auth required:** any role

**Response 200** — `OrgMemberRead`  
**Errors:** 404

---

### PUT /organizations/{org_id}/members/{member_id}
Update an org member (partial). Setting `password` is supported.

**Auth required:** admin, owner

**Request body** (all optional)
```json
{
  "email": "new@vidanueva.com",
  "full_name": "Carlos García Ruiz",
  "phone": "+57 310 111 2222",
  "role": "admin",
  "is_active": true,
  "password": "NewP@ss123"
}
```

**Response 200** — `OrgMemberRead`  
**Errors:** 404, 409 Email already in use

---

### DELETE /organizations/{org_id}/members/{member_id}
Remove a member from an organization.

**Auth required:** admin, owner

**Response 204** — No content  
**Errors:** 404

---

## Audit Logs

### GET /admin/logs
Return audit logs in reverse chronological order.

**Auth required:** owner

**Query params:** `page` (0-based, default 0), `limit` (1-200, default 50), `action` (exact match), `resource_type` (exact match), `actor_username` (ilike)

**Response 200** — `list[AuditLogRead]`
```json
[{
  "id": "uuid",
  "actor_id": "uuid | null",
  "actor_username": "string",
  "action": "auth.login | user.create | org.delete | tenant.start | ...",
  "resource_type": "session | user | org | tenant | settings",
  "resource_id": "string | null",
  "resource_name": "string | null",
  "details": "JSON string | null",
  "created_at": "ISO 8601"
}]
```

### GET /admin/logs/count
Return total audit log count.

**Auth required:** owner

**Response 200** `{"total": 1234}`

---

## Data models

### AdminUserRead
```json
{
  "id": "uuid",
  "username": "string",
  "email": "string",
  "full_name": "string | null",
  "role": "user | admin | owner",
  "is_active": true,
  "must_change_password": false,
  "created_at": "ISO 8601",
  "last_login_at": "ISO 8601 | null"
}
```

### HealthResponse
```json
{
  "status": "ok",
  "version": "0.1.0",
  "db": "ok | error"
}
```

---

*Last updated: 2026-05-20 — endpoints: health, auth (incl. TOTP 2FA), organizations (CRUD), org_members (CRUD), org_roles (CRUD), admin/users (CRUD + avatar + 2FA reset), admin/settings/database, admin/settings/general, admin/settings/security (incl. SSO scaffold), admin/logs (audit trail)*
