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

> If `must_change_password` is `true`, the frontend shows a red banner: *"Debes cambiar tu contraseña. Ve a Perfil › Seguridad."*

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

## Org Members

All org member endpoints are nested under `/organizations/{org_id}/members`.  
Email is unique **within** an organization, not globally.

### GET /organizations/{org_id}/members
List all members of an organization.

**Auth required:** any role

**Response 200**
```json
[
  {
    "id": "uuid",
    "org_id": "uuid",
    "email": "pastor@church.com",
    "full_name": "John Pastor",
    "role": "owner",
    "is_active": true,
    "created_at": "2026-05-11T00:00:00+00:00"
  }
]
```

---

### POST /organizations/{org_id}/members
Create a new org member.

**Auth required:** admin, owner

**Request body**
```json
{
  "email": "member@church.com",
  "full_name": "Jane Member",
  "role": "member"
}
```

**Response 201** — `OrgMemberRead`

**Errors**

| Code | Detail |
|------|--------|
| 404  | Organization not found |
| 409  | Email already registered in this organization |

---

### GET /organizations/{org_id}/members/{member_id}
Get a single org member.

**Auth required:** any role  
**Response 200** — `OrgMemberRead`

---

### PUT /organizations/{org_id}/members/{member_id}
Update an org member.

**Auth required:** admin, owner  
**Response 200** — `OrgMemberRead`

---

### DELETE /organizations/{org_id}/members/{member_id}
Delete an org member.

**Auth required:** admin, owner  
**Response 204** — No content

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

*Last updated: 2026-05-11 — endpoints: health, auth (login/me/change-credentials), organizations (CRUD + member_count), org_members (CRUD nested), admin/users (CRUD), admin/settings/database*
