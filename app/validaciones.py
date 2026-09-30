import re

def validar_cuadre(base: float, iva_importe: float, total: float, margen: float = 0.02) -> tuple[bool, str]:
    if None in (base, iva_importe, total):
        return False, "Faltan campos numéricos"
    esperado = round(base + iva_importe, 2)
    if abs(esperado - total) > margen:
        return False, f"No cuadra: {base} + {iva_importe} = {esperado} pero total es {total}"
    return True, ""

def validar_cif(cif: str) -> tuple[bool, str]:
    if not cif:
        return False, "CIF/NIF vacío"
    cif = cif.strip().upper()
    if re.match(r'^[A-Z]\d{7}[A-Z0-9]$', cif):
        return True, ""
    if re.match(r'^\d{8}[A-Z]$', cif):
        return True, ""
    return False, f"Formato de CIF/NIF no reconocido: {cif}"

def detectar_duplicado(db, proveedor: str, total: float, fecha: str, exclude_id: int) -> tuple[bool, str]:
    from app.models import Document
    if not all([proveedor, total, fecha]):
        return False, ""
    existente = db.query(Document).filter(
        Document.proveedor == proveedor,
        Document.total == total,
        Document.fecha == fecha,
        Document.id != exclude_id,
        Document.status != "error"
    ).first()
    if existente:
        return True, f"Posible duplicado del documento #{existente.id}"
    return False, ""

def validar_documento(db, doc) -> tuple[str, str]:
    """Devuelve (nuevo_status, motivo_revision)"""
    motivos = []

    ok, msg = validar_cuadre(doc.base_imponible, doc.iva_importe, doc.total)
    if not ok:
        motivos.append(msg)

    ok, msg = validar_cif(doc.cif)
    if not ok:
        motivos.append(msg)

    ok, msg = detectar_duplicado(db, doc.proveedor, doc.total, doc.fecha, doc.id)
    if ok:
        motivos.append(msg)

    if motivos:
        return "revisar", " | ".join(motivos)
    return "procesado", ""