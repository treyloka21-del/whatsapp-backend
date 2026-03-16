@app.route('/confirmar_pago', methods=['POST'])
def confirmar_pago():
    try:
        data = request.get_json() if request.is_json else request.form
        accion = data.get('accion', 'cotizar') # Recibe 'cotizar' o 'confirmar_pago'
        
        nombre_user = data.get('nombre', 'Cliente')
        distrito_user = data.get('distrito', 'No especificado').strip().upper()
        whatsapp_user = data.get('whatsapp', 'S/N')
        
        # Procesar proyecto
        proyectos_raw = data.get('proyecto') or data.get('proyectos', [])
        proyectos = json.loads(proyectos_raw) if isinstance(proyectos_raw, str) else proyectos_raw

        # --- LÓGICA DE CÁLCULO (Se mantiene igual) ---
        client = conectar_google()
        # ... (aquí va tu lógica actual de cálculo con Hoja3) ...
        # Supongamos que calculamos 'total_con_igv' y 'detalles_texto'
        
        # --- LÓGICA DE GUARDADO SEGÚN ACCIÓN ---
        
        if accion == "confirmar_pago":
            # GUARDAR EN HOJA 'Clients'
            sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Clients")
            sheet.append_row([
                nombre_user, whatsapp_user, distrito_user, 
                ", ".join(detalles_texto), total_con_igv, 0, total_con_igv, "Pendiente"
            ])
        else:
            # GUARDAR EN HOJA 'Leads' (Para análisis de consultas)
            try:
                sheet_leads = client.open_by_key(SPREADSHEET_ID).worksheet("Leads")
                sheet_leads.append_row([
                    nombre_user, whatsapp_user, distrito_user, 
                    ", ".join(detalles_texto), total_con_igv, "Solo Consulta"
                ])
            except:
                print("Crea la hoja 'Leads' en tu Excel")

        return jsonify({
            "status": "success",
            "total": total_con_igv,
            "detalles": detalles_texto
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
