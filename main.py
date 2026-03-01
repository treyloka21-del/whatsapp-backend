from flask import Flask, request, jsonify
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json

app = Flask(__name__)

def conectar_google():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    pk = os.environ.get('GOOGLE_PRIVATE_KEY')
    email = os.environ.get('GOOGLE_CLIENT_EMAIL')
    if not pk or not email:
        raise ValueError("Faltan credenciales en Render")
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

SPREADSHEET_ID = "1os4j4fVMY8Jx07IXR9DD2RUgY1IK4HSLtQJH8B7z8Rw"

@app.route('/confirmar_pago', methods=['POST'])
def confirmar_pago():
    try:
        data = request.get_json() if request.is_json else request.form
        nombre_user = data.get('nombre', 'Cliente')
        distrito_user = data.get('distrito', 'SJL')
        whatsapp_user = data.get('whatsapp', 'S/N')
        
        # PROCESAR PROYECTOS (Asegurar que sea lista)
        proyectos_raw = data.get('proyectos', '[]')
        if isinstance(proyectos_raw, str):
            try: proyectos = json.loads(proyectos_raw)
            except: proyectos = []
        else:
            proyectos = proyectos_raw

        # CONECTAR Y LEER HOJA3
        client = conectar_google()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Hoja3")
        df = pd.DataFrame(sheet.get_all_records())

        # Limpieza de columnas del Excel
        df.columns = df.columns.str.strip()
        df['Ambiente_Busqueda'] = df['Ambiente'].astype(str).str.strip().str.lower()

        subtotal = 0
        detalles = []

        for p in proyectos:
            # Limpieza de lo que envía la IA
            amb_solicitado = str(p.get('ambiente', '')).strip().lower()
            m2_solicitado = float(p.get('m2', 0))

            # Filtrar por Ambiente
            df_amb = df[df['Ambiente_Busqueda'] == amb_solicitado]
            
            # Buscar el Rango (usando float para evitar errores de tipo)
            fila = df_amb[
                (df_amb['RangoMin'].astype(float) <= m2_solicitado) & 
                (df_amb['RangoMax'].astype(float) >= m2_solicitado)
            ]

            if not fila.empty:
                precio = float(fila.iloc[0]['Precio'])
                subtotal += precio
                detalles.append(f"{amb_solicitado.upper()} ({m2_solicitado}m2) = S/ {precio}")
            else:
                detalles.append(f"{amb_solicitado.upper()}: Rango {m2_solicitado}m2 no encontrado")

        total_final = subtotal * 1.18 # IGV incluido
        
        # GUARDAR EN HOJA 6 (nombre, distrito, proyectos, whatsapp, total)
        try:
            sheet6 = client.open_by_key(SPREADSHEET_ID).worksheet("Hoja6")
            sheet6.append_row([nombre_user, distrito_user, str(proyectos), str(whatsapp_user), round(total_final, 2)])
        except Exception as e:
            print(f"Error Hoja6: {e}")

        return jsonify({
            "status": "success",
            "cliente": nombre_user,
            "detalles": detalles,
            "total": round(total_final, 2)
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
