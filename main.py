from flask import Flask, request, jsonify
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json

# 1. Definición de la App (DEBE IR AQUÍ ARRIBA)
app = Flask(__name__)

def conectar_google():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    pk = os.environ.get('GOOGLE_PRIVATE_KEY')
    email = os.environ.get('GOOGLE_CLIENT_EMAIL')
    
    if not pk or not email:
        raise ValueError("Faltan credenciales GOOGLE_PRIVATE_KEY o GOOGLE_CLIENT_EMAIL en Render")
    
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
        accion = data.get('accion', 'cotizar')
        nombre_user = data.get('nombre', 'Cliente')
        distrito_user = data.get('distrito', 'No especificado').strip().upper()
        whatsapp_user = data.get('whatsapp', 'S/N')
        
        # 2. Procesar proyectos (Soporta 'proyecto' o 'proyectos')
        proyectos_raw = data.get('proyecto') or data.get('proyectos', [])
        if isinstance(proyectos_raw, str):
            try:
                proyectos = json.loads(proyectos_raw)
            except:
                proyectos = []
        else:
            proyectos = proyectos_raw

        # 3. Conexión y Cálculo de Presupuesto (Hoja3)
        client = conectar_google()
        sheet_precios = client.open_by_key(SPREADSHEET_ID).worksheet("Hoja3")
        df = pd.DataFrame(sheet_precios.get_all_records())
        
        df.columns = df.columns.str.strip()
        df['Ambiente_Busqueda'] = df['Ambiente'].astype(str).str.strip().str.lower()

        subtotal_acumulado = 0
        detalles_texto = []

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
                detalles_texto.append(f"{amb_solicitado.upper()} ({m2_solicitado}m2)")
            else:
                detalles_texto.append(f"{amb_solicitado.upper()} (S/R)")

        subtotal_final = round(subtotal_acumulado, 2)
        total_con_igv = round(subtotal_final * 1.18, 2)
        resumen_ambientes = ", ".join(detalles_texto)

        # 4. LÓGICA DE GUARDADO SEGÚN ACCIÓN
        if accion == "confirmar_pago":
            # Guardar en Clients (Basado en tu imagen de columnas)
            sheet_clients = client.open_by_key(SPREADSHEET_ID).worksheet("Clients")
            sheet_clients.append_row([
                nombre_user,        # A: Nombre
                str(whatsapp_user), # B: WhatsApp
                distrito_user,      # C: Distrito
                resumen_ambientes,  # D: Ambiente/m2
                total_con_igv,      # E: Total Cotizado
                0,                  # F: Monto Pagado
                total_con_igv,      # G: Saldo
                "Pendiente"         # H: Estado
            ])
        else:
            # Guardar en Leads (Análisis de consultas)
            try:
                sheet_leads = client.open_by_key(SPREADSHEET_ID).worksheet("Leads")
                sheet_leads.append_row([
                    nombre_user,
                    str(whatsapp_user),
                    distrito_user,
                    resumen_ambientes,
                    total_con_igv,
                    "Solo Consulta"
                ])
            except Exception as e:
                print(f"Error Leads: {e}. Asegúrate que la hoja 'Leads' exista.")

        # 5. Respuesta para n8n
        return jsonify({
            "status": "success",
            "total": total_con_igv,
            "detalles": detalles_texto,
            "cliente": nombre_user
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
