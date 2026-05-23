# Worsyn — Stack técnico y decisiones de arquitectura

## Infraestructura actual

| Servicio    | Imagen Docker              | Puerto | Nombre contenedor  |
|-------------|----------------------------|--------|--------------------||
| Frontend    | worsyn-dashboard-frontend  | 80     | worsyn-dashboard   |
| Backend     | worsyn-backend-backend     | 8000   | worsyn-backend     |
| PostgreSQL  | postgres:16-alpine         | 5432   | worsyn-db          |
| Redis       | redis:7-alpine             | 6379   | worsyn-redis       |
| Tenant DB * | postgres:16-alpine         | 6001+  | worsyn-tenant-{slug}-db |

\* Un contenedor PostgreSQL independiente por organización, gestionado dinámicamente.

- **Servidor:** 10.211.55.11 · hostname `worsyn-server` (root), Debian/Ubuntu, Docker 29.4.2
- **Compose file backend:** `/mnt/worsyn-backend/docker-compose.yml`
- **Frontend source:** `/mnt/worsyn-dashboard/`
- **Backend source:** `/mnt/worsyn-backend/`
- **Artefactos / docs:** `/mnt/worsyn-backend/artifacts/`
- **Tenants:** `/mnt/tenants/{slug}/` (docker-compose.yml + data/)

### Levantar el sistema completo (un solo comando)
```bash
cd /mnt/worsyn-backend && docker compose up -d && docker start worsyn-dashboard 2>/dev/null; docker network connect worsyn-backend_worsyn worsyn-dashboard 2>/dev/null; docker exec worsyn-dashboard nginx -s reload 2>/dev/null; docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

**Qué hace:**
1. Levanta DB + Redis + backend (docker compose)
2. Arranca nginx si estaba caído
3. Conecta nginx a la red del backend (idempotente)
4. Recarga nginx (para que resuelva `worsyn-backend`)
5. Muestra estado de todos los contenedores

> La IP del servidor puede cambiar (NAT/bridged). El proxy nginx usa el nombre de contenedor `worsyn-backend` en la red Docker interna — la IP del host no importa.

### Deploy del frontend (sin rebuild desde Docker Hub)
```bash
# Compilar
docker run --rm -v /mnt/worsyn-dashboard:/app -w /app node:20-alpine sh -c "npm run build"
# Desplegar (limpio)
docker exec worsyn-dashboard sh -c "rm -rf /usr/share/nginx/html/*"
docker cp /mnt/worsyn-dashboard/dist/. worsyn-dashboard:/usr/share/nginx/html/
```
> Docker Hub no tiene acceso a internet desde este servidor. Los builds usan el contenedor node:20-alpine local.

### Proxy nginx
El contenedor nginx (`worsyn-dashboard`) proxea `/api/` → `http://worsyn-backend:8000/api/` (nombre de contenedor Docker, no IP).  
Usa `resolver 127.0.0.11 valid=30s` para resolución DNS en tiempo de petición (no al inicio).  
Ambos contenedores deben estar en la red `worsyn-backend_worsyn`.  
El archivo fuente es `/mnt/worsyn-dashboard/nginx.conf`.

---

## Frontend

| Tecnología       | Versión | Uso actual |
|------------------|---------|------------|
| React            | 18      | SPA, componentes |
| TypeScript       | 5       | Tipado estricto |
| Vite             | 5       | Build + HMR |
| React Router DOM | 6       | Routing SPA |
| CSS custom       | —       | Sistema de diseño propio (Adminator-inspired) |

