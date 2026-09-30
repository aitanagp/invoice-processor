import os
import json
from pathlib import Path
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Asegúrate de que tienes un archivo .env en la misma carpeta que uvicorn 
# con la línea: GEMINI_API_KEY="tu_clave_aqui"
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

PROMPT = """Analiza esta factura y extrae los siguientes datos.
Devuelve el resultado con esta estructura exacta.
Si no encuentras algún campo, ponlo como null.

{
  "proveedor": "nombre de la empresa que emite la factura",
  "cif": "CIF o NIF del proveedor",
  "fecha": "YYYY-MM-DD",
  "base_imponible": 0.00,
  "iva_porcentaje": 21,
  "iva_importe": 0.00,
  "total": 0.00
}
"""

def extraer_datos_factura(filepath: str):
    path = Path(filepath)
    ext = path.suffix.lower()

    with open(path, "rb") as f:
        file_bytes = f.read()

    if ext == ".pdf":
        mime_type = "application/pdf"
    elif ext in [".jpg", ".jpeg"]:
        mime_type = "image/jpeg"
    else:
        mime_type = "image/png"

    try:
        # Usamos GenerateContentConfig para FORZAR un JSON perfecto
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                PROMPT
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        raw = response.text.strip()
        datos = json.loads(raw)
        return datos, raw

    except Exception as e:
        # ¡Magia! Si algo falla, ahora se imprimirá en tu consola de color rojo o blanco
        print(f"\n❌ ERROR EN GEMINI: {e}\n")
        raise e