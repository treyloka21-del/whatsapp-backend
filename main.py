from flask import Flask, request, jsonify
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os

app = Flask(__name__)

# --- CONFIGURACIÓN AJUSTADA A TUS VARIABLES EN RENDER ---
def conectar_google():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # Usamos los nombres exactos que aparecen en tu imagen de Render
    pk = os.environ.get('GOOGLE_PRIVATE_KEY')
    email = os.environ.get('GOOGLE_CLIENT_EMAIL')

    if not pk or not email:
        raise ValueError("CRÍTICO: No se detectan GOOGLE_PRIVATE_KEY o GOOGLE_CLIENT_EMAIL en Render.")

    # Reparamos la llave (esto es vital para el error del PEM file)
    pk_limpia = pk.replace('\\n', '\n')

    info = {
        "type": "service_account",
        "project_id": "whatsapp-backend-488021",
        "private_key": pk_limpia,
        "client_email": email,
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    
    creds = Credentials.from_service_account_info(info, scopes=scope)
    return gspread.authorize(creds)

# Inicialización
try:
    client = conectar_google()
    print("✅ Conectado exitosamente con las variables de Render")
except Exception as e:
    print(f"❌ Error de conexión: {e}")

SPREADSHEET_ID = "1os4j4fVMY8Jx07IXR9DD2RUgY1IK4HSLtQJH8B7z8Rw"

def leer_excel():
    # Según tu imagen, los datos están en la pestaña 'Hoja3'
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Hoja3")
    data = sheet.get_all_records()
    return pd.DataFrame(data)

@app.route('/', methods=['GET'])
def home():
    return "Servidor Cotizador Activo ✅", 200

@app.route('/confirmar_pago', methods=['POST'])
def confirmar_pago():
    try:
        data = request.get_json()
        proyectos = data.get('proyectos', [])
        df = leer_excel()
        
        # Convertimos columnas numéricas por si acaso el Excel las manda como texto
        df['RangoMin'] = pd.to_numeric(df['RangoMin'].astype(str).str.replace(',', '.'), errors='coerce')
        df['RangoMax'] = pd.to_numeric(df['RangoMax'].astype(str).str.replace(',', '.'), errors='coerce')
        df['Precio'] = pd.to_numeric(df['Precio'].astype(str).str.replace('.', '').str.replace(',', '.'), errors='coerce')

        subtotal = 0
        detalles = []

        for p in proyectos:
            ambiente_user = str(p.get('ambiente', '')).strip().lower()
            m2_user = float(p.get('m2', 0))

            # Filtrar por ambiente y rango
            df_amb = df[df['Ambiente'].str.strip().str.lower() == ambiente_user]
            fila = df_amb[(df_amb['RangoMin'] <= m2_user) & (df_amb['RangoMax'] >= m2_user)]

            if not fila.empty:
                precio = float(fila.iloc[0]['Precio'])
                subtotal += precio
                detalles.append(f"{ambiente_user.upper()} ({m2_user} m2) = S/ {precio:,.2f}")
            else:
                detalles.append(f"No hay rango para {ambiente_user} con {m2_user} m2")

        igv = subtotal * 0.18
        return jsonify({
            "status": "success",
            "detalles": detalles,
            "subtotal": round(subtotal, 2),
            "igv": round(igv, 2),
            "total": round(subtotal + igv, 2)
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
