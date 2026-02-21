# ... (inicio del código igual)

# 🔹 Configuración de nombres (AJUSTA EL NOMBRE DEL ARCHIVO AQUÍ)
nombre_documento = "EL_NOMBRE_DE_TU_ARCHIVO_DE_SHEETS" 

try:
    doc = client.open(nombre_documento)
    hoja_finanzas = doc.worksheet("Hoja 1")     # Hoja 1: Nombre, Celular, Ambientes, Total, Deposito, Saldo, Estado
    hoja_cotizaciones = doc.worksheet("Hoja 5") # Hoja 5: Nombre, Celular, Ambientes, Total_Cotizado, Monto_pagado, Estado, Voucher_URL
    print("Conexión exitosa")
except Exception as e:
    print(f"Error: {e}")

# 🔹 Función para Hoja 1 (Estado Financiero)
def actualizar_finanzas(nombre, celular, ambientes, total_cotizado, monto_pagado):
    total = float(total_cotizado)
    deposito = float(monto_pagado)
    
    registros = hoja_finanzas.get_all_records()
    df = pd.DataFrame(registros)
    
    # Buscamos por Nombre (Asegúrate que la columna en Hoja 1 se llame "Nombre")
    cliente_existente = df[df["Nombre"] == nombre]

    if not cliente_existente.empty:
        # Si ya existe, sumamos el abono
        deposito_actual = float(cliente_existente.iloc[0]["Deposito"])
        nuevo_deposito = deposito_actual + deposito
        saldo = total - nuevo_deposito
        estado = "Pagado" if saldo <= 0 else "Pendiente"
        
        fila_index = cliente_existente.index[0] + 2
        # Columnas: 1:Nombre, 2:Celular, 3:Ambientes, 4:Total, 5:Deposito, 6:Saldo, 7:Estado
        hoja_finanzas.update_cell(fila_index, 5, nuevo_deposito)
        hoja_finanzas.update_cell(fila_index, 6, max(saldo, 0))
        hoja_finanzas.update_cell(fila_index, 7, estado)
    else:
        # Si es nuevo, creamos la fila
        saldo = total - deposito
        estado = "Pagado" if saldo <= 0 else "Pendiente"
        # Orden: Nombre, Celular, Ambientes, Total, Deposito, Saldo, Estado
        hoja_finanzas.append_row([nombre, celular, ambientes, total, deposito, saldo, estado])
