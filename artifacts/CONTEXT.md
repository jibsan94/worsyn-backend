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

**Rol `admin`:**
```
Principal
  Dashboard · Organizaciones · Usuarios · Facturación
  Sistema · Usuarios del Sistema

Sistema
  Configuración → Base de datos / General / Seguridad / Correo SMTP / Integraciones
```

**Rol `owner`** (todo lo de admin más):
```
Principal
  ...
  Logs del Sistema   ← owner only
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
- Muestra: datos de la cuenta (usuario, nombre, email, rol) + formulario de cambio de contraseña + upload de foto de perfil
- El cambio de contraseña llama a `POST /api/v1/auth/change-credentials`
- El avatar se guarda via `PUT /api/v1/admin/users/{id}/avatar` (base64 JPEG, max ~450 KB)
- Avatar visible en el navbar (esquina superior derecha); si no tiene foto, se muestran iniciales
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
| Tenants     | ✅ Implementado     | Docker por org (postgres:16-alpine) |
| Infra local | ✅ Docker Compose   | Docker 29.4.2 · hostname worsyn-server |
| Infra prod  | ⏳ Pendiente (fase 2) | AWS ECS Fargate             |

## Funcionalidades implementadas

- [x] Login page con redirección automática si no autenticado
- [x] ProtectedRoute (guard por autenticación)
- [x] RoleRoute (guard por rol — redirige a `/` si no autorizado)
- [x] Logout desde el dropdown del avatar
- [x] Sidebar con secciones condicionales por rol
- [x] Alerta `must_change_password` en el Layout
- [x] Página Perfil con cambio de contraseña y upload de foto de perfil (base64, resize automático a 256×256)
- [x] CRUD completo de `system_users` con permisos por rol
- [x] Auto-refresco de sesión al editarse a sí mismo
- [x] Configuración BD: solo lectura para admin, editable para owner
- [x] Toast notifications
- [x] Tema claro/oscuro (localStorage)
- [x] Métricas del sistema en tiempo real (CPU, RAM, disco, uptime, hostname, servicios)
- [x] Organizaciones: datos reales de BD, modal de creación, vista de detalle
- [x] Campo `email` en organizaciones (para comunicaciones del sistema con la org)
- [x] Campo `alias` en organizaciones (identificador corto para acceso futuro del tenant)
- [x] Eliminar organización desde la lista (con confirmación inline por fila)
- [x] Crear usuario administrador inicial al crear una organización (sección colapsable en modal)
- [x] Tenant por organización: aprovisionamiento automático de PostgreSQL en Docker
- [x] Gestión de tenant desde detalle de org: start/stop/sincronizar/destruir/reaprovisionar
- [x] Botón "Ver portal" en detalle de org → abre `/portal/:slug` en nueva pestaña
- [x] TenantPortal (`/portal/:slug`): ruta pública, muestra login de org + dashboard simulado
- [x] Vista global de usuarios (miembros de org) en `/users` con filtros y KPIs
- [x] Vista detalle de miembro en `/users/:id` — editable para admin/owner
- [x] Rol de OrgMember: `admin`, `leader`, `member` — gestionables desde Configuración
- [x] Tabla `org_roles`: define roles disponibles para org members, con CRUD en `/settings/roles`
- [x] Configuración General: nombre plataforma, correo soporte, zona horaria, modo mantenimiento — `GET/POST /api/v1/admin/settings/general`, keys `general.*`
- [x] Configuración de Seguridad: políticas de contraseñas, sesiones, política 2FA global — `GET/POST /api/v1/admin/settings/security`, keys `security.*`
- [x] SSO / Active Directory: configuración scaffolding en Seguridad — keys `security.sso_*`, sin integración LDAP activa aún
- [x] Campo `two_factor_enabled` en `system_users` — cada usuario gestiona su propio 2FA
- [x] Vista detalle de usuario del sistema (`/system-users/:id`) — editar campos, restablecer contraseña, toggle/reset 2FA
- [x] Owner puede desactivar el 2FA de otro usuario (`DELETE /api/v1/admin/users/{id}/2fa`)
- [x] Filas de SystemUsers clickeables → navegan a detalle del usuario
- [x] 2FA TOTP completo: `GET /auth/2fa/setup` (QR base64) → `POST /auth/2fa/enable` → `POST /auth/2fa/disable`
- [x] Login con 2FA: flujo dos pasos — partial_token (5 min, type "2fa_pending") → `POST /auth/2fa/complete` → tokens completos
- [x] Perfil: sección 2FA con QR, código manual, activar/desactivar con confirmación TOTP
- [x] SystemUserDetail: propia sección → link a Mi Perfil (no toggle simple)
- [x] AuthUser en contexto incluye `two_factor_enabled: boolean`
- [x] Logs del sistema: `AuditLog` model + `app/services/audit.py` + `GET/GET-count /admin/logs` (owner only)
- [x] Audit logging integrado en: login, 2FA, change-credentials, user CRUD, org CRUD, tenant lifecycle, settings save
- [x] Frontend: `/logs` (owner only) con tabla, filtros por acción/recurso/actor, paginación, tags de color
- [x] **Módulo Servicios (tenant)** — `service_types` extendido con `recurrence` (none|random|daily|weekly|weekdays|biweekly|monthly) + `description`; nuevas tablas `service_times` (franjas horarias) y `service_teams` (M2M con `teams`)
- [x] Wizard de creación de servicio en 3 pasos: (1) nombre + recurrencia + color · (2) horarios — fecha (default próximo domingo) + hora inicio/fin, multi-fila · (3) equipos participantes (multi-select)
- [x] Endpoints `POST/PATCH/DELETE /tenant/{slug}/services/types` con nested `times[]` + `team_ids[]` (replace-on-PATCH). Guard `admin/leader`
- [x] Endpoint `GET /tenant/{slug}/services/occurrences?range_from&range_to` — proyecta `service_times` hacia adelante (90 días por defecto) según recurrence. Devuelve `[{date, start_time, end_time, service_type_id, service_type_name, color}]`
- [x] MiniCalendar (sidebar) con punto de color por día con ocurrencia. Navegación entre meses con ‹ • ›
- [x] **Calendario Maestro** — modal full-screen con grid mensual + panel lateral por día seleccionado, eventos con color del service_type
- [x] Equipos (`/tenant/{slug}/teams`): CRUD completo + memberships (`/teams/{id}/members` POST/DELETE). Listado incluye `member_count`
- [x] Pestaña **Personas → Equipos** en módulo Servicios: alta/edición/baja de equipos con color y descripción
- [x] Endpoint `POST /tenant/{slug}/services/plans` para crear plan one-off (instancia concreta de un service_type)
- [x] Documentación API: nuevas secciones `Tenant · Services` y `Tenant · Teams` en `API-DOCS.md` (preparado para Fase 3/4 — apps móvil + desktop)
- [x] **Servicios → Personas (permisos a nivel módulo)** — nuevas tablas `service_members` + `service_member_type_perms` con roles dedicados (`administrator | editor | coordinator | viewer | scheduled_viewer`)
- [x] Auto-provisioning: cualquier org_member con `org_role='admin'` aparece automáticamente como `administrator` en Servicios (idempotente, en cada GET)
- [x] Wizard de alta de persona en 3 pasos: (1) elegir miembro existente o crear nuevo · (2) permisos (rol global + override por tipo + canciones/media + acceso a ficheros) · (3) bienvenida con contraseña temporal
- [x] Bienvenida: `POST /tenant/{slug}/services/people/{id}/welcome` genera contraseña temporal (12 chars) y marca `welcomed_at`. La contraseña se muestra UNA VEZ en pantalla (SMTP pendiente — worsyn-integrations)
- [x] Filtro de sidebar por permisos: `GET /tenant/{slug}/auth/me` devuelve `accessible_modules` + `service_role`. Miembros sin rol de org pero con entrada en `service_members` solo ven Servicios + Perfil. Frontend redirige automáticamente fuera de módulos prohibidos
- [x] Editor no puede añadir ni eliminar personas — solo Administrador (a nivel servicio) o admin/leader de org pueden gestionar la lista
- [x] Per-service-type permission overrides ("Mismo que arriba" / rol específico) via `service_member_type_perms`
- [x] **Vista de detalle de persona** (Servicios → Personas → clic en fila): cabecera con avatar + nombre + email + rol + acciones; tabs **Programación · Comunicación · Detalles**
- [x] **Bloqueos de indisponibilidad** — tabla `service_member_blockouts` + endpoints CRUD bajo `/services/people/{sm_id}/blockouts`. Soporta rango de fechas + recurrencia (`Cada N día/semana/mes/año`, `siempre` o `hasta fecha`) + motivo opcional
- [x] Modal de bloqueo con calendario mensual (clic = inicio; segundo clic = fin del rango), formulario de repetición traducido al español ("Cada", "Cada dos"…) y switch siempre/hasta fecha
- [x] Programación: secciones **Calendario** (bloqueos), **Preferencias** (stub), **Equipos asignados** (stub)
- [x] Comunicación (stub): Mensajes (Recibidos/Enviados) · Contraseña (reset email — SMTP pendiente) · Notificaciones (App preferida) · Firma
- [x] Detalles (stub): Etiquetas · Notas · Archivos (drag&drop) · Carpeta actual · Actividad (último acceso + creación)
- [x] Permisos de edición de bloqueos: admin/leader/coordinator OR la persona sobre sí misma (self-edit)
- [x] **Mobile/Desktop integration guide** completa en `API-DOCS.md` §1–§10 (auth Bearer para apps nativas, conventions JSON, errores, índice de endpoints con estado Stable/Stub)
- [x] Documentación de stubs read-only (songs, media, scores, events, rehearsals, calendar, finance) — list endpoints + payload + planned Phase-3 work
- [x] Tenant portal **responsive** (≤900 px tablet / ≤640 px móvil) — `<style>` global inyectado en `TenantPortal.tsx` con queries que apuntan a `data-tp="..."` (topbar, sidebar, main, content, table-wrap, detail-header/grid, tab-strip, modales). Login card + person detail + tablas y calendarios reaccionan sin refactor de estilos inline
- [x] App nativa (Fase 3/4): autenticación 100% Bearer (`POST /tenant/auth/login` → `partial_token` → `POST /tenant/auth/select` → `access_token`). Módulos visibles se piden a `/auth/me` (no se decodifica el JWT)
- [x] **Preferencias de agendado**: `service_members.scheduling_max_per_month` + `scheduling_max_per_day` (INT nullable, NULL = sin límite). UI editable en PersonDetail → Programación → Preferencias (dropdowns "Sin límite" / "Hasta N"). Consumido por el generador de cuadrantes en Fase 3
- [x] **Equipos por persona**: endpoint `GET /tenant/{slug}/services/people/{sm_id}/teams` (join `team_memberships` + `teams`). UI en PersonDetail → Programación → Equipos con picker (selecciona equipo + rol opcional) y botón × para quitar. Alta/baja vía endpoints existentes `/teams/{id}/members`
- [x] **BlockoutModal mejoras**: botón "Hoy" (vuelve al mes actual + selecciona hoy) y resaltado del día actual (borde + fondo azul claro)
- [x] **Firma de email por persona** — `service_members.signature_text` (TEXT ≤16 000 chars) + `signature_image` (data URL base64, máx 1 MB decoded). Auto-editable por el propio usuario (resto de campos siguen requiriendo admin). UI en Comunicación → Firma con textarea + upload (preview + reemplazar/quitar), validación cliente (`size`/`mime`) + servidor (regex data URL + `b64decode` size). Lista para inyectarse al pie de los correos cuando SMTP esté wired (Fase 3)
- [x] **Sistema de Email completo** — nuevas tablas `email_templates` (4 kinds: general/schedule/signup/welcome) y `email_messages` (log sent/received). Engine de variables propio (`app/services/email_render.py`) con sintaxis `{{var}}` + `{% if %}{% endif %}` (no nested). Catálogo completo de variables en `artifacts/EMAIL-VARIABLES.md` (= documentación oficial Worsyn)
- [x] **Endpoints email**: `/tenant/{slug}/email/templates` CRUD, `/tenant/{slug}/email/messages` GET/POST (send-render-queue), `/preview` (render sin enviar), `/services/people/{sm_id}/messages` (buzón personal sent ∪ received). Permisos: send = admin/leader/coordinator/svc-editor; templates igual
- [x] **Notificaciones (per-persona)**: `service_members.preferred_notif_app` (default `servicios`, opción `worsyn` deshabilitada). Self-editable. Preparado para Fase 3 (push notifications móvil)
- [x] **Retención de email**: `organizations.email_retention_months` (default 3, max 12 — surfaced in UI de settings de org en Fase 3). Cron de limpieza pendiente (TODO worsyn-integrations)
- [x] **UI Comunicación completa**: Mensajes (tabs Recibidos/Enviados con click→ver, badge En cola/Fallido) · Notificaciones dropdown · Contraseña (stub) · Firma (stub real) · Botón "+ Nuevo" abre Compose
- [x] **Compose modal**: selector de plantilla + To: + Asunto + Cuerpo con VariablePicker en ambos campos + botón Vista previa (render server-side) + Enviar (queues sin SMTP)
- [x] **Templates manager**: 4 tabs (General/Programación/Hojas inscripción/Bienvenida) con CRUD inline, editor con VariablePicker
- [x] **Compatibilidad Planning Center**: `{{ to.max_plan_permissions_s }}` y `{{ from.signature }}` funcionan igual que en PCO; plantillas exportadas de PCO funcionan sin cambios
- [x] **SMTP a nivel plataforma (Worsyn Admin)** — `system_settings` con claves `email.smtp.*`, contraseña cifrada con **Fernet** (env `WORSYN_SETTINGS_KEY`). Owner-only para escritura, admin+owner para lectura/test
- [x] Endpoints admin: `GET/POST /api/v1/admin/settings/email` + `POST /admin/settings/email/test` (con `override` opcional para iterar sin guardar)
- [x] Servicio `app/services/smtp.py` con `SmtpConfig`, `send_one()` y `dispatch_queued()` (BG task). Soporta STARTTLS (587) e SSL implícito (465), texto plano fallback + HTML alt, From dual (org + worsyn) y Reply-To al miembro tenant
- [x] Envío real wired: `POST /tenant/{slug}/email/messages` ahora agenda `BackgroundTask(dispatch_queued, ids)` después de crear filas — status `queued` → `sent` / `failed` con `error` cuando aplica
- [x] UI admin `SettingsEmail.tsx` rediseñada: selector de proveedor (Gmail / Workspace / Outlook / SendGrid / Mailgun / Custom) con presets de host/puerto, formulario completo (host, puerto, usuario, contraseña cifrada con máscara `••••••••`, STARTTLS/SSL, from + reply-to), botón "Probar envío" usando valores del form (no guardados)
- [x] Skill `worsyn-smtp` (`.claude/skills/worsyn-smtp/SKILL.md`) — especialista en configuración por proveedor, diagnóstico de errores SMTP, rotación de clave Fernet, deliverability (SPF/DKIM/DMARC) y mejoras pendientes (worker dedicado, retry con backoff, OAuth2 XOAUTH2)
- [x] **Auto-mirror sent → received** — cuando `dispatch_queued` confirma envío y el `recipient_member_id` existe, crea fila espejo `direction='received'` para que el destinatario lo vea en su pestaña "Recibidos" del portal Worsyn (además de en su inbox Gmail/iCloud)
- [x] **DELETE `/tenant/{slug}/email/messages/{id}`** — elimina solo el registro Worsyn (no toca inbox externo). Permisos: admin/leader/coordinator/svc-editor para cualquier fila; sender/recipient para las suyas
- [x] **Welcome flow real con magic link** — `service_members.send_welcome=true` ahora dispara `send_welcome_email` que: (1) emite token `secrets.token_urlsafe(32)` con TTL 7 días → `org_members.password_reset_token` + `password_reset_expires_at` (2) auto-seed default Welcome template (3) renderiza con `{{ to.welcome_url }}` = `{general.app_url}/set-password/{token}` (4) envía vía SMTP (BG task). Fallback a temp_password si SMTP no configurado
- [x] **Endpoints públicos `/tenant/auth/reset-password/{token}`** (GET info + POST set new pwd). Token single-use, min 8 chars, rechaza contraseñas obvias
- [x] **Página pública `/set-password/:token`** (React, fuera del auth shell) con avatar Worsyn, info de la org, doble input + strength meter, botón "Ir a Servicios →" que navega a `/portal/:slug`
- [x] **`general.app_url`** setting — base URL del frontend usado para construir magic links (default `http://10.211.55.11`, owner ajusta a dominio público en producción)
- [x] **Password reset por email** (Comunicación → Contraseña → "Enviar email de restablecimiento") — nuevo `kind=password_reset` en `email_templates` auto-seed, TTL **10 minutos** (vs 7 días del welcome), endpoint `POST /tenant/{slug}/services/people/{sm_id}/password-reset` (admin/leader/coord/svc-editor)
- [x] Helper genérico `_send_magic_link_email(kind, ttl, ...)` en `tenant_email.py` — comparte la lógica entre welcome y password_reset (token rotation + render con fail-fast + SMTP queue). Wrappers thin: `send_welcome_email` y `send_password_reset_email`
- [x] Variables nuevas para plantillas reset: `{{ to.welcome_ttl_minutes }}` (= 10) además de `{{ to.welcome_ttl_days }}`. Mismo `{{ to.welcome_url }}` reutilizado
- [x] **Resumen de programación por persona** (Programación → nueva sección "Resumen de programación") — donut SVG con conteo de **Confirmados / Sin responder / Rechazados** + tabla de planes en el rango. Selector de rango: Próximos · Último mes · Últimos 3/6/12 meses · Personalizado (start+end date)
- [x] DB: nueva tabla `plan_assignments` (org/plan/member/team/position/status/requested_by/responded_at/decline_reason) — productor futuro: cuadrante de Fase 3
- [x] Endpoints CRUD `/tenant/{slug}/services/people/{sm_id}/assignments` — GET con `range_from/range_to` (ISO date) devuelve `{ range, summary, items }`. POST/PATCH/DELETE para admin/coord; PATCH self-edit del status (auto-stamps `responded_at`)

