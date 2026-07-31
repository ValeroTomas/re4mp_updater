import os
import sys
import runpy
import tkinter as tk
from tkinter import messagebox

import requests

WORKER_BASE_URL = "https://re4mp-worker.insanyteam-devs-8a9.workers.dev"

try:
    from _config import CLIENT_API_KEY
except ImportError:
    CLIENT_API_KEY = os.environ.get("CLIENT_API_KEY", "")

APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "RE4MPUpdater")
APP_PY_PATH = os.path.join(APP_DIR, "updater_app.py")

# Ruta del propio launcher: compilado, es el .exe; en desarrollo, este mismo
# archivo. La app (updater_app.py) la necesita para relanzarse tras un
# self-update, sin tener que reemplazar este .exe para nada.
LAUNCHER_PATH = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)


def ensure_app_downloaded():
    os.makedirs(APP_DIR, exist_ok=True)
    if os.path.exists(APP_PY_PATH):
        return
    headers = {"X-Api-Key": CLIENT_API_KEY}
    response = requests.get(f"{WORKER_BASE_URL}/updater/app/download", headers=headers, timeout=20)
    response.raise_for_status()
    with open(APP_PY_PATH, "wb") as f:
        f.write(response.content)


def show_fatal_error(message):
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("RE4MP Updater", message)
    root.destroy()


def main():
    try:
        ensure_app_downloaded()
    except Exception as exc:
        show_fatal_error(
            "No se pudo descargar el updater. Revisá tu conexión a internet e intentá de nuevo.\n\n"
            f"Detalle: {exc}"
        )
        sys.exit(1)

    # Se ejecuta en el mismo proceso (no un subproceso de Python aparte):
    # runpy corre el archivo como si fuera el script principal, inyectándole
    # estos nombres ya resueltos en su namespace global.
    runpy.run_path(
        APP_PY_PATH,
        init_globals={
            "CLIENT_API_KEY": CLIENT_API_KEY,
            "WORKER_BASE_URL": WORKER_BASE_URL,
            "APP_DIR": APP_DIR,
            "APP_PY_PATH": APP_PY_PATH,
            "LAUNCHER_PATH": LAUNCHER_PATH,
        },
        run_name="__main__",
    )


if __name__ == "__main__":
    main()
