from flask import Flask, request, jsonify
import gspread
from google.oauth2 import service_account
import pandas as pd
import os

# 1. Definir la APP primero para evitar errores de Gunicorn
app = Flask(__name__)

# 2. Configurar Google Sheets
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# 🔹 NOMBRE EXACTO (Mayúsculas importan)
nombre_documento = "Cotizaciones" 

# Variables globales para las hojas
hoja_finanzas = None
hoja_cotizaciones = None

def conectar_google_sheets():
    global hoja_finanzas, hoja_cotizaciones
    try:
        # Autenticación con el archivo JSON que subiste a Render
        creds = service_account.Credentials.from_service_account_file("credentials.json", scopes=scope)
        gc = gspread.authorize(creds)
        
        # Abrir el documento por su nombre exacto
        doc = gc.open(nombre_documento)
        
        # Conectar a las pestañas específicas
        hoja_finanzas = doc.worksheet("Hoja 1")
        hoja_cotizaciones = doc.worksheet("Hoja 5")
        print("✅ Conexión con Google Sheets 'Cotizaciones' exitosa")
        return True
    except Exception as e:
        print(f"❌ Error conectando a Google Sheets: {e}")
        return False

# Intentar la conexión inicial
conectar_google_sheets()

# 🔹 Función para Hoja 1 (Estado Financiero)
def actualizar_finanzas(nombre, celular, ambientes, total_cotizado, monto_pagado):
    if not hoja_finanzas:
        if not conectar_google_sheets():
            return {"error": "No se pudo conectar a la Hoja 1"}
        
    try:
        total = float(total_cotizado)
        deposito = float(monto_pagado)
        
        registros = hoja_finanzas.get_all_records()
        df = pd.DataFrame(registros)
        
        # Buscar cliente por Nombre
        cliente_existente = df[df["Nombre"] == nombre]

        if not cliente_existente.empty:
            # SI EXISTE: Sumar nuevo abono
            deposito_actual = float(cliente_existente.iloc[0]["Deposito"])
            nuevo_deposito = deposito_actual + deposito
            saldo = total - nuevo_deposito
            estado = "Pagado" if saldo <= 0 else "Pendiente"
            
            fila_index = cliente_existente.index[0] + 2
            # Actualizar columnas: 5:Deposito, 6:Saldo, 7:Estado
            hoja_finanzas.update_cell(fila_index, 5, nuevo_deposito)
            hoja_finanzas.update_cell(fila_index, 6, max(saldo, 0))
            hoja_finanzas.update_cell(fila_index, 7, estado)
        else:
            # SI NO EXISTE: Crear nueva fila
            saldo = total - deposito
            estado = "Pagado" if saldo <= 0 else "Pendiente"
            hoja_finanzas.append_row([nombre, celular, ambientes, total, deposito, saldo, estado])

        return {"status": "ok", "nombre": nombre, "saldo_actual": max(saldo, 0)}
    except Exception as e:
        return {"error": str(e)}

# 🔹 RUTAS DE LA API
@app.route("/", methods=["GET"])
def healthcheck():
    status_sheets = "CONECTADO" if hoja_finanzas else "DESCONECTADO"
    return jsonify({
        "backend": "activo", 
        "google_sheets": status_sheets,
        "archivo": nombre_documento
    })

@app.route("/confirmar_pago", methods=["POST"])
def confirmar_pago():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    resultado = actualizar_finanzas(
        data.get("nombre"), 
        data.get("celular"), 
        data.get("ambientes"),
        data.get("total_cotizado"), 
        data.get("monto_pagado")
    )
    return jsonify(resultado)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
