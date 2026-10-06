"""
Monitor de CEDEARs con alertas por Telegram
Corre en Render.com (gratis, 24/7)
Envía 1 mensaje por día a las 12:00 hs Argentina (lunes a viernes)
"""

import requests
import time
import os
from datetime import datetime
from flask import Flask
import threading
import schedule

app = Flask(__name__)

# ============================================================
# ⚙️  CONFIGURACIÓN
# ============================================================
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID", "")

# Cartera: ticker NYSE -> (cantidad, precio_compra_usd)
CARTERA = {
    "IREN.BA":  (27,  3.62),
    "NVDA.BA":  (14, 10.50),
    "MU.BA":    (1,  222.75),
    "IBIT.BA":  (19,  5.07),
    "GOOGL.BA": (15,  6.27),
    "AVGO.BA":  (9,  10.16),
    "VST.BA":   (15,  6.49),
}

ALERTA_PORCENTAJE = 5.0   # alerta si varía más de 5% vs compra
HORARIO_ENVIO     = "12:00"  # hora Argentina

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
            "var_dia": variacion_dia,
            "ok": True,
        }
    except Exception as e:
        return {"ticker": ticker, "ok": False, "error": str(e)}


def construir_mensaje(resultados: list) -> str:
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    lineas = [f"📊 *Resumen Cartera* — {ahora} hs\n"]

    total_invertido = 0
    total_actual    = 0
    alertas         = []

    for d in resultados:
        ticker = d["ticker"]
        cant, p_compra = CARTERA[ticker]
        total_invertido += cant * p_compra

        if not d["ok"]:
            lineas.append(f"❌ *{ticker}*: error al obtener datos\n")
            continue

        precio   = d["precio"]
        var_dia  = d["var_dia"]
        valor_actual   = round(cant * precio, 2)
        valor_compra   = round(cant * p_compra, 2)
        var_compra     = round(((precio - p_compra) / p_compra) * 100, 2)
        gan_perdida    = round(valor_actual - valor_compra, 2)
        total_actual  += valor_actual

        emoji_dia    = "🟢" if var_dia >= 0 else "🔴"
        emoji_compra = "🟢" if var_compra >= 0 else "🔴"
        signo_dia    = "+" if var_dia >= 0 else ""
        signo_compra = "+" if var_compra >= 0 else ""
        signo_gan    = "+" if gan_perdida >= 0 else ""

        lineas.append(f"*{ticker}* ({cant} acc.)")
        lineas.append(f"  💵 Precio: *${precio}* | Compra: ${p_compra}")
        lineas.append(f"  {emoji_dia} Hoy: *{signo_dia}{var_dia}%*")
        lineas.append(f"  {emoji_compra} vs Compra: *{signo_compra}{var_compra}%* ({signo_gan}${gan_perdida})")
        lineas.append("")

        if abs(var_compra) >= ALERTA_PORCENTAJE:
            dir = "SUBIÓ 📈" if var_compra > 0 else "BAJÓ 📉"
            alertas.append(f"🚨 *{ticker}*: {dir} *{abs(var_compra)}%* desde tu compra!")

    # Resumen total
    total_var = round(((total_actual - total_invertido) / total_invertido) * 100, 2)
    gan_total = round(total_actual - total_invertido, 2)
    emoji_total = "🟢" if total_var >= 0 else "🔴"
    signo_total = "+" if gan_total >= 0 else ""

    lineas.append("━━━━━━━━━━━━━━")
    lineas.append(f"💼 *TOTAL CARTERA*")
    lineas.append(f"  Invertido: *${round(total_invertido, 2)}*")
    lineas.append(f"  Actual:    *${round(total_actual, 2)}*")
    lineas.append(f"  {emoji_total} Resultado: *{signo_total}${gan_total} ({signo_total}{total_var}%)*")

    if alertas:
        lineas.append("")
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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Consultando precios...")
    resultados = [obtener_precio(t) for t in CARTERA.keys()]
    mensaje = construir_mensaje(resultados)
    print(mensaje)
    enviar_telegram(mensaje)


def loop_monitor():
    schedule.every().monday.at(HORARIO_ENVIO).do(ejecutar_chequeo)
    schedule.every().tuesday.at(HORARIO_ENVIO).do(ejecutar_chequeo)
    schedule.every().wednesday.at(HORARIO_ENVIO).do(ejecutar_chequeo)
    schedule.every().thursday.at(HORARIO_ENVIO).do(ejecutar_chequeo)
    schedule.every().friday.at(HORARIO_ENVIO).do(ejecutar_chequeo)
    print(f"Monitor activo — envío diario a las {HORARIO_ENVIO} hs (lunes a viernes)")
    while True:
        schedule.run_pending()
        time.sleep(30)


@app.route("/")
def home():
    return "Monitor Cartera corriendo ✅"


# Arranca el hilo al importar — funciona con gunicorn y python directo
hilo = threading.Thread(target=loop_monitor, daemon=True)
hilo.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
