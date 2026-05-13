# TEST 1 — Auth & Role Matrix
**Fecha:** 2026-05-11  
**Entorno:** localhost:8000 (Docker Compose — backend + PostgreSQL 16 + Redis 7)  
**Estado DB:** Reset limpio + seed automático (owner `worsyn`/`worsyn`)

---

## Escenario de prueba

Simula el primer arranque del sistema y valida el flujo completo de autenticación y permisos por rol.

---

## Casos evaluados

| # | Descripción | Resultado |
|---|-------------|-----------|
| T1.1 | Login owner `worsyn`/`worsyn` devuelve `access_token` | ✅ PASS |
| T1.2 | `must_change_password=true` en primer login | ✅ PASS |
| T1.3 | `role=owner` en la respuesta | ✅ PASS |
| T2.1 | `change-credentials` devuelve `status=ok` | ✅ PASS |
| T2.2 | Nuevo username retornado correctamente | ✅ PASS |
| T2.3 | Re-login con nuevas credenciales funciona | ✅ PASS |
| T2.4 | `must_change_password=false` tras cambio | ✅ PASS |
| T3.1 | Owner crea usuario admin → username correcto | ✅ PASS |
| T3.2 | Usuario creado tiene `role=admin` | ✅ PASS |
| T3.3 | Nuevo usuario arranca con `must_change_password=true` | ✅ PASS |
| T4.1 | Owner crea usuario normal → username correcto | ✅ PASS |
| T4.2 | Usuario creado tiene `role=user` | ✅ PASS |
| T4.3 | Usuario normal arranca con `must_change_password=true` | ✅ PASS |
| T5.1 | Login como `admin_test` devuelve `access_token` | ✅ PASS |
| T5.2 | Admin tiene `must_change_password=true` en primer login | ✅ PASS |
| T5.3 | `role=admin` en la respuesta | ✅ PASS |
| T5.4 | Admin forzado a cambiar credenciales → `status=ok` | ✅ PASS |
| T5.5 | Admin re-login con nueva contraseña funciona | ✅ PASS |
| T5.6 | `must_change_password=false` tras cambio de admin | ✅ PASS |
| T6.1 | Login como `user_test` devuelve `access_token` | ✅ PASS |
| T6.2 | Usuario normal tiene `must_change_password=true` | ✅ PASS |
| T6.3 | `role=user` en la respuesta | ✅ PASS |
| T6.4 | Usuario normal forzado a cambiar credenciales → `status=ok` | ✅ PASS |
| T6.5 | Usuario normal re-login funciona | ✅ PASS |
| T6.6 | `must_change_password=false` tras cambio de usuario normal | ✅ PASS |
| T7.1 | Owner puede editar `full_name` de cualquier usuario | ✅ PASS |
| T8.1 | Admin puede editar `full_name` de usuario normal | ✅ PASS |
| T9.1 | Usuario normal recibe `403 Insufficient permissions` al intentar listar admin_users | ✅ PASS |
| T10.1 | Owner puede crear un segundo owner con `role=owner` | ✅ PASS |
| T10.2 | Owner2 tiene username correcto | ✅ PASS |
| T10.3 | Owner puede leer (GET) a owner2 | ✅ PASS |
| T10.4 | Owner puede editar (PUT) a owner2 | ✅ PASS |
| T10.5 | Owner puede eliminar (DELETE) a owner2 → 204 | ✅ PASS |
| T11.1 | Admin NO puede eliminar a un owner → `403` | ✅ PASS |
| T11.2 | Admin NO puede editar a un owner → `403` | ✅ PASS |
| T11.3 | Admin NO puede crear un nuevo owner → `403` | ✅ PASS |
| T11.4 | Admin NO puede promover a un usuario a role=owner → `403` | ✅ PASS |
| T11.5 | Admin SÍ puede listar todos los usuarios | ✅ PASS |
| T11.6 | Admin SÍ puede eliminar un usuario normal → `204` | ✅ PASS |

---

## Resultado final

| Métrica | Valor |
|---------|-------|
| **Total casos** | 39 |
| **PASS** | 39 ✅ |
| **FAIL** | 0 ❌ |
| **Cobertura** | 100% |

---

## Flujo completo validado

```
Sistema vacío
    │
    ▼
[SEED] Owner worsyn/worsyn creado (must_change_password=true)
    │
    ▼
T1 → Login owner → token OK + must_change=true + role=owner
    │
    ▼
T2 → change-credentials → must_change=false, re-login OK
    │
    ├── T3 → Owner crea admin_test (must_change=true, role=admin)
    ├── T4 → Owner crea user_test  (must_change=true, role=user)
    │
    ▼
T5 → Login admin → must_change=true → change → re-login OK
T6 → Login user  → must_change=true → change → re-login OK
    │
    ├── T7  → Owner edita user           ✅
    ├── T8  → Admin edita user           ✅
    ├── T9  → User NO puede listar admins → 403  ✅
    │
    ├── T10 → Owner crea owner2, READ/UPDATE/DELETE  ✅
    │
    └── T11 → Admin:
             DELETE  owner  → 403  ✅
             EDIT    owner  → 403  ✅
             CREATE  owner  → 403  ✅
             PROMOTE → owner → 403  ✅
             LIST users     → 200  ✅
             DELETE user    → 204  ✅
```

---

## Notas técnicas

- La API devuelve JSON compacto (sin espacios en campos); las aserciones usan extracción por campo con `python3 -c json.load`.
- El campo `must_change_password` devuelve Python `True`/`False` al extraer el campo directamente.
- Emails `.local` aceptados correctamente por el validador personalizado (`@` + `.` en dominio).
- Los tokens no expiran durante el test (validez 30 min).
- El script de test vive en `/tmp/test01.sh` en el servidor.

---

*Siguiente test: TEST-02 (pendiente de definir)*
