# Ollama y DeepSeek

La integracion se encuentra preparada, pero desactivada:

```env
LIFE_OS_AI_ENABLED=false
LIFE_OS_OLLAMA_URL=http://127.0.0.1:11434/api/generate
LIFE_OS_OLLAMA_MODEL=deepseek-r1:7b
```

`AIService` devuelve `disabled` sin realizar conexiones mientras la variable permanezca en `false`.

Cuando se habilite en una fase posterior, enviara:

```json
{
  "model": "deepseek-r1:7b",
  "prompt": "contexto y solicitud",
  "stream": false
}
```

La aplicacion maneja cuatro estados:

- `disabled`: configuracion apagada;
- `ok`: respuesta local valida;
- `unavailable`: Ollama no responde;
- `error`: timeout, HTTP invalido o respuesta no valida.

Finanzas, tareas, backups, importaciones y clasificacion por reglas nunca dependen de Ollama.
