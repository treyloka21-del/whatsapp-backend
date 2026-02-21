from flask import Flask, request, jsonify
import gspread
from google.oauth2 import service_account
import pandas as pd
import os

app = Flask(__name__)

# Configuración de Google Sheets desde Variables de Entorno
def obtener_hojas():
    try:
        # Extraer variables de Render
        pk = os.environ.get("GOOGLE_PRIVATE_KEY")
        email = os.environ.get("GOOGLE_CLIENT_EMAIL")

        if not pk or not email:
            print("❌ Error: Faltan variables de entorno en Render")
            return None, None

        # Limpiar la llave (quitar comillas y arreglar saltos de línea)
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
        
        # Buscar hojas de forma flexible (Hoja 1 o Hoja1)
        h_fin = None
        h_cot = None
        for s in doc.worksheets():
            nombre_limpio = s.title.replace(" ", "").lower()
            if nombre_limpio == "hoja1": h_fin = s
            if nombre_limpio == "hoja5": h_cot = s
            
        return h_fin, h_cot
    except Exception as e:
        print(f"❌ Error en la conexión: {str(e)}")
        return None, None

# Intentar conectar
hoja_finanzas, hoja_cotizaciones = obtener_hojas()

@app.route("/", methods=["GET"])
def healthcheck():
    status = "CONECTADO" if hoja_finanzas else "DESCONECTADO"
    return jsonify({
        "backend": "activo",
        "google_sheets": status,
        "ayuda": "Si dice DESCONECTADO, revisa los Logs en Render"
    })

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
        
        # Lógica de actualización o inserción
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
                return jsonify({"status": "actualizado", "nombre": nombre})

        # Si el cliente es nuevo
        saldo = total - deposito
        hoja_finanzas.append_row([nombre, celular, ambientes, total, deposito, saldo, "Pagado" if saldo <= 0 else "Pendiente"])
        return jsonify({"status": "creado", "nombre": nombre})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
