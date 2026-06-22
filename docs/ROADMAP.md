# Roadmap

## V1: fundamento local

- [x] Auditoria y saneamiento.
- [x] FastAPI, SQLite, SQLAlchemy y Alembic.
- [x] APIs de finanzas, tareas, eventos, rutina, salud, coche y SAT.
- [x] Importador gradual y backups.
- [x] Inbox y contratos n8n.
- [x] Adaptador Ollama desactivado.
- [x] Dependencias frontend offline.
- [x] Arranque automatico en macOS.
- [x] Fase 2: cliente API, estado del backend y data provider por dominio.
- [x] Dashboard con resumen API y fallback local.
- [x] Tareas y eventos con CRUD API y fallback local.
- [x] Finanzas con lectura API, conversion monetaria y comparacion de paridad.
- [x] PWA sin cachear respuestas `/api/*`.
- [x] Fase 3: transacciones con escritura idempotente, auditoria y borrado logico.
- [x] Presupuestos, suscripciones y deudas con puente API.
- [x] Inversiones en lectura API con escritura preparada y desactivada.
- [x] Paginacion financiera completa sin limite practico de 500 registros.
- [x] Fase 4: Salud, bienestar y rutinas con lectura API y fallback.
- [x] Fase 4: Coche, perfil, obligaciones y mantenimiento con lectura API y fallback.
- [x] CRUD idempotente, auditoria, borrado logico y paginacion para Salud/Coche.
- [x] Importador `v4-health-car` y verificacion de paridad por dominio.
- [ ] Cambiar cada vista de `localStorage` a API tras validar paridad.
- [ ] Migrar Carrera, Diario y Calendario.

## V1.1

- Panel de revision del inbox dentro de la PWA.
- Historial de importaciones y restauracion asistida.
- Validar y activar gradualmente escrituras de Salud/Rutinas/Coche.
- Validar escrituras financieras con una copia de datos y activar dominio por dominio.
- Edicion completa sobre SQLite por dominio.
- Pruebas visuales y de accesibilidad.

## Futuro

- Activacion opcional de n8n.
- Activacion opcional de Ollama/DeepSeek.
- Google Calendar y Gmail con OAuth.
- WhatsApp mediante proveedor oficial.
- Acceso movil autenticado y cifrado.

No se contempla conexion bancaria directa ni presentacion automatica de declaraciones.
