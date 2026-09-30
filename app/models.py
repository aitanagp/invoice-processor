from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Document(Base):
    __tablename__ = "documents"

    id            = Column(Integer, primary_key=True, index=True)
    filename      = Column(String(255), nullable=False)
    status        = Column(String(50), default="pendiente")  # pendiente | procesando | procesado | revisar | error
    
    # Datos extraídos por la IA
    proveedor     = Column(String(255))
    cif           = Column(String(20))
    fecha         = Column(String(20))
    base_imponible = Column(Float)
    iva_porcentaje = Column(Float)
    iva_importe   = Column(Float)
    total         = Column(Float)
    
    # Metadata
    error_msg     = Column(Text)
    raw_response  = Column(Text)   # respuesta raw de la IA, para depurar
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)