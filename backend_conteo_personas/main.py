# backend_conteo_personas/main.py (modificado)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import os
import json
import threading
import time
import datetime
# import cv2 # No necesitas importar cv2 directamente aquí si PeopleCounterService lo maneja internamente

# Importar tus módulos locales
# Asegúrate de que la ruta sea correcta a tu nuevo archivo
from people_counter_service import PeopleCounterService, get_current_config_from_file # Importa la nueva clase y función

# --- Carga de configuración global (ajustaremos esto para que sea dinámico) ---
CONFIG_FILE_PATH = "utils/config.json"
SCHEDULE_CONFIG_PATH = "utils/schedule_config.json"

# Variables globales para el estado del conteo y los datos
# Usaremos un bloqueo para la seguridad de hilos si se acceden desde múltiples lugares
count_lock = threading.Lock()
current_counts = {
    "totalUp": 0,
    "totalDown": 0,
    "totalInside": 0,
    "status": "Inactivo",
    "last_update": None
}

# Variable para controlar el hilo de conteo y la instancia del servicio
counting_thread = None
people_counter_instance = None # Para almacenar la instancia de PeopleCounterService
stop_counting_event = threading.Event() # Evento para detener el hilo de forma segura

# --- Modelo Pydantic para la configuración (ya lo tenías) ---
class CameraConfig(BaseModel):
    url: str
    threshold: int = 10
    alert: bool = False
    log: bool = False
    timer: bool = False
    # Puedes añadir más campos de config.json si son relevantes para el frontend
    skip_frames: int = 30 # Añadido según people_counter_service
    confidence: float = 0.4 # Añadido según people_counter_service


class ScheduleRange(BaseModel):
    start: str
    end: str

class ScheduleConfig(BaseModel):
    active_days: list[str]
    time_ranges: list[ScheduleRange]
    email_report_receiver: str

# --- Instancia de FastAPI (ya la tenías) ---
app = FastAPI(
    title="API de Conteo de Personas",
    description="Backend para el conteo de personas mediante stream de video.",
    version="1.0.0"
)

# --- Endpoint de prueba (ya lo tenías) ---
@app.get("/")
async def root():
    return {"message": "API de Conteo de Personas en funcionamiento."}

# --- Endpoints para la configuración (ya los tenías, pero asegúrate de que CameraConfig tenga todos los campos) ---
@app.get("/config")
async def get_config():
    """Obtiene la configuración actual del sistema."""
    try:
        with open(CONFIG_FILE_PATH, "r") as f:
            config_data = json.load(f)
        return config_data
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archivo de configuración no encontrado.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Error al leer el archivo de configuración.")

@app.post("/config")
async def update_config(new_config: CameraConfig):
    """Actualiza la configuración del sistema."""
    try:
        with open(CONFIG_FILE_PATH, "r+") as f:
            current_config = json.load(f)
            # Actualiza solo los campos que están en new_config
            current_config.update(new_config.dict(exclude_unset=True))
            f.seek(0) # Vuelve al inicio del archivo
            json.dump(current_config, f, indent=2)
            f.truncate() # Recorta el resto del archivo si el nuevo contenido es más corto
        return {"message": "Configuración actualizada con éxito", "new_config": current_config}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archivo de configuración no encontrado.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Error al escribir el archivo de configuración.")

@app.get("/schedule")
async def get_schedule_config():
    """Obtiene la configuración actual del horario."""
    try:
        with open(SCHEDULE_CONFIG_PATH, "r") as f:
            schedule_data = json.load(f)
        return schedule_data
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archivo de configuración de horario no encontrado.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Error al leer el archivo de configuración de horario.")

@app.post("/schedule")
async def update_schedule_config(new_schedule: ScheduleConfig):
    """Actualiza la configuración del horario."""
    try:
        with open(SCHEDULE_CONFIG_PATH, "w") as f:
            json.dump(new_schedule.dict(), f, indent=2)
        return {"message": "Horario actualizado con éxito", "new_schedule": new_schedule}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al escribir el archivo de horario: {e}")

