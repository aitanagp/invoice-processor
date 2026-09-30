from app.worker import celery_app
from app.database import SessionLocal
from app.models import Document
from app.extractor import extraer_datos_factura
from app.validaciones import validar_documento

@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def procesar_factura(self, document_id: int, filepath: str):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return

        doc.status = "procesando"
        db.commit()

        datos, raw = extraer_datos_factura(filepath)

        doc.proveedor       = datos.get("proveedor")
        doc.cif             = datos.get("cif")
        doc.fecha           = datos.get("fecha")
        doc.base_imponible  = datos.get("base_imponible")
        doc.iva_porcentaje  = datos.get("iva_porcentaje")
        doc.iva_importe     = datos.get("iva_importe")
        doc.total           = datos.get("total")
        doc.raw_response    = raw

        # Validar antes de marcar como procesado
        nuevo_status, motivo = validar_documento(db, doc)
        doc.status    = nuevo_status
        doc.error_msg = motivo if motivo else None
        db.commit()

    except Exception as exc:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            if self.request.retries < self.max_retries:
                doc.status = "pendiente"
                db.commit()
                raise self.retry(exc=exc)
            else:
                doc.status    = "error"
                doc.error_msg = str(exc)
                db.commit()
    finally:
        db.close()