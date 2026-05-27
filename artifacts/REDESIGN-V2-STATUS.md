# Servicios V2 · Estado de migración

**Rama:** `redesign` (frontend + backend)
**Estado:** 🟢 **Migración masiva desplegada** — Sidebar+Topbar V2, 5 sub-vistas + Vista antigua, 3 temas funcionando
**Última actualización:** 2026-05-27 (sesión 2)

---

## Lo que está en `redesign` HOY

### Archivos creados / modificados

| Archivo | Estado | Qué hace |
|---|---|---|
| `src/tenant/pages/ServiciosLegacy.tsx` | **NUEVO** (copia verbatim) | Snapshot 5440 líneas de la versión anterior. **Funciona 100%.** |
| `src/tenant/pages/Servicios.tsx` | **REESCRITO** | Entry V2: wrapper `tenant-v2` + theme switcher + routing a Personas V2 / Legacy / placeholders |
| `src/tenant/styles/tenant.css` | **NUEVO** | Design tokens para los 3 temas (clean-light · clean-dark · cyber) + clases base |
| `src/tenant/components/IconsV2.tsx` | **NUEVO** | Set de iconos SVG portados del prototipo (28 iconos) |
| `src/pages/TenantPortal.tsx` | **EDITADO** | Tipo `ServiciosTab` + arrays incluyen `'legacy'` (← Vista antigua) |
| `artifacts/REDESIGN-SERVICIOS-PLAN.md` | (ya existía) | Plan original — sigue válido |
| `artifacts/REDESIGN-V2-STATUS.md` | **ESTE** | Tracking de migración |

### Lo que ya funciona en V2 — **MIGRACIÓN COMPLETA DE SHELL**

- ✅ **Takeover del viewport** (`position: fixed; inset: 0; z-index: 50`). Cuando se abre Servicios, el shell V2 reemplaza completamente el chrome del portal antiguo. Vuelve a verse el chrome legacy al elegir "Vista antigua" desde la sidebar.
- ✅ **Sidebar V2 propia** (`.sb`) con 3 modos (full 232px · icons 64px · hidden) + persistencia en localStorage. Acceso directo a Vista antigua desde la sidebar.
- ✅ **Topbar V2 propia** con breadcrumbs dinámicos, search bar fake (⌘K), Mi Perfil dropdown con tema selector + logout REAL conectado a `/tenant/auth/logout`.
- ✅ **Wrapper con CSS variables** scoped al `.tenant-v2`. No contamina el resto del admin.
- ✅ **3 temas:**
  - **Claro** (`clean-light`) — Apple-clean light, fondo blanco
  - **Menos claro** (`clean-dark`) — Apple-clean dark, fondo negro
  - **Cyberpunk** (`cyber`) — neón cian/magenta + grid + bg gradiente
- ✅ **Persistencia tema** en `localStorage["worsyn-tenant-appearance"]`.
- ✅ **Mi Perfil dropdown** (top-right de la toolbar Servicios):
  - Editar perfil (stub)
  - Cambiar contraseña (stub)
  - Selector de Apariencia con los 3 modos · ✓ marca el activo
  - Cerrar sesión (stub)
- ✅ **Sub-tab "← Vista antigua"** en la barra de sub-tabs del portal: renderiza ServiciosLegacy verbatim con su chrome viejo → permite comparar A/B sin tocar nada.
- ✅ **Mi Planificación V2** — hero personalizado · 2-col layout · lista de próximos planes con badges de status + colored date pills · mini-calendario del mes (marca con dot los días con ocurrencias) · resumen Confirmados/Pendientes/Rechazados. Conectado a `/services/people/{sm}/assignments?range_from&range_to` + `/services/occurrences`.
- ✅ **Servicios list V2** — cards por tipo de servicio con **ribbon gradiente** del color del tipo, decoraciones circulares, contador de próximos, chips de horarios, lista de instancias con `svc-instance` rows + colored date tiles + chevron. Conectado a `/services/types` + `/services/occurrences`. Empty state bonito.
- ✅ **Personas V2** completamente migrada — hero, 4 KPIs animados, tabla con buscador/filtros/avatars seed, chips dual de estado. Click en fila abre **PersonaDetail V2**.
- ✅ **PersonaDetail V2** — 2-col layout: avatar grande + info card · todas las llamadas reales. Stub explícito para acciones avanzadas (redirige a Vista antigua).
- ✅ **Canciones / Media** — empty-states V2 elegantes (la lógica real llegará en Fase 3, backend stub).
- ✅ Reset interno en cambio de tab + cambio de selectedPerson.