## Roles de OrgMember

| Rol | Slug | Descripción | Tipo |
|-----|------|-------------|------|
| Administrador de Organización | `admin` | Gestión completa dentro de la org | Sistema |
| Líder | `leader` | Líder de equipo o área (alabanza, jóvenes, etc.) | Sistema |
| Miembro | `member` | Miembro activo de la organización | Sistema |

Los roles están almacenados en la tabla `org_roles`. Los roles de sistema (`is_system=true`) no se pueden eliminar pero sí editar su nombre/descripción/orden. Se pueden crear roles personalizados adicionales desde **Configuración → Roles de org**.

El campo `org_members.role` almacena el slug del rol (`admin`, `leader`, `member`, o cualquier slug personalizado creado).

## Portal de organizaciones (`/portal/:slug`)

Ruta pública (sin autenticación de admin) accesible desde el botón "Ver portal" en el detalle de cada organización.

**Flujo actual (mock):**
1. La URL `/portal/{slug}` carga el componente `TenantPortal`
2. Hace `GET /api/v1/organizations/slug/{slug}` (endpoint público, sin auth) → obtiene nombre y alias
3. Muestra formulario de login con email + contraseña
4. Al "iniciar sesión" (simulado), entra al app shell con navegación completa

**App shell del tenant:**
- Top bar con logo W + module switcher dropdown (Planning Center-style) + user avatar
- Módulos: Principal, Servicios, Personas, Equipos, Partituras, Eventos, Ensayos, Calendario, Finanzas
- Opciones de la cuenta al pie del dropdown
- Vista por defecto: Personas — sidebar con filtros (Todas/Por ministerio/Nuevos) + tabla de personas con avatar, ministerio, rol, contacto, estado
- Resto de módulos: placeholder "Próximamente"
- Todo inline styles (sin contaminar CSS del panel admin)