# --- Callback para que el hilo de conteo actualice los contadores globales ---
def update_global_counts(total_up, total_down, total_inside, status):
    with count_lock:
        current_counts["totalUp"] = total_up
        current_counts["totalDown"] = total_down
        current_counts["totalInside"] = total_inside
        current_counts["status"] = status
        current_counts["last_update"] = datetime.datetime.now().isoformat()

# --- Endpoints para el control del conteo (modificados) ---
@app.post("/start_counting")
async def start_counting():
    """Inicia el proceso de conteo de personas."""
    global counting_thread
    global people_counter_instance
    global stop_counting_event

    if counting_thread is not None and counting_thread.is_alive():
        return {"message": "El conteo de personas ya está en marcha."}

    # Restablece el evento de parada
    stop_counting_event.clear()

    try:
        # Cargar la configuración actual desde el archivo para el servicio
        current_app_config = get_current_config_from_file()
        camera_url = current_app_config.get("url")
        if not camera_url:
            raise HTTPException(status_code=400, detail="URL de la cámara no configurada en utils/config.json.")

        # Crear una instancia del servicio de conteo
        people_counter_instance = PeopleCounterService(
            camera_url=camera_url,
            update_callback=update_global_counts, # Pasa la función de callback
            stop_event=stop_counting_event,
            current_config=current_app_config # Pasa la configuración actual
        )

        # Iniciar el hilo que ejecuta el método run() del servicio
        counting_thread = threading.Thread(target=people_counter_instance.run)
        counting_thread.daemon = True
        counting_thread.start()

        with count_lock:
            current_counts["status"] = "Iniciando..." # Estado inicial mientras se conecta
            current_counts["last_update"] = datetime.datetime.now().isoformat()

        return {"message": "Iniciando el conteo de personas..."}
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Error de archivo: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al iniciar el conteo: {e}")

@app.post("/stop_counting")
async def stop_counting():
    """Detiene el proceso de conteo de personas."""
    global counting_thread
    global people_counter_instance
    global stop_counting_event

    if counting_thread is None or not counting_thread.is_alive():
        return {"message": "El conteo de personas no está activo."}

    logger.info("Solicitando detener el hilo de conteo...")
    stop_counting_event.set() # Señala al hilo que debe detenerse
    counting_thread.join(timeout=10) # Espera a que el hilo termine (con timeout)

    if counting_thread.is_alive():
        logger.error("No se pudo detener el conteo de personas de forma limpia.")
        raise HTTPException(status_code=500, detail="No se pudo detener el conteo de personas de forma limpia.")

    with count_lock:
        current_counts["status"] = "Detenido"
        current_counts["last_update"] = datetime.datetime.now().isoformat()

    logger.info("Conteo de personas detenido exitosamente.")
    return {"message": "Conteo de personas detenido."}

@app.get("/get_counts")
async def get_counts():
    """Obtiene los datos de conteo actuales."""
    with count_lock:
        return current_counts

# --- Endpoint para generar reporte (sin implementar aún la lógica de report_generator.py) ---
@app.post("/generate_report")
async def generate_report():
    """Genera un reporte diario y lo envía por correo."""
    try:
        # Aquí se ejecutaría la lógica de report_generator.py
        # Podrías importar tu script de report_generator.py y llamarlo aquí.
        # Por ejemplo:
        # from report_generator import generate_report_logic
        # generate_report_logic()
        print("Simulando la generación y envío de reporte...")
        # Llama a tu Mailer class o la lógica de report_generator.py aquí
        # from report_generator import generate_and_send_report (después de crearla)
        # generate_and_send_report()
        return {"message": "Reporte generado y enviado (simulado)."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar reporte: {e}")


# --- Iniciar el servidor Uvicorn ---
if __name__ == "__main__":
    # La configuración inicial de config.json se cargará automáticamente
    # cuando PeopleCounterService se inicialice en /start_counting
    uvicorn.run(app, host="0.0.0.0", port=8000)