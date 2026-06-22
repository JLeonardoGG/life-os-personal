from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from defusedxml import ElementTree

from lifeos.serializers import to_cents


class TaxXmlError(ValueError):
    pass


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1]


def _attr(node, name: str, default: str = "") -> str:
    for key, value in node.attrib.items():
        if _local_name(key).lower() == name.lower():
            return value
    return default


def _decimal(value: str | None) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except InvalidOperation:
        return Decimal(0)


def _find_first(root, local_name: str):
    return next((node for node in root.iter() if _local_name(node.tag) == local_name), None)


def _sum_tax(root, container_name: str, tax_code: str) -> Decimal:
    total = Decimal(0)
    for node in root.iter():
        if _local_name(node.tag) != container_name:
            continue
        if _attr(node, "Impuesto") == tax_code:
            total += _decimal(_attr(node, "Importe"))
    return total


def parse_tax_xml(
    content: bytes,
    requested_kind: str = "auto",
    taxpayer_rfc: str = "",
) -> dict[str, Any]:
    upper = content[:4096].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise TaxXmlError("XML con entidades externas no permitido")
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise TaxXmlError("XML invalido") from exc

    root_name = _local_name(root.tag)
    source_hash = hashlib.sha256(content).hexdigest()
    if root_name.lower() == "retenciones":
        issue_value = _attr(root, "FechaExp") or _attr(root, "Fecha")
        issue_date = _parse_date(issue_value)
        issuer = _find_first(root, "Emisor")
        receiver = _find_first(root, "Receptor")
        totals = _find_first(root, "Totales")
        uuid_node = _find_first(root, "TimbreFiscalDigital")
        total_withheld = _decimal(_attr(totals, "montoTotRet")) if totals is not None else Decimal(0)
        return {
            "document_kind": "retention",
            "period": issue_date.strftime("%Y-%m"),
            "document_date": issue_date,
            "uuid": _attr(uuid_node, "UUID").upper() if uuid_node is not None else None,
            "issuer_rfc": _attr(issuer, "RfcE") if issuer is not None else "",
            "receiver_rfc": _attr(receiver, "RfcRecep") if receiver is not None else "",
            "subtotal_cents": 0,
            "tax_transferred_cents": 0,
            "tax_withheld_cents": to_cents(total_withheld),
            "total_cents": to_cents(_attr(totals, "montoTotOperacion") if totals is not None else 0),
            "source_hash": source_hash,
            "summary": {"root": root_name, "total_withheld": float(total_withheld)},
        }

    if root_name != "Comprobante":
        raise TaxXmlError(f"Tipo XML no soportado: {root_name}")

    issue_date = _parse_date(_attr(root, "Fecha"))
    issuer = _find_first(root, "Emisor")
    receiver = _find_first(root, "Receptor")
    uuid_node = _find_first(root, "TimbreFiscalDigital")
    issuer_rfc = _attr(issuer, "Rfc") if issuer is not None else ""
    receiver_rfc = _attr(receiver, "Rfc") if receiver is not None else ""
    normalized_taxpayer = taxpayer_rfc.strip().upper()
    kind = requested_kind
    if kind == "auto":
        if normalized_taxpayer and issuer_rfc.upper() == normalized_taxpayer:
            kind = "income"
        elif normalized_taxpayer and receiver_rfc.upper() == normalized_taxpayer:
            kind = "expense"
        else:
            kind = "unknown"

    iva_transferred = _sum_tax(root, "Traslado", "002")
    isr_withheld = _sum_tax(root, "Retencion", "001")
    iva_withheld = _sum_tax(root, "Retencion", "002")
    concepts = []
    for node in root.iter():
        if _local_name(node.tag) == "Concepto":
            description = _attr(node, "Descripcion")
            if description:
                concepts.append(description)

    return {
        "document_kind": kind,
        "period": issue_date.strftime("%Y-%m"),
        "document_date": issue_date,
        "uuid": _attr(uuid_node, "UUID").upper() if uuid_node is not None else None,
        "issuer_rfc": issuer_rfc,
        "receiver_rfc": receiver_rfc,
        "subtotal_cents": to_cents(_attr(root, "SubTotal")),
        "tax_transferred_cents": to_cents(iva_transferred),
        "tax_withheld_cents": to_cents(isr_withheld + iva_withheld),
        "total_cents": to_cents(_attr(root, "Total")),
        "source_hash": source_hash,
        "summary": {
            "root": root_name,
            "voucher_type": _attr(root, "TipoDeComprobante"),
            "currency": _attr(root, "Moneda"),
            "payment_method": _attr(root, "MetodoPago"),
            "payment_form": _attr(root, "FormaPago"),
            "isr_withheld": float(isr_withheld),
            "iva_withheld": float(iva_withheld),
            "concepts": concepts[:30],
        },
    }


def _parse_date(value: str) -> date:
    if not value:
        raise TaxXmlError("XML sin fecha")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise TaxXmlError("Fecha XML invalida") from exc