**Flujo futuro (pendiente de implementar):**
1. El miembro entra a `/portal/{slug}` o `/portal/{alias}`
2. El sistema identifica la organización por slug o alias
3. Se autentica con su email + contraseña contra `POST /api/v1/tenant/{slug}/auth/login`
4. Recibe un JWT de miembro (`OrgMember`) — sistema de auth separado del admin
5. Accede al panel de gestión de su iglesia

> **Nota:** El sistema de auth para `OrgMember` es completamente independiente del auth de `AdminUser`.
> Los miembros nunca tendrán acceso al panel de administración Worsyn.

## Campos de organización

| Campo | Tipo | Propósito |
|-------|------|-----------|
| `name` | str | Nombre completo de la iglesia |
| `slug` | str (único) | Identificador técnico, nombre del contenedor Docker |
| `alias` | str (único, nullable) | Alias corto para que los miembros accedan al portal (ej: `bethel` → `/portal/bethel`) |
| `email` | str (nullable) | Email de la organización para comunicaciones del sistema (avisos, facturas, alertas) |
| `plan` | free/pro/teams | Plan de suscripción |
| `status` | active/trial/suspended/cancelled | Estado de la suscripción |
| `country` / `city` | str | Ubicación |
| `phone` / `website` | str | Datos de contacto |

