# Worsyn — Contexto del sistema

## Qué es Worsyn

SaaS B2B para gestión de organizaciones religiosas (iglesias). Permite planificar
servicios de adoración, gestionar voluntarios, editar canciones en formato ChordPro
y coordinar equipos. El operador (nosotros) gestiona la plataforma desde este dashboard.

## Empresa

- **Nombre:** Worsyn
- **Modelo:** SaaS multi-tenant (Free / Pro $12/mes / Teams $29/mes)
- **Mercado primario:** Iglesias hispanohablantes (España, México, Colombia, Argentina)
- **Idioma:** Español nativo

## Competencia directa

| Plataforma           | Precio base | Usuarios | Editor ChordPro | Español |
|----------------------|-------------|----------|-----------------|---------|
| WorshipTools Pro     | $15/mes     | 30 máx   | Solo importa    | No      |
| Planning Center      | $14/mes     | Ilimitados | No             | No      |
| **Worsyn Pro**        | **$12/mes** | **Ilimitados** | **Nativo** | **Sí** |

## Módulos del producto (para el cliente-iglesia)

1. **Service Planner** — Crear/gestionar servicios de adoración
2. **ChordPro Editor** — Crear, editar y transponer canciones
3. **Volunteer Manager** — Asignar equipo a roles
4. **Availability** — Voluntarios marcan fechas bloqueadas
5. **Reports** — Historial, estadísticas por persona/rol
6. **Multi-campus** (plan Teams) — Varias sedes comparten repositorio

## Este dashboard (Worsyn Admin)

Panel **interno** del operador de la plataforma para:
- Ver todas las organizaciones (iglesias) clientes
- Monitorizar suscripciones, pagos y MRR
- Ver usuarios activos y métricas del sistema
- Detectar problemas y gestionar el ciclo de vida de cada organización

## Roles del sistema (system_users)

| Rol      | Sección Principal | Sección Sistema | Configuración (ver) | Configuración (editar) | Gestión system_users |
|----------|-------------------|-----------------|---------------------|------------------------|----------------------|
| **user** | ✅                | ❌              | ❌                  | ❌                     | ❌                   |
| **admin**| ✅                | ✅              | ✅ (solo lectura)   | ❌                     | ✅ (no puede tocar owners) |
| **owner**| ✅                | ✅              | ✅                  | ✅                     | ✅ (control total)   |

### Lo que ve cada rol en el sidebar

**Rol `user`:**
```
Principal
  Dashboard · Organizaciones · Usuarios · Facturación
```

**Rol `admin` y `owner`:**
```
Principal
  Dashboard · Organizaciones · Usuarios · Facturación
  Sistema · Usuarios del Sistema

Sistema
  Configuración → Base de datos / General / Seguridad / Correo SMTP / Integraciones
```

### Regla crítica de protección de owners
Un usuario `admin` **nunca** puede eliminar ni cambiar el rol de un `owner`. Solo otro `owner` puede modificar o eliminar una cuenta con rol `owner`. Esto garantiza que la jerarquía de control nunca quede expuesta a personal operativo.

### Auto-degradación de rol
Si un `admin` se edita a sí mismo y se asigna el rol `user`, la sesión activa se actualiza **inmediatamente** (sin logout) y el sidebar se re-renderiza mostrando solo la sección Principal. El badge del avatar también cambia en tiempo real.

## Dos tipos de usuarios completamente separados

| Tipo | Modelo | Tabla | Propósito |
|------|--------|-------|-----------|
| **AdminUser** | `AdminUser` | `system_users` | Operadores del panel Worsyn (nosotros) |
| **OrgMember** | `OrgMember` | `org_members` | Miembros de las iglesias cliente |

- **AdminUser** — Tiene acceso al panel de administración. Roles: `user`, `admin`, `owner`
- **OrgMember** — Pertenece a una organización concreta (campo `org_id`). Roles dentro de la org: `owner`, `admin`, `member`, `viewer`. **No tiene acceso al panel Worsyn**

### Visibilidad en el frontend
- La pestaña **Usuarios del Sistema** (ruta `/system-users`) muestra los `system_users` y es visible **solo para admin y owner**
- La pestaña **Usuarios** (ruta `/users`) mostrará los `org_members` (miembros de las iglesias cliente)

## Autenticación y sesión

- Login: `POST /api/v1/auth/login` → JWT access token (30 min) + refresh token (7 días)
- Token almacenado en `localStorage` con clave `worsyn-token`
- Usuario almacenado en `localStorage` con clave `worsyn-user`
- Si el servidor devuelve 401, la sesión se limpia automáticamente y redirige a `/login`
- `AuthContext` expone: `user`, `token`, `isLoading`, `setSession`, `clearSession`, `hasRole`

## Flujo de primer login / must_change_password

Al desplegarse por primera vez, se crea automáticamente un usuario **owner** por defecto:
- Username: `worsyn` · Password: `worsyn` · `must_change_password: true`

Cuando `must_change_password: true`:
1. Se muestra un **banner rojo** en la parte superior del contenido: *"Debes cambiar tu contraseña antes de continuar. Ve a **Perfil › Seguridad**."*
2. El usuario va al Perfil (icono de avatar → Perfil) y cambia la contraseña
3. Al guardar, `must_change_password` pasa a `false` y el banner desaparece sin reload

## Página de Perfil

- Acceso: **solo desde el dropdown del avatar** (arriba derecha) → opción "Perfil"
- Ruta: `/profile` — protegida, no aparece en el sidebar
- Muestra: datos de la cuenta (usuario, nombre, email, rol) + formulario de cambio de contraseña
- El cambio de contraseña llama a `POST /api/v1/auth/change-credentials`
- Disponible para todos los roles (`user`, `admin`, `owner`)

## Dropdown del avatar (navbar)

```
[Nombre completo o username]
[rol]
────────────────
👤 Perfil
────────────────
🚪 Cerrar sesión
```

## Estado actual del proyecto

| Capa        | Estado              | Tecnología                    |
|-------------|---------------------|-------------------------------|
| Frontend    | ✅ Operativo        | React 18 + Vite 5 + TypeScript 5 |
| Backend     | ✅ Operativo        | FastAPI + SQLAlchemy 2.0 + asyncpg |
| Base de datos | ✅ Operativo      | PostgreSQL 16 (Docker)        |
| Cache/Queue | ✅ Desplegado       | Redis 7 (Docker)              |
| Auth        | ✅ Completo         | JWT (python-jose) + bcrypt 4  |
| Infra local | ✅ Docker Compose   | Docker 29.4.2                 |
| Infra prod  | ⏳ Pendiente (fase 2) | AWS ECS Fargate             |

## Funcionalidades implementadas

- [x] Login page con redirección automática si no autenticado
- [x] ProtectedRoute (guard por autenticación)
- [x] RoleRoute (guard por rol — redirige a `/` si no autorizado)
- [x] Logout desde el dropdown del avatar
- [x] Sidebar con secciones condicionales por rol
- [x] Alerta `must_change_password` en el Layout
- [x] Página Perfil con cambio de contraseña
- [x] CRUD completo de `system_users` con permisos por rol
- [x] Auto-refresco de sesión al editarse a sí mismo
- [x] Configuración BD: solo lectura para admin, editable para owner
- [x] Toast notifications
- [x] Tema claro/oscuro (localStorage)
