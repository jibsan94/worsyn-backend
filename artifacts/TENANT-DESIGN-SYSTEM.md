# Worsyn · Tenant Portal — Sistema de diseño

**Cargar este artefacto antes de tocar UI del portal tenant
(`/mnt/worsyn-dashboard/src/tenant/`). Esto no puede volver a salir feo.**

El portal tenant **NO** usa las clases CSS del admin (`.card`, `.btn-primary`).
Vive en su propio universo de **estilos inline** con la paleta `C` y la
máquina de estilos `s`. Todo lo aquí descrito está vivo en `Servicios.tsx`.

---

## Paleta `C` (tokens)

```ts
const C = {
  bg: '#F8FAFC',          // fondo de página
  surface: '#FFFFFF',     // fondo de cards / modals / tablas
  border: '#E2E8F0',      // borde por defecto
  soft: '#F1F5F9',        // hover suave / chips ligeros
  text: '#0F172A',        // texto principal
  muted: '#64748B',       // hints, labels secundarios
  light: '#94A3B8',       // texto débil, placeholders
  primary: '#4F46E5',     // indigo Worsyn — acción principal
  primaryLight: '#EEF2FF',// fondo seleccionado / chips activos
  primaryMid: '#6366F1',  // hover de primary
  success: '#10B981',
  successLight: '#ECFDF5',
  danger: '#EF4444',
  dangerLight: '#FEF2F2',
  warning: '#F59E0B',
}
```

Cualquier color nuevo debe entrar en `C`. No incrustar literales hex.

---

## Estilos base `s`

Tokens compartidos en `s: Record<string, React.CSSProperties>`:

- `s.main` — contenedor principal de página
- `s.mainTitle` — título de página (h2)
- `s.btnPrimary`, `s.btnGhost`, `s.btnDanger` — botones canónicos
- `s.iconBtn` — botón sólo-icono
- `s.label`, `s.input`, `s.select` — campos de formulario
- `s.overlay`, `s.modal`, `s.modalTitle`, `s.modalActions` — modales
- `s.pill` — chips/badges
- `s.planTable`, `s.planTh`, `s.planTd` — tablas
- `s.errorText` — mensaje de error

**Regla:** si un estilo se usa en 2+ sitios, va a `s`.

---

## Patrón **Card** (tarjeta de contenido)

Toda sección visual lleva contorno blanco con sombra suave:

```tsx
const cardStyle: React.CSSProperties = {
  background: C.surface,
  border: `1px solid ${C.border}`,
  borderRadius: 10,
  padding: '16px 18px',
  display: 'flex',
  flexDirection: 'column',
  gap: 0,                  // separadores se hacen con borderBottom en rows
}

const cardTitle: React.CSSProperties = {
  fontSize: 11, fontWeight: 700, color: C.muted,
  letterSpacing: '0.08em', textTransform: 'uppercase',
  paddingBottom: 12, marginBottom: 4,
  borderBottom: `1px solid ${C.border}`,
  display: 'flex', alignItems: 'center', gap: 8,  // espacio para icono
}
```

**Cuándo aplica:** tarjetas de settings, secciones de detalle, paneles de
información. NO en filas de tabla.

### Layout en cuadrícula

Cuando una página tiene varias cards relacionadas, **rejilla 2 columnas**:

```tsx
<div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
  <Card>…</Card>
  <Card>…</Card>
  …
  <Card style={{ gridColumn: '1 / -1' }}>…</Card>  {/* full-width */}
</div>
```

---

## Iconos

Worsyn usa **SVG inline** stroke 2, viewBox 24×24, tamaño 14–18 px. NO emojis
en cabeceras (los emojis quedan sólo para `flagCard` de tipos donde la
identidad pesa).

```tsx
<svg viewBox="0 0 24 24" width={16} height={16}
     fill="none" stroke="currentColor" strokeWidth={2}
     strokeLinecap="round" strokeLinejoin="round">
  <path d="M…" />
</svg>
```

### Icon set canónico (Lucide / Heroicons-style, NUNCA inventes paths)

