# backend_conteo_personas/people_counter_service.py

# Importaciones necesarias (mantén las que ya tenías y elimina las de GUI)
from tracker.centroidtracker import CentroidTracker
from tracker.trackableobject import TrackableObject
from imutils.video import VideoStream # Aunque usaremos cv2.VideoCapture directamente, imutils.video.FPS es útil
from itertools import zip_longest
from utils.mailer import Mailer
from imutils.video import FPS
from utils import thread # Si config["Thread"] es True
import numpy as np
import threading
import datetime
import logging
import imutils
import time
import dlib
import json
import csv
import cv2
import os

# Suponiendo que config.json y schedule_config.json están en utils/
CONFIG_FILE_PATH = "utils/config.json"
SCHEDULE_CONFIG_PATH = "utils/schedule_config.json"

# Configuración de logging para este módulo
logging.basicConfig(level=logging.INFO, format="[INFO] %(message)s")
logger = logging.getLogger(__name__)

# --- Carga de configuración (para uso interno de esta clase/función) ---
# En un entorno de producción, es mejor cargar esto una sola vez o pasarlo como parámetro
try:
    with open(CONFIG_FILE_PATH, "r") as file:
        config = json.load(file)
except FileNotFoundError:
    logger.error(f"Error: {CONFIG_FILE_PATH} no encontrado.")
    config = {} # Configuración vacía si no se encuentra
except json.JSONDecodeError:
    logger.error(f"Error: {CONFIG_FILE_PATH} no es un JSON válido.")
    config = {}

# Clases y funciones auxiliares (Mailer, log_data, etc. si se usan directamente aquí)
# No necesitas redefinir Mailer si lo importas.

# Función para enviar correo (puede ser llamada por Mailer().send)
def send_mail_alert(receiver_email, threshold):
    """
    Función para enviar alertas por correo electrónico.
    Se conecta a las credenciales de config.json.
    """
    if not config.get("ALERT", False):
        logger.info("Alertas por correo electrónico deshabilitadas en la configuración.")
        return

    try:
        mailer = Mailer() # Mailer ya carga la configuración
        mailer.send(receiver_email)
        logger.info("Alerta por correo enviada con éxito.")
    except Exception as e:
        logger.error(f"Error al enviar alerta por correo: {e}")

# Función para registrar datos (simplificada, `report_generator.py` se encargará de los finales)
def log_counting_data(move_in_data, in_time_data, move_out_data, out_time_data):
    """
    Registra datos de conteo en un archivo CSV.
    Esta función podría ser invocada por report_generator.py al final.
    """
    if not config.get("Log", False):
        return

    try:
        data = [move_in_data, in_time_data, move_out_data, out_time_data]
        export_data = zip_longest(*data, fillvalue='')

        # Usar 'a' para append si quieres registrar cada evento, 'w' para sobrescribir
        # Si quieres un log constante de los totales, esto debería ser más complejo.
        # Por ahora, mantendremos la lógica original de sobrescribir en people_counter.py
        # Pero considera usar un enfoque de append para mantener un historial.
        with open('utils/data/logs/counting_data.csv', 'w', newline='') as myfile:
            wr = csv.writer(myfile, quoting=csv.QUOTE_ALL)
            # Solo escribe el encabezado si el archivo está vacío
            if myfile.tell() == 0:
                wr.writerow(("Entradas", "Hora Entrada", "Salidas", "Hora Salida"))
            wr.writerows(export_data)
        logger.debug("Datos de conteo registrados en CSV.")
    except Exception as e:
        logger.error(f"Error al registrar datos de conteo: {e}")


