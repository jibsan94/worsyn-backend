# Equipos · Vista de detalle + Posiciones (PCO-style)

**Estado:** ✅ Completado · 2026-05-25

Continuación de [`TEAM-CREATION-FLOW.md`](./TEAM-CREATION-FLOW.md). Aquí se
implementa la **vista de detalle** de un equipo (al hacer clic en el nombre en
la lista de Servicios → Personas → Equipos) con su gestión de **Posiciones**
(Piano, Bajo, Guitarra Acústica, etc.) y acciones por sublista (correo / PDF /
borrar).

---

## Resumen funcional

1. En la lista de Equipos cada fila tiene **hover** (highlight + cursor pointer).
2. Clic sobre el **nombre** del equipo → entra a `TeamDetailView`.
3. La vista de detalle tiene 3 pestañas (UI): **Settings · Members · Automations**.
   Por ahora sólo implementamos **Members** + reutilizamos el modal del equipo
   para Settings. Automations es stub (Fase 3 — cuadrante).
4. **Members tab** = layout con barra lateral izquierda + panel principal:
   - **All team members** — unión deduplicada de personas en cualquier posición.
   - **Team leaders** — los registros de `team_leaders` ya existentes.
   - **POSITIONS** — lista dinámica creada por el usuario (Piano, Bajo, …).
   - **+ Add position** — botón al final de la sidebar para crear una posición.
5. Panel principal de cada sub-vista:
   - Cabecera con el título (nombre de la sub-vista) + 3 iconos de acción.
   - Tabla con columnas: **First name · Last name · Positions · Preferences**.
6. Iconos (top-right del panel):
   - ✉️ **Mail** — abre `ComposeEmailModal` reutilizado, pre-rellena
     `recipient_member_ids` con la lista visible. El admin puede quitar/añadir
     destinatarios antes de enviar.
   - 🖨️ **Print** — descarga PDF con logo de Worsyn + nombre del equipo + título
     de la sub-vista + tabla de personas. Útil para repartir en mano.
   - 🗑️ **Delete** — **solo visible en sub-vistas de Posición**. Borra la
     posición (cascada a sus miembros). Confirm dialog.
7. Crear posición = modal sencillo con `name` (Piano, Bajo, …).
8. Añadir persona a una posición = picker de personas del módulo Servicios
   (mismas personas que ven en `PersonasView`). Devuelve `member_id`,
   muestra nombre + apellido + preferencias (`scheduling.max_per_month` etc.).

---

## Plan de trabajo

### 1 · Base de datos

- [x] **Nueva tabla `team_positions`**:
  - `id UUID PK`
  - `team_id UUID FK→teams(id) ON DELETE CASCADE`
  - `name VARCHAR(150) NOT NULL`
  - `sort_order INT DEFAULT 0`
  - `created_at TIMESTAMPTZ`
  - `UNIQUE(team_id, name)` — dos posiciones con mismo nombre por equipo no tienen sentido.
- [x] **Nueva tabla `team_position_members`** (M2M position ↔ org_members):
  - `id UUID PK`
  - `position_id UUID FK→team_positions(id) ON DELETE CASCADE`
  - `member_id UUID FK→org_members(id) ON DELETE CASCADE`
  - `created_at TIMESTAMPTZ`
  - `UNIQUE(position_id, member_id)`

### 2 · Modelos SQLAlchemy

- [x] `TeamPosition(Base)` + `TeamPositionMember(Base)` en `app/models/models.py`.

### 3 · Backend (`tenant_teams.py`)

- [x] **GET `/tenant/{slug}/teams/{team_id}/detail`** — devuelve `{
  team: {...}, leaders: [...], positions: [{id, name, sort_order, members: [...]}], all_members: [...] }`.
  Cada persona trae: `{ member_id, full_name, email, avatar, preferences: { max_per_month, max_per_day } }`.