| Concepto                  | SVG path (stroke=currentColor strokeWidth=2)              |
|---------------------------|-----------------------------------------------------------|
| settings / tipo equipo    | `<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>` |
| calendario / programación | `<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>`        |
| alerta / huecos           | `<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/>` |
| opciones / sliders        | `<path d="M21 4H14M10 4H3M21 12h-9M8 12H3M21 20h-7M10 20H3M14 2v4M8 10v4M14 18v4"/>`        |
| layers / tipos servicio   | `<path d="m12 2 10 6.5L12 15 2 8.5z"/><path d="m2 17.5 10 6.5 10-6.5"/><path d="m2 13 10 6.5L22 13"/>` |
| usuarios / equipos        | `<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>` |
| reciclar / reagendar      | `<path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5"/>` |
| eliminar                  | `<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>` |
| guardar / check           | `<path d="M20 6 9 17l-5-5"/>`                                                              |
| mail                      | `<path d="M4 6h16v12H4z"/><path d="M4 6l8 7 8-7"/>`                                        |
| imprimir                  | `<path d="M6 9V3h12v6"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 14h12v8H6z"/>` |
| añadir / plus             | `<path d="M12 5v14M5 12h14"/>`                                                             |

Usa **un componente `<Icon name="…" size={16}/>`** centralizado si lo prefieres.
Mientras no exista, pega el SVG inline. **NO inventes paths.**

---

## Transiciones

Toda interacción visible (hover, focus, expansión) lleva transición:

```tsx
style={{ transition: 'background 0.15s ease, border-color 0.15s ease, transform 0.1s ease' }}
```

- **Hover en card seleccionable** → borde a `C.primary`, fondo `rgba(79,70,229,0.04)`
- **Hover en fila de tabla** → fondo `C.bg` o `C.soft`, cursor pointer
- **Hover en botón primary** → fondo `C.primaryMid`
- **Botón disabled** → opacity 0.5, cursor not-allowed
- **Animaciones largas (modals)** → 0.18s ease-out para fade-in (overlay)

---

## Patrón **FlagCard** (selector tipo card)

Para selecciones booleanas con identidad (no checkboxes pelones):

```tsx
const flagCard = (
  active: boolean, onToggle: () => void,
  icon: ReactNode, title: string, desc: string,
) => (
  <div onClick={onToggle}
    style={{
      border: `1px solid ${active ? C.primary : C.border}`,
      background: active ? 'rgba(79,70,229,0.04)' : C.surface,
      borderRadius: 10, padding: 12, cursor: 'pointer',
      display: 'flex', gap: 10, alignItems: 'flex-start',
      transition: 'background 0.15s ease, border-color 0.15s ease',
    }}>
    <div style={{
      width: 18, height: 18, borderRadius: 4,
      border: `1px solid ${active ? C.primary : C.border}`,
      background: active ? C.primary : 'transparent',
      flexShrink: 0, marginTop: 2,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: 'white', fontSize: 12, fontWeight: 700,
    }}>{active ? '✓' : ''}</div>
    <div style={{ flex: 1 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
        <span style={{ display: 'flex', color: active ? C.primary : C.muted }}>{icon}</span>
        <span style={{ fontWeight: 600, fontSize: 13, color: C.text }}>{title}</span>
      </div>
      <div style={{ fontSize: 12, color: C.muted, lineHeight: 1.4 }}>{desc}</div>
    </div>
  </div>
)
```

Vive en `TeamFormModal.flagCard` (Servicios.tsx ~line 890). Cuando el contexto
sea un grupo de opciones booleanas relacionadas, **úsalo, no pongas checkboxes
sueltos**.

---

## Patrón **ChipPicker** (selección multi)

Para "tipos de servicio", "líderes", "equipos relacionados":

```tsx
// Chips activos (visibles)
<span style={{
  display: 'inline-flex', alignItems: 'center', gap: 3,
  background: C.soft, border: `1px solid ${C.border}`,
  borderRadius: 6, padding: '3px 6px 3px 9px',
  fontSize: 12, color: C.text,
}}>
  {label}
  <button onClick={remove} style={{
    background: 'none', border: 'none', cursor: 'pointer',
    color: C.muted, fontSize: 14, lineHeight: '1',
    transition: 'color 0.15s', /* hover: color = C.danger */
  }}>×</button>
</span>

// Dropdown para añadir
<button onClick={openDropdown} style={{ ...s.btnGhost, padding: '4px 10px', fontSize: 12 }}>
  + Añadir
</button>
```