### Pruebas internas ejecutadas (sesión 2)

```
SMOKE BACKEND  (post-migración, branch redesign)
✓ GET  /tenant/{slug}/auth/me                              200
✓ GET  /tenant/{slug}/members                              200
✓ GET  /tenant/{slug}/services/types                       200
✓ GET  /tenant/{slug}/services/occurrences                 200
✓ GET  /tenant/{slug}/services/plans                       200
✓ GET  /tenant/{slug}/services/people                      200
✓ GET  /tenant/{slug}/teams                                200
✓ GET  /tenant/{slug}/email/templates                      200
✓ GET  /tenant/{slug}/email/messages                       200
✓ GET  /tenant/{slug}/services/people/<sm>/assignments     200
✓ POST /tenant/{slug}/email/messages/preview (welcome)     200
Resultado: 11 OK / 0 fallidos

SMTP
SMTP configured: True
SMTP host: smtp.gmail.com:587
SMTP from: no-reply@worsyn.com

EMAIL RENDER
✓ team_welcome preview: 200 · team.name presente
✓ welcome preview:      200 · organization.name presente
```

Build TypeScript estricto: **0 errores**. Build Vite: **OK** (701 KB bundle).

---

## Pendientes para completar la migración a V2

### Sub-vistas / features pendientes para PARIDAD total con Legacy

| # | Item | Esfuerzo | Bloqueante |
|---|---|---|---|
| 1 | **PersonaDetail completa** — tabs Programación/Comunicación/Detalles con donut chart, blockouts CRUD, signature editor, assignments table | XL | No (V2 ya muestra info básica; acciones via Vista antigua) |
| 2 | **TeamDetail V2** — sub-sidebar de posiciones, 7 cards de Settings, leaders CRUD, posiciones CRUD, automatizaciones | XL | No |
| 3 | **CreateTypeWizard V2** — drawer derecho 3 pasos (detalles · horarios · equipos) | M | No |
| 4 | **AddPersonWizard V2** — drawer derecho (persona · permisos · welcome) | L | No |
| 5 | **TeamFormModal V2** — crear/editar equipo con leaders + service types + flagCards | M | No |
| 6 | **ComposeEmailModal V2** — drawer derecho con rich editor + variable picker | XL | No (rich text editor existente se puede reusar) |
| 7 | **TemplatesManagerModal / TemplateEditor V2** | L | No |
| 8 | **BlockoutModal V2** | S | No |
| 9 | **Canciones library full** — backend stub primero | XL | **Backend** |
| 10 | **Media library full** — backend stub primero | L | **Backend** |
| 11 | **PlanDetail completo** — orden de servicio, equipos, canciones, media, notas, historial | XL | **Backend** (plan_items) |
| 12 | **Solicitudes pendientes inbox** en Mi Planificación con drawer detail + Aceptar/Rechazar | M | **Backend** (`service_plan_invitations` o estado `invited` en `plan_assignments`) |
| 13 | **Persona detail · navegación al detalle de equipo** desde la sub-tab Equipos del miembro | M | No |
| 14 | **Persistencia tema en BD** (`org_members.preferred_appearance`) | S | No, opcional |
| 15 | **Self-host Geist / JetBrains Mono fonts** | S | No, optimización |

### Modales a re-skinear

| Modal | Función | Reemplazo V2 |
|---|---|---|
| `CreateTypeWizard` | Wizard 3-step crear tipo servicio | Drawer derecho con steps |
| `TeamFormModal` | Crear/editar equipo + leaders + service types | Modal V2 con flagCards |
| `AddPersonWizard` | Onboarding multi-step | Drawer derecho |
| `BlockoutModal` | Crear/editar bloqueo | Modal compacto |
| `ComposeEmailModal` | Composer rich text + variables | Drawer derecho (full-height) |
| `TemplatesManagerModal` | Lista templates | Card en página dedicada |
| `TemplateEditorModal` | Editor template | Drawer derecho |
| `AddPositionModal` | Crear posición | Modal compacto |
| `AddLeaderModal` | Picker líder | Modal compacto |
| `AddPersonsToPositionModal` | Multi-pick personas a posición | Modal compacto |
| `TeamBulkEmailModal` | Envío masivo email a equipo | Drawer derecho |

