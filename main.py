"""
Monitor de CEDEARs - XLE y GLD con alertas por Telegram
Corre en Render.com (gratis, 24/7)
"""

import requests
import time
import os
from datetime import datetime
from flask import Flask
import threading

app = Flask(__name__)

# ============================================================
# ⚙️  CONFIGURACIÓN — se leen desde variables de entorno
# ============================================================
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID", "")
ALPHAVANTAGE_APIKEY = os.environ.get("ALPHAVANTAGE_APIKEY", "")

PRECIO_COMPRA = {
    "XLE": float(os.environ.get("PRECIO_XLE", "0")),
    "GLD": float(os.environ.get("PRECIO_GLD", "0")),
}

ALERTA_PORCENTAJE = 3.0
INTERVALO         = 1800   # 30 minutos
HORA_INICIO       = 9
HORA_FIN          = 20

# ============================================================

def obtener_precio(ticker: str) -> dict:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        meta = data["chart"]["result"][0]["meta"]
        precio_actual = round(float(meta["regularMarketPrice"]), 2)
        precio_cierre = round(float(meta["previousClose"]), 2)
        variacion_dia = round(((precio_actual - precio_cierre) / precio_cierre) * 100, 2)
        return {
            "ticker": ticker,
            "precio": precio_actual,
            "cierre_anterior": precio_cierre,
            "var_dia": variacion_dia,
            "ok": True,
        }
    except Exception as e:
        return {"ticker": ticker, "ok": False, "error": str(e)}


def calcular_var_compra(ticker: str, precio_actual: float) -> str:
    compra = PRECIO_COMPRA.get(ticker, 0)
    if compra <= 0:
        return "  📌 _Precio de compra no cargado_"
    var = round(((precio_actual - compra) / compra) * 100, 2)
    emoji = "🟢" if var >= 0 else "🔴"
    signo = "+" if var >= 0 else ""
    return f"  {emoji} vs compra (${compra}): *{signo}{var}%*"


def construir_mensaje(datos_list: list) -> str:
    ahora = datetime.now().strftime("%d/%m %H:%M")
    lineas = [f"📊 *Monitor CEDEARs* — {ahora} hs\n"]
    alertas = []

    for d in datos_list:
        if not d["ok"]:
            lineas.append(f"❌ {d['ticker']}: {d.get('error','error')}\n")
            continue

        ticker  = d["ticker"]
        precio  = d["precio"]
        var_dia = d["var_dia"]

        emoji_dia = "🟢" if var_dia >= 0 else "🔴"
        signo     = "+" if var_dia >= 0 else ""

        lineas.append(f"*{ticker}*")
        lineas.append(f"  💵 Precio: *${precio}*")
        lineas.append(f"  {emoji_dia} Variación día: *{signo}{var_dia}%*")
        lineas.append(calcular_var_compra(ticker, precio))

        compra = PRECIO_COMPRA.get(ticker, 0)
        if compra > 0:
            var_compra = ((precio - compra) / compra) * 100
            if abs(var_compra) >= ALERTA_PORCENTAJE:
                direccion = "SUBIÓ 📈" if var_compra > 0 else "BAJÓ 📉"
                alertas.append(
                    f"🚨 *ALERTA {ticker}*: {direccion} *{abs(round(var_compra,2))}%* desde tu compra!"
                )
        lineas.append("")

    if alertas:
        lineas.append("━━━━━━━━━━━━━━")
        lineas += alertas

    return "\n".join(lineas)


def enviar_telegram(mensaje: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       mensaje,
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Telegram: {resp.status_code}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error Telegram: {e}")


def ejecutar_chequeo():
    hora_actual = datetime.now().hour
    if not (HORA_INICIO <= hora_actual < HORA_FIN):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Fuera de horario, saltando...")
        return
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Consultando precios...")
    datos   = [obtener_precio("XLE"), obtener_precio("GLD")]
    mensaje = construir_mensaje(datos)
    print(mensaje)
    enviar_telegram(mensaje)


def loop_monitor():
    ejecutar_chequeo()
    while True:
        time.sleep(INTERVALO)
        ejecutar_chequeo()


# Render necesita un servidor web activo
@app.route("/")
def home():
    return "Monitor CEDEARs corriendo ✅"


# Arranca el hilo al importar — funciona con gunicorn y con python directo
hilo = threading.Thread(target=loop_monitor, daemon=True)
hilo.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
