# Servicios · Integración pendiente (Fase 3)

**Auto-cargar este artefacto cuando se empiece a implementar el cuadrante /
auto-scheduler / signup sheets.**

Campos ya persistidos en `teams` (BD) que esperan comportamiento real:

| Campo BD                       | Tipo    | Trigger esperado                                                    |
|--------------------------------|---------|---------------------------------------------------------------------|
| `gap_alerts_enabled`           | BOOL    | Servicio próximo + posición sin asignar tras deadline → notificación|
| `notify_on_prepare`            | BOOL    | Plan marcado "Preparado" → notificación masiva a involucrados       |
| `default_status`               | VARCHAR | Estado inicial al crear `service_plan_member` (`unconfirmed`/`confirmed`) |
| `replies_to`                   | VARCHAR | Reply-To del correo de invitación/confirmación                      |
| `last_scheduled_date_rule`     | VARCHAR | Cómo computar "última vez que sirvió" en el auto-scheduler          |
| `scheduled_viewer_access`      | VARCHAR | Qué expone el plan a quien tenga rol `scheduled_viewer`             |
| `signup_sheets_auto_enable`    | BOOL    | Al crear plan nuevo, abrir signup sheet automáticamente             |
| `reschedule_on_decline`        | VARCHAR | Acción tras decline: none/manual/volunteer/auto/signup_sheet        |

---

## 1 · `gap_alerts_enabled` — alertas de huecos en programación

**Comportamiento:**
- Cuando alguien programado NO ha confirmado al llegar la fecha límite del plan,
  enviar email a:
  - Líder del servicio (`team_leaders` + `replies_to` setting)
  - La persona que no confirmó
- Sólo dispara si el equipo tiene `gap_alerts_enabled = TRUE`.

**Implementación:**
- Job recurrente (cron / APScheduler) que escanee `service_plan_members` con
  `status='unconfirmed'` cerca de su `plan.scheduled_at`.
- Usar `tenant_email.send_message` con plantilla `gap_alert.html`.
- Marcar `gap_alert_sent_at` en `service_plan_members` (nueva columna) para no
  reenviar.

**Plantilla email a crear:** `gap_alert` — variables `{{ to.full_name }}`,
`{{ plan.scheduled_at }}`, `{{ team.name }}`, `{{ position.name }}`.

---

## 2 · `notify_on_prepare` — notificar al preparar plan

**Comportamiento:**
- Cuando un admin/coord marca el plan como "Preparado" (nuevo estado en
  `service_plans.preparation_status`), si el equipo tiene
  `notify_on_prepare = TRUE`, mandar email a todos los miembros asignados con
  el detalle del plan.

**Implementación:**
- Endpoint `POST /tenant/{slug}/services/plans/{plan_id}/prepare` →
  cambia estado + dispara loop sobre `service_plan_members` del plan, por equipo.
- Por cada equipo del plan, si `team.notify_on_prepare = TRUE`, encolar emails.
- Plantilla nueva: `plan_prepared`.

---

## 3 · `last_scheduled_date_rule` — regla para auto-scheduler

**Valores y semántica:**
- `same_as_service_type` — heredar regla del padre `service_type`
- `last_used_anywhere` — `MAX(plans.scheduled_at)` cruzando todos los equipos
- `last_used_in_team` — `MAX(...)` filtrando por `team_id = self`
- `last_used_in_position` — `MAX(...)` filtrando por `position_id = X`

**Implementación:**
- Helper `services/scheduler.py::compute_last_scheduled(member_id, team, position)`
  que aplique la regla correcta. Devuelve `date|None`.
- Auto-scheduler lo usa como uno de los inputs para ranking de candidatos.
- UI: en el picker de personas para una posición, mostrar la fecha junto al
  nombre ("Último: 12 ene 2025").

---

## 4 · `scheduled_viewer_access` — filtro de plan para viewers

**Valores y semántica:**
- `full_plan` — el viewer ve todo el plan
- `limited` — sólo bloques donde aparece asignado + bloques previos/siguientes
  con título únicamente
