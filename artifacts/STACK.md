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

### Deploy del frontend (sin rebuilkit)
```bash
# Compilar
docker run --rm -v /mnt/worsyn-dashboard:/app -w /app node:20-alpine sh -c "npm run build"
# Desplegar (limpio)
docker exec worsyn-dashboard sh -c "rm -rf /usr/share/nginx/html/*"
docker cp /mnt/worsyn-dashboard/dist/. worsyn-dashboard:/usr/share/nginx/html/
```
> Docker Hub no tiene acceso a internet desde este servidor. Los builds usan `DOCKER_BUILDKIT=0` o el enfoque de compilar dentro del contenedor node local.

### Proxy nginx
El contenedor nginx (`worsyn-dashboard`) proxea `/api/` → `http://10.211.55.11:8000/api/`.
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
```
organizations    — tenants (iglesias cliente)
  id, name, slug, plan, status, country, city, phone, website, created_at

tenants          — tenant Docker por organización (one-to-one con organizations)
  org_id (PK+FK), status, db_port, db_password, container_name,
  compose_dir, provisioned_at, error_msg, updated_at

org_members      — usuarios de cada iglesia (no tienen acceso al panel)
  id, org_id, email, full_name, role, is_active, created_at

system_users     — operadores del panel Worsyn (antes: admin_users)
  id, username, email, hashed_password, full_name, role,
  is_active, must_change_password, created_at, last_login_at

system_settings  — configuración clave-valor del sistema
  id, key, value, updated_at
```

### Seguridad
- Contraseñas: bcrypt con 12 rounds, truncado explícito a 72 bytes (`plain[:72]`)
- JWT access token: 30 min · Refresh token: 7 días
- `require_role(*roles)` dependency factory para guards por rol
- 401 en cualquier endpoint → frontend limpia sesión y redirige a `/login`

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
