from flask import Flask, request, jsonify
import gspread
from google.oauth2 import service_account
import pandas as pd
import os
import requests

app = Flask(__name__)

# --- CONFIGURACIÓN DE EVOLUTION API ---
EVOLUTION_URL = os.environ.get("EVOLUTION_API_URL", "https://api-whatsapp-pro-v2.onrender.com")
EVOLUTION_KEY = os.environ.get("AUTHENTICATION_API_KEY", "trey123")
INSTANCE_NAME = os.environ.get("INSTANCE_NAME", "tu_instancia") 

def enviar_whatsapp(numero, mensaje):
    try:
        numero_limpio = "".join(filter(str.isdigit, str(numero)))
        if len(numero_limpio) == 9: 
            numero_limpio = "51" + numero_limpio

        url = f"{EVOLUTION_URL.rstrip('/')}/message/sendText/{INSTANCE_NAME}"
        headers = {"apikey": EVOLUTION_KEY, "Content-Type": "application/json"}
        payload = {
            "number": numero_limpio,
            "options": {"delay": 1200, "presence": "composing", "linkPreview": False},
            "textMessage": {"text": mensaje}
        }
        res = requests.post(url, json=payload, headers=headers)
        return res.status_code in [200, 201]
    except Exception as e:
        print(f"❌ Error WhatsApp: {e}")
        return False

# --- CONFIGURACIÓN DE GOOGLE SHEETS ---
def obtener_conexion_sheets():
    try:
        pk = os.environ.get("GOOGLE_PRIVATE_KEY").strip('"').replace("\\n", "\n")
        email = os.environ.get("GOOGLE_CLIENT_EMAIL")
        info = {
            "type": "service_account",
            "private_key": pk,
            "client_email": email,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = service_account.Credentials.from_service_account_info(info, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"❌ Error Conexión Sheets: {e}")
        return None

# --- RUTA PRINCIPAL (RECIBE DE N8N) ---
@app.route("/confirmar_pago", methods=["POST"])
def confirmar_pago():
    gc = obtener_conexion_sheets()
    if not gc: return jsonify({"error": "No hay conexión con Sheets"}), 500
    
    try:
        data = request.get_json()
        nombre = data.get("Nombre", "Sin Nombre")
        celular = data.get("Celular", "")
        distrito = data.get("Distrito", "No especificado")
        ambiente_solicitado = data.get("Ambiente", "")
        m2_solicitado = float(data.get("m2", 0))

        doc = gc.open("Cotizaciones")
        h3 = doc.worksheet("Hoja 3") # Precios
        h1 = doc.worksheet("Hoja 1") # Clientes/Saldos
        h5 = doc.worksheet("Hoja 5") # Historial/Registro

        # 1. Buscar Precio en Hoja 3 por Ambiente y Rango m2
        df_precios = pd.DataFrame(h3.get_all_records())
        # Filtramos: mismo ambiente y que los m2 estén entre Min y Max
        match = df_precios[
            (df_precios['Ambiente'] == ambiente_solicitado) & 
            (df_precios['RangoMin'] <= m2_solicitado) & 
            (df_precios['RangoMax'] >= m2_solicitado)
        ]

        if match.empty:
            return jsonify({"error": "No se encontró un rango de precio para esos m2"}), 404

        precio_base = float(match.iloc[0]['Precio'])
        igv = precio_base * 0.18
        total = precio_base + igv

        # 2. Registro en Hoja 1 (Saldos)
        h1.append_row([nombre, celular, ambiente_solicitado, total, 0, total, "Pendiente"])

        # 3. Registro en Hoja 5 (Detalle)
        h5.append_row([nombre, distrito, ambiente_solicitado, m2_solicitado, total])

        # 4. Enviar WhatsApp con Cotización
        mensaje_cot = (
            f"¡Hola {nombre}! ✨\n\n"
            f"Hemos generado tu cotización para: *{ambiente_solicitado}*\n"
            f"📐 Área: {m2_solicitado} m2\n"
            f"📍 Distrito: {distrito}\n\n"
            f"💰 Subtotal: S/ {precio_base:.2f}\n"
            f"📝 IGV (18%): S/ {igv:.2f}\n"
            f"💵 *TOTAL: S/ {total:.2f}*\n\n"
            f"Para iniciar el diseño, se requiere un depósito inicial. ¡Quedamos atentos! 🚀"
        )
        enviar_whatsapp(celular, mensaje_cot)

        return jsonify({"status": "Cotización procesada", "total": total})

    except Exception as e:
        print(f"❌ Error en Proceso: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
