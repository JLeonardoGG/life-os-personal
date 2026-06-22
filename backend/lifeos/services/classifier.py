from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

MEXICO_CITY = ZoneInfo("America/Mexico_City")


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.lower())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _amount(message: str) -> float | None:
    matches = re.findall(r"(?:\$|mxn\s*)?(\d{1,7}(?:[.,]\d{1,2})?)", message, re.IGNORECASE)
    if not matches:
        return None
    return float(matches[-1].replace(",", "."))


def _due_at(message: str, received_at: datetime) -> str | None:
    normalized = _normalize(message)
    local = received_at.astimezone(MEXICO_CITY)
    target = None
    if "pasado manana" in normalized:
        target = local + timedelta(days=2)
    elif "manana" in normalized:
        target = local + timedelta(days=1)
    elif "hoy" in normalized:
        target = local
    time_match = re.search(r"\b(?:a\s+las?\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", normalized)
    if target and time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        suffix = time_match.group(3)
        if suffix == "pm" and hour < 12:
            hour += 12
        if suffix == "am" and hour == 12:
            hour = 0
        target = target.replace(hour=min(hour, 23), minute=min(minute, 59), second=0, microsecond=0)
    elif target:
        target = target.replace(hour=9, minute=0, second=0, microsecond=0)
    return target.isoformat() if target else None


def classify_message(message: str, received_at: datetime) -> dict:
    normalized = _normalize(message)
    amount = _amount(message)
    due_at = _due_at(message, received_at)

    expense_words = ("gaste", "pague", "compre", "costo", "gasolina", "despensa")
    reminder_words = ("recuerdame", "recordarme", "no olvidar", "avisa")
    event_words = ("cita", "reunion", "evento", "clase", "consulta")
    task_words = ("pendiente", "tengo que", "debo hacer", "hacer ")

    if amount is not None and any(word in normalized for word in expense_words):
        category = "Transporte" if "gasolina" in normalized or "uber" in normalized else "Otro"
        if "despensa" in normalized or "super" in normalized:
            category = "Comida"
        return {
            "type": "expense",
            "confidence": 0.9,
            "rule": "expense_amount",
            "payload": {
                "date": received_at.astimezone(MEXICO_CITY).date().isoformat(),
                "type": "gasto",
                "category": category,
                "name": message.strip(),
                "amount": amount,
                "source": "inbox",
            },
        }
    if any(word in normalized for word in reminder_words):
        return {
            "type": "reminder",
            "confidence": 0.85,
            "rule": "reminder_phrase",
            "payload": {
                "title": message.strip(),
                "due_at": due_at,
                "priority": "normal",
                "source": "inbox",
            },
        }
    if any(word in normalized for word in event_words) and due_at:
        return {
            "type": "event",
            "confidence": 0.75,
            "rule": "event_with_date",
            "payload": {
                "title": message.strip(),
                "starts_at": due_at,
                "source": "inbox",
            },
        }
    if any(word in normalized for word in task_words):
        return {
            "type": "task",
            "confidence": 0.7,
            "rule": "task_phrase",
            "payload": {
                "title": message.strip(),
                "due_at": due_at,
                "priority": "normal",
                "source": "inbox",
            },
        }
    return {
        "type": "note",
        "confidence": 0.4,
        "rule": "fallback_note",
        "payload": {
            "title": "Mensaje recibido",
            "body": message.strip(),
            "note_type": "inbox",
        },
    }
