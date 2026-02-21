from flask import Flask, request, jsonify
import gspread
from google.oauth2 import service_account
import pandas as pd
import os
import requests  # <-- NUEVO: Necesario para hablar con la Evolution API

app = Flask(__name__)

# Configuración de Evolution API (Variables de Entorno)
# Asegúrate de tener estas variables en Render -> Environment
EVOLUTION_URL = os.environ.get("EVOLUTION_API_URL", "https://api-whatsapp-pro-v2.onrender.com")
EVOLUTION_KEY = os.environ.get("AUTHENTICATION_API_KEY", "tu_clave_aqui")
INSTANCE_NAME = "tu_instancia" # Cámbialo por el nombre que le pongas en la API

def enviar_whatsapp(numero, mensaje):
    """Función para enviar mensajes vía Evolution API"""
    try:
        # Limpiar el número (quitar símbolos si los hay)
        numero_limpio = "".join(filter(str.isdigit, str(numero)))
        if not numero_limpio.startswith("51"): # Ejemplo para Perú, ajusta según tu país
            numero_limpio = "51" + numero_limpio

        url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE_NAME}"
        headers = {
            "apikey": EVOLUTION_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "number": numero_limpio,
            "options": {"delay": 1200, "presence": "composing", "linkPreview": False},
            "textMessage": {"text": mensaje}
        }
        res = requests.post(url, json=payload, headers=headers)
        return res.status_code == 201
    except Exception as e:
        print(f"❌ Error enviando WhatsApp: {e}")
        return False

# Configuración de Google Sheets
def obtener_hojas():
    try:
        pk = os.environ.get("GOOGLE_PRIVATE_KEY")
        email = os.environ.get("GOOGLE_CLIENT_EMAIL")
        if not pk or not email:
            return None, None
        pk = pk.strip('"').replace("\\n", "\n")
        info = {
            "type": "service_account",
            "private_key": pk,
            "client_email": email,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = service_account.Credentials.from_service_account_info(info, scopes=scope)
        gc = gspread.authorize(creds)
        doc = gc.open("Cotizaciones")
        h_fin = None
        h_cot = None
        for s in doc.worksheets():
            nombre_limpio = s.title.replace(" ", "").lower()
            if nombre_limpio == "hoja1": h_fin = s
            if nombre_limpio == "hoja5": h_cot = s
        return h_fin, h_cot
    except Exception as e:
        print(f"❌ Error en la conexión Sheets: {str(e)}")
        return None, None

hoja_finanzas, hoja_cotizaciones = obtener_hojas()

@app.route("/", methods=["GET"])
def healthcheck():
    status = "CONECTADO" if hoja_finanzas else "DESCONECTADO"
    return jsonify({"backend": "activo", "google_sheets": status})

@app.route("/confirmar_pago", methods=["POST"])
def confirmar_pago():
    if not hoja_finanzas:
        return jsonify({"error": "No hay conexión con Google Sheets"}), 500
    
    try:
        data = request.get_json()
        nombre = data.get("nombre")
        total = float(data.get("total_cotizado", 0))
        deposito = float(data.get("monto_pagado", 0))
        celular = data.get("celular", "")
        ambientes = data.get("ambientes", "")

        registros = hoja_finanzas.get_all_records()
        df = pd.DataFrame(registros)
        
        mensaje_ws = f"¡Hola {nombre}! Hemos registrado tu pago de {deposito}. "
        
        if not df.empty and "Nombre" in df.columns:
            cliente_existente = df[df["Nombre"] == nombre]
            if not cliente_existente.empty:
                fila_index = cliente_existente.index[0] + 2
                dep_actual = float(cliente_existente.iloc[0].get("Deposito", 0))
                nuevo_dep = dep_actual + deposito
                saldo = total - nuevo_dep
                
                hoja_finanzas.update_cell(fila_index, 5, nuevo_dep)
                hoja_finanzas.update_cell(fila_index, 6, max(saldo, 0))
                hoja_finanzas.update_cell(fila_index, 7, "Pagado" if saldo <= 0 else "Pendiente")
                
                mensaje_ws += f"Tu saldo actual es de {max(saldo, 0)}."
                enviar_whatsapp(celular, mensaje_ws) # <-- ENVÍO DE WHATSAPP
                return jsonify({"status": "actualizado", "nombre": nombre})

        # Si el cliente es nuevo
        saldo = total - deposito
        hoja_finanzas.append_row([nombre, celular, ambientes, total, deposito, saldo, "Pagado" if saldo <= 0 else "Pendiente"])
        
        mensaje_ws += f"Tu saldo pendiente es de {saldo}."
        enviar_whatsapp(celular, mensaje_ws) # <-- ENVÍO DE WHATSAPP
        return jsonify({"status": "creado", "nombre": nombre})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
