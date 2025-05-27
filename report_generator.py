import csv
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import os

CSV_PATH = "utils/data/logs/counting_data.csv"
CONFIG_PATH = "utils/schedule_config.json"
EMAIL_CONFIG_PATH = "utils/config.json"

def cargar_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def cargar_email_config():
    with open(EMAIL_CONFIG_PATH, "r") as f:
        return json.load(f)

def generar_resumen():
    if not os.path.exists(CSV_PATH):
        return "<p>No hay datos disponibles para hoy.</p>"

    entradas = 0
    salidas = 0

    with open(CSV_PATH, newline='') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row.get("Entradas"):
                entradas += int(row["Entradas"])
            if row.get("Salidas"):
                salidas += int(row["Salidas"])

    total = entradas - salidas
    fecha = datetime.now().strftime('%d/%m/%Y')

    resumen = f"""
    <html>
        <body>
            <h2>Reporte Diario - {fecha}</h2>
            <table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; font-family: Arial;">
                <tr><th>Detalle</th><th>Valor</th></tr>
                <tr><td>👥 Personas que entraron</td><td>{entradas}</td></tr>
                <tr><td>🚪 Personas que salieron</td><td>{salidas}</td></tr>
                <tr><td>🟢 Total dentro al cierre</td><td>{total}</td></tr>
            </table>
            <p style="font-size: 13px; color: gray; margin-top: 20px;">
                Este reporte fue generado automáticamente por el sistema de conteo de personas.<br>
                Gracias por utilizar <strong>Punto Axzo – Control de Tráfico en Tiendas</strong>.
            </p>
        </body>
    </html>
    """
    return resumen

def enviar_correo(reporte):
    config_email = cargar_email_config()
    config_general = cargar_config()

    remitente = config_email["Email_Send"]
    receptor = config_general["email_report_receiver"]
    password = config_email["Email_Password"]

    if not remitente or not receptor or not password:
        print(f"[ERROR] Faltan credenciales de correo. Remitente: {remitente}, Receptor: {receptor}, Contraseña: {'sí' if password else 'no'}")
        return

    msg = MIMEMultipart()
    fecha_asunto = datetime.now().strftime('%-d/%-m/%Y') if os.name != 'nt' else datetime.now().strftime('%#d/%#m/%Y')
    msg['Subject'] = f"📋 Reporte Diario - {fecha_asunto}"
    msg['From'] = remitente
    msg['To'] = receptor

    # Parte HTML
    msg.attach(MIMEText(reporte, "html"))

    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            fecha = datetime.now().strftime('%-d-%-m-%Y') if os.name != 'nt' else datetime.now().strftime('%#d-%#m-%Y')
            part.add_header("Content-Disposition", f"attachment; filename=conteo_{fecha}.csv")
            msg.attach(part)

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(remitente, password)
        server.send_message(msg)
        server.quit()
        print("[INFO] Reporte enviado exitosamente.")
    except Exception as e:
        print(f"[ERROR] No se pudo enviar el correo: {e}")

if __name__ == "__main__":
    resumen = generar_resumen()
    enviar_correo(resumen)