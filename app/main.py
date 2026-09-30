import os
import shutil
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import func
from fastapi.responses import StreamingResponse
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from io import BytesIO

load_dotenv()

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Document
from app.tasks import procesar_factura

app = FastAPI(title="Invoice Processor")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@app.post("/upload")
async def upload_factura(file: UploadFile = File(...), db: Session = Depends(get_db)):
    allowed = [".pdf", ".jpg", ".jpeg", ".png"]
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail="Formato no permitido.")

    dest = UPLOAD_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    doc = Document(filename=file.filename, status="pendiente")
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Encola la tarea — devuelve inmediatamente
    procesar_factura.delay(doc.id, str(dest))

    return {"id": doc.id, "status": "pendiente"}


@app.get("/documents")
def listar_documentos(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return docs


@app.get("/documents/{doc_id}/status")
def estado_documento(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return {"id": doc.id, "status": doc.status, "error": doc.error_msg}

@app.get("/revisar", response_class=HTMLResponse)
def pantalla_revision(db: Session = Depends(get_db)):
    docs = db.query(Document).filter(Document.status == "revisar").order_by(Document.created_at.desc()).all()
    filas = ""
    for d in docs:
        filas += f"""
        <tr id="fila-{d.id}">
          <td>{d.filename}</td>
          <td><input id="proveedor-{d.id}" value="{d.proveedor or ''}"></td>
          <td><input id="cif-{d.id}" value="{d.cif or ''}"></td>
          <td><input id="fecha-{d.id}" value="{d.fecha or ''}"></td>
          <td><input id="base-{d.id}" type="number" step="0.01" value="{d.base_imponible or ''}"></td>
          <td><input id="iva-{d.id}" type="number" step="0.01" value="{d.iva_importe or ''}"></td>
          <td><input id="total-{d.id}" type="number" step="0.01" value="{d.total or ''}"></td>
          <td style="color:orange;font-size:12px">{d.error_msg or ''}</td>
          <td>
            <button onclick="confirmar({d.id})">Confirmar</button>
            <button onclick="descartar({d.id})" style="margin-left:4px;background:#c00">Descartar</button>
          </td>
        </tr>"""

    return f"""
    <html><head><title>Revisión</title>
    <style>
      body {{ font-family:sans-serif; max-width:1200px; margin:40px auto; padding:0 20px; }}
      h1 {{ font-size:20px; margin-bottom:20px; }}
      a {{ font-size:13px; color:#555; }}
      table {{ width:100%; border-collapse:collapse; font-size:12px; margin-top:16px; }}
      th {{ text-align:left; border-bottom:2px solid #eee; padding:8px; }}
      td {{ padding:6px 8px; border-bottom:1px solid #f0f0f0; vertical-align:middle; }}
      input {{ width:100%; border:1px solid #ddd; border-radius:4px; padding:4px 6px; font-size:12px; }}
      button {{ padding:5px 12px; background:#1a1a1a; color:white; border:none; border-radius:4px; cursor:pointer; font-size:12px; }}
      .vacio {{ color:#888; padding:20px 0; }}
    </style></head>
    <body>
      <h1>Facturas para revisar</h1>
      <a href="/">Volver al inicio</a>
      <table>
        <thead><tr>
          <th>Archivo</th><th>Proveedor</th><th>CIF</th><th>Fecha</th>
          <th>Base</th><th>IVA</th><th>Total</th><th>Motivo</th><th>Acción</th>
        </tr></thead>
        <tbody>{''.join([filas]) if docs else '<tr><td colspan=9 class=vacio>No hay facturas pendientes de revisión</td></tr>'}</tbody>
      </table>
      <script>
        async function confirmar(id) {{
          const body = {{
            proveedor: document.getElementById('proveedor-'+id).value,
            cif:       document.getElementById('cif-'+id).value,
            fecha:     document.getElementById('fecha-'+id).value,
            base_imponible: parseFloat(document.getElementById('base-'+id).value),
            iva_importe:    parseFloat(document.getElementById('iva-'+id).value),
            total:          parseFloat(document.getElementById('total-'+id).value),
          }};
          await fetch('/documents/'+id+'/confirmar', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(body)}});
          document.getElementById('fila-'+id).remove();
        }}
        async function descartar(id) {{
          await fetch('/documents/'+id+'/descartar', {{method:'POST'}});
          document.getElementById('fila-'+id).remove();
        }}
      </script>
    </body></html>
    """


@app.post("/documents/{doc_id}/confirmar")
def confirmar_documento(doc_id: int, datos: dict, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="No encontrado")
    doc.proveedor       = datos.get("proveedor")
    doc.cif             = datos.get("cif")
    doc.fecha           = datos.get("fecha")
    doc.base_imponible  = datos.get("base_imponible")
    doc.iva_importe     = datos.get("iva_importe")
    doc.total           = datos.get("total")
    doc.status          = "procesado"
    doc.error_msg       = None
    db.commit()
    return {"ok": True}


@app.post("/documents/{doc_id}/descartar")
def descartar_documento(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="No encontrado")
    doc.status = "error"
    doc.error_msg = "Descartado manualmente"
    db.commit()
    return {"ok": True}

@app.get("/stats")
def estadisticas(db: Session = Depends(get_db)):
    # Gasto por mes
    por_mes = db.query(
        func.to_char(Document.created_at, 'YYYY-MM').label("mes"),
        func.sum(Document.total).label("total")
    ).filter(Document.status == "procesado").group_by("mes").order_by("mes").all()

    # Top proveedores
    por_proveedor = db.query(
        Document.proveedor,
        func.sum(Document.total).label("total"),
        func.count(Document.id).label("facturas")
    ).filter(
        Document.status == "procesado",
        Document.proveedor != None
    ).group_by(Document.proveedor).order_by(func.sum(Document.total).desc()).limit(5).all()

    # Conteo por estado
    por_estado = db.query(
        Document.status,
        func.count(Document.id).label("cantidad")
    ).group_by(Document.status).all()

    return {
        "por_mes": [{"mes": r.mes, "total": float(r.total or 0)} for r in por_mes],
        "por_proveedor": [{"proveedor": r.proveedor, "total": float(r.total or 0), "facturas": r.facturas} for r in por_proveedor],
        "por_estado": [{"estado": r.status, "cantidad": r.cantidad} for r in por_estado],
    }

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return """
    <html><head><title>Dashboard</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
    <style>
      *{box-sizing:border-box;margin:0;padding:0}
      body{font-family:sans-serif;background:#f8f8f8;padding:32px 24px}
      h1{font-size:20px;margin-bottom:24px;color:#1a1a1a}
      a{font-size:13px;color:#555;text-decoration:none}
      .grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:20px}
      .card{background:white;border-radius:12px;padding:20px;border:1px solid #eee}
      .card.wide{grid-column:1/-1}
      .card h2{font-size:14px;font-weight:500;color:#555;margin-bottom:16px}
      .kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px}
      .kpi{background:white;border-radius:12px;padding:20px;border:1px solid #eee;text-align:center}
      .kpi .valor{font-size:28px;font-weight:500;color:#1a1a1a;margin-bottom:4px}
      .kpi .label{font-size:12px;color:#888}
      canvas{max-height:220px}
    </style></head>
    <body>
      <h1>Dashboard</h1>
      <a href="/">Volver al inicio</a>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px">
        <h1 style="margin:0">Dashboard</h1>
        <a href="/export" style="padding:8px 18px;background:#1a1a1a;color:white;border-radius:6px;font-size:13px;text-decoration:none">Exportar Excel</a>
      </div>

      <div class="kpis">
        <div class="kpi"><div class="valor" id="kpi-total">-</div><div class="label">Gasto total procesado</div></div>
        <div class="kpi"><div class="valor" id="kpi-docs">-</div><div class="label">Facturas procesadas</div></div>
        <div class="kpi"><div class="valor" id="kpi-revisar">-</div><div class="label">Pendientes de revisión</div></div>
      </div>

      <div class="grid">
        <div class="card wide">
          <h2>Gasto por mes</h2>
          <canvas id="chart-mes"></canvas>
        </div>
        <div class="card">
          <h2>Top 5 proveedores</h2>
          <canvas id="chart-prov"></canvas>
        </div>
        <div class="card">
          <h2>Estado de documentos</h2>
          <canvas id="chart-estado"></canvas>
        </div>
      </div>

      <script>
        async function cargar() {
          const r = await fetch('/stats');
          const d = await r.json();

          const procesadas = d.por_estado.find(e => e.estado === 'procesado');
          const revision   = d.por_estado.find(e => e.estado === 'revisar');
          const totalGasto = d.por_mes.reduce((s, m) => s + m.total, 0);

          document.getElementById('kpi-total').textContent   = totalGasto.toFixed(2) + ' €';
          document.getElementById('kpi-docs').textContent    = procesadas ? procesadas.cantidad : 0;
          document.getElementById('kpi-revisar').textContent = revision   ? revision.cantidad   : 0;

          new Chart(document.getElementById('chart-mes'), {
            type: 'bar',
            data: {
              labels: d.por_mes.map(m => m.mes),
              datasets: [{
                label: 'Gasto (€)',
                data: d.por_mes.map(m => m.total),
                backgroundColor: '#378ADD',
                borderRadius: 6,
              }]
            },
            options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
          });

          new Chart(document.getElementById('chart-prov'), {
            type: 'bar',
            data: {
              labels: d.por_proveedor.map(p => p.proveedor),
              datasets: [{
                label: 'Gasto (€)',
                data: d.por_proveedor.map(p => p.total),
                backgroundColor: ['#534AB7','#1D9E75','#D85A30','#378ADD','#BA7517'],
                borderRadius: 6,
              }]
            },
            options: {
              indexAxis: 'y',
              plugins: { legend: { display: false } },
              scales: { x: { beginAtZero: true } }
            }
          });

          const colores = {
            procesado: '#1D9E75', revisar: '#BA7517',
            error: '#E24B4A', pendiente: '#888780', procesando: '#378ADD'
          };
          new Chart(document.getElementById('chart-estado'), {
            type: 'doughnut',
            data: {
              labels: d.por_estado.map(e => e.estado),
              datasets: [{
                data: d.por_estado.map(e => e.cantidad),
                backgroundColor: d.por_estado.map(e => colores[e.estado] || '#ccc'),
                borderWidth: 0,
              }]
            },
            options: { plugins: { legend: { position: 'bottom' } }, cutout: '65%' }
          });
        }
        cargar();
      </script>
    </body></html>
    """

@app.get("/export")
def exportar_excel(db: Session = Depends(get_db)):
    docs = db.query(Document).filter(Document.status == "procesado").order_by(Document.created_at.desc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Facturas"

    # Cabecera
    cabecera = ["ID", "Archivo", "Proveedor", "CIF", "Fecha", "Base imponible", "IVA %", "IVA importe", "Total", "Fecha subida"]
    for col, texto in enumerate(cabecera, 1):
        cell = ws.cell(row=1, column=col, value=texto)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1a1a1a")
        cell.alignment = Alignment(horizontal="center")

    # Datos
    for row, doc in enumerate(docs, 2):
        ws.cell(row=row, column=1,  value=doc.id)
        ws.cell(row=row, column=2,  value=doc.filename)
        ws.cell(row=row, column=3,  value=doc.proveedor)
        ws.cell(row=row, column=4,  value=doc.cif)
        ws.cell(row=row, column=5,  value=doc.fecha)
        ws.cell(row=row, column=6,  value=doc.base_imponible).number_format = '#,##0.00 €'
        ws.cell(row=row, column=7,  value=doc.iva_porcentaje)
        ws.cell(row=row, column=8,  value=doc.iva_importe).number_format = '#,##0.00 €'
        ws.cell(row=row, column=9,  value=doc.total).number_format = '#,##0.00 €'
        ws.cell(row=row, column=10, value=doc.created_at.strftime("%Y-%m-%d %H:%M") if doc.created_at else None)

        # Fila alternada
        if row % 2 == 0:
            for col in range(1, 11):
                ws.cell(row=row, column=col).fill = PatternFill("solid", fgColor="F5F5F5")

    # Ancho de columnas
    anchos = [6, 30, 30, 15, 12, 16, 8, 14, 12, 18]
    for col, ancho in enumerate(anchos, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = ancho

    # Fila de totales
    fila_total = len(docs) + 2
    ws.cell(row=fila_total, column=5, value="TOTAL").font = Font(bold=True)
    ws.cell(row=fila_total, column=6, value=f"=SUM(F2:F{len(docs)+1})").number_format = '#,##0.00 €'
    ws.cell(row=fila_total, column=8, value=f"=SUM(H2:H{len(docs)+1})").number_format = '#,##0.00 €'
    ws.cell(row=fila_total, column=9, value=f"=SUM(I2:I{len(docs)+1})").number_format = '#,##0.00 €'

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=facturas.xlsx"}
    )

@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <html><head><title>Invoice Processor</title>
    <style>
      body { font-family: sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; }
      h1 { font-size: 22px; margin-bottom: 24px; }
      .upload-area { display:flex; gap:12px; align-items:center; margin-bottom:8px; }
      input[type=file] { flex:1; }
      button { padding: 8px 20px; background: #1a1a1a; color: white; border: none; border-radius: 6px; cursor: pointer; }
      #msg { font-size:13px; color:#555; margin-bottom:24px; min-height:18px; }
      table { width: 100%; border-collapse: collapse; font-size: 13px; }
      th { text-align: left; border-bottom: 2px solid #eee; padding: 8px 12px; }
      td { padding: 8px 12px; border-bottom: 1px solid #f0f0f0; }
      .procesado{color:green} .error{color:red} .revisar{color:orange} .pendiente{color:#888} .procesando{color:#2196F3}
    </style></head>
    <body>
      <h1>Procesador de facturas</h1>
      <a href="/revisar" style="font-size:13px;color:#555">Ver facturas para revisar →</a>
      &nbsp;&nbsp;
      <a href="/dashboard" style="font-size:13px;color:#555">Dashboard →</a>
      <div class="upload-area">
        <input type="file" id="file" accept=".pdf,.jpg,.jpeg,.png" multiple>
        <button onclick="subir()">Subir</button>
      </div>
      <div id="msg"></div>
      <table>
        <thead><tr>
          <th>Archivo</th><th>Proveedor</th><th>Fecha</th>
          <th>Base</th><th>IVA</th><th>Total</th><th>Estado</th>
        </tr></thead>
        <tbody id="tbody"></tbody>
      </table>
      <script>
        async function subir() {
          const files = document.getElementById('file').files;
          if (!files.length) return;
          document.getElementById('msg').textContent = 'Enviando ' + files.length + ' factura(s)...';
          for (const f of files) {
            const fd = new FormData();
            fd.append('file', f);
            await fetch('/upload', {method:'POST', body:fd});
          }
          document.getElementById('msg').textContent = files.length + ' factura(s) en cola. Procesando...';
          cargar();
        }
        async function cargar() {
          const r = await fetch('/documents');
          const docs = await r.json();
          document.getElementById('tbody').innerHTML = docs.map(d => `<tr>
            <td>${d.filename}</td>
            <td>${d.proveedor || '-'}</td>
            <td>${d.fecha || '-'}</td>
            <td>${d.base_imponible != null ? d.base_imponible.toFixed(2)+'€' : '-'}</td>
            <td>${d.iva_importe != null ? d.iva_importe.toFixed(2)+'€' : '-'}</td>
            <td>${d.total != null ? d.total.toFixed(2)+'€' : '-'}</td>
            <td class="${d.status}">${d.status}</td>
          </tr>`).join('');
          const hayPendientes = docs.some(d => ['pendiente','procesando'].includes(d.status));
          if (hayPendientes) setTimeout(cargar, 2000);
        }
        cargar();
        setInterval(cargar, 5000);
      </script>
    </body></html>
    """