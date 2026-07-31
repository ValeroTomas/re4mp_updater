import tkinter as tk
from tkinter import ttk
import requests
import re
import os
import sys
import subprocess
import threading
import hashlib
from datetime import datetime, timezone

# ==========================================
# CONFIGURACIÓN
# ==========================================
# La URL del Worker no es secreta (ya es pública, la usa el webhook de
# GitLab), así que puede vivir acá tranquilamente.
WORKER_BASE_URL = "https://re4mp-worker.insanyteam-devs-8a9.workers.dev"

# CLIENT_API_KEY y UPDATER_VERSION NO viven en este archivo ni en el repo.
# Los genera el pipeline de CI (_config.py con la key desde un secret de
# GitHub, _version.py con el commit corto) justo antes de compilar con
# PyInstaller, y quedan embebidos en el .exe. En desarrollo local, si no
# existen esos archivos, cae a variables de entorno / valores de placeholder
# para poder correr el script sin compilar.
try:
    from _config import CLIENT_API_KEY
except ImportError:
    CLIENT_API_KEY = os.environ.get("CLIENT_API_KEY", "")

try:
    from _version import UPDATER_VERSION
except ImportError:
    UPDATER_VERSION = "dev"

HEADERS = {"X-Api-Key": CLIENT_API_KEY}
POLLING_INTERVAL_MS = 60000
GAME_EXE_NAME = "bio4.exe"
DLL_NAME = "dinput8.dll"

# Paleta simple, oscura, consistente en toda la UI
COLOR_BG = "#1E1E1E"
COLOR_BG_PANEL = "#2A2A2A"
COLOR_TEXT = "#E8E8E8"
COLOR_MUTED = "#9A9A9A"
COLOR_ACCENT = "#4CAF50"
COLOR_ERROR = "#E05555"
COLOR_WARN = "#E0A030"


