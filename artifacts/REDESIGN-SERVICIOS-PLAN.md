# Servicios · Plan de rediseño (basado en `/mnt/Worsyn`)

**Estado:** 📋 Borrador para aprobación. **NO** se ha implementado nada todavía.
**Alcance de esta fase:** SÓLO el módulo Servicios del portal tenant. El resto del sistema queda intacto hasta que decidamos.

---

## 1 · Lo que es el código en `/mnt/Worsyn`

Prototipo React 18 **sin build**: HTML estático (`Worsyn Rediseño.html`) que sirve los `.jsx` directamente con Babel Standalone + React UMD desde unpkg. Es un **mock visual**, sin backend, datos inventados en `data.jsx`. No es código listo para producción — es la **fuente de verdad estética**.

### Estructura

| Archivo | Líneas | Qué contiene |
|---|---|---|
| `Worsyn Rediseño.html` | 26 | Mount + carga de scripts con Babel |
| `src/styles.css` | 1192 | Design tokens (light/dark · clean/futurist/cyber), tipografías, componentes |
| `src/icons.jsx` | 86 | SVG icons como componentes (`Home, Cal, Music, Photo, People, Inbox, Bolt, Settings, Bell, Plus, Chev, ChevLeft, Clock, Check, X, Send, Doc, Edit, Folder, Upload, Down, Sort, Filter, Tag, Star, Heart, Play, Search, Sidebar, Sun, Moon, Sparkles, Wave, Grip, Dots, Eye, Arrow, List, Grid, Menu`) |
| `src/data.jsx` | 134 | Mock seed (`org, user, serviceTypes, pendingRequests, upcoming, songs, media, plan`) |
| `src/shell.jsx` | 110 | `<Sidebar>` + `<Topbar>` |
| `src/screens-a.jsx` | 726 | `MiPlanificacion`, `Servicios` (list), `PlanDetail`, `RequestDetail` drawer |
| `src/screens-b.jsx` | 698 | `Canciones`, `CancionDetail`, `Media`, `Login` |
| `src/screens-c.jsx` | 356 | `Personas` (list + KPIs + equipos grid) + `PersonaDetail` |
| `src/mobile.jsx` | 633 | Pantallas iOS (`MobHome`, `MobServicios`, `MobPlan`, `MobCanciones`, `MobCancionDetail`, `MobMedia`, `MobTabBar`, `MobStatus`) |
| `src/app.jsx` | 296 | Root: routing por estado, `TweaksPanel` con tema/estilo/acento/densidad/sidebar |
| `src/tweaks-panel.jsx` | 530 | Panel de tweaks (no es feature de producto — es la herramienta de iteración del prototipo) |
| `uploads/Login.tsx` | 215 | Versión TSX del Login lista para integrar |

### Tokens y temas — diseño multicanal

Los temas viven en `[data-theme]` × `[data-style]` (4 combinaciones reales):
| theme | style | nombre comercial |
|---|---|---|
| `light` | `clean` | **Claro** (Apple-clean light) |
| `dark`  | `clean` | **Oscuro** (Apple-clean dark) |
| `light` o `dark` | `futurist` | **Futurist** (glass + gradientes) |
| `light` o `dark` | `cyber` | **Cyberpunk** (neón cian/magenta + grid) |

→ La **estructura de 3 modos pedida por el usuario** mapea limpia:
- **Claro** = `theme=light, style=clean`
- **Menos claro** = `theme=dark, style=clean` (o `style=futurist` si quieres "menos claro pero con personalidad")
- **Cyberpunk** = `style=cyber` (theme se ignora)

---

## 2 · Mapping nuevo ↔ código actual (sólo Servicios)

**Lo que llamamos hoy "Servicios"** en `/mnt/worsyn-dashboard/src/tenant/pages/Servicios.tsx` (4500+ líneas, 39 componentes) incluye actualmente **varios submódulos** porque en el portal Servicios es la sub-app principal con tabs internos. Mapeo a las nuevas pantallas:

