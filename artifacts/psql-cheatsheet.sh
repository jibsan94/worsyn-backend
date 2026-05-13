#!/usr/bin/env bash
# ============================================================
#  Worsyn — PostgreSQL cheatsheet
#  Contenedor: worsyn-db  |  Usuario: worsyn  |  BD: worsyn
# ============================================================

# ── Entrar al contenedor ────────────────────────────────────
docker exec -it worsyn-db psql -U worsyn -d worsyn

# ── Entrar a una BD específica directamente ─────────────────
docker exec -it worsyn-db psql -U worsyn -d nombre_bd

# ── Ejecutar query sin entrar al contenedor ─────────────────
docker exec worsyn-db psql -U worsyn -d worsyn -c "SELECT * FROM organizations;"


# ============================================================
#  Dentro del prompt psql (worsyn=#)
# ============================================================

# ── Seleccionar / cambiar de base de datos ──────────────────
\c nombre_bd                  # conectarse a otra BD
\c worsyn                     # volver a la BD principal

# ── Exploración ─────────────────────────────────────────────
\l                            # listar todas las BDs
\dt                           # listar tablas de la BD actual
\dt *.*                       # tablas de todos los schemas
\dn                           # listar schemas
\d nombre_tabla               # describir estructura de una tabla
\d+ nombre_tabla              # descripción extendida (con tamaños)
\du                           # listar roles/usuarios

# ── Consultas ───────────────────────────────────────────────
SELECT * FROM organizations;
SELECT * FROM organizations LIMIT 10;
SELECT id, name, plan, status FROM organizations WHERE status = 'active';
SELECT COUNT(*) FROM users;
SELECT * FROM users WHERE org_id = 'uuid-aqui';

# ── Crear base de datos ─────────────────────────────────────
CREATE DATABASE nombre_bd;
CREATE DATABASE nombre_bd OWNER worsyn;
DROP DATABASE nombre_bd;       # ¡cuidado!

# ── Crear schema (para multi-tenant por schema) ─────────────
CREATE SCHEMA org_uuid_aqui;
SET search_path TO org_uuid_aqui, public;

# ── Migraciones Alembic ─────────────────────────────────────
# Generar migración automática desde modelos SQLAlchemy
docker compose -f /mnt/worsyn-backend/docker-compose.yml exec backend \
  alembic revision --autogenerate -m "descripcion"

# Aplicar todas las migraciones pendientes
docker compose -f /mnt/worsyn-backend/docker-compose.yml exec backend \
  alembic upgrade head

# Ver historial de migraciones aplicadas
docker compose -f /mnt/worsyn-backend/docker-compose.yml exec backend \
  alembic history

# Revertir última migración
docker compose -f /mnt/worsyn-backend/docker-compose.yml exec backend \
  alembic downgrade -1

# ── Salir de psql ───────────────────────────────────────────
\q