def app_dir() -> str:
    """Carpeta donde vive el .exe compilado (o el script, en desarrollo)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\-]", "-", text).lower()


def file_hash(filepath: str):
    if not os.path.exists(filepath):
        return None
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def format_date(iso_date: str) -> str:
    if not iso_date:
        return "--"
    try:
        dt = datetime.strptime(iso_date[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return iso_date


class RE4ModUpdater:
    def __init__(self, root):
        self.root = root
        self.root.title("RE4MP - Mod Updater")
        self.root.geometry("380x420")
        self.root.resizable(False, False)
        self.root.configure(bg=COLOR_BG)

        self.branches_data = {}
        self.branches_raw_dates = {}
        self.new_updater_path = None

        self._build_style()

        # Si no está en la carpeta correcta, mostramos solo el error y no
        # armamos el resto de la interfaz — no tiene sentido ofrecer
        # funciones que van a fallar igual.
        if not self._validate_game_folder():
            self._build_folder_error_ui()
            return

        self._build_header()
        self._build_updater_section()
        self._build_separator()
        self._build_branches_section()

        threading.Thread(target=self.fetch_branches, daemon=True).start()
        threading.Thread(target=self.check_updater_version, daemon=True).start()

    # ---------------------------------------------------------
    # Setup / validaciones
    # ---------------------------------------------------------
    def _build_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox", fieldbackground=COLOR_BG_PANEL, background=COLOR_BG_PANEL)
        style.configure("Green.Horizontal.TProgressbar", troughcolor=COLOR_BG_PANEL, background=COLOR_ACCENT)

    def _validate_game_folder(self) -> bool:
        return os.path.exists(os.path.join(app_dir(), GAME_EXE_NAME))

    def _build_folder_error_ui(self):
        frame = tk.Frame(self.root, bg=COLOR_BG)
        frame.pack(expand=True, fill="both", padx=20, pady=20)
        tk.Label(
            frame,
            text="⚠",
            font=("Arial", 32),
            fg=COLOR_ERROR,
            bg=COLOR_BG,
        ).pack(pady=(10, 5))
        tk.Label(
            frame,
            text=f"No se encontró {GAME_EXE_NAME} en esta carpeta.",
            font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT,
            bg=COLOR_BG,
            wraplength=320,
            justify="center",
        ).pack(pady=(0, 8))
        tk.Label(
            frame,
            text=(
                "Movés este .exe a la carpeta donde está instalado "
                "Resident Evil 4 (2005) UHD, junto al ejecutable del juego, "
                "y lo volvés a abrir desde ahí."
            ),
            font=("Segoe UI", 9),
            fg=COLOR_MUTED,
            bg=COLOR_BG,
            wraplength=320,
            justify="center",
        ).pack()

    # ---------------------------------------------------------
    # UI
    # ---------------------------------------------------------
    def _build_header(self):
        header = tk.Frame(self.root, bg=COLOR_BG)
        header.pack(fill="x", padx=20, pady=(18, 10))
        tk.Label(
            header, text="RE4MP", font=("Segoe UI", 16, "bold"), fg=COLOR_TEXT, bg=COLOR_BG
        ).pack(anchor="w")
        tk.Label(
            header, text="Mod Updater", font=("Segoe UI", 9), fg=COLOR_MUTED, bg=COLOR_BG
        ).pack(anchor="w")

    def _build_updater_section(self):
        panel = tk.Frame(self.root, bg=COLOR_BG_PANEL)
        panel.pack(fill="x", padx=20, pady=(0, 10))

        row = tk.Frame(panel, bg=COLOR_BG_PANEL)
        row.pack(fill="x", padx=12, pady=10)

        left = tk.Frame(row, bg=COLOR_BG_PANEL)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(
            left, text=f"Versión del updater: {UPDATER_VERSION}",
            font=("Segoe UI", 9), fg=COLOR_MUTED, bg=COLOR_BG_PANEL,
        ).pack(anchor="w")
        self.lbl_updater_status = tk.Label(
            left, text="", font=("Segoe UI", 9, "bold"), fg=COLOR_MUTED, bg=COLOR_BG_PANEL,
            wraplength=220, justify="left",
        )
        self.lbl_updater_status.pack(anchor="w", pady=(3, 0))

        self.btn_check_updater = tk.Button(
            row, text="Buscar\nactualización", command=self.start_updater_check_thread,
            bg="#3A3A3A", fg=COLOR_TEXT, activebackground="#4A4A4A", activeforeground=COLOR_TEXT,
            relief="flat", font=("Segoe UI", 8), width=12,
        )
        self.btn_check_updater.pack(side="right")

    def _build_separator(self):
        tk.Frame(self.root, bg="#3A3A3A", height=1).pack(fill="x", padx=20, pady=6)

    def _build_branches_section(self):
        panel = tk.Frame(self.root, bg=COLOR_BG)
        panel.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        header_row = tk.Frame(panel, bg=COLOR_BG)
        header_row.pack(fill="x")
        tk.Label(
            header_row, text="Rama del mod", font=("Segoe UI", 10, "bold"),
            fg=COLOR_TEXT, bg=COLOR_BG,
        ).pack(side="left")
        tk.Button(
            header_row, text="↻ Actualizar", command=self.start_refresh_branches_thread,
            bg="#3A3A3A", fg=COLOR_TEXT, activebackground="#4A4A4A", activeforeground=COLOR_TEXT,
            relief="flat", font=("Segoe UI", 8),
        ).pack(side="right")

        self.combo_var = tk.StringVar(value="Cargando ramas...")
        self.combo = ttk.Combobox(panel, textvariable=self.combo_var, state="disabled", width=38)
        self.combo.pack(pady=(8, 5), fill="x")
        self.combo.bind("<<ComboboxSelected>>", self.on_branch_select)

        self.progress = ttk.Progressbar(
            panel, mode="indeterminate", length=200, style="Green.Horizontal.TProgressbar"
        )
        self.progress.pack(pady=5, fill="x")
        self.progress.start(15)

        self.lbl_date = tk.Label(panel, text="Última actualización: --", fg=COLOR_MUTED, bg=COLOR_BG, font=("Segoe UI", 9))
        self.lbl_date.pack(pady=(5, 10), anchor="w")

        self.btn_download = tk.Button(
            panel, text="Descargar e instalar", command=self.start_download_thread,
            state=tk.DISABLED, bg=COLOR_ACCENT, fg="white", activebackground="#3d8b40",
            activeforeground="white", relief="flat", font=("Segoe UI", 10, "bold"), pady=6,
        )
        self.btn_download.pack(fill="x", pady=(0, 8))

        self.lbl_status = tk.Label(
            panel, text="", font=("Segoe UI", 9, "bold"), bg=COLOR_BG,
            wraplength=330, justify="center",
        )
        self.lbl_status.pack(pady=5)

    # ---------------------------------------------------------
    # Helpers de estado
    # ---------------------------------------------------------
    def set_status(self, message, is_error=False, is_warning=False):
        color = COLOR_ERROR if is_error else COLOR_WARN if is_warning else COLOR_ACCENT
        self.lbl_status.config(text=message, fg=color)

    # ---------------------------------------------------------
    # Ramas del mod (habla con el Worker, no con GitLab directo)
    # ---------------------------------------------------------
    def start_refresh_branches_thread(self):
        threading.Thread(target=self.fetch_branches, daemon=True).start()

    def fetch_branches(self):
        try:
            response = requests.get(f"{WORKER_BASE_URL}/builds", headers=HEADERS, timeout=10)
            if response.status_code == 200:
                data = response.json().get("builds", [])
                self.branches_data = {}
                self.branches_raw_dates = {}
                for build in data:
                    label = build.get("branch") or build["slug"]
                    self.branches_data[label] = {
                        "slug": build["slug"],
                        "date": format_date(build.get("committedDate")),
                    }
                self.root.after(0, self._update_branches_ui_success)
            else:
                self.root.after(0, self._update_branches_ui_error, f"Error al cargar (código {response.status_code}).")
        except Exception:
            self.root.after(0, self._update_branches_ui_error, "Error de conexión al cargar ramas.")

    def _update_branches_ui_success(self):
        self.progress.stop()
        self.progress.pack_forget()
        self.combo.config(state="readonly")
        self.combo["values"] = list(self.branches_data.keys())
        if self.combo["values"]:
            self.combo.current(0)
            self.on_branch_select()
        else:
            self.combo_var.set("No hay builds publicados")

    def _update_branches_ui_error(self, message):
        self.progress.stop()
        self.progress.pack_forget()
        self.combo_var.set("Error de conexión")
        self.set_status(message, is_error=True)

    def on_branch_select(self, event=None):
        selected = self.combo_var.get()
        if selected in self.branches_data:
            self.lbl_date.config(text=f"Última actualización: {self.branches_data[selected]['date']}")
            self.btn_download.config(state=tk.NORMAL)
            self.lbl_status.config(text="")

    def start_download_thread(self):
        selected = self.combo_var.get()
        if selected not in self.branches_data:
            return
        self.btn_download.config(text="Descargando...", state=tk.DISABLED)
        self.set_status("Descargando desde el servidor...", is_error=False)
        threading.Thread(target=self._process_download, args=(self.branches_data[selected]["slug"],), daemon=True).start()

    def _process_download(self, slug):
        target_path = os.path.join(app_dir(), DLL_NAME)
        temp_path = os.path.join(app_dir(), f"{DLL_NAME}.tmp")

        try:
            response = requests.get(f"{WORKER_BASE_URL}/download/{slug}", headers=HEADERS, stream=True, timeout=15)
            if response.status_code == 200:
                with open(temp_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1048576):
                        f.write(chunk)

                if file_hash(target_path) == file_hash(temp_path):
                    os.remove(temp_path)
                    self.root.after(0, self.set_status, "Ya tenés instalada esta versión.", False, True)
                else:
                    os.replace(temp_path, target_path)
                    self.root.after(0, self.set_status, f"¡Listo! {DLL_NAME} fue actualizado.", False, False)
            else:
                self.root.after(0, self.set_status, f"El archivo no existe (código {response.status_code}).", True)
        except PermissionError:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            self.root.after(0, self.set_status, "Permiso denegado. Cerrá el juego e intentá de nuevo.", True)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            self.root.after(0, self.set_status, "Ocurrió un error inesperado al descargar.", True)
        finally:
            self.root.after(0, lambda: self.btn_download.config(text="Descargar e instalar", state=tk.NORMAL))

    # ---------------------------------------------------------
    # Self-update del propio updater
    # ---------------------------------------------------------
    def start_updater_check_thread(self):
        threading.Thread(target=self.check_updater_version, daemon=True).start()

    def check_updater_version(self):
        try:
            response = requests.get(f"{WORKER_BASE_URL}/updater/latest", headers=HEADERS, timeout=10)
            if response.status_code != 200:
                return
            remote_commit = response.json().get("commit")
            if remote_commit and remote_commit != UPDATER_VERSION:
                self.root.after(0, self._show_updater_available, remote_commit)
        except Exception:
            pass  # el chequeo de self-update es best-effort, no bloquea el resto de la app

    def _show_updater_available(self, remote_commit):
        self.lbl_updater_status.config(
            text=f"Hay una versión nueva disponible ({remote_commit})", fg=COLOR_WARN
        )
        self.btn_check_updater.config(text="Descargar\nactualización", command=self.start_updater_download_thread)

    def start_updater_download_thread(self):
        self.btn_check_updater.config(state=tk.DISABLED)
        threading.Thread(target=self._download_new_updater, daemon=True).start()

    def _download_new_updater(self):
        new_path = os.path.join(app_dir(), "re4mp_updater_new.exe")
        try:
            response = requests.get(f"{WORKER_BASE_URL}/updater/download", headers=HEADERS, stream=True, timeout=20)
            if response.status_code == 200:
                with open(new_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1048576):
                        f.write(chunk)
                self.new_updater_path = new_path
                self.root.after(0, self._show_restart_button)
            else:
                self.root.after(0, self.lbl_updater_status.config, {"text": "No se pudo descargar la actualización.", "fg": COLOR_ERROR})
        except Exception:
            self.root.after(0, self.lbl_updater_status.config, {"text": "Error al descargar la actualización.", "fg": COLOR_ERROR})

    def _show_restart_button(self):
        self.lbl_updater_status.config(text="Actualización descargada.", fg=COLOR_ACCENT)
        self.btn_check_updater.config(text="Reiniciar\nahora", state=tk.NORMAL, command=self.apply_updater_update)

    def apply_updater_update(self):
        # No se reemplaza el .exe en uso solo: Windows no deja sobreescribir
        # un binario que está corriendo. Lanzamos el nuevo como proceso
        # aparte y cerramos este. El usuario decidió que esto sea explícito
        # (un click en "Reiniciar ahora"), no automático al detectar la
        # versión nueva.
        if not self.new_updater_path or not os.path.exists(self.new_updater_path):
            return
        try:
            subprocess.Popen([self.new_updater_path])
        except Exception:
            self.lbl_updater_status.config(text="No se pudo iniciar la nueva versión.", fg=COLOR_ERROR)
            return
        # El .exe viejo queda en la carpeta (no se autoborra): Windows no
        # permite borrar un binario mientras sigue en ejecución, y este
        # proceso todavía no terminó de cerrarse en este punto. Para
        # mantenerlo simple en esta primera versión, el usuario lo borra a
        # mano una vez confirma que el nuevo abre bien.
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = RE4ModUpdater(root)
    root.mainloop()