- [x] **POST `/tenant/{slug}/teams/{team_id}/positions`** — body: `{ name }`. 409 si duplicado.
- [x] **PATCH `/tenant/{slug}/teams/{team_id}/positions/{pos_id}`** — rename (opcional).
- [x] **DELETE `/tenant/{slug}/teams/{team_id}/positions/{pos_id}`** — cascade.
- [x] **POST `/tenant/{slug}/teams/{team_id}/positions/{pos_id}/members`** —
  body: `{ member_ids: [...] }` (idempotente, silently dedupe).
- [x] **DELETE `/tenant/{slug}/teams/{team_id}/positions/{pos_id}/members/{member_id}`** — quitar persona.
- [x] Guard `admin/leader` + same-org silently drop unknowns.

### 4 · Frontend (`Servicios.tsx`)

- [x] **Hover** en filas de la tabla de equipos.
- [x] Click sobre nombre del equipo → `selectedTeamId` state, render `TeamDetailView`.
- [x] `TeamDetailView` con:
  - [x] Cabecera: nombre + indicadores (badges: `is_rehearsal`/`is_secure`/`is_split` + tipos servicio).
  - [x] Tabs: Settings (reutiliza `TeamFormModal` inline) / Members (default) / Automations (placeholder).
  - [x] Botón Volver.
- [x] **MembersTab** con sidebar izquierda:
  - [x] All team members (badge count)
  - [x] Team leaders (badge count)
  - [x] Lista de posiciones (badge count cada una)
  - [x] `+ Add position` botón
- [x] **Panel principal** con tabla + iconos de acción:
  - [x] Email reusa `ComposeEmailModal` (pre-rellena recipients).
  - [x] Print abre nueva pestaña con HTML estilado (Worsyn logo + lista) y dispara `window.print()` → user "Guarda como PDF".
  - [x] Delete (solo posiciones) con confirm.
- [x] Modal `AddPositionModal` (input name).
- [x] Modal `AddPersonToPositionModal` (picker de personas del módulo Servicios — reusa estilo de chip picker, multi-select).

### 5 · Smoke tests

- [x] Crear posición → GET detail muestra la posición vacía.
- [x] Añadir 2 personas → all_members tiene 2, positions[0].members tiene 2.
- [x] Crear segunda posición con misma persona → all_members sigue siendo 2 (dedup).
- [x] DELETE posición → cascade a team_position_members.
- [x] DELETE persona de posición → posición sigue, all_members re-calcula.

### 6 · Artefactos

- [x] `STACK.md` — esquema de `team_positions` + `team_position_members`.
- [x] `API-DOCS.md` — sección Teams ampliada con detail + positions endpoints.
- [x] `CONTEXT.md` — entrada changelog.
- [x] `napkin.md` — patrón "sub-listas dinámicas con acción print/email/delete".
- [x] Este doc — actualizar estado a ✅ Completado.

---

## Notas / decisiones

- **Print = window.print()**: no añadimos dependencia de PDF backend (reportlab,
  weasyprint). Renderizamos una página HTML estilada para impresión y el navegador
  ofrece "Guardar como PDF". Beneficios: zero deps, encajable en cualquier
  cliente, el usuario elige tamaño/papel.
- **Email reuse**: `ComposeEmailModal` ya acepta `recipient_member_ids[]`.
  Sólo hay que pasar la lista visible. No tocamos backend de email.
- **Posición vs `team_memberships`**: posiciones son una capa nueva por ENCIMA
  de `team_memberships`. NO migramos los memberships existentes — la pestaña
  "Equipos" de PersonDetail sigue funcionando contra `team_memberships`. La
  pestaña Members del equipo nuevo usa `team_position_members`. Si en Fase 3 el
  cuadrante necesita ambas, hacemos UNION.
- **"All team members"** = `SELECT DISTINCT member` across todas las posiciones
  del equipo (sin `team_memberships`). Si una posición se borra y la persona no
  estaba en otras, desaparece de All.
- **"Preferences"** = `service_members.scheduling_max_per_month` / `_max_per_day`
  de la org_member ligada. Si no tiene fila en `service_members`, "Sin límite".

---

_Estado al final de la sesión:_ ✅ Implementación completa. DB + backend (8 smoke tests OK) + frontend desplegado + artefactos sincronizados.
