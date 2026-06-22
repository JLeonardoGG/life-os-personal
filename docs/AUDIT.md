# Auditoria tecnica inicial

Fecha: 2026-06-21

## Estado encontrado

- Aplicacion PWA sin backend, construida en HTML, CSS y JavaScript global.
- `index.html` y `lifeos_dashboard.html` son copias exactas de 572,716 bytes.
- El documento principal contiene 9,193 lineas, 463 funciones globales y 169 manejadores HTML inline.
- Los datos principales se guardan en `localStorage` bajo `lifeos_data_v2`.
- Las fotografias se guardan en IndexedDB bajo `lifeos_photo_db_v1`, con fallback `lifeos_progress_photos_v1`.
- El backup existente exporta el estado completo y las fotografias a JSON.
- La PWA usa CDN para Tailwind, Chart.js, JSZip, PDF.js, SheetJS, Font Awesome y Google Fonts.
- El service worker y los scripts inline pasan validacion sintactica.
- La aplicacion responde en `127.0.0.1:8765` cuando se inicia un servidor HTTP. El fallo actual es la ausencia de un proceso de arranque persistente.

## Hallazgos prioritarios

1. Hay 127 referencias estaticas a elementos DOM que ya no existen.
2. Salud, bienestar, carrera, diario, calendario y coche conservan estado y funciones, pero perdieron sus pantallas navegables.
3. Al menos 44 funciones no tienen un punto de entrada visible en la interfaz actual.
4. La seccion de cuentas puede conservar contrasenas en texto plano dentro de `localStorage` y backups.
5. El RFC personal estaba incrustado como valor por defecto en el codigo.
6. No existen pruebas automatizadas, modelos de datos versionados ni migraciones.
7. Las dependencias CDN impiden garantizar uso offline.
8. No existe aislamiento entre datos personales, archivos cargados y codigo fuente.

## Decisiones de migracion

- La migracion a SQLite sera gradual y repetible.
- `localStorage` e IndexedDB permaneceran intactos hasta comprobar paridad por modulo.
- La boveda de contrasenas heredada no se migrara y su interfaz quedara desactivada.
- Los modulos ocultos se preservaran en el importador y se restauraran gradualmente.
- FastAPI escuchara solo en `127.0.0.1`.
- Los archivos originales se copiaran al directorio privado de datos y se deduplicaran con SHA-256.
- n8n y Ollama tendran contratos documentados, pero permaneceran desactivados.

## Mapa de estado heredado

| Estado actual | Destino V1 |
| --- | --- |
| `movements` | `transactions` |
| `finance.budgets` | `budgets` |
| `finance.closures` | `monthly_closures` |
| `finance.subscriptions` | `subscriptions` |
| `debtLedger` | `debts`, `debt_movements` |
| `investments` | `investments` |
| `uberTax.*` | `tax_documents`, `tax_entries` |
| `todos` | `tasks` |
| `calendar.events` | `events` |
| `routine`, `fitness`, `skincare` | `routines`, `health_logs` |
| `health`, `wellbeing` | `health_logs` |
| `academic` | `academic_courses`, `projects`, `notes` |
| `journal` | `notes` con tipo `journal` |
| `vehicle` | `car_logs`, `car_reminders` |
| fotografias IndexedDB | `uploaded_files` y archivos locales |
| `credentials` | excluido de la migracion |

## Regla de compatibilidad

Ningun dato heredado se elimina automaticamente. Cada importacion tendra vista previa, identificador de lote, deduplicacion y reporte de conteos antes de marcar un modulo como migrado.