Dropdown va absoluto, z-index 50, fondo blanco, sombra `0 4px 16px rgba(0,0,0,.12)`.

---

## Patrón **Row** (label + control)

Dentro de una card, cada par "label + valor":

```tsx
const row: React.CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  gap: 12, padding: '11px 0', borderBottom: `1px solid ${C.border}`,
}
const lastRow = { ...row, borderBottom: 'none', paddingBottom: 2 }

<div style={row}>
  <div>
    <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>Label</div>
    <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>Hint corto</div>
  </div>
  <select|input|checkbox|... />
</div>
```

---

## Patrón **Tab strip** (pestañas)

```tsx
<div style={{ display: 'flex', gap: 0, borderBottom: `1px solid ${C.border}`, marginBottom: 18 }}>
  {tabs.map(k => {
    const active = k === current
    return (
      <button key={k} onClick={() => setTab(k)}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          padding: '10px 16px', fontSize: 13, fontWeight: 600,
          color: active ? C.text : C.muted,
          borderBottom: `2px solid ${active ? C.primary : 'transparent'}`,
          marginBottom: -1,
          transition: 'color 0.15s, border-color 0.15s',
        }}>{label}</button>
    )
  })}
</div>
```

---

## Patrón **Modal**

Usa `s.overlay` + `s.modal`. Cabecera + cuerpo (overflow auto) + footer
sticky cuando el contenido sea alto:

```tsx
<div style={s.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
  <div style={{ ...s.modal, width: 560, maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}>
    <div style={{ padding: '20px 24px', borderBottom: `1px solid ${C.border}` }}>
      <h3 style={s.modalTitle}>Título</h3>
    </div>
    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 24px' }}>…</div>
    <div style={{ ...s.modalActions, padding: '14px 24px', borderTop: `1px solid ${C.border}` }}>
      <button style={s.btnGhost} onClick={onClose}>Cancelar</button>
      <button style={s.btnPrimary} onClick={save}>Guardar</button>
    </div>
  </div>
</div>
```

Siempre `useEscape(onClose)` en cada modal.

---

## Patrón **Botón con icono**

```tsx
<button style={s.btnPrimary} onClick={…}>
  <svg …/* icon canónico */>{/* … */}</svg>
  Guardar cambios
</button>
```

`s.btnPrimary` ya define `display: inline-flex, alignItems: center, gap: 6`.

---

## Reglas (no negociables)

1. **No CSS classes del admin.** Sólo inline styles + `C`/`s`.
2. **No emojis en cabeceras de cards.** SVG inline siempre.
3. **No literales hex sueltos.** Si necesitas un color nuevo, súbelo a `C`.
4. **Transiciones en TODO lo interactivo.** Hover, focus, expand.
5. **Cards en cuadrícula** cuando hay 3+ secciones relacionadas; nunca scroll
   infinito vertical de filas.
6. **FlagCard** para flags booleanos con identidad visual; checkbox pelado sólo
   para opciones sin descripción larga (1 línea).
7. **Components a module scope** (rule 35 del napkin) — nunca dentro de otra
   función React.
8. **useEscape** en todo modal.
9. **Sombras suaves**: cards `box-shadow: 0 1px 2px rgb(15 23 42 / 0.04)`,
   modals `0 8px 40px rgba(0,0,0,.18)`.
10. **Densidad: media-alta**. Padding 16–20px en cards, gap 12–14 entre rows.

---

## Checklist cuando crees una nueva vista del portal

- [ ] ¿Está construida sobre cards en cuadrícula?
- [ ] ¿Cada card tiene `cardTitle` con icono SVG?
- [ ] ¿Botones primary usan `s.btnPrimary`?
- [ ] ¿Inputs/selects usan `s.input`/`s.select`?
- [ ] ¿Modales usan `s.overlay` + `s.modal` + `useEscape`?
- [ ] ¿FlagCard para flags con identidad? ¿ChipPicker para multi-select?
- [ ] ¿Transiciones en hover/focus de TODO lo interactivo?
- [ ] ¿Componentes auxiliares en module scope?
- [ ] ¿Hay un artefacto en `artifacts/` documentando el cambio?

Si la respuesta a cualquiera es NO → no se merge. Worsyn merece pulido.
