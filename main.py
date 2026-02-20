from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

@app.get("/")
def root():
    return {"status": "Backend activo"}

@app.post("/webhook")
async def receive_data(request: Request):
    data = await request.json()

    if not N8N_WEBHOOK_URL:
        return {"error": "N8N_WEBHOOK_URL no configurado"}

    try:
        response = requests.post(N8N_WEBHOOK_URL, json=data, timeout=10)
        return {
            "status": "Enviado a n8n",
            "n8n_status": response.status_code
        }
    except Exception as e:
        return {
            "error": str(e)
        }
      
