from flask import Flask, request, jsonify
import gspread
from google.oauth2 import service_account
import pandas as pd
import os
import requests
import re
import unicodedata

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

def normalizar_texto(texto):
    """Elimina tildes y convierte a minúsculas para comparaciones exactas"""
    if not texto: return ""
    texto = str(texto).strip().lower()
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

@app.route("/", methods=["GET"])
def home():
    return "Servidor de Cotizaciones Activo 🚀", 200

@app.route("/confirmar_pago", methods=["POST"])
def confirmar_pago():
    gc = obtener_conexion_sheets()
    if not gc: return jsonify({"error": "No hay conexión con Sheets"}), 500
    
    try:
        data = request.get_json()
        nombre = data.get("nombre", "Sin Nombre")
        celular = data.get("celular", "")
        distrito = data.get("distrito", "No especificado")
        proyectos_raw = data.get("proyectos", [])

        doc = gc.open("Cotizaciones")
        h3 = doc.worksheet("Hoja3") # Precios
        h1 = doc.worksheet("Hoja1") # Saldos
        h5 = doc.worksheet("Hoja5") # Historial

        # --- PROCESAMIENTO DE DATOS DEL EXCEL ---
        df_precios = pd.DataFrame(h3.get_all_records())
        df_precios.columns = df_precios.columns.str.strip()
        
        # Limpieza profunda de la columna Precio (quita S/, comas, espacios)
        df_precios['Precio'] = df_precios['Precio'].replace(r'[S/,\s]', '', regex=True)
        df_precios['Precio'] = pd.to_numeric(df_precios['Precio'], errors='coerce')
        
        df_precios['RangoMin'] = pd.to_numeric(df_precios['RangoMin'], errors='coerce')
        df_precios['RangoMax'] = pd.to_numeric(df_precios['RangoMax'], errors='coerce')

        subtotal_acumulado = 0.0
        detalles_para_ia = []
        nombres_ambientes = []

        # --- CICLO PARA EVALUAR CADA AMBIENTE ---
        for p in proyectos_raw:
            amb_nombre = p.get("ambiente", "").strip()
            m2_valor = float(p.get("m2", 0))

            # Búsqueda robusta ignorando tildes y mayúsculas
            match = df_precios[
                (df_precios['Ambiente'].apply(normalizar_texto) == normalizar_texto(amb_nombre)) & 
                (df_precios['RangoMin'] <= m2_valor) & 
                (df_precios['RangoMax'] >= m2_valor)
            ]

            if not match.empty:
                precio_encontrado = float(match.iloc[0]['Precio'])
                subtotal_acumulado += precio_encontrado
                
                linea_detalle = f"{amb_nombre.upper()} ({m2_valor} m2) = S/ {precio_encontrado:.2f}"
                detalles_para_ia.append(linea_detalle)
                nombres_ambientes.append(amb_nombre)
                
                # Registro en Hoja 5
                h5.append_row([nombre, distrito, amb_nombre, m2_valor, precio_encontrado])

        if not detalles_para_ia:
            return jsonify({"error": f"No se encontró precio para {amb_nombre} con {m2_valor} m2"}), 404

        # --- CÁLCULOS FINALES ---
        igv = round(subtotal_acumulado * 0.18, 2)
        total_final = round(subtotal_acumulado + igv, 2)

        # Registro único en Hoja 1
        h1.append_row([nombre, str(celular), ", ".join(nombres_ambientes), total_final, 0.0, total_final, "Pendiente"])

        # --- MENSAJE DE WHATSAPP ---
        resumen_wsp = "\n".join([f"✅ *{d}*" for d in detalles_para_ia])
        mensaje_cot = (
            f"¡Hola {nombre}! ✨\n\nAquí tienes el presupuesto detallado:\n\n"
            f"{resumen_wsp}\n\n"
            f"💰 Subtotal: S/ {subtotal_acumulado:.2f}\n"
            f"📝 IGV (18%): S/ {igv:.2f}\n"
            f"💵 *TOTAL: S/ {total_final:.2f}*\n\n"
            f"📍 Distrito: {distrito}\n\n¿Deseas agendar una visita técnica? 🚀"
        )
        enviar_whatsapp(celular, mensaje_cot)

        # --- RESPUESTA PARA LA IA ---
        return jsonify({
            "status": "success",
            "nombre": nombre,
            "distrito": distrito,
            "detalles": detalles_para_ia,
            "subtotal": subtotal_acumulado,
            "igv": igv,
            "total": total_final
        })

    except Exception as e:
        print(f"❌ Error en Proceso: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