### Estructura de carpetas relevante
```
src/
├── context/
│   └── AuthContext.tsx       # Sesión: user, token, setSession, clearSession, hasRole
├── components/
│   ├── ProtectedRoute.tsx    # Guard: redirige a /login si no autenticado
│   ├── RoleRoute.tsx         # Guard: redirige a / si rol insuficiente
│   ├── Toast.tsx             # Notificaciones toast
│   └── Layout/
│       ├── Layout.tsx        # Shell principal + banner must_change_password
│       ├── Navbar.tsx        # Topbar: breadcrumb, tema, dropdown avatar
│       └── Sidebar.tsx       # Navegación lateral condicional por rol
├── pages/
│   ├── Login.tsx             # Página pública de login
│   ├── Profile.tsx           # Perfil + cambio de contraseña (solo desde dropdown)
│   ├── Dashboard.tsx
│   ├── Organizations.tsx     # Lista orgs (datos reales) + modal crear org
│   ├── OrganizationDetail.tsx# Detalle org + gestión tenant Docker
│   ├── Users.tsx             # org_members (fase 2)
│   ├── SystemUsers.tsx       # CRUD admin_users — solo admin/owner
│   ├── System.tsx            # Métricas host en tiempo real (psutil + Docker)
│   ├── Settings.tsx          # Config BD — owner edita, admin solo lectura
│   ├── SettingsSecurity.tsx
│   ├── SettingsGeneral.tsx
│   ├── SettingsEmail.tsx
│   └── SettingsIntegrations.tsx
└── App.tsx                   # Rutas: /login público, resto ProtectedRoute/RoleRoute
```

### Rutas y permisos
| Ruta                       | Guard                         | Rol mínimo |
|----------------------------|-------------------------------|------------|
| `/login`                   | Pública                       | —          |
| `/`                        | ProtectedRoute                | any        |
| `/organizations`           | ProtectedRoute                | any        |
| `/organizations/:id`       | ProtectedRoute                | any (tenant: admin+) |
| `/users`                   | ProtectedRoute                | any        |
| `/billing`                 | ProtectedRoute                | any        |
| `/profile`                 | ProtectedRoute                | any        |
| `/system`                  | ProtectedRoute                | any (sidebar solo admin+) |
| `/system-users`            | ProtectedRoute + RoleRoute    | admin, owner |
| `/settings/*`              | ProtectedRoute + RoleRoute    | admin, owner |

---

## Backend

| Tecnología        | Versión | Notas |
|-------------------|---------|-------|
| Python            | 3.11    | |
| FastAPI           | 0.115   | Async, OpenAPI auto |
| SQLAlchemy        | 2.0     | Async ORM |
| asyncpg           | —       | Driver PostgreSQL async |
| python-jose       | —       | JWT (HS256) |
| passlib + bcrypt  | 1.7.4 + **4.0.1** | bcrypt 5.x es incompatible con passlib 1.7.4 |
| Pydantic          | v2      | Schemas, validación |
| Alembic           | —       | Migraciones (configurado, no en uso activo aún) |

### Modelos de base de datos
### Tenant module tables (Fase 1 — vacías, scaffolded)

Cada módulo de tenant es independiente: tabla(s) propias + endpoint en fichero separado.
Para mantenimiento, comentar `include_router()` en `app/api/v1/router.py`.

