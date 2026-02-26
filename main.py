from flask import Flask, request, jsonify
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os

app = Flask(__name__)

# --- CONFIGURACIÓN DE GOOGLE SHEETS ---
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# Asegúrate de que el archivo 'credentials.json' esté en la misma carpeta que main.py
creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
client = gspread.authorize(creds)

# TU ID REAL EXTRAÍDO DE LA URL:
SPREADSHEET_ID = "1os4j4fVMY8Jx07IXR9DD2RUgY1IK4HSLtQJH8B7z8Rw"

def leer_excel():
    # Abre el documento por ID y selecciona la primera pestaña (Hoja 1)
    sheet = client.open_by_key(SPREADSHEET_ID).sheet1
    data = sheet.get_all_records()
    return pd.DataFrame(data)

@app.route('/', methods=['GET'])
def home():
    return "Servidor de Cotizaciones de WhatsApp Activo 🚀", 200

@app.route('/confirmar_pago', methods=['POST'])
def confirmar_pago():
    try:
        data = request.get_json()
        nombre = data.get('nombre', 'Cliente')
        distrito = data.get('distrito', 'No especificado')
        proyectos = data.get('proyectos', [])

        df = leer_excel()
        
        subtotal = 0
        detalles = []

        for p in proyectos:
            # Limpiar entrada del usuario para evitar errores por espacios o mayúsculas
            ambiente_user = str(p.get('ambiente')).strip().lower()
            m2_user = float(p.get('m2', 0))

            # 1. Filtrar por nombre de ambiente
            df_ambiente = df[df['Ambiente'].str.strip().str.lower() == ambiente_user]

            if df_ambiente.empty:
                detalles.append(f"Ambiente '{ambiente_user}' no encontrado.")
                continue

            # 2. Lógica de Rangos: Busca la fila donde RangoMin <= m2_user <= RangoMax
            fila_correcta = df_ambiente[
                (df_ambiente['RangoMin'] <= m2_user) & 
                (df_ambiente['RangoMax'] >= m2_user)
            ]

            if not fila_correcta.empty:
                # Tomamos el precio directo de la tabla (no multiplicamos por m2)
                precio_rango = float(fila_correcta.iloc[0]['Precio'])
                subtotal += precio_rango
                detalles.append(f"{ambiente_user.upper()} ({m2_user} m2) = S/ {precio_rango:.2f}")
            else:
                detalles.append(f"No hay rango de precio para {ambiente_user} con {m2_user} m2")

        # Cálculos finales de impuestos (ajusta el 0.18 si es necesario)
        igv = subtotal * 0.18
        total = subtotal + igv

        return jsonify({
            "status": "success",
            "nombre": nombre,
            "distrito": distrito,
            "detalles": detalles,
            "subtotal": round(subtotal, 2),
            "igv": round(igv, 2),
            "total": round(total, 2)
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Render asigna el puerto automáticamente
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