---

## ⚠ Para quitar antes de producción (test-only)

Funcionalidades temporales para QA local. **ELIMINAR cuando el usuario dé la orden.**

### 1. Campo `service_members.debug_password` (plaintext)

- **Tabla**: `service_members.debug_password TEXT NULL`
- **Por qué**: durante el desarrollo necesitamos ver la contraseña de cada `service_member` para entrar manualmente al portal y comprobar permisos.
- **Cómo se rellena**: cualquier endpoint que genere una contraseña temporal (POST `/services/people` con `send_welcome:true`, POST `/services/people/{id}/welcome`, POST `/services/people/{id}/reset-password`) escribe el plaintext aquí además del hash en `org_members.hashed_password`.
- **Cómo se expone**: incluido en la respuesta de `GET /tenant/{slug}/services/people` como `debug_password`.

### 2. Endpoint `POST /tenant/{slug}/services/people/{id}/reset-password`

- **Por qué**: para miembros existentes que ya tienen `hashed_password` configurada (y por tanto el flujo de bienvenida no la regenera), necesitamos forzar un reset y ver el plaintext.
- **Comportamiento**: fuerza regeneración + guarda plaintext en `debug_password` + actualiza hash + stamp `welcomed_at`. Bloquea para `org_role=admin` (su contraseña vive en el tenant principal).
- **Definido en**: `app/api/v1/endpoints/tenant_service_people.py` (función `reset_password_debug`).

