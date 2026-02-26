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

try:
    client = conectar_google()
    print("✅ Conexión exitosa a Google Sheets")
except Exception as e:
    print(f"❌ Error de conexión: {e}")

SPREADSHEET_ID = "1os4j4fVMY8Jx07IXR9DD2RUgY1IK4HSLtQJH8B7z8Rw"

def leer_y_limpiar_excel():
    # Abrimos la Hoja3
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Hoja3")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    # Función para limpiar los números del Excel (Ej: "1.040,00" -> 1040.0)
    def limpiar_numero(valor):
        if isinstance(valor, str):
            # Quitamos el punto de miles y cambiamos la coma decimal por punto
            valor = valor.replace('.', '').replace(',', '.')
        try:
            return float(valor)
        except:
            return 0.0

    # Aplicamos la limpieza a las columnas numéricas
    df['RangoMin'] = df['RangoMin'].apply(limpiar_numero)
    df['RangoMax'] = df['RangoMax'].apply(limpiar_numero)
    df['Precio'] = df['Precio'].apply(limpiar_numero)
    
    return df

@app.route('/', methods=['GET'])
def home():
    return "Servidor Cotizador Activo ✅", 200

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

            # Filtrar por nombre de ambiente
            df_amb = df[df['Ambiente'].str.strip().str.lower() == ambiente_user]
            
            # Buscar el rango correcto: RangoMin <= m2 <= RangoMax
            fila = df_amb[(df_amb['RangoMin'] <= m2_user) & (df_amb['RangoMax'] >= m2_user)]

            if not fila.empty:
                precio_fijo = float(fila.iloc[0]['Precio'])
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
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
