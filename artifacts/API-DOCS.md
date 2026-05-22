# Worsyn API Documentation

**Base URL:** `http://<host>:8000/api/v1`  
**Auth:** Bearer JWT (`Authorization: Bearer <access_token>`)  
**Content-Type:** `application/json` (except `/auth/login` → `application/x-www-form-urlencoded`)

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

A Team groups org_members for service assignments (Adoración, Audio/Visual, Recibo, Desayunos, etc.). Linked to ServiceType via `service_teams` M2M. Same auth/role rules as Services.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/tenant/{slug}/teams` | JWT or cookie | List teams + `member_count` |
| POST   | `/tenant/{slug}/teams` | admin/leader | Create team |
| PATCH  | `/tenant/{slug}/teams/{team_id}` | admin/leader | Update team (name, color, description) |
| DELETE | `/tenant/{slug}/teams/{team_id}` | admin/leader | Cascade-deletes memberships + service_teams links |
| GET    | `/tenant/{slug}/teams/{team_id}/members` | JWT or cookie | List memberships (joins `org_members` for name/email) |
| POST   | `/tenant/{slug}/teams/{team_id}/members` | admin/leader | Add a member to the team — body: `{ member_id, role? }` |
| DELETE | `/tenant/{slug}/teams/{team_id}/members/{member_id}` | admin/leader | Remove member from team |

### POST /tenant/{slug}/teams — Request body

```json
{
  "name": "Equipo de Adoración",
  "color": "#4F46E5",
  "description": "Cantantes, instrumentistas, dirección musical"
}
```

### Response

```json
{
  "id": "uuid",
  "name": "Equipo de Adoración",
  "color": "#4F46E5",
  "description": "...",
  "member_count": 0
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

---

## Settings

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
