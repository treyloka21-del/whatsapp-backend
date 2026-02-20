from flask import Flask, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

app = Flask(__name__)

# 🔹 Google Sheets
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

hoja_finanzas = client.open("Nombre_de_tu_sheets").worksheet("Hoja1")  # Estado financiero
hoja_cotizaciones = client.open("Nombre_de_tu_sheets").worksheet("Hoja5")  # Historial cotizaciones

# 🔹 Guardar pagos pendientes (Hoja5)
def guardar_pago_pendiente(nombre, celular, ambientes, total_cotizado, monto_pagado, voucher_url=None):
    hoja_cotizaciones.append_row([nombre, celular, ambientes, total_cotizado, monto_pagado, "Pendiente", voucher_url])
    return {"status": "pendiente", "nombre": nombre}

# 🔹 Actualizar Hoja 1 después de confirmación
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

# 🔹 Endpoint para recibir pagos desde WhatsApp/n8n
@app.route("/webhook_pago", methods=["POST"])
def webhook_pago():
    data = request.json

    nombre = data.get("nombre")
    celular = data.get("celular")
    ambientes = data.get("ambientes")
    total_cotizado = data.get("total_cotizado")
    monto_pagado = data.get("monto_pagado")
    voucher_url = data.get("voucher_url")  # foto del pago si viene de WhatsApp

    if not all([nombre, celular, ambientes, total_cotizado, monto_pagado]):
        return jsonify({"error": "Faltan datos"}), 400

    # Guardamos en Hoja5 y esperamos confirmación de la diseñadora
    resultado = guardar_pago_pendiente(nombre, celular, ambientes, total_cotizado, monto_pagado, voucher_url)
    return jsonify({"status": "ok", "resultado": resultado})

# 🔹 Endpoint que la diseñadora usa para confirmar un pago
@app.route("/confirmar_pago", methods=["POST"])
def confirmar_pago():
    data = request.json
    nombre = data.get("nombre")
    monto_pagado = data.get("monto_pagado")
    total_cotizado = data.get("total_cotizado")
    celular = data.get("celular")
    ambientes = data.get("ambientes")

    # Solo se ejecuta después de verificación manual
    resultado = actualizar_finanzas(nombre, celular, ambientes, total_cotizado, monto_pagado)
    return jsonify({"status": "confirmado", "resultado": resultado})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