### 3. Columna "Contraseña (test)" + botón "Reset pw" en frontend

- **Dónde**: pestaña Servicios → Personas, tabla de personas, columna amarilla.
- **Definido en**: `src/tenant/pages/Servicios.tsx` (`PersonasView` / `resetPasswordDebug`).
- **Tarjeta amarilla** + estilo `#FFFBEB` para señalizar que es contenido de QA.

### Checklist de eliminación (cuando se ordene)

- [ ] `ALTER TABLE service_members DROP COLUMN debug_password;`
- [ ] Quitar campo `debug_password` del modelo `ServiceMember` en `app/models/models.py`
- [ ] Quitar `debug_password` del serializer en `tenant_service_people.py` (`_serialize`)
- [ ] Quitar asignaciones `sm.debug_password = ...` en POST create + POST welcome
- [ ] Eliminar endpoint `reset_password_debug` + ruta `POST /services/people/{id}/reset-password`
- [ ] Quitar campo `debug_password` de `ServicePerson` (interface TS) en `Servicios.tsx`
- [ ] Quitar columna "Contraseña (test)" y celda asociada en la tabla `PersonasView`
- [ ] Quitar función `resetPasswordDebug` + botón "Reset pw"
- [ ] Quitar referencias en `API-DOCS.md`

