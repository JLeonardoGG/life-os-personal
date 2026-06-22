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

## Fase 2: Frontend API Bridge

La migracion de datos y el cambio de fuente son pasos separados:

1. Ejecutar `preview`.
2. Revisar conteos y diferencias.
3. Ejecutar `commit`.
4. Abrir el modulo y confirmar la etiqueta de fuente.
5. Comparar registros y totales antes de retirar el fallback.

Los flags se encuentran en `frontend/assets/js/core/featureFlags.js`:

```js
export const FEATURE_FLAGS = {
  useApiForSummary: true,
  useApiForTransactions: true,
  useApiForBudgets: true,
  useApiForSubscriptions: true,
  useApiForDebts: true,
  useApiForInvestments: true,
  useApiForTasks: true,
  useApiForEvents: true,
  useApiForHealth: true,
  useApiForRoutines: true,
  useApiForCar: true,
  useApiForTax: false,
  allowLocalStorageFallback: true,
  showBackendStatus: true,
};
```

Finanzas permanece en lectura:

```js
export const FINANCE_WRITE_FLAGS = {
  useApiForTransactionWrites: false,
  useApiForBudgetWrites: false,
  useApiForSubscriptionWrites: false,
  useApiForDebtWrites: false,
  useApiForInvestmentWrites: false,
};
```

Cuando Finanzas usa SQLite, la interfaz compara cantidad, ingresos y gastos del mes contra
localStorage. Muestra `paridad OK` o `revisar paridad`. Mientras la escritura API siga apagada,
la captura de movimientos se bloquea en modo SQLite para evitar datos invisibles o duplicados.

### Probar sin backend

En macOS, detener temporalmente el LaunchAgent:

```bash
launchctl bootout "gui/$(id -u)/com.lifeos.personal"
```

Recargar la PWA y confirmar:

- `Backend no disponible`;
- `Usando localStorage fallback`;
- dashboard, tareas y finanzas siguen abriendo.

Restaurar siempre el servicio:

```bash
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.lifeos.personal.plist"
curl http://127.0.0.1:8765/api/health
```

No desactivar `allowLocalStorageFallback` ni borrar `lifeos_data_v2` hasta validar todos los
dominios, archivos y fotografias.

## Fase 3: Finanzas SQLite Write Bridge

Lecturas API activas:

- transacciones;
- presupuestos;
- suscripciones;
- deudas y sus movimientos;
- inversiones.

Escrituras API disponibles pero desactivadas por defecto:

```js
export const FINANCE_WRITE_FLAGS = {
  useApiForTransactionWrites: false,
  useApiForBudgetWrites: false,
  useApiForSubscriptionWrites: false,
  useApiForDebtWrites: false,
  useApiForInvestmentWrites: false,
};
```

Para una prueba controlada se puede activar un flag desde la consola local:

```js
setLifeOSFinanceWriteFlag('useApiForTransactionWrites', true)
```

Antes de activarlo:

1. Crear un backup V1.
2. Abrir Finanzas y pulsar `Verificar paridad financiera`.
3. Confirmar conteos, ingresos, gastos, deuda y suscripciones.
4. Activar un solo dominio.
5. Crear, editar y borrar un registro demo.
6. Volver a desactivar el flag.

`Idempotency-Key` evita duplicar altas de transacciones. Los borrados financieros son logicos
mediante `deleted_at`. El frontend nunca hace doble escritura API + localStorage y pagina hasta
completar todos los registros.

## Fase 4: Salud y Coche en SQLite

El importador `v4-health-car` agrega:

- peso y medidas;
- estado diario de calorias, agua, actividad, macros y meta corporal;
- comidas y sueño/animo;
- rutina semanal, gym, cardio, skincare y notas de habitos;
- kilometraje, servicios, mantenimiento, obligaciones y perfil del vehiculo.

Las comidas legacy sin fecha usan la fecha del respaldo y quedan marcadas con
`inferredDate: true`. `preview` reporta conteos, fechas inferidas, candidatos duplicados y campos
no migrados. El hash incluye la version del importador, por lo que una instalacion que ya migro
finanzas puede ejecutar una sola migracion adicional de Salud/Coche sin duplicar lo anterior.

Escrituras experimentales:

```js
setLifeOSHealthWriteFlag('useApiForHealthWrites', true)
setLifeOSRoutineWriteFlag('useApiForRoutineWrites', true)
setLifeOSCarWriteFlag('useApiForCarWrites', true)
```

Desactivar de nuevo:

```js
setLifeOSHealthWriteFlag('useApiForHealthWrites', false)
setLifeOSRoutineWriteFlag('useApiForRoutineWrites', false)
setLifeOSCarWriteFlag('useApiForCarWrites', false)
```

Validacion recomendada:

1. Crear backup V1.
2. Ejecutar vista previa de migracion.
3. Ejecutar commit solo despues de revisar el reporte.
4. Recargar la PWA.
5. Ejecutar `verifyLifeOSHealthCarParity()` en la consola.
6. Activar un solo flag de escritura y probar un registro demo.

El reporte separa Salud/Rutinas de Coche. No eliminar `lifeos_data_v2` aunque la paridad sea cero;
seguira siendo el fallback hasta una fase posterior.
