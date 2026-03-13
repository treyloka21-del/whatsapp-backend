from flask import Flask, request, jsonify
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
from datetime import datetime

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
        distrito_user = data.get('distrito', 'SJL').strip()
        whatsapp_user = data.get('whatsapp', 'S/N')
        
        # PROCESAR PROYECTOS (Asegurar que sea lista)
        proyectos_raw = data.get('proyectos', '[]')
        if isinstance(proyectos_raw, str):
            try: proyectos = json.loads(proyectos_raw)
            except: proyectos = []
        else:
            proyectos = proyectos_raw

        # CONECTAR Y LEER HOJA3 (Donde están tus precios por ambiente)
        client = conectar_google()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Hoja3")
        df = pd.DataFrame(sheet.get_all_records())

        # Limpieza de columnas del Excel de precios
        df.columns = df.columns.str.strip()
        df['Ambiente_Busqueda'] = df['Ambiente'].astype(str).str.strip().str.lower()
        if 'Distrito' in df.columns:
            df['Distrito_Busqueda'] = df['Distrito'].astype(str).str.strip().str.lower()

        subtotal = 0
        detalles = []
        ambientes_m2_lista = []

        for p in proyectos:
            amb_solicitado = str(p.get('ambiente', '')).strip().lower()
            m2_solicitado = float(p.get('m2', 0))
            
            # Guardamos el formato para la columna Ambiente/m2
            ambientes_m2_lista.append(f"{amb_solicitado.upper()} ({m2_solicitado}m2)")

            # Filtrado por Ambiente y Distrito
            if 'Distrito_Busqueda' in df.columns:
                df_amb = df[
                    (df['Ambiente_Busqueda'] == amb_solicitado) & 
                    (df['Distrito_Busqueda'] == distrito_user.lower())
                ]
            else:
                df_amb = df[df['Ambiente_Busqueda'] == amb_solicitado]
            
            # Buscar el Rango
            fila = df_amb[
                (df_amb['RangoMin'].astype(float) <= m2_solicitado) & 
                (df_amb['RangoMax'].astype(float) >= m2_solicitado)
            ]

            if not fila.empty:
                precio = float(fila.iloc[0]['Precio'])
                subtotal += precio
                detalles.append(f"{amb_solicitado.upper()} = S/ {precio}")
            else:
                detalles.append(f"{amb_solicitado.upper()}: No encontrado")

        total_final = subtotal * 1.18 # IGV incluido
        ambientes_m2_str = ", ".join(ambientes_m2_lista)
        fecha_hoy = datetime.now().strftime("%d/%m/%Y")
        
        # GUARDAR EN HOJA "Clients" 
        # Columnas: Nombre, WhatsApp, Distrito, Ambiente/m2, Total Cotizado, Monto Pagado, Saldo, Estado, Fecha Inicio, Fecha Entrega
        try:
            sheet_clients = client.open_by_key(SPREADSHEET_ID).worksheet("Clients")
            
            # Preparamos la fila según tu nueva estructura
            nueva_fila = [
                nombre_user,          # Nombre
                whatsapp_user,        # WhatsApp
                distrito_user,        # Distrito
                ambientes_m2_str,     # Ambiente/m2
                round(total_final, 2),# Total Cotizado
                0,                    # Monto Pagado (Inicia en 0)
                round(total_final, 2),# Saldo (Inicia igual al total)
                "Pendiente",          # Estado
                fecha_hoy,            # Fecha Inicio (Hoy)
                ""                    # Fecha Entrega (Vacío por ahora)
            ]
            
            sheet_clients.append_row(nueva_fila)
        except Exception as e:
            print(f"Error en pestaña Clients: {e}")

        return jsonify({
            "status": "success",
            "cliente": nombre_user,
            "total": round(total_final, 2),
            "hoja": "Clients"
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
