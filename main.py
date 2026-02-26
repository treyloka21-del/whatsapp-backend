from flask import Flask, request, jsonify
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json

app = Flask(__name__)

# --- CONFIGURACIÓN DE SEGURIDAD PARA GOOGLE SHEETS ---
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def obtener_creds():
    # Intentamos leer la llave desde la variable de entorno de Render
    private_key = os.environ.get('PRIVATE_KEY')
    
    if private_key:
        # Si la llave está en Render, construimos el diccionario de credenciales
        # Reemplaza los datos de abajo con los de tu service account si son distintos
        info = {
            "type": "service_account",
            "project_id": "whatsapp-backend-488021",
            "private_key_id": "6732f7b8c8d8a7e6f5d4c3b2a1", # ID ficticio, no es crítico
            "private_key": private_key.replace('\\n', '\n'), # Reparamos los saltos de línea
            "client_email": "whatsapp-backend-sa@whatsapp-backend-488021.iam.gserviceaccount.com",
            "client_id": "1234567890",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/whatsapp-backend-sa%40whatsapp-backend-488021.iam.gserviceaccount.com"
        }
        return Credentials.from_service_account_info(info, scopes=scope)
    else:
        # Si no hay variable, busca el archivo local (útil para pruebas en tu PC)
        return Credentials.from_service_account_file('credentials.json', scopes=scope)

# Inicializamos el cliente de Google Sheets
creds = obtener_creds()
client = gspread.authorize(creds)

SPREADSHEET_ID = "1os4j4fVMY8Jx07IXR9DD2RUgY1IK4HSLtQJH8B7z8Rw"

def leer_excel():
    sheet = client.open_by_key(SPREADSHEET_ID).sheet1
    data = sheet.get_all_records()
    return pd.DataFrame(data)

@app.route('/', methods=['GET'])
def home():
    return "Servidor Cotizador Activo 🚀", 200

@app.route('/confirmar_pago', methods=['POST'])
def confirmar_pago():
    try:
        data = request.get_json()
        nombre = data.get('nombre', 'Cliente')
        proyectos = data.get('proyectos', [])

        df = leer_excel()
        subtotal = 0
        detalles = []

        for p in proyectos:
            ambiente_user = str(p.get('ambiente')).strip().lower()
            m2_user = float(p.get('m2', 0))

            df_ambiente = df[df['Ambiente'].str.strip().str.lower() == ambiente_user]

            # Búsqueda por rangos
            fila = df_ambiente[(df_ambiente['RangoMin'] <= m2_user) & (df_ambiente['RangoMax'] >= m2_user)]

            if not fila.empty:
                precio_rango = float(fila.iloc[0]['Precio'])
                subtotal += precio_rango
                detalles.append(f"{ambiente_user.upper()} ({m2_user} m2) = S/ {precio_rango:.2f}")
            else:
                detalles.append(f"Sin rango para {ambiente_user} con {m2_user} m2")

        igv = subtotal * 0.18
        total = subtotal + igv

        return jsonify({
            "status": "success",
            "detalles": detalles,
            "subtotal": round(subtotal, 2),
            "igv": round(igv, 2),
            "total": round(total, 2)
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
