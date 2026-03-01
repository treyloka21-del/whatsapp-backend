from flask import Flask, request, jsonify
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
from datetime import datetime

app = Flask(__name__)

# --- CONFIGURACIÓN DE GOOGLE SHEETS ---
def conectar_google():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    pk = os.environ.get('GOOGLE_PRIVATE_KEY')
    email = os.environ.get('GOOGLE_CLIENT_EMAIL')

    if not pk or not email:
        raise ValueError("Faltan variables GOOGLE_PRIVATE_KEY o GOOGLE_CLIENT_EMAIL en Render")

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

client = None
try:
    client = conectar_google()
    print("✅ Conexión exitosa a Google Sheets")
except Exception as e:
    print(f"❌ Error de conexión inicial: {e}")

SPREADSHEET_ID = "1os4j4fVMY8Jx07IXR9DD2RUgY1IK4HSLtQJH8B7z8Rw"

def leer_y_limpiar_excel():
    global client
    if client is None: client = conectar_google()
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Hoja3")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    def limpiar_numero(valor):
        if valor is None or valor == "": return 0.0
        valor_str = str(valor).strip().replace('.', '').replace(',', '.')
        try: return float(valor_str)
        except: return 0.0

    df['RangoMin'] = df['RangoMin'].apply(limpiar_numero)
    df['RangoMax'] = df['RangoMax'].apply(limpiar_numero)
    df['Precio'] = df['Precio'].apply(limpiar_numero)
    return df

def registrar_en_hoja6(nombre, distrito, proyectos, whatsapp, total):
    try:
        global client
        if client is None: client = conectar_google()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Hoja6")
        
        # Formateamos la fecha y los proyectos para que queden legibles en una celda
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        proyectos_str = str(proyectos)
        
        # Orden de columnas: nombre, distrito, proyectos, whatsapp, total, fecha
        nueva_fila = [nombre, distrito, proyectos_str, whatsapp, total, fecha]
        sheet.append_row(nueva_fila)
        print(f"✅ Datos guardados en Hoja6 para: {nombre}")
    except Exception as e:
        print(f"❌ Error al guardar en Hoja6: {e}")

@app.route('/', methods=['GET'])
def home():
    return "Servidor Cotizador ONLINE - v2.5 (Registro Hoja6 Activo) 🚀", 200

@app.route('/confirmar_pago', methods=['POST'])
def confirmar_pago():
    try:
        data = request.get_json() if request.is_json else request.form
        nombre_user = data.get('nombre', 'Cliente')
        distrito_user = data.get('distrito', 'No especificado')
        whatsapp_user = data.get('whatsapp', 'Sin número')
        
        proyectos_raw = data.get('proyectos', '[]')
        if isinstance(proyectos_raw, str):
            try: proyectos = json.loads(proyectos_raw)
            except: proyectos = []
        else:
            proyectos = proyectos_raw
        
        df = leer_y_limpiar_excel()
        subtotal = 0
        detalles = []
        conteos = {} 

        for p in proyectos:
            ambiente_user = str(p.get('ambiente', '')).strip().lower()
            m2_user = float(p.get('m2', 0))

            if ambiente_user not in conteos: conteos[ambiente_user] = 1
            else: conteos[ambiente_user] += 1
            
            total_de_este_tipo = sum(1 for x in proyectos if str(x.get('ambiente', '')).strip().lower() == ambiente_user)
            label_ambiente = f"{ambiente_user.upper()} {conteos[ambiente_user]}" if total_de_este_tipo > 1 else ambiente_user.upper()

            df_amb = df[df['Ambiente'].str.strip().str.lower() == ambiente_user]
            fila = df_amb[(df_amb['RangoMin'] <= m2_user) & (df_amb['RangoMax'] >= m2_user)]

            if not fila.empty:
                precio_fijo = float(fila.iloc[0]['Precio'])
                subtotal += precio_fijo
                detalles.append(f"{label_ambiente} ({m2_user} m2) = S/ {precio_fijo:,.2f}")
            else:
                detalles.append(f"{label_ambiente} ({m2_user} m2) = No hay rango en tabla")

        igv = subtotal * 0.18
        total_final = subtotal + igv

        # --- LLAMADA PARA GUARDAR EN HOJA 6 ---
        registrar_en_hoja6(nombre_user, distrito_user, proyectos, whatsapp_user, total_final)

        return jsonify({
            "status": "success",
            "cliente": nombre_user,
            "distrito": distrito_user,
            "detalles": detalles,
            "subtotal": round(subtotal, 2),
            "igv": round(igv, 2),
            "total": round(total_final, 2)
        }), 200

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
