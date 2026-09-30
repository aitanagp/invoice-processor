# Invoice Processor

Procesador automático de facturas para pymes. Extrae datos de PDFs e imágenes
usando IA, los valida y los presenta en un dashboard con exportación a Excel.

## Problema que resuelve

Una gestoría con 60 clientes puede recibir más de 1.500 facturas al mes.
Introducirlas a mano son unas 75 horas de trabajo repetitivo y con errores.
Este sistema las procesa automáticamente, marca las dudosas para revisión humana
y reduce el trabajo manual a supervisar excepciones.

## Funcionalidades

- Subida de facturas en PDF, JPG y PNG (múltiples a la vez)
- Extracción automática de datos con IA (Gemini)
- Procesamiento en paralelo con Celery + Redis
- Validaciones automáticas: cuadre de importes, formato CIF/NIF, duplicados
- Pantalla de revisión humana para facturas con incidencias
- Dashboard con gasto por mes, top proveedores y estado de documentos
- Exportación a Excel con totales automáticos

## Stack

Python · FastAPI · PostgreSQL · SQLAlchemy · Celery · Redis · Google Gemini · Docker

## Rendimiento

| Modo | 20 facturas |
|------|------------|
| Secuencial | ~60 segundos |
| Paralelo (4 workers) | ~18 segundos |

## Arrancar en local

Requisitos: Docker Desktop

```bash
git clone https://github.com/tuusuario/invoice-processor
cd invoice-processor
cp .env.example .env  # añade tu GEMINI_API_KEY
docker-compose up --build
```

Abre http://localhost:8000

## Estructura

```
app/
├── main.py         # endpoints FastAPI
├── models.py       # modelos SQLAlchemy
├── database.py     # conexión a PostgreSQL
├── extractor.py    # extracción con Gemini
├── validaciones.py # validación de datos
├── tasks.py        # tareas Celery
└── worker.py       # configuración Celery
```