| Sub-vista actual (Servicios.tsx) | Pantalla prototipo nueva | Origen |
|---|---|---|
| `Mi Planificación` (resumen + agenda) | `MiPlanificacion` | `screens-a.jsx` |
| `ListView` (tipos de servicio + ocurrencias) | `Servicios` (list) | `screens-a.jsx` |
| `PersonasView` (lista personas+equipos) | `Personas` | `screens-c.jsx` |
| `PersonDetailView` | `PersonaDetail` | `screens-c.jsx` |
| `TeamDetailView` (Miembros/Configuración/Automatizaciones) | **no existe en el prototipo todavía** | — |
| `ComposeEmailModal`, `TemplatesManagerModal`, `TemplateEditorModal` | **mantener como modales adaptados al CSS nuevo** | — |
| Canciones / Media / Plan-detail | `Canciones`, `Media`, `PlanDetail` | `screens-a/b.jsx` |

**Componentes del prototipo que NO tienen contrapartida actual y los descartamos en esta fase:**
- `Login` rediseñado (vive fuera del portal — fase posterior)
- `MobileGallery` + todo `mobile.jsx` (apps nativas — fase posterior)
- `TweaksPanel` — sólo herramienta interna del prototipo, no va al producto

**Componentes del actual que NO existen en el prototipo (hay que diseñarlos respetando el lenguaje):**
- `TeamDetailView` con sub-vistas Miembros (sidebar de posiciones), Configuración (7 cards), Automatizaciones
- `BlockoutModal` + bloqueos del calendario personal
- `CreateTypeWizard` (wizard de 3 pasos)
- Todo el motor de emails (compose + templates manager + variable picker + rich text editor)
- `TeamFormModal`, `AddPositionModal`, `AddLeaderModal`, `AddPersonsToPositionModal` (4 modales del flujo de equipos)
- Configuración granular de permisos por miembro de Services

---

## 3 · Inventario de endpoints API ↔ pantalla (qué sostiene qué)

El prototipo es **front-only**. Toda la lógica live en el backend FastAPI actual sigue válida — sólo cambia la capa visual. La nueva interfaz consume los **mismos endpoints**.

### 3.1 Endpoints que sostienen la nueva pantalla "Servicios" (list)

| Endpoint | Verbo | Uso en nueva UI |
|---|---|---|
| `/api/v1/tenant/{slug}/services/types` | GET/POST/PATCH/DELETE | Tipo de servicio + sus instancias (ribbons coloreados) |
| `/api/v1/tenant/{slug}/services/occurrences` | GET | Proyección de ocurrencias futuras (ribbon "X próximos") |
| `/api/v1/tenant/{slug}/services/plans` | GET/POST | Listado de planes (instancias) |

### 3.2 Endpoints que sostienen "Mi Planificación"

| Endpoint | Uso |
|---|---|
| `/api/v1/tenant/{slug}/auth/me` | Usuario actual + accessible_modules |
| `/api/v1/tenant/{slug}/services/people/{sm}/assignments?range_from&range_to` | KPIs Confirmados/Pendientes/Rechazados + lista de próximos planes |
| `/api/v1/tenant/{slug}/services/people/{sm}/blockouts` | Calendario personal de indisponibilidades |
| **TODO Fase 3:** request inbox (invitaciones pendientes con `Aceptar`/`Rechazar` + plantilla) | El bloque "Solicitudes pendientes" del prototipo es **nuevo** — necesita una tabla `service_plan_invitations` o reusar `plan_assignments` con un estado `invited` |

### 3.3 Endpoints que sostienen "Personas"

| Endpoint | Uso |
|---|---|
| `/api/v1/tenant/{slug}/services/people` | Lista, filtros, KPIs (admins / leaders / activos) |
| `/api/v1/tenant/{slug}/services/people/{sm}` | PATCH/DELETE (modificar permisos, deshabilitar, eliminar) |
| `/api/v1/tenant/{slug}/services/people/{sm}/teams` | Sub-vista Equipos del miembro |
| `/api/v1/tenant/{slug}/services/people/{sm}/welcome` | Reenviar bienvenida |
| `/api/v1/tenant/{slug}/services/people/{sm}/reset-password` | Reset pw |
| `/api/v1/tenant/{slug}/services/people/{sm}/messages` | Buzón personal |
| `/api/v1/tenant/{slug}/services/people/{sm}/blockouts` | Bloqueos |
| `/api/v1/tenant/{slug}/services/people/{sm}/assignments` | Estadística + planes |
| `/api/v1/tenant/{slug}/members` | Picker de orgMembers candidatos |

### 3.4 Endpoints que sostienen "Equipos" (sub-vista de Personas)