### Funciones nuevas del prototipo a backportar

| Feature prototipo | Backend necesario | Prioridad |
|---|---|---|
| Inbox "Solicitudes pendientes" en Mi Planificación | Nueva tabla `service_plan_invitations` o estado `invited` en `plan_assignments` | Alta |
| RequestDetail drawer con songs preview | Endpoint que listee canciones del plan | Alta |
| Live mode (botón en PlanDetail) | `POST /plans/{id}/live-mode` | Media |
| Vista pública del plan | `GET /public/plans/{public_slug}` sin auth | Media |
| Persistir apariencia por usuario (no sólo localStorage) | `ALTER TABLE org_members ADD COLUMN preferred_appearance VARCHAR(20)` + PATCH | Baja |
| Plan order de servicio (items, secciones, canciones) | Nueva tabla `service_plan_items` | Alta (bloquea PlanDetail) |
| Mini-cal mensual en Mi Planificación | `GET /services/occurrences?month=YYYY-MM` ya existe — wire |
| Cancion detalle con tono ±, letra+acordes monospace | Nueva tabla `songs` rica (key, bpm, lyrics, chords) | Alta (bloquea Canciones) |
| Media folders + tags | Nueva tabla `media_folders` + `media_assets.tags` | Alta (bloquea Media) |

### Mejoras pendientes en V2 actual

- Personas V2: falta el sub-tab "Equipos" con grid de equipos (existe en `screens-c.jsx:Personas`); falta navegación al detalle de la persona al click.
- ServiciosToolbar: el Mi Perfil tiene Editar perfil y Cambiar contraseña como **stubs** (no wired).
- Falta una vista de Logout funcional (Mi Perfil → Cerrar sesión todavía es stub).
- En theme=cyber el contraste de algunos chips puede mejorarse para AA.
- La fuente Geist se carga desde Google Fonts CDN — recomendado self-host para producción.

### Decisiones técnicas tomadas en este MVP

1. **Sin takeover de chrome:** el parent `TenantPortal` sigue renderizando su sidebar/topbar. El V2 vive **dentro** del contenido del módulo Servicios. Esto evita tocar 2900 líneas de TenantPortal y permite migrar sin riesgo.
2. **CSS scoped:** todas las clases V2 viven bajo `.tenant-v2`. Cero contaminación al admin u otros módulos del portal.
3. **Toolbar interna por módulo:** la barra "Servicios · Personas" con Mi Perfil dropdown es del módulo, no global. Cuando otros módulos migren tendrán la suya o un componente compartido.
4. **Legacy como pestaña dentro del mismo módulo:** así el usuario puede comparar A/B en 1 click sin perder estado. Cuando V2 esté completa, se quita la pestaña.
5. **Sin nuevas tablas BD aún:** la persistencia de tema vive en localStorage; lo elevaremos a `org_members.preferred_appearance` en una fase posterior.

---

## Cómo probar AHORA

1. Abre el portal tenant → Servicios.
2. Ve a la sub-pestaña **Personas** (es la única V2 completa) — verás el rediseño con tokens nuevos.
3. Click en el botón **Mi Perfil** (top-right) → cambia entre Claro · Menos claro · Cyberpunk. La preferencia se guarda en localStorage por sesión.
4. Click en **← Vista antigua** (última pestaña del strip) → ves la versión anterior intacta. Vuelve a las otras pestañas y sigues en V2.
5. Las pestañas Mi Planificación / Servicios / Canciones / Media muestran el placeholder "En migración" intencionalmente.

---

## Compromiso de conectividad backend

✅ **Todos los endpoints existentes siguen funcionando.** No se ha tocado código de backend en esta sesión.
✅ **SMTP configurado y operativo.** Tests de preview de plantillas welcome + team_welcome pasan.
✅ **Auth flow intacto.** `tenant_access` cookie/Bearer funcionan igual.
✅ **El módulo Servicios sigue sirviendo a usuarios actuales** vía `← Vista antigua` con cero pérdida de funcionalidad.
