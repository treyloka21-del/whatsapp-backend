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
    """Envía mensaje de texto a través de Evolution API"""
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
    """Establece conexión con Google Sheets usando variables de entorno"""
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

# --- RUTA QUE RECIBE DE N8N ---
@app.route("/confirmar_pago", methods=["POST"])
def confirmar_pago():
    gc = obtener_conexion_sheets()
    if not gc: return jsonify({"error": "No hay conexión con Sheets"}), 500
    
    try:
        data = request.get_json()
        
        # --- CAPTURA DE DATOS DEL CLIENTE ---
        nombre = data.get("Nombre", data.get("nombre", "Sin Nombre"))
        celular = data.get("Celular", data.get("celular", ""))
        distrito = data.get("Distrito", data.get("distrito", "No especificado"))
        
        # --- PROCESAMIENTO DE AMBIENTES (LISTA) ---
        # Si viene un solo ambiente, lo convertimos en lista para que el código no falle
        proyectos_raw = data.get("proyectos", [])
        if not proyectos_raw:
            # Soporte para el formato antiguo de un solo ambiente
            amb_unico = data.get("Ambiente", data.get("ambiente"))
            m2_unico = data.get("m2", data.get("M2"))
            if amb_unico:
                proyectos_raw = [{"ambiente": amb_unico, "m2": m2_unico}]

        # Conectar al documento
        doc = gc.open("Cotizaciones")
        h3 = doc.worksheet("Hoja3") # Precios
        h1 = doc.worksheet("Hoja1") # Saldos
        h5 = doc.worksheet("Hoja5") # Historial

        df_precios = pd.DataFrame(h3.get_all_records())
        df_precios.columns = df_precios.columns.str.strip()
        df_precios['RangoMin'] = pd.to_numeric(df_precios['RangoMin'], errors='coerce')
        df_precios['RangoMax'] = pd.to_numeric(df_precios['RangoMax'], errors='coerce')
        df_precios['Precio'] = pd.to_numeric(df_precios['Precio'], errors='coerce')

        subtotal_acumulado = 0
        detalles_lista = []
        nombres_ambientes = []

        # --- CICLO PARA EVALUAR CADA AMBIENTE ---
        for p in proyectos_raw:
            amb_nombre = p.get("ambiente", "").strip()
            try:
                m2_valor = float(p.get("m2", 0))
            except:
                m2_valor = 0.0

            match = df_precios[
                (df_precios['Ambiente'].astype(str).str.strip().str.lower() == amb_nombre.lower()) & 
                (df_precios['RangoMin'] <= m2_valor) & 
                (df_precios['RangoMax'] >= m2_valor)
            ]

            if not match.empty:
                precio_fila = float(match.iloc[0]['Precio'])
                subtotal_acumulado += precio_fila
                detalles_lista.append(f"✅ *{amb_nombre}* ({m2_valor}m2): S/ {precio_fila:.2f}")
                nombres_ambientes.append(amb_nombre)
                
                # Registro individual en Historial (Hoja 5)
                h5.append_row([nombre, distrito, amb_nombre, m2_valor, precio_fila])

        if not detalles_lista:
            return jsonify({"error": "No se encontró ningún ambiente válido para cotizar"}), 404

        # --- CÁLCULOS FINALES ---
        igv = subtotal_acumulado * 0.18
        total_final = subtotal_acumulado + igv
        lista_ambientes_str = ", ".join(nombres_ambientes)

        # Registro único en Hoja 1 (Resumen de deuda)
        h1.append_row([nombre, celular, f"Cotización: {lista_ambientes_str}", total_final, 0, total_final, "Pendiente"])

        # --- MENSAJE DE WHATSAPP ---
        resumen_texto = "\n".join(detalles_lista)
        mensaje_cot = (
            f"¡Hola {nombre}! ✨\n\n"
            f"Aquí tienes el presupuesto detallado para tus espacios:\n\n"
            f"{resumen_texto}\n\n"
            f"--------------------------\n"
            f"💰 Subtotal: S/ {subtotal_acumulado:.2f}\n"
            f"📝 IGV (18%): S/ {igv:.2f}\n"
            f"💵 *TOTAL: S/ {total_final:.2f}*\n\n"
            f"📍 Distrito: {distrito}\n\n"
            f"¿Deseas que agendemos una visita técnica para validar los espacios? 🚀"
        )
        enviar_whatsapp(celular, mensaje_cot)

        return jsonify({"status": "Multi-cotización exitosa", "total": total_final})

    except Exception as e:
        print(f"❌ Error en Proceso: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