| Endpoint | Uso |
|---|---|
| `/api/v1/tenant/{slug}/teams` | Lista de equipos |
| `/api/v1/tenant/{slug}/teams/{id}/detail` | Vista detalle del equipo (leaders + positions + all_members) |
| `/api/v1/tenant/{slug}/teams/{id}/positions[/{pos_id}/members]` | CRUD posiciones + miembros de posición |
| `/api/v1/tenant/{slug}/teams/{id}/leaders[/{member_id}]` | CRUD líderes single-op |
| `/api/v1/tenant/{slug}/teams/{id}/members[/{member_id}]` | Memberships legacy (mantener) |

### 3.5 Endpoints que sostienen "Canciones" / "Media" / "PlanDetail"

| Endpoint | Estado |
|---|---|
| `/api/v1/tenant/{slug}/services/songs` | **Stub hoy** — el prototipo asume una tabla `songs` rica. Necesitará trabajo de backend para que funcione real. **NO bloqueante para Servicios sólo.** |
| `/api/v1/tenant/{slug}/services/media` | **Stub hoy** — igual que songs. |
| `/api/v1/tenant/{slug}/services/plans/{id}` | **Stub hoy** — la pantalla `PlanDetail` muestra orden de servicio (`plan.items`) que aún no existe en BD. **Bloqueante si queremos PlanDetail funcional.** |

**Email + Templates + Welcome flow** — ya funcional. Mantenerlo intacto y sólo re-skin de los modales.

### 3.6 Resumen de bloqueo backend

✅ **Funciona ya (sin tocar backend):** Mi Planificación (parcial — sin inbox de requests), Personas, Equipos detalle, Configuración, Compose/Templates email, BlockoutModal.

⚠️ **Necesita trabajo Fase 3 para funcionar pleno:** Solicitudes pendientes (inbox), PlanDetail orden de servicio, Canciones library, Media library, Live mode.

→ **Para esta fase de rediseño**, decisión recomendada: hacer el rediseño visual de TODAS las pantallas usables hoy, dejar **placeholders bonitos** (mismo lenguaje visual) en Canciones/Media/Plan/Inbox y avanzar backend en paralelo más adelante.

---

## 4 · Estrategia de los 3 temas + Mi perfil

### Estructura técnica

