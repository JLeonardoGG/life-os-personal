# Privacidad y seguridad local

Life OS esta disenado para funcionar en una sola computadora y mantener los datos fuera del repositorio.

## Datos prohibidos

Life OS V1 no debe guardar:

- contrasenas bancarias o del SAT;
- CVV, NIP o codigos de un solo uso;
- tokens bancarios o cookies de sesion;
- claves privadas;
- secretos dentro del codigo, logs o backups exportables.

## Archivos privados

La base SQLite, XML, estados de cuenta, facturas, fotos, uploads, logs y backups se guardan en:

`~/Library/Application Support/LifeOS/`

Estas rutas y extensiones estan excluidas por `.gitignore`.

## Boveda heredada

La seccion antigua de cuentas puede contener secretos en `localStorage`. No se migrara al backend, no se incluira en nuevos backups y su edicion se desactiva durante la migracion. El usuario debe trasladar contrasenas importantes a un gestor especializado.

## Red

FastAPI escuchara exclusivamente en `127.0.0.1`. No se habilitara CORS abierto ni acceso desde otros dispositivos durante V1.

## Automatizaciones

n8n usara una API key local. Ollama permanecera desactivado por defecto. Ninguna integracion externa se ejecutara sin habilitacion explicita posterior.

## Escritura financiera

Los montos se guardan como centavos enteros en SQLite. Las eliminaciones de transacciones,
presupuestos, suscripciones, deudas e inversiones usan `deleted_at`; no se borran fisicamente.
Los errores de API no disparan una segunda escritura silenciosa en localStorage.

Los reportes de paridad muestran solo conteos y totales agregados. No imprimen descripciones,
instituciones, numeros de cuenta ni payloads financieros completos en consola.

## Salud y coche

Los registros de salud se limitan a habitos, medidas y bienestar capturados por el usuario.
Life OS no genera diagnosticos ni tratamientos. Las fechas se almacenan en UTC y se presentan
en `America/Mexico_City`.

Las auditorias de Salud/Coche guardan tipo de entidad, accion, resultado e idempotencia. No
guardan notas, comidas, medidas corporales, placas ni payloads completos en `automation_logs`.
