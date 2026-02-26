from flask import Flask, request, jsonify
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os

app = Flask(__name__)

# --- CONFIGURACIÓN DE GOOGLE SHEETS ---
def conectar_google():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    pk = os.environ.get('GOOGLE_PRIVATE_KEY')
    email = os.environ.get('GOOGLE_CLIENT_EMAIL')

    if not pk or not email:
        raise ValueError("Faltan variables GOOGLE_PRIVATE_KEY o GOOGLE_CLIENT_EMAIL en Render")

    # Reparamos la llave para evitar errores de PEM
    pk_limpia = pk.replace('\\n', '\n')
    info = {
        "type": "service_account",
        "project_id": "whatsapp-backend-488021",
        "private_key": pk_limpia,
        "client_email": email,
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    creds = Credentials.from_service_account_info(info, scopes=scope)
    return gspread.authorize(creds)

# Inicialización de la conexión
client = None
try:
    client = conectar_google()
    print("✅ Conexión exitosa a Google Sheets")
except Exception as e:
    print(f"❌ Error de conexión inicial: {e}")

SPREADSHEET_ID = "1os4j4fVMY8Jx07IXR9DD2RUgY1IK4HSLtQJH8B7z8Rw"

def leer_y_limpiar_excel():
    global client
    if client is None:
        client = conectar_google()
        
    # Accedemos específicamente a la Hoja3
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Hoja3")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    # Función robusta para limpiar formatos de moneda peruanos (Ej: "1.040,00" -> 1040.0)
    def limpiar_numero(valor):
        if valor is None or valor == "": return 0.0
        valor_str = str(valor).strip()
        # Quitamos puntos de miles y cambiamos coma decimal por punto
        valor_str = valor_str.replace('.', '').replace(',', '.')
        try:
            return float(valor_str)
        except:
            return 0.0

    # Aplicamos limpieza a las columnas críticas
    df['RangoMin'] = df['RangoMin'].apply(limpiar_numero)
    df['RangoMax'] = df['RangoMax'].apply(limpiar_numero)
    df['Precio'] = df['Precio'].apply(limpiar_numero)
    
    return df

@app.route('/', methods=['GET'])
def home():
    # Mensaje de control para saber que el código cambió
    return "Servidor Cotizador ONLINE - Versión v2.0 🚀", 200

@app.route('/confirmar_pago', methods=['POST'])
def confirmar_pago():
    try:
        data = request.get_json()
        proyectos = data.get('proyectos', [])
        df = leer_y_limpiar_excel()
        
        subtotal = 0
        detalles = []

        for p in proyectos:
            ambiente_user = str(p.get('ambiente', '')).strip().lower()
            m2_user = float(p.get('m2', 0))

            # Filtrar por ambiente
            df_amb = df[df['Ambiente'].str.strip().str.lower() == ambiente_user]
            
            # Buscar rango exacto
            fila = df_amb[(df_amb['RangoMin'] <= m2_user) & (df_amb['RangoMax'] >= m2_user)]

            if not fila.empty:
                # OBTENEMOS EL PRECIO FIJO DE LA TABLA
                precio_fijo = float(fila.iloc[0]['Precio'])
                
                # IMPORTANTE: Aquí NO hay multiplicación por m2. Es suma directa.
                subtotal += precio_fijo
                detalles.append(f"{ambiente_user.upper()} ({m2_user} m2) = S/ {precio_fijo:,.2f}")
            else:
                detalles.append(f"No hay rango para {ambiente_user} con {m2_user} m2")

        igv = subtotal * 0.18
        total = subtotal + igv

        return jsonify({
            "status": "success",
            "detalles": detalles,
            "subtotal": round(subtotal, 2),
            "igv": round(igv, 2),
            "total": round(total, 2)
        }), 200

    except Exception as e:
        print(f"❌ Error en /confirmar_pago: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Usamos el puerto que Render nos asigne o el 8080 por defecto
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