El sistema actual usa **inline styles** en `Servicios.tsx` con la paleta `C` (rule de napkin #60). El prototipo nuevo usa **CSS vars + clases globales**. Migrar a este modelo es el cambio más sustancial.

**Propuesta:**

1. Mover `src/styles.css` del prototipo a `src/tenant/styles/tenant.css` (NO mezclar con `index.css` del admin — son sistemas separados).
2. Reescribir/portar los componentes de Servicios para usar clases (`.card`, `.list-row`, `.btn-primary`, `.chip`, `.pill-tone`, etc.) en lugar de `style={...}`.
3. Añadir `data-theme` y `data-style` a `<html>` desde el contexto del portal tenant.

### Persistencia y selector

**Mi Perfil** (avatar arriba-derecha del topbar): dropdown con opciones:
```
Mi Perfil
─────────
👤 Editar perfil
🎨 Apariencia  ▾
   ○ Claro          (theme=light, style=clean)
   ● Menos claro    (theme=dark,  style=clean)
   ○ Cyberpunk      (theme=dark,  style=cyber)
🔐 Cambiar contraseña
⏏ Cerrar sesión
```

Persistencia: `localStorage["worsyn-tenant-appearance"]` = `'clean-light' | 'clean-dark' | 'cyber'`. Aplicación: `<html data-theme=... data-style=...>` desde `TenantPortal.tsx` en mount + onChange.

### Mapping concreto a tokens existentes en `styles.css`

| Modo UI | Tokens activos | Identidad |
|---|---|---|
| **Claro** | `[data-theme="light"][data-style="clean"]` | Fondo `#F7F8FA`, surface blanco, acento azul Apple `#0A84FF`, sombras suaves. Default por defecto. |
| **Menos claro** | `[data-theme="dark"][data-style="clean"]` | Fondo `#000`, surface `#1C1C1E`, acento azul Apple `#0A84FF`. Dark "Apple", no neón. |
| **Cyberpunk** | `[data-style="cyber"]` (theme ignorado) | Fondo gradient violeta+magenta, grid scan, acento cian neón `#00F0FF`, hot magenta `#FF2EC4`, JetBrains Mono. CSS ya escrito en `styles.css:131-171` y polish `:814-883`. |

**No exponemos `futurist`** — el usuario pidió 3, no 4. Lo guardamos disponible en CSS para más adelante.

---

## 5 · Estrategia de migración

Dos caminos. Recomiendo el **A** salvo que tengas miedo a romper Servicios temporalmente.

### Opción A · Rama paralela `redesign/servicios` (RECOMENDADA)

1. **Crear branch** desde `main`/`develop` después de cerrar el trabajo actual.
2. En esa rama, crear **un Servicios paralelo**: `src/tenant/pages/ServiciosV2.tsx` + `src/tenant/styles/tenant.css`. Mantener `Servicios.tsx` actual intacto en `/main`.
3. Router de portal puede leer un flag `localStorage["worsyn-redesign"]=='true'` para alternar V1↔V2 → permite probar lado a lado.
4. Migrar de a poco las sub-vistas (orden recomendado abajo). Cada PR aterriza una sub-vista funcional con tests visuales.
5. Cuando V2 esté completa y validada, swap default + borrar V1 + cerrar branch.

**Ventajas:** producción sigue estable; rollback gratis; permite QA paralelo; flag de feature por usuario.

**Coste:** dos `Servicios.tsx` cohabitando 2-4 semanas; algún drift menor.

### Opción B · In-place gradual con flag por sub-vista

1. Mismo branch `main`/`develop`. Cada sub-vista (Mi Planificación, Personas, etc.) se duplica internamente; un `<RedesignFlag />` decide qué render.
2. Cuando todas las sub-vistas estén migradas → eliminar flag + viejo código.

**Ventajas:** un único archivo; sin drift.

**Coste:** `Servicios.tsx` crece a ~9000 líneas temporalmente; PRs gigantes; rollback no es atómico.

### Orden de migración recomendado (en cualquiera de las dos opciones)

| Paso | Sub-vista | Esfuerzo | Riesgo | Notas |
|---|---|---|---|---|
| 1 | **Tokens + Sidebar + Topbar + Mi Perfil dropdown** | M | bajo | Habilita los 3 temas; sin lógica de datos |
| 2 | **Mi Planificación** | M | bajo | Sólo consume `auth/me`, `assignments`, `blockouts` |
| 3 | **Personas** (list + detail) | L | medio | Mucha tabla; reutilizar `.tbl` del prototipo |
| 4 | **Equipos detalle** (sub-vistas Miembros + Configuración + Automations) | XL | alto | Es el corazón actual; los 7 cards de Settings ya están bien pulidos, sólo cambia paleta + tokens |
| 5 | **Modales** (Compose, Templates, Wizards) | L | medio | El rich text editor + variable picker requieren `useRichEditorStyles` que ya existe; portar a nuevo CSS |
| 6 | **ServiceType list (cards con ribbon)** | M | bajo | Apariencia muy distinta — ribbon coloreado top + lista de ocurrencias |
| 7 | **PlanDetail** (placeholder bonito; backend stub) | S | bajo | Sólo skeleton funcional |
| 8 | **Personas → Equipos sub-tab** | M | bajo | Reusa cards y `.av` |
| 9 | **Canciones / Media** | placeholder | bajo | Esperar Fase 3 backend |

Cada paso es independiente y mergeable por separado.

---

## 6 · Componentes a portar 1:1 desde `/mnt/Worsyn`

Lista de los **bloques visuales** que copiamos tal cual (sólo cambia que pasan de `.jsx` con Babel a `.tsx` con tipos):

1. **`Sidebar`** (`shell.jsx:6-73`) — secciones Iglesia/Trabajo, brand pill, user footer, toggle iconos/completa/oculta.
2. **`Topbar`** (`shell.jsx:76-108`) — breadcrumbs, search ⌘K, theme toggle, bell, plus.
3. **`Personas` list + KPIs row + filtros + grid de equipos** (`screens-c.jsx`).
4. **`PersonaDetail` 2-col layout** (`screens-c.jsx:282-354`) — left: avatar + stats; right: info rows.
5. **`Servicios` list** con `svc-ribbon` por tipo (`screens-a.jsx:430-542`).
6. **`MiPlanificacion` dashboard** con request cards + mini-cal + actividad reciente.
7. **Drawer derecho** (`.drawer`, `.drawer-backdrop`) para RequestDetail u otros (`styles.css:1054-1086`).
8. **KPI row** (`.kpi-row`, `.kpi`) con números grandes + delta arrow.
9. **`pill-tone`** (chip de color por tipo de servicio) — la forma canónica de mostrar tipo+estado.
10. **`av` colored avatars** con seed `data-c="1..7"`.
11. **`mini-cal`** mes-mini reusable en cualquier sidebar.
12. **`svc-instance`** (fila de ocurrencia futura).
13. **`tbl`** tabla compacta con header Mono uppercase.
14. **`seg` segmented control iOS-style**.

---

## 7 · Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **Romper Servicios mientras está en uso por la iglesia de prueba** | Rama paralela (Opción A) o flag por usuario |
| **Rich text editor + Variable picker no encajan en el nuevo CSS** | Estos componentes ya usan estilos inline aislados — pueden vivir dentro de la nueva shell sin tocar |
| **Tablas grandes (Personas) cambian de inline → clase** | Migración en bloque de PersonasView; testing visual lado a lado |
| **3 temas multiplican casos de QA** | Cap. tests visuales por tema en una sola página de "kitchen sink"; revisar contraste AA en cada uno |
| **`localStorage` para tema no propagable entre dispositivos** | Aceptar para Fase 1; luego añadir `org_members.preferred_theme` en BD |
| **El usuario abre Cyberpunk y la legibilidad de tablas grandes baja** | Tests con datos reales; ajustes específicos `[data-style="cyber"] .tbl` ya existen |
| **`Geist` font fetch desde Google Fonts puede bloquear** | Self-hostear las fuentes en `/public/fonts/` |

---

## 8 · Trabajo de backend NO bloqueante (para mantenerlo en lista)

Cosas que la nueva UI deja "preparadas" pero requieren backend para soltarlas:

1. **Inbox de solicitudes** (`Mi Planificación → Solicitudes pendientes`) → nueva tabla `service_plan_invitations` o estado `invited` en `plan_assignments`.
2. **Live mode** (botón en PlanDetail) → endpoint `POST /plans/{id}/live-mode` para activar Service-Day mode.
3. **Vista pública del plan** (botón Vista pública) → `GET /public/plans/{public_slug}` sin auth.
4. **Notificar equipo masivo** (botón en PlanDetail) → ya existe `email/messages` con `team_id`, sólo wire.
5. **Persistir preferencia de apariencia** → `ALTER TABLE org_members ADD COLUMN preferred_appearance VARCHAR(20)`.

---

## 9 · Decisión que necesito de ti antes de implementar

1. **Branch:** ¿Opción A (rama paralela `redesign/servicios`) o B (in-place con flags)?
2. **Inicio:** ¿Por dónde empezamos? Recomiendo Paso 1 del orden (tokens + sidebar/topbar/Mi-perfil) — habilita los 3 temas sin tocar datos.
3. **Antes de migrar Equipos detalle (paso 4 — el más caro):** ¿Conservamos exactamente las 7 cards de Configuración (`TeamSettingsTab`) o las repensamos también?
4. **Persistencia tema:** ¿`localStorage` (rápido) o `org_members.preferred_appearance` desde el día 1 (más caro pero correcto)?
5. **Fuentes Geist/JetBrains Mono:** ¿self-host o vía Google Fonts CDN?
6. **Login rediseñado:** ¿se incluye en esta fase o se deja para fase posterior? (Está listo en `uploads/Login.tsx`).

---

## 10 · Próximos pasos cuando aprobemos

1. Crear branch `redesign/servicios` desde el HEAD actual.
2. Copiar `src/styles.css` → `src/tenant/styles/tenant.css` (limpiando el panel de tweaks y el mobile gallery — son sólo del prototipo).
3. Copiar `icons.jsx` → `src/tenant/components/Icons.tsx` con tipos.
4. Construir `<TenantShell>` (Sidebar + Topbar) wrapping el `Outlet` del router → tematizado por `<html data-theme>`.
5. Implementar dropdown "Mi Perfil" con los 3 modos.
6. Migrar Mi Planificación.
7. (... el resto sigue el orden de §5)

Cada paso = PR pequeño + screenshot before/after + smoke test manual.

---

_Plan generado: 2026-05-27. Aprobación pendiente._
