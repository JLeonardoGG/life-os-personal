# Automatizaciones y n8n

n8n no se ejecuta ni se configura automaticamente en V1. Life OS solo expone contratos locales.

## Autenticacion

Todas las rutas de automatizacion requieren:

```http
X-LifeOS-API-Key: <clave local>
Idempotency-Key: <identificador unico para la escritura>
Content-Type: application/json
```

La clave se genera en:

```text
~/Library/Application Support/LifeOS/.env
```

No debe copiarse al repositorio.

## Recibir mensaje

```bash
curl -X POST http://127.0.0.1:8765/api/inbox/message \
  -H "X-LifeOS-API-Key: $LIFE_OS_API_KEY" \
  -H "Idempotency-Key: n8n-demo-001" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "n8n",
    "message": "Gasté $180 en gasolina",
    "timestamp": "2026-06-21T22:30:00-06:00",
    "external_id": "mensaje-demo",
    "metadata": {}
  }'
```

Respuesta: mensaje `pending_review` con `proposed_type` y `proposed_payload`.

## Revision humana

```bash
curl http://127.0.0.1:8765/api/inbox/messages \
  -H "X-LifeOS-API-Key: $LIFE_OS_API_KEY"
```

Confirmar:

```bash
curl -X POST http://127.0.0.1:8765/api/inbox/messages/<ID>/confirm \
  -H "X-LifeOS-API-Key: $LIFE_OS_API_KEY" \
  -H "Idempotency-Key: n8n-confirm-001"
```

Rechazar:

```bash
curl -X POST http://127.0.0.1:8765/api/inbox/messages/<ID>/reject \
  -H "X-LifeOS-API-Key: $LIFE_OS_API_KEY" \
  -H "Idempotency-Key: n8n-reject-001"
```

## Rutas disponibles

n8n podra usar los CRUD normales para transacciones, tareas, eventos, rutinas y salud, consultar `/api/summary/today` y solicitar `/api/backup/create`.

Cada nodo HTTP Request debe apuntar a `127.0.0.1`; por tanto, n8n tendra que ejecutarse en la misma Mac.

## Garantias

- Repetir un `Idempotency-Key` no duplica el mensaje.
- El clasificador por reglas funciona sin IA.
- Ninguna propuesta se aplica sin confirmacion.
- `automation_logs` no almacena el texto completo ni secretos.
