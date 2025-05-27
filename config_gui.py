from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QLineEdit, QPushButton, QGridLayout, QMessageBox
)
from PyQt5.QtCore import Qt, QTime, QTimer
import sys, os, json, datetime, subprocess

CONFIG_PATH = "utils/schedule_config.json"
EMAIL_CONFIG_PATH = "utils/config.json"

DAYS = [
    ("Lunes", "Monday"), ("Martes", "Tuesday"), ("Miércoles", "Wednesday"),
    ("Jueves", "Thursday"), ("Viernes", "Friday"), ("Sábado", "Saturday"), ("Domingo", "Sunday")
]

class ConfigApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Configuración de Días y Horarios")
        self.setStyleSheet("""
    QWidget {
        background-color: #f0f4ff;
        font-family: 'Comic Sans MS';
        font-size: 13px;
    }
    QLabel#Header {
        font-size: 20px;
        font-weight: bold;
        color: #222;
        margin-bottom: 15px;
    }
    QPushButton {
        background-color: #9cc2ff;
        border: 2px solid #5d9bff;
        border-radius: 12px;
        padding: 6px 12px;
    }
    QPushButton:hover {
        background-color: #b3d4ff;
    }
    QCheckBox {
        background-color: #cbe2ff;
        border-radius: 10px;
        padding: 4px 8px;
        margin: 2px;
    }
    QLineEdit {
        border: 1px solid #aaa;
        border-radius: 6px;
        padding: 4px;
        background-color: #ffffff;
    }
""")
        self.resize(400, 500)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.day_checkboxes = {}
        self.time_ranges = []
        self.email_input = QLineEdit()

        self.build_day_section()
        self.build_time_section()
        self.build_email_section()
        self.build_buttons()
        self.load_existing_config()

    def build_day_section(self):
        # Encabezado atractivo tipo “Horario semanal”
        header = QLabel("Horario semanal")
        header.setObjectName("Header")
        self.layout.addWidget(header, alignment=Qt.AlignCenter)
        # Fila de checkboxes con estilo de pastilla
        row = QHBoxLayout()
        for day_esp, day_eng in DAYS:
            checkbox = QCheckBox(day_esp)
            self.day_checkboxes[day_eng] = checkbox
            row.addWidget(checkbox)
        self.layout.addLayout(row)

    def build_time_section(self):
        self.layout.addWidget(QLabel("Rangos horarios disponibles:"))
        self.time_layout = QGridLayout()
        self.layout.addLayout(self.time_layout)
        self.add_time_range()

        self.add_time_btn = QPushButton("Agregar otro rango")
        self.add_time_btn.clicked.connect(self.add_time_range)
        self.layout.addWidget(self.add_time_btn)

    def add_time_range(self):
        start_input = QLineEdit()
        start_input.setPlaceholderText("Inicio (HH:MM)")
        end_input = QLineEdit()
        end_input.setPlaceholderText("Fin (HH:MM)")
        row = len(self.time_ranges)
        self.time_layout.addWidget(start_input, row, 0)
        self.time_layout.addWidget(QLabel(" a "), row, 1)
        self.time_layout.addWidget(end_input, row, 2)
        self.time_ranges.append((start_input, end_input))

    def build_email_section(self):
        self.layout.addWidget(QLabel("Correo para recibir el reporte diario:"))
        self.layout.addWidget(self.email_input)

    def build_buttons(self):
        self.save_btn = QPushButton("Guardar configuración")
        self.save_btn.clicked.connect(self.save_config)
        self.layout.addWidget(self.save_btn)

        # Verificar si la cámara debería estar activa
        if self.esta_dentro_de_horario():
            self.reporte_btn = QPushButton("Enviar reporte ahora")
            self.reporte_btn.clicked.connect(lambda: subprocess.call(["python3", "report_generator.py"]))
            self.layout.addWidget(self.reporte_btn)
            self.layout.addWidget(QLabel("📷 Cámara activa", self))
        else:
            self.layout.addWidget(QLabel("⏳ Fuera de horario de grabación", self))

    def save_config(self):
        active_days = [day for day, cb in self.day_checkboxes.items() if cb.isChecked()]
        ranges = []
        for start, end in self.time_ranges:
            if start.text() and end.text():
                ranges.append({"start": start.text(), "end": end.text()})

        config = {
            "active_days": active_days,
            "time_ranges": ranges,
            "email_report_receiver": self.email_input.text()
        }

        os.makedirs("utils", exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)

        if os.path.exists(EMAIL_CONFIG_PATH):
            with open(EMAIL_CONFIG_PATH, "r") as f:
                email_config = json.load(f)
        else:
            email_config = {}

        email_config["Email_Receive"] = self.email_input.text()
        with open(EMAIL_CONFIG_PATH, "w") as f:
            json.dump(email_config, f, indent=2)

        QMessageBox.information(self, "Guardado", "La configuración se guardó correctamente.")

        if self.esta_dentro_de_horario():
            subprocess.Popen(["python3", "scheduler_main.py"])
        else:
            # Intentar cerrar procesos previos (opcional y simple)
            try:
                os.system("pkill -f scheduler_main.py")
            except Exception as e:
                print(f"[WARN] No se pudo cerrar scheduler_main.py: {e}")

        self.actualizar_estado_camara()

    def load_existing_config(self):
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                saved = json.load(f)
                for day in saved.get("active_days", []):
                    if day in self.day_checkboxes:
                        self.day_checkboxes[day].setChecked(True)
                for idx, rango in enumerate(saved.get("time_ranges", [])):
                    if idx < len(self.time_ranges):
                        self.time_ranges[idx][0].setText(rango["start"])
                        self.time_ranges[idx][1].setText(rango["end"])
                    else:
                        self.add_time_range()
                        self.time_ranges[idx][0].setText(rango["start"])
                        self.time_ranges[idx][1].setText(rango["end"])
                self.email_input.setText(saved.get("email_report_receiver", ""))

    def esta_dentro_de_horario(self):
        if not os.path.exists(CONFIG_PATH):
            return False
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
        ahora = datetime.datetime.now()
        dia = ahora.strftime("%A")
        hora = ahora.strftime("%H:%M").lstrip("0").rjust(5, "0")
        if dia not in config.get("active_days", []):
            return False
        for rango in config.get("time_ranges", []):
            start = rango["start"].lstrip("0").rjust(5, "0")
            end = rango["end"].lstrip("0").rjust(5, "0")
            if start <= hora <= end:
                return True
        return False

    def actualizar_estado_camara(self):
        # Elimina antiguos botones y etiquetas de estado
        for i in reversed(range(self.layout.count())):
            widget = self.layout.itemAt(i).widget()
            if isinstance(widget, QLabel) and ("Cámara activa" in widget.text() or "Fuera de horario" in widget.text()):
                self.layout.removeWidget(widget)
                widget.deleteLater()
            elif isinstance(widget, QPushButton) and widget.text() == "Enviar reporte ahora":
                self.layout.removeWidget(widget)
                widget.deleteLater()

        # Añade nuevos controles según el estado actual
        if self.esta_dentro_de_horario():
            self.reporte_btn = QPushButton("Enviar reporte ahora")
            self.reporte_btn.clicked.connect(lambda: subprocess.call(["python3", "report_generator.py"]))
            self.layout.addWidget(self.reporte_btn)
            self.layout.addWidget(QLabel("📷 Cámara activa", self))
        else:
            self.layout.addWidget(QLabel("⏳ Fuera de horario de grabación", self))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ConfigApp()
    window.show()
    sys.exit(app.exec_())