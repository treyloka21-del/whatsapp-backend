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
        raise ValueError("Faltan credenciales GOOGLE_PRIVATE_KEY o GOOGLE_CLIENT_EMAIL en Render")
    
    # Limpieza de la llave privada para Render
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
        # 1. Obtención de datos
        data = request.get_json() if request.is_json else request.form
        nombre_user = data.get('nombre', 'Cliente')
        distrito_user = data.get('distrito', 'No especificado').strip().upper()
        whatsapp_user = data.get('whatsapp', 'S/N')
        
        # 2. Procesar proyectos
        proyectos_raw = data.get('proyectos', [])
        if isinstance(proyectos_raw, str):
            try:
                proyectos = json.loads(proyectos_raw)
            except:
                proyectos = []
        else:
            proyectos = proyectos_raw

        # 3. Conexión a Google Sheets
        client = conectar_google()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Hoja3")
        df = pd.DataFrame(sheet.get_all_records())

        # Limpieza de columnas del Excel
        df.columns = df.columns.str.strip()
        df['Ambiente_Busqueda'] = df['Ambiente'].astype(str).str.strip().str.lower()

        subtotal_acumulado = 0
        detalles = []

        # 4. Cálculo de presupuesto (Por Ambiente y Rango m2)
        for p in proyectos:
            amb_solicitado = str(p.get('ambiente', '')).strip().lower()
            try:
                m2_solicitado = float(p.get('m2', 0))
            except:
                m2_solicitado = 0

            df_amb = df[df['Ambiente_Busqueda'] == amb_solicitado]
            
            fila = df_amb[
                (df_amb['RangoMin'].astype(float) <= m2_solicitado) & 
                (df_amb['RangoMax'].astype(float) >= m2_solicitado)
            ]

            if not fila.empty:
                precio_unitario = float(fila.iloc[0]['Precio'])
                subtotal_acumulado += precio_unitario
                detalles.append(f"{amb_solicitado.upper()} ({m2_solicitado}m2) = S/ {precio_unitario}")
            else:
                detalles.append(f"{amb_solicitado.upper()}: Rango no encontrado para {m2_solicitado}m2")

        # Lógica de IGV
        subtotal_final = round(subtotal_acumulado, 2)
        monto_igv = round(subtotal_final * 0.18, 2)
        total_con_igv = round(subtotal_final + monto_igv, 2)
        
        # 5. Guardar en Hoja6
        try:
            sheet6 = client.open_by_key(SPREADSHEET_ID).worksheet("Hoja6")
            sheet6.append_row([
                nombre_user, 
                distrito_user, 
                str(proyectos), 
                str(whatsapp_user), 
                subtotal_final,
                monto_igv,
                total_con_igv
            ])
        except Exception as e:
            print(f"Error Hoja6: {e}")

        # 6. Respuesta para n8n
        return jsonify({
            "status": "success",
            "cliente": nombre_user,
            "distrito": distrito_user,
            "detalles": detalles,
            "subtotal": subtotal_final,
            "igv": monto_igv,
            "total": total_con_igv
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
