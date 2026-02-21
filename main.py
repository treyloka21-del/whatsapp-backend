from flask import Flask, request, jsonify
import gspread
from google.oauth2 import service_account  # 🔹 Librería moderna
import pandas as pd
import os

app = Flask(__name__)

# 🔹 Configurar Google Sheets
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Ruta al JSON (En Render está en la raíz según configuramos)
ruta_json = "credentials.json"

try:
    creds = service_account.Credentials.from_service_account_file(ruta_json, scopes=scope)
    client = gspread.authorize(creds)
    
    # 🔹 Definir hojas de Google Sheets (CAMBIA LOS NOMBRES AQUÍ)
    nombre_documento = "Nombre_de_tu_sheets" 
    hoja_finanzas = client.open(nombre_documento).worksheet("Hoja1")
    hoja_cotizaciones = client.open(nombre_documento).worksheet("Hoja5")
    print("Conexión con Google Sheets exitosa")
except Exception as e:
    print(f"Error conectando a Google Sheets: {e}")

# 🔹 Función para guardar pagos pendientes
def guardar_pago_pendiente(nombre, celular, ambientes, total_cotizado, monto_pagado, voucher_url=None):
    hoja_cotizaciones.append_row([nombre, celular, ambientes, total_cotizado, monto_pagado, "Pendiente", voucher_url])
    return {"status": "pendiente", "nombre": nombre}

# 🔹 Función para actualizar finanzas
def actualizar_finanzas(nombre, celular, ambientes, total_cotizado, monto_pagado):
    total = float(total_cotizado)
    deposito = float(monto_pagado)
    
    registros = hoja_finanzas.get_all_records()
    df = pd.DataFrame(registros)
    cliente_existente = df[df["Nombre"] == nombre]

    if not cliente_existente.empty:
        deposito_actual = float(cliente_existente.iloc[0]["Deposito"])
        nuevo_deposito = deposito_actual + deposito
        saldo = total - nuevo_deposito
        estado = "Pagado" if saldo <= 0 else "Pendiente"
        
        fila_index = cliente_existente.index[0] + 2
        hoja_finanzas.update_cell(fila_index, 4, nuevo_deposito)
        hoja_finanzas.update_cell(fila_index, 5, max(saldo, 0))
        hoja_finanzas.update_cell(fila_index, 6, estado)
    else:
        saldo = total - deposito
        estado = "Pagado" if saldo <= 0 else "Pendiente"
        hoja_finanzas.append_row([nombre, celular, ambientes, total, deposito, saldo, estado])

    return {"nombre": nombre, "total": total, "deposito": deposito, "saldo": saldo, "estado": estado}

@app.route("/webhook_pago", methods=["POST"])
def webhook_pago():
    data = request.get_json()
    nombre = data.get("nombre")
    celular = data.get("celular")
    ambientes = data.get("ambientes")
    total_cotizado = data.get("total_cotizado")
    monto_pagado = data.get("monto_pagado")
    voucher_url = data.get("voucher_url")

    if not all([nombre, celular, ambientes, total_cotizado, monto_pagado]):
        return jsonify({"error": "Faltan datos"}), 400

    resultado = guardar_pago_pendiente(nombre, celular, ambientes, total_cotizado, monto_pagado, voucher_url)
    return jsonify({"status": "ok", "resultado": resultado})

@app.route("/confirmar_pago", methods=["POST"])
def confirmar_pago():
    data = request.get_json()
    nombre = data.get("nombre")
    monto_pagado = data.get("monto_pagado")
    total_cotizado = data.get("total_cotizado")
    celular = data.get("celular")
    ambientes = data.get("ambientes")

    resultado = actualizar_finanzas(nombre, celular, ambientes, total_cotizado, monto_pagado)
    return jsonify({"status": "confirmado", "resultado": resultado})

@app.route("/", methods=["GET"])
def healthcheck():
    return jsonify({"status": "Backend activo"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
