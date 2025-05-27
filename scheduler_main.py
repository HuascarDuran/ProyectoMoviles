# scheduler_main.py
import json
import subprocess
import datetime
import time
import os

CONFIG_PATH = "utils/schedule_config.json"

def cargar_config():
    if not os.path.exists(CONFIG_PATH):
        return None
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def esta_dentro_del_horario(config):
    ahora = datetime.datetime.now()
    dia_actual = ahora.strftime("%A")  # Ej: Monday
    hora_actual = ahora.strftime("%H:%M").lstrip("0").rjust(5, "0")

    if dia_actual not in config["active_days"]:
        return False

    for rango in config["time_ranges"]:
        if rango["start"] <= hora_actual <= rango["end"]:
            return True
    return False

def iniciar_contador():
    print("[INFO] Activando el conteo de personas...")
    subprocess.call(["python3", "people_counter.py",
                     "-p", "detector/MobileNetSSD_deploy.prototxt",
                     "-m", "detector/MobileNetSSD_deploy.caffemodel"])

def jornada_finalizada(config):
    ahora = datetime.datetime.now().strftime("%H:%M")
    ult_hora = max(r["end"] for r in config["time_ranges"])
    return ahora > ult_hora

def main_loop():
    print("[INFO] Iniciando sistema de vigilancia por horario.")
    reporte_enviado = False
    fecha_actual = datetime.date.today()
    while True:
        config = cargar_config()
        if config and esta_dentro_del_horario(config):
            iniciar_contador()
            print("[INFO] Conteo activo. Esperando 1 minuto para la próxima verificación.")
            ahora = datetime.datetime.now()
            time.sleep(60 - ahora.second)
        else:
            print("[INFO] ⏳ Fuera del horario o día configurado.")
            ahora = datetime.datetime.now()
            print(f"[DEBUG] Ahora es {ahora.strftime('%A')} a las {ahora.strftime('%H:%M')}")
            time.sleep(60 - ahora.second)
        nueva_fecha = datetime.date.today()
        if config:
            hora_actual = datetime.datetime.now().strftime("%H:%M").lstrip("0").rjust(5, "0")
            for rango in config.get("time_ranges", []):
                rango_end = rango["end"].lstrip("0").rjust(5, "0")
                if hora_actual == rango_end and not reporte_enviado:
                    print("[INFO] Hora exacta de fin de jornada. Enviando reporte diario...")
                    subprocess.call(["python3", "report_generator.py"])
                    reporte_enviado = True

        # Reiniciar flag si cambia el día
        if nueva_fecha != fecha_actual:
            fecha_actual = nueva_fecha
            reporte_enviado = False

if __name__ == "__main__":
    main_loop()