# --- Clase principal de People Counter como un Servicio ---
class PeopleCounterService:
    def __init__(self, camera_url: str, update_callback, stop_event: threading.Event, current_config: dict):
        """
        Inicializa el servicio de conteo de personas.
        Args:
            camera_url (str): La URL del stream de video (ej. DroidCam).
            update_callback (callable): Una función de callback para actualizar los contadores en el hilo principal.
            stop_event (threading.Event): Un evento para señalizar al hilo de conteo que debe detenerse.
            current_config (dict): La configuración actual cargada de config.json.
        """
        self.camera_url = camera_url
        self.update_callback = update_callback
        self.stop_event = stop_event
        self.config = current_config # La configuración actual cargada de main.py

        # Cargar el modelo (rutas relativas a la ejecución de main.py)
        # Asegúrate de que estos archivos estén accesibles
        prototxt_path = "detector/MobileNetSSD_deploy.prototxt"
        model_path = "detector/MobileNetSSD_deploy.caffemodel"

        if not os.path.exists(prototxt_path):
            logger.error(f"Error: Prototxt no encontrado en {prototxt_path}")
            raise FileNotFoundError(f"Prototxt no encontrado: {prototxt_path}")
        if not os.path.exists(model_path):
            logger.error(f"Error: Modelo no encontrado en {model_path}")
            raise FileNotFoundError(f"Modelo no encontrado: {model_path}")

        self.net = cv2.dnn.readNetFromCaffe(prototxt_path, model_path)
        logger.info("Modelo de detección de objetos cargado.")

        self.CLASSES = ["fondo", "aeroplane", "bicycle", "bird", "boat",
                        "bottle", "bus", "car", "cat", "chair", "cow", "diningtable",
                        "dog", "horse", "motorbike", "person", "pottedplant", "sheep",
                        "sofa", "train", "tvmonitor"]

        self.ct = CentroidTracker(maxDisappeared=40, maxDistance=50)
        self.trackers = []
        self.trackableObjects = {}

        self.totalFrames = 0
        self.totalDown = 0  # Entradas
        self.totalUp = 0    # Salidas
        self.move_out_timestamps = []
        self.move_in_timestamps = []

        self.W = None
        self.H = None

        logger.info(f"Servicio de conteo inicializado con URL: {self.camera_url}")

    def run(self):
        """
        Bucle principal para la lectura de frames y el procesamiento.
        """
        logger.info("Iniciando la transmisión de video...")
        try:
            if self.config.get("Thread", False):
                # Usar tu ThreadingClass para la lectura de frames
                vs = thread.ThreadingClass(self.camera_url)
                logger.info("Usando ThreadingClass para la captura de video.")
            else:
                vs = cv2.VideoCapture(self.camera_url)
                logger.info("Usando cv2.VideoCapture estándar para la captura de video.")

            # Esperar un momento para que la cámara se inicialice
            time.sleep(2.0)

            if not vs.isOpened():
                logger.error(f"No se pudo abrir la cámara en {self.camera_url}. Verifique la URL y la conexión.")
                self.stop_event.set() # Señalar un error para detener
                return

        except Exception as e:
            logger.error(f"Error al inicializar la captura de video: {e}")
            self.stop_event.set()
            return

        fps = FPS().start() # Iniciar el contador de FPS

        while not self.stop_event.is_set():
            frame = vs.read()
            # Si usas ThreadingClass, frame es directamente la imagen
            # Si usas cv2.VideoCapture, frame = frame[1] si el primer elemento es el ret, y el segundo el frame
            # En la forma actual, vs.read() para VideoCapture devuelve (ret, frame)
            # Y para ThreadingClass.read() devuelve solo el frame
            # Necesitamos unificar esto.

            # Si es cv2.VideoCapture, necesitamos extraer el frame y verificar 'ret'
            if isinstance(vs, cv2.VideoCapture):
                ret, frame = frame
                if not ret or frame is None:
                    logger.warning("No se pudo capturar el frame de la cámara. Reintentando...")
                    time.sleep(0.5) # Esperar un poco antes de reintentar
                    continue
            elif frame is None: # Para ThreadingClass si devuelve None
                logger.warning("No se recibió frame de ThreadingClass. Reintentando...")
                time.sleep(0.5)
                continue


            frame = imutils.resize(frame, width=500)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if self.W is None or self.H is None:
                (self.H, self.W) = frame.shape[:2]

            status = "Esperando"
            rects = []

            if self.totalFrames % self.config.get("skip_frames", 30) == 0:
                status = "Detectando"
                self.trackers = []

                blob = cv2.dnn.blobFromImage(frame, 0.007843, (self.W, self.H), 127.5)
                self.net.setInput(blob)
                detections = self.net.forward()

                for i in np.arange(0, detections.shape[2]):
                    confidence = detections[0, 0, i, 2]
                    if confidence > self.config.get("confidence", 0.4):
                        idx = int(detections[0, 0, i, 1])
                        if self.CLASSES[idx] != "person":
                            continue

                        box = detections[0, 0, i, 3:7] * np.array([self.W, self.H, self.W, self.H])
                        (startX, startY, endX, endY) = box.astype("int")

                        tracker = dlib.correlation_tracker()
                        rect = dlib.rectangle(startX, startY, endX, endY)
                        tracker.start_track(rgb, rect)
                        self.trackers.append(tracker)
            else:
                status = "Rastreando"
                for tracker in self.trackers:
                    tracker.update(rgb)
                    pos = tracker.get_position()

                    startX = int(pos.left())
                    startY = int(pos.top())
                    endX = int(pos.right())
                    endY = int(pos.bottom())
                    rects.append((startX, startY, endX, endY))

            objects = self.ct.update(rects)

            for (objectID, centroid) in objects.items():
                to = self.trackableObjects.get(objectID, None)

                if to is None:
                    to = TrackableObject(objectID, centroid)
                else:
                    y = [c[1] for c in to.centroids]
                    direction = centroid[1] - np.mean(y)
                    to.centroids.append(centroid)

                    if not to.counted:
                        # Contar 'Salidas' (totalUp)
                        if direction < 0 and centroid[1] < self.H // 2:
                            self.totalUp += 1
                            date_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                            self.move_out_timestamps.append(date_time)
                            to.counted = True
                            logger.info(f"Persona saliendo: {self.totalUp} salidas")

                        # Contar 'Entradas' (totalDown)
                        elif direction > 0 and centroid[1] > self.H // 2:
                            self.totalDown += 1
                            date_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                            self.move_in_timestamps.append(date_time)
                            to.counted = True
                            logger.info(f"Persona entrando: {self.totalDown} entradas")

                            # Alerta por umbral
                            total_inside = self.totalDown - self.totalUp
                            if total_inside >= self.config.get("Threshold", 10) and self.config.get("ALERT", False):
                                logger.info("¡ALERTA: Límite de personas superado!")
                                # Lanza un hilo separado para enviar el correo para no bloquear el procesamiento
                                threading.Thread(target=send_mail_alert,
                                                 args=(self.config.get("Email_Receive"), self.config.get("Threshold"))).start()


                self.trackableObjects[objectID] = to

            # Calcular total dentro
            total_inside = self.totalDown - self.totalUp

            # Actualizar los contadores en el hilo principal de FastAPI de forma segura
            self.update_callback(self.totalUp, self.totalDown, total_inside, status)

            # --- Eliminado: cv2.imshow(), cv2.waitKey() ---
            # La visualización ahora será responsabilidad de Flutter

            # Actualizar el log de datos (esto podría ser más eficiente o manejado por report_generator)
            if self.config.get("Log", False):
                log_counting_data(
                    list(range(1, self.totalDown + 1)), # Simular lista para Entradas
                    self.move_in_timestamps,
                    list(range(1, self.totalUp + 1)),   # Simular lista para Salidas
                    self.move_out_timestamps
                )

            self.totalFrames += 1
            fps.update()

            # Lógica de "Timer" si está habilitada (similar a lo que estaba en people_counter.py)
            if self.config.get("Timer", False):
                # Esto es solo un ejemplo; necesitas definir 'start_time' si lo usas
                # El timer de 8 horas debería ser manejado por el backend principal o el scheduler.
                # Aquí, si se detiene, el hilo se detendrá.
                pass # Por ahora, omitimos la lógica de temporizador dentro del bucle de frames.
                     # Es mejor que el "scheduler" o el "main" de FastAPI gestionen cuándo se detiene.

        # Fuera del bucle while not self.stop_event.is_set():
        fps.stop()
        logger.info("Tiempo transcurrido: {:.2f}".format(fps.elapsed()))
        logger.info("FPS aproximado: {:.2f}".format(fps.fps()))

        if isinstance(vs, thread.ThreadingClass):
            vs.release()
        elif isinstance(vs, cv2.VideoCapture):
            vs.release()
        logger.info("Recursos de cámara liberados.")


# --- Función auxiliar para obtener la configuración (útil para el __main__ de FastAPI) ---
def get_current_config_from_file():
    try:
        with open(CONFIG_FILE_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error al cargar la configuración inicial: {e}")
        return {}