```
service_types        — plantilla de servicio (Servicio Dominical, Campamentos…)
  id, org_id (FK→organizations CASCADE), name, color, sort_order,
  recurrence (none|random|daily|weekly|weekdays|biweekly|monthly  default 'weekly'),
  description (TEXT nullable), created_at, updated_at
service_times        — franjas horarias de un service_type (puede haber varias)
  id, org_id (FK CASCADE), service_type_id (FK→service_types CASCADE),
  starts_on (DATE), start_time (TIME), end_time (TIME), sort_order, created_at
  Notas: starts_on es la primera ocurrencia; weekday se deriva (date.weekday()).
service_teams        — M2M service_type ↔ team (qué equipos sirven)
  id, service_type_id (FK CASCADE), team_id (FK→teams CASCADE), sort_order, created_at
service_members      — permisos del módulo Servicios por miembro
  id, org_id (FK CASCADE), member_id (FK→org_members CASCADE, UNIQUE),
  service_role  (administrator|editor|coordinator|viewer|scheduled_viewer),
  songs_role    (administrator|editor|viewer|scheduled_viewer  nullable),
  media_role    (administrator|editor|viewer|scheduled_viewer  nullable),
  file_access_plans BOOL, file_access_songs BOOL, file_access_media BOOL,
  scheduling_max_per_month INT NULL (NULL = sin límite, 1..31),
  scheduling_max_per_day   INT NULL (NULL = sin límite, 1..31),
  welcomed_at (ts nullable), password_set_at (ts nullable),
  created_at, updated_at
service_member_type_perms — override por tipo de servicio (Same-as-parent)
  id, service_member_id (FK CASCADE), service_type_id (FK CASCADE),
  role (str nullable — NULL = heredar)
service_member_blockouts — periodos de indisponibilidad por persona
  id, org_id (FK CASCADE), service_member_id (FK CASCADE),
  start_date (DATE), end_date (DATE), all_day BOOL,
  repeat_kind (none|day|week|month|year), repeat_interval INT 1..12,
  repeat_until (DATE nullable — NULL = siempre),
  reason (TEXT nullable), created_at, updated_at
  Proyección de recurrencia: cliente (frontend) calcula próximas ocurrencias
service_plans        — instancia concreta (un domingo específico, etc.)
  id, org_id (FK CASCADE), service_type_id (FK→service_types SET NULL),
  title, scheduled_at, status (draft|published|completed), notes
songs                — biblioteca de canciones
  id, org_id, title, author, song_key, tempo, ccli, lyrics, chords (JSON), tags (JSON)
media_assets         — multimedia (imagen/vídeo/audio/doc)
  id, org_id, name, kind, url, size_bytes, mime, uploaded_at
teams                — equipos de voluntarios (Adoración, Audio/Visual, Recibo…)
  id, org_id (FK CASCADE), name, color, description, created_at, updated_at
team_memberships     — pertenencia equipo↔org_member (m:n)
  id, team_id (FK CASCADE), member_id (FK→org_members CASCADE), role
scores               — partituras (por instrumento)
  id, org_id, song_id, title, score_key, instrument, file_url
events               — eventos puntuales (campamentos, retiros)
  id, org_id, name, starts_at, ends_at, location, description
rehearsals           — ensayos (opcional link a service_plan)
  id, org_id, service_plan_id, scheduled_at, location, notes
finance_transactions — diezmos, ofrendas, gastos
  id, org_id, amount_cents, currency, kind, description, category, occurred_on
```

#### Recurrence + occurrence projection

`service_types.recurrence` + `service_times` rows act as a *template*. The endpoint
`GET /tenant/{slug}/services/occurrences?range_from&range_to` projects the
template forward (today → today+90d by default) and returns concrete
`{date, start_time, end_time, service_type_id, color}` rows ordered by
`(date, start_time)`. The frontend MiniCalendar uses this for day-dots; the
Calendario Maestro modal uses it for the month-grid view.

Projection rules:
- `none` / `random` → single anchor date (no repetition)
- `daily` → +1 day forever
- `weekly` → +7 days
- `biweekly` → +14 days
- `weekdays` → Mon–Fri only
- `monthly` → same day-of-month, clamped to last day if shorter (e.g. Jan 31 → Feb 28)

### Tablas principales

```
organizations    — tenants (iglesias cliente)
  id, name, slug, plan, status, country, city, phone, website, created_at

tenants          — tenant Docker por organización (one-to-one con organizations)
  org_id (PK+FK), status, db_port, db_password, container_name,
  compose_dir, provisioned_at, error_msg, updated_at

organizations    — tenants (iglesias cliente)
  id, name, slug, plan, status, country, city, phone, website, email, alias,
  ministries (JSONB []), member_roles (JSONB []), icon (TEXT base64), require_2fa_admins,
  created_at, updated_at

org_members      — usuarios de cada iglesia (no tienen acceso al panel)
  id, org_id, email, hashed_password (nullable), full_name, phone, role, is_active,
  joined_at, updated_at,
  prefix, gender, birthdate, anniversary, ministry, org_roles (JSONB []),
  avatar (TEXT nullable — base64 data URL, max ~3 MB)

member_attachments — ficheros adjuntos a org_members (base64 en DB)
  id, org_id (FK→organizations CASCADE), member_id (FK→org_members CASCADE),
  label (VARCHAR 255 — nombre legible), original_name, mime_type, size_bytes,
  file_data (TEXT base64 — max 10 MB decoded), uploaded_at
  Upload/download/preview restringido a role admin o leader en la org.

system_users     — operadores del panel Worsyn (antes: admin_users)
  id, username, email, hashed_password, full_name, role,
  is_active, must_change_password, two_factor_enabled,
  avatar (TEXT nullable — base64 data URL, max ~450 KB),
  created_at, last_login_at

system_settings  — configuración clave-valor del sistema
  id, key, value, updated_at
```

### Seguridad
- Contraseñas: bcrypt con 12 rounds, truncado explícito a 72 bytes (`plain[:72]`)
- JWT access token: 30 min · Refresh token: 7 días
- Cookies httpOnly: `worsyn_access` (admin, 30min) · `worsyn_refresh` (admin, 7d) · `tenant_access` (tenant, 7d, impersonation: 1h)
- Auth acepta `Authorization: Bearer <token>` O cookie httpOnly (header tiene prioridad)
- Logout: `POST /auth/logout` (admin) · `POST /tenant/{slug}/auth/logout` (tenant) → borra cookies
- `require_role(*roles)` dependency factory para guards por rol
- 401 en cualquier endpoint → frontend limpia sesión y redirige a `/login`

### Login unificado de tenants
- **URL única `/portal`** para todos los tenants — no hay login por organización
- `POST /tenant/auth/login` (email+password) → valida contra todas las orgs activas
  - 1 org coincide → frontend llama `/tenant/auth/select` → entra al portal
  - 2+ orgs coinciden → picker visual → user elige → `/tenant/auth/select` → portal
- `partial_token` (10 min, JWT type `org_select`) encierra la lista de slugs autorizados
- `/portal/:slug` sin cookie válida → redirige a `/portal`
- Email único por org: índice `UNIQUE(org_id, email)` en `org_members`
- **Impersonation**: `POST /organizations/{id}/impersonate` (admin+) → cookie `tenant_access` con flag `impersonating: true` → admin entra al portal con rol sintético `admin` para soporte. Auditado como `org.impersonate`

### Seed automático
Al arrancar, si `system_users` está vacío, se crea:
```
username: worsyn  |  password: worsyn  |  role: owner  |  must_change_password: true
```

---

## Base de datos

- **PostgreSQL 16** en contenedor `worsyn-db`
- Credenciales: user `worsyn`, pass `worsyn`, db `worsyn`
- Puerto: 5432

```bash
# Acceso directo
docker exec -it worsyn-db psql -U worsyn -d worsyn

# Query sin entrar
docker exec worsyn-db psql -U worsyn -d worsyn -c "SELECT username, role FROM system_users;"
```

---

## Infraestructura de producción (fase 2)

```
Internet → CloudFront → ALB
                          ├── ECS Fargate: frontend (nginx)
                          └── ECS Fargate: backend (FastAPI)
                                    ├── RDS PostgreSQL Multi-AZ
                                    └── ElastiCache Redis
```

**Costes AWS estimados**

| Etapa       | Clientes | Coste/mes |
|-------------|----------|-----------|
| MVP (fase 0) | 0–10    | ~$40–$55  |
| Producción  | 10–50    | ~$80–$95  |
| Escala      | 50–200   | ~$200–$250 |

---

## Convenciones

- Idioma del código: **inglés** (variables, funciones, comentarios)
- Idioma del UI: **español**
- Commits: `feat:`, `fix:`, `chore:`, `docs:`
- Ramas: `main` (producción), `develop` (integración), `feature/nombre`
- Emails: campo `str` con validación `"@" in v` (no `EmailStr`) — permite `.local` TLD