- `none` — sólo su asignación

**Implementación:**
- Endpoint `GET /tenant/{slug}/services/plans/{plan_id}` (cuando se implemente):
  si el caller tiene `service_role = 'scheduled_viewer'`, filtrar response según
  `team.scheduled_viewer_access` (del equipo donde está asignado).
- Si el viewer está en varios equipos del plan, usar el MÁS permisivo.

---

## 5 · `signup_sheets_auto_enable` — hojas de inscripción auto

**Concepto:**
Una **hoja de inscripción** = lista de posiciones abiertas para que voluntarios
se autoasignen. Solo aplica si el equipo NO está lleno.

**Implementación:**
- Nueva tabla `signup_sheets`:
  ```
  id, plan_id, team_id, position_id, status (open|closed), opened_at, closed_at
  ```
- Trigger: cuando se cree un nuevo `service_plan`, por cada equipo del plan:
  si `team.signup_sheets_auto_enable = TRUE`, insertar `signup_sheets` row con
  `status='open'` para cada posición sin asignar.
- Endpoint público (o con token): `GET /signup-sheets/{plan_id}` lista hojas.
- Endpoint: `POST /signup-sheets/{sheet_id}/sign-up` (miembro se autoasigna).

---

## 6 · `reschedule_on_decline` — acción tras un decline

**Comportamiento por valor:**
- `none` — no hacer nada. La posición queda vacía.
- `manual` (default) — crear "needed_position" en backlog del scheduler para que
  un admin/coord la asigne manualmente.
- `volunteer` — el que rechaza puede elegir su sustituto entre miembros del equipo
  con misma posición; si elige, se envía request al sustituto.
- `auto` — auto-scheduler busca el siguiente mejor candidato y le envía request.
- `signup_sheet` — abrir la posición en la hoja de inscripción del equipo.

**Implementación:**
- Hook en `PATCH /service_plan_members/{id}/respond` cuando `status='declined'`.
- Switch sobre `team.reschedule_on_decline`. Cada modo invoca un service helper
  separado (`services/decline_actions.py::on_none`, `::on_manual`, etc.).

---

## 7 · `replies_to` — Reply-To en emails

**Valores y semántica:**
- `all_leaders` (default) — Reply-To = todos los emails de `team_leaders`
- `service_type_leaders` — leaders del `service_type` del plan
- `no_one` — Reply-To = `noreply@<org_domain>` (o vacío)

**Implementación:**
- Helper `services/smtp.py::build_reply_to(team, service_type)` invocado al
  construir el `EmailMessage` SMTP.
- Sustituye el actual `reply_to = sender_member.email` cuando el contexto sea
  invitación/confirmación de servicio.

---

## Checklist para Fase 3 (servicios)

Cuando se arranque la implementación de servicios completa:

- [ ] Cargar este artefacto y revisar cada sección antes de tocar el módulo.
- [ ] Crear las tablas/columnas adicionales señaladas (`gap_alert_sent_at`,
      `signup_sheets`, `preparation_status`, etc.).
- [ ] Crear plantillas de email: `gap_alert`, `plan_prepared`.
- [ ] Wire SMTP `Reply-To` a `team.replies_to`.
- [ ] Auto-scheduler: leer `last_scheduled_date_rule` por equipo.
- [ ] Plan viewer endpoint: filtro por `scheduled_viewer_access`.
- [ ] Decline hook: switch sobre `reschedule_on_decline`.
- [ ] Cron job: barrer planes próximos + `gap_alerts_enabled`.
- [ ] Signup sheet creation hook al crear plan, si `signup_sheets_auto_enable`.

**Hoy (2026-05-27)** todas estas configuraciones se PERSISTEN en BD vía la
pestaña Configuración del equipo, pero NO tienen efecto runtime. Si el admin
las cambia, sólo se guarda el valor — el comportamiento real arranca cuando
se construya el módulo Servicios completo.
