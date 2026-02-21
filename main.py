from flask import Flask, request, jsonify
import gspread
from google.oauth2 import service_account
import pandas as pd
import os
import requests

app = Flask(__name__)

# --- CONFIGURACIÓN DE EVOLUTION API ---
# Extraemos de variables de entorno para que sea seguro
EVOLUTION_URL = os.environ.get("EVOLUTION_API_URL", "https://api-whatsapp-pro-v2.onrender.com")
EVOLUTION_KEY = os.environ.get("AUTHENTICATION_API_KEY", "trey123") # Clave que configuramos
# IMPORTANTE: INSTANCE_NAME debe ser el nombre que creaste al escanear el QR
INSTANCE_NAME = os.environ.get("INSTANCE_NAME", "tu_instancia") 

def enviar_whatsapp(numero, mensaje):
    """Función para enviar mensajes vía Evolution API v2"""
    try:
        # 1. Limpiar el número
        numero_limpio = "".join(filter(str.isdigit, str(numero)))
        
        # 2. Asegurar formato internacional (Ejemplo Perú: 51)
        if len(numero_limpio) == 9: 
            numero_limpio = "51" + numero_limpio

        # 3. Construir URL y Headers
        # La ruta correcta es /message/sendText/{instancia}
        url = f"{EVOLUTION_URL.rstrip('/')}/message/sendText/{INSTANCE_NAME}"
        
        headers = {
            "apikey": EVOLUTION_KEY,
            "Content-Type": "application/json"
        }
        
        payload = {
            "number": numero_limpio,
            "options": {
                "delay": 1200, 
                "presence": "composing", 
                "linkPreview": False
            },
            "textMessage": {"text": mensaje}
        }

        print(f"DEBUG: Intentando enviar a {url}")
        res = requests.post(url, json=payload, headers=headers)
        
        if res.status_code in [200, 201]:
            print("✅ WhatsApp enviado con éxito")
            return True
        else:
            print(f"❌ Error API ({res.status_code}): {res.text}")
            return False

    except Exception as e:
        print(f"❌ Exception en enviar_whatsapp: {e}")
        return False

# --- CONFIGURACIÓN DE GOOGLE SHEETS ---
def obtener_hojas():
    try:
        pk = os.environ.get("GOOGLE_PRIVATE_KEY")
        email = os.environ.get("GOOGLE_CLIENT_EMAIL")
        if not pk or not email:
            print("⚠️ Faltan credenciales de Google en Environment Variables")
            return None, None
        
        # Limpieza de la llave privada
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
        
        # Abrir el documento
        doc = gc.open("Cotizaciones")
        h_fin = None
        
        for s in doc.worksheets():
            nombre_limpio = s.title.replace(" ", "").lower()
            if nombre_limpio == "hoja1": h_fin = s
            
        return h_fin, None
    except Exception as e:
        print(f"❌ Error en la conexión Sheets: {str(e)}")
        return None, None

# --- RUTAS ---

@app.route("/", methods=["GET"])
def healthcheck():
    # Intentamos conectar a hojas si no está conectado
    h_fin, _ = obtener_hojas()
    status = "CONECTADO" if h_fin else "DESCONECTADO"
    return jsonify({
        "backend": "activo", 
        "google_sheets": status,
        "instancia_api": INSTANCE_NAME
    })

@app.route("/confirmar_pago", methods=["POST"])
def confirmar_pago():
    h_fin, _ = obtener_hojas()
    if not h_fin:
        return jsonify({"error": "No hay conexión con Google Sheets"}), 500
    
    try:
        data = request.get_json()
        nombre = data.get("nombre", "Sin Nombre")
        total = float(data.get("total_cotizado", 0))
        deposito = float(data.get("monto_pagado", 0))
        celular = data.get("celular", "")
        
        # 1. Registrar en Google Sheets
        registros = h_fin.get_all_records()
        df = pd.DataFrame(registros)
        
        mensaje_ws = f"¡Hola {nombre}! Hemos registrado tu pago de {deposito}. "
        
        if not df.empty and "Nombre" in df.columns:
            cliente_existente = df[df["Nombre"] == nombre]
            if not cliente_existente.empty:
                fila_index = cliente_existente.index[0] + 2
                dep_actual = float(cliente_existente.iloc[0].get("Deposito", 0))
                nuevo_dep = dep_actual + deposito
                saldo = total - nuevo_dep
                
                h_fin.update_cell(fila_index, 5, nuevo_dep) # Columna Deposito
                h_fin.update_cell(fila_index, 6, max(saldo, 0)) # Columna Saldo
                h_fin.update_cell(fila_index, 7, "Pagado" if saldo <= 0 else "Pendiente")
                
                mensaje_ws += f"Tu saldo actual es de {max(saldo, 0)}."
                enviar_whatsapp(celular, mensaje_ws)
                return jsonify({"status": "actualizado", "nombre": nombre})

        # 2. Si es cliente nuevo
        saldo = total - deposito
        h_fin.append_row([nombre, celular, "Cotización", total, deposito, saldo, "Pagado" if saldo <= 0 else "Pendiente"])
        
        mensaje_ws += f"Tu saldo pendiente es de {saldo}."
        enviar_whatsapp(celular, mensaje_ws)
        
        return jsonify({"status": "creado", "nombre": nombre})

    except Exception as e:
        print(f"❌ Error en confirmar_pago: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Render usa el puerto 8080 por defecto para gunicorn, pero esto ayuda en local
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
