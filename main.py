import subprocess
import threading
import datetime
import json
import os

CONFIG_PATH = "utils/schedule_config.json"

def esta_dentro_del_horario():
    if not os.path.exists(CONFIG_PATH):
        return False
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
    ahora = datetime.datetime.now()
    dia_actual = ahora.strftime("%A")
    hora_actual = ahora.strftime("%H:%M")

    if dia_actual not in config.get("active_days", []):
        return False
    for rango in config.get("time_ranges", []):
        if rango["start"] <= hora_actual <= rango["end"]:
            return True
    return False

def ejecutar_config_gui():
    subprocess.Popen(["python3", "config_gui.py"])

def ejecutar_scheduler():
    subprocess.Popen(["python3", "scheduler_main.py"])

def monitorear_estado():
    proceso = None
    dentro = esta_dentro_del_horario()
    if dentro:
        proceso = subprocess.Popen(["python3", "scheduler_main.py"])

    while True:
        nueva_eval = esta_dentro_del_horario()
        if nueva_eval and not dentro:
            proceso = subprocess.Popen(["python3", "scheduler_main.py"])
            dentro = True
        elif not nueva_eval and dentro:
            os.system("pkill -f scheduler_main.py")
            dentro = False
        time.sleep(60)

if __name__ == "__main__":
    import time
    t1 = threading.Thread(target=monitorear_estado)
    t1.daemon = True
    t1.start()

    ejecutar_config_gui()