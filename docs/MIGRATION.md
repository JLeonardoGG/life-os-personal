# Migracion desde localStorage

## Fuente

- `localStorage.lifeos_data_v2`
- IndexedDB `lifeos_photo_db_v1`
- backups JSON V3

## Flujo

1. Life OS crea una sesion local.
2. El frontend copia el estado en memoria.
3. Elimina `state.credentials` antes de enviarlo.
4. `preview` devuelve conteos sin escribir.
5. `commit` crea un backup previo.
6. Cada registro obtiene un `legacy_key`.
7. SQLite guarda una copia saneada del estado para campos pendientes.
8. localStorage e IndexedDB permanecen intactos.

## Endpoint

```text
POST /api/import/localstorage?mode=preview
POST /api/import/localstorage?mode=commit
```

El hash del payload identifica lotes ya importados. Repetir el mismo commit devuelve `already_imported`.

## Correspondencias

Consulta la tabla completa en [AUDIT.md](AUDIT.md).

## Recuperacion

Antes de cada commit se generan:

- snapshot SQLite;
- export JSON;
- manifiesto con hashes SHA-256.

La retencion predeterminada conserva 30 respaldos diarios y 12 referencias mensuales.
