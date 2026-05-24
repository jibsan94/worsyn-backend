# Equipos · Flujo de creación (PCO-style)

**Estado:** 🚧 En implementación · iniciado 2026-05-27

Este documento describe el nuevo modal de creación / edición de equipos
inspirado en el "Add Team" de Planning Center, junto con el resto del trabajo
(BD, API, frontend, tests). Se va tachando ítem a ítem; si se acaba la sesión,
retomar desde el primer cuadro sin marcar.

---

## Resumen funcional

El admin abre `Servicios → Personas → Equipos → + Nuevo equipo`. Se muestra
un pop-up con:

1. **Nombre** del equipo (input) + toggle `Nuevo` / `Copiar` (Copy deshabilitado
   en esta fase — la copia de equipos llega más adelante).
2. **Líderes del equipo** (`Team Leaders`): chips multi-select. Por defecto se
   pre-rellena con el nombre de quien está creando el equipo. Se pueden quitar
   y/o añadir más líderes a partir de los miembros de la organización.
3. **Tipos de servicio** (`Service Types`): multi-select de los `service_types`
   ya existentes en la org. Sirve para indicar en qué servicios participará el
   equipo. Botón "Seleccionar todos".
4. **Tipo de equipo** (banderas excluyentes-pero-no-mutuamente-exclusivas):
   - **Equipo de ensayo** (`is_rehearsal`) — puede acceder a player de
     canciones, partituras y media del servicio asignado.
   - **Equipo seguro** (`is_secure`) — sólo personas con verificación de
     antecedentes pueden ser asignadas. *(Por ahora la verificación es un flag
     manual en el miembro; integración real con check-providers llega en Fase 3.)*
   - **Equipo dividido** (`is_split`) — si la iglesia tiene varios servicios el
     mismo día (mañana + tarde), permite distintas personas por franja.

---

## Plan de trabajo

### 1 · Base de datos

- [x] **ALTER `teams`**: añadir `is_rehearsal BOOL DEFAULT FALSE`,
  `is_secure BOOL DEFAULT FALSE`, `is_split BOOL DEFAULT FALSE`.
- [x] **Nueva tabla `team_leaders`** (M2M team ↔ org_members):
  - `id UUID PK`
  - `team_id UUID FK→teams(id) ON DELETE CASCADE`
  - `member_id UUID FK→org_members(id) ON DELETE CASCADE`
  - `created_at TIMESTAMPTZ`
  - `UNIQUE(team_id, member_id)`
- [x] **`service_teams`** ya existe (M2M team ↔ service_type) — reutilizamos.
- [x] Actualizar modelo `Team` y crear modelo `TeamLeader` en `models.py`.

### 2 · Backend

- [x] **GET `/tenant/{slug}/teams`** — añadir al payload: `is_rehearsal`,
  `is_secure`, `is_split`, `leader_member_ids[]`, `service_type_ids[]`.
- [x] **POST `/tenant/{slug}/teams`** — aceptar nuevos campos. Si
  `leader_member_ids` no se envía o está vacío, **auto-añadir el caller** como
  primer líder.
- [x] **PATCH `/tenant/{slug}/teams/{team_id}`** — acepta y reemplaza `leader_member_ids[]`
  y `service_type_ids[]`. Resto de flags también editables.
- [x] **GET `/tenant/{slug}/teams/{team_id}`** *(opcional)* — devolver el equipo
  completo (lo cubre el GET de lista). Skip — la lista basta.
- [x] Validaciones: `leader_member_ids` y `service_type_ids` deben referir a
  miembros/tipos de la misma org (silently drop unknowns).

### 3 · Frontend

- [x] Reescribir `TeamFormModal` en `Servicios.tsx`:
  - [x] Nombre + toggle New/Copy (Copy disabled).
  - [x] Líderes: chip-picker con búsqueda; pre-rellena al usuario actual.
  - [x] Tipos de servicio: chip-picker con "Seleccionar todos".
  - [x] Tipo de equipo: 3 cards con checkbox + icono + descripción + "Aprende más".
- [x] Reutilizar `useEscape` + `ReactDOM.createPortal` para sub-pickers que pudieran clipearse.
- [x] Render del equipo en la lista de Equipos (`PersonasView`): añadir badges
  `Ensayo · Seguro · Dividido` cuando proceda. Mostrar conteo de líderes.

### 4 · Pruebas (smoke test)

- [x] POST con todos los campos → verificar filas en `teams`, `team_leaders`,
  `service_teams`.
- [x] PATCH cambiando líderes (replace-all) → verificar que el set anterior se
  borra y el nuevo persiste.
- [x] Lista GET devuelve `leader_member_ids` y `service_type_ids` correctamente.
- [x] Crear team sin `leader_member_ids` → el caller debe quedar como leader.

### 5 · Artefactos & docs

- [x] `STACK.md` — schema de `teams` + `team_leaders`.
- [x] `API-DOCS.md` — sección Teams actualizada con nuevos campos.
- [x] `CONTEXT.md` — entrada de changelog.
- [x] `napkin.md` — patrón de "wizard de creación con M2M anidadas en single POST".
- [x] Este documento (`TEAM-CREATION-FLOW.md`) — actualizar estado a "✅ Completado" al final.

---

## Notas / decisiones

- **Copy disabled**: no se implementa duplicación de equipo en esta fase.
  Cuando llegue, será otro endpoint `POST /teams/{id}/duplicate` que copia
  nombre+flags+service_types+leaders y opcionalmente memberships.
- **Secure Team** sólo guarda el flag por ahora. La verificación real de
  antecedentes (background check) es Fase 3 y necesita integración con un
  servicio externo (Checkr / Verified First / similar).
- **Split Team** sólo guarda el flag por ahora. La lógica de "distintas
  personas por franja del mismo día" se integra cuando el cuadrante de Fase 3
  lo consuma (`service_times` ya soporta múltiples slots por día).
- **Team Leaders ≠ Team Members**: un líder puede o no ser miembro del equipo.
  La membresía sigue gestionándose vía `team_memberships`. Esta separación
  permite que el líder coordine pero no sea él mismo el que sirva.

---

_Estado al final de la sesión:_ ✅ Implementación completa. Frontend desplegado, backend probado end-to-end (4 smoke tests OK), artefactos sincronizados.
