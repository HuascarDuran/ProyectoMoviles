# backend_conteo_personas/report_service.py
import csv
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import os
import logging # Añadimos logging para mejor trazabilidad

# Configuración de logging para este módulo
logger = logging.getLogger(__name__)

# Rutas de los archivos (relativas a donde se ejecuta el main.py de FastAPI)
CSV_PATH = "utils/data/logs/counting_data.csv"
SCHEDULE_CONFIG_PATH = "utils/schedule_config.json" # Renombrado para consistencia
EMAIL_CONFIG_PATH = "utils/config.json"

def _cargar_json(path):
    """Función auxiliar para cargar archivos JSON."""
    if not os.path.exists(path):
        logger.error(f"Error: Archivo de configuración no encontrado en {path}")
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Error al leer JSON de {path}: {e}")
        return None

def generar_resumen_html():
    """Genera el resumen HTML del conteo diario."""
    if not os.path.exists(CSV_PATH):
        logger.warning(f"No hay archivo CSV de datos de conteo en {CSV_PATH}. No se puede generar resumen.")
        return "<p>No hay datos disponibles para hoy.</p>"

    entradas = 0
    salidas = 0

    try:
        with open(CSV_PATH, newline='') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Asegurarse de que las claves existan antes de acceder
                if row.get("Entradas") and row["Entradas"].strip():
                    entradas += int(row["Entradas"])
                if row.get("Salidas") and row["Salidas"].strip():
                    salidas += int(row["Salidas"])
        
        # Eliminar el archivo CSV después de generar el resumen para un nuevo día
        # Opcional: Podrías querer moverlo a una carpeta de históricos en lugar de borrarlo
        # os.remove(CSV_PATH) 
        # logger.info(f"Archivo de log CSV '{CSV_PATH}' procesado y eliminado.")

    except FileNotFoundError: # Debería ser capturado por os.path.exists, pero por seguridad
        logger.warning(f"Archivo CSV '{CSV_PATH}' no encontrado al intentar leerlo.")
        return "<p>No hay datos disponibles para hoy.</p>"
    except Exception as e:
        logger.error(f"Error al leer el archivo CSV o calcular resumen: {e}")
        return "<p>Error al generar el resumen de datos.</p>"


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

def send_daily_report_email():
    """
    Función principal para generar el reporte y enviarlo por correo.
    Esta es la función que será llamada por el endpoint de FastAPI.
    """
    logger.info("Iniciando generación y envío de reporte diario...")
    
    config_email = _cargar_json(EMAIL_CONFIG_PATH)
    config_schedule = _cargar_json(SCHEDULE_CONFIG_PATH) # Usamos schedule_config para email_report_receiver

    if not config_email:
        logger.error("No se pudo cargar la configuración de correo.")
        return False
    if not config_schedule:
        logger.error("No se pudo cargar la configuración de horario para el receptor del email.")
        return False

    remitente = config_email.get("Email_Send")
    receptor = config_schedule.get("email_report_receiver") # Del schedule_config.json
    password = config_email.get("Email_Password")

    if not remitente or not receptor or not password:
        logger.error(f"Faltan credenciales o receptor de correo. Remitente: {remitente}, Receptor: {receptor}, Contraseña: {'sí' if password else 'no'}")
        return False

    resumen_html = generar_resumen_html()
    if resumen_html == "<p>No hay datos disponibles para hoy.</p>":
         logger.info("No hay datos para el reporte diario. No se enviará correo.")
         return False

    msg = MIMEMultipart()
    fecha_asunto = datetime.now().strftime('%d/%m/%Y') # Formato estándar para Windows y Linux/macOS
    msg['Subject'] = f"📋 Reporte Diario - {fecha_asunto}"
    msg['From'] = remitente
    msg['To'] = receptor

    msg.attach(MIMEText(resumen_html, "html"))

    # Adjuntar archivo CSV si existe
    if os.path.exists(CSV_PATH):
        try:
            with open(CSV_PATH, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                fecha_archivo = datetime.now().strftime('%d-%m-%Y') # Formato estándar
                part.add_header("Content-Disposition", f"attachment; filename=conteo_{fecha_archivo}.csv")
                msg.attach(part)
            logger.info(f"Archivo CSV '{CSV_PATH}' adjuntado al correo.")
        except Exception as e:
            logger.error(f"Error al adjuntar archivo CSV: {e}")
            # Continuar enviando el correo sin el adjunto si este falla
    else:
        logger.warning(f"No se encontró el archivo CSV '{CSV_PATH}' para adjuntar.")

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(remitente, password)
        server.send_message(msg)
        server.quit()
        logger.info("Reporte enviado exitosamente.")
        
        # Opcional: Eliminar el CSV después de enviarlo si quieres un nuevo log cada día
        # Esto es importante para que el reporte sea "diario" y el CSV se resetee
        if os.path.exists(CSV_PATH):
            os.remove(CSV_PATH)
            logger.info(f"Archivo de log CSV '{CSV_PATH}' eliminado después de enviar reporte.")

        return True
    except Exception as e:
        logger.error(f"No se pudo enviar el correo del reporte: {e}")
        return False