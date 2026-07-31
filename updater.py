import customtkinter as ctk
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
WORKER_BASE_URL = "https://re4mp-worker.insanyteam-devs-8a9.workers.dev"

try:
    from _config import CLIENT_API_KEY
except ImportError:
    CLIENT_API_KEY = os.environ.get("CLIENT_API_KEY", "")

try:
    from _version import UPDATER_VERSION
except ImportError:
    UPDATER_VERSION = "dev"

HEADERS = {"X-Api-Key": CLIENT_API_KEY}
GAME_EXE_NAME = "bio4.exe"
DLL_NAME = "dinput8.dll"

# Colores como tupla (claro, oscuro): customtkinter elige el que corresponde
# solo al cambiar el modo de apariencia, no hace falta repintar nada a mano.
COLOR_ACCENT = ("#3d9142", "#4CAF50")
COLOR_ACCENT_HOVER = ("#357a39", "#3d8b40")
COLOR_ERROR = ("#c0392b", "#E05555")
COLOR_WARN = ("#b3720a", "#E0A030")
COLOR_MUTED = ("#666666", "#9A9A9A")
COLOR_PANEL = ("#EAEAEA", "#242424")
COLOR_PANEL_BTN = ("#DADADA", "#3A3A3A")
COLOR_PANEL_BTN_HOVER = ("#C8C8C8", "#4A4A4A")

ctk.set_default_color_theme("green")


def app_dir() -> str:
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


class RE4ModUpdater(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("Dark")

        self.title("RE4MP - Mod Updater")
        self.geometry("380x460")
        self.resizable(False, False)

        self.branches_data = {}
        self.new_updater_path = None

        if not self._validate_game_folder():
            self._build_folder_error_ui()
            return

        self._build_header()
        self._build_updater_section()
        self._build_branches_section()

        threading.Thread(target=self.fetch_branches, daemon=True).start()
        threading.Thread(target=self.check_updater_version, daemon=True).start()

    # ---------------------------------------------------------
    # Setup / validaciones
    # ---------------------------------------------------------
    def _validate_game_folder(self) -> bool:
        return os.path.exists(os.path.join(app_dir(), GAME_EXE_NAME))

    def _build_folder_error_ui(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(expand=True, fill="both", padx=24, pady=24)
        ctk.CTkLabel(frame, text="⚠", font=ctk.CTkFont(size=36), text_color=COLOR_ERROR).pack(pady=(10, 5))
        ctk.CTkLabel(
            frame,
            text=f"No se encontró {GAME_EXE_NAME} en esta carpeta.",
            font=ctk.CTkFont(size=14, weight="bold"),
            wraplength=320,
            justify="center",
        ).pack(pady=(0, 8))
        ctk.CTkLabel(
            frame,
            text=(
                "Movés este .exe a la carpeta donde está instalado "
                "Resident Evil 4 (2005) UHD, junto al ejecutable del "
                "juego, y lo volvés a abrir desde ahí."
            ),
            font=ctk.CTkFont(size=12),
            text_color=COLOR_MUTED,
            wraplength=320,
            justify="center",
        ).pack()

    # ---------------------------------------------------------
    # UI
    # ---------------------------------------------------------
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(18, 10))

        title_col = ctk.CTkFrame(header, fg_color="transparent")
        title_col.pack(side="left")
        ctk.CTkLabel(title_col, text="RE4MP", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(title_col, text="Mod Updater", font=ctk.CTkFont(size=11), text_color=COLOR_MUTED).pack(anchor="w")

        self.theme_btn = ctk.CTkButton(
            header, text="☀", width=36, height=36, corner_radius=18,
            fg_color=COLOR_PANEL_BTN, hover_color=COLOR_PANEL_BTN_HOVER,
            text_color=("#333333", "#EEEEEE"), command=self.toggle_theme,
        )
        self.theme_btn.pack(side="right")

    def toggle_theme(self):
        current = ctk.get_appearance_mode()  # "Light" o "Dark"
        if current == "Dark":
            ctk.set_appearance_mode("Light")
            self.theme_btn.configure(text="🌙")
        else:
            ctk.set_appearance_mode("Dark")
            self.theme_btn.configure(text="☀")

    def _build_updater_section(self):
        panel = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=14)
        panel.pack(fill="x", padx=20, pady=(0, 14))

        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=12)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            left, text=f"Versión del updater: {UPDATER_VERSION}",
            font=ctk.CTkFont(size=11), text_color=COLOR_MUTED,
        ).pack(anchor="w")
        self.lbl_updater_status = ctk.CTkLabel(
            left, text="", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLOR_MUTED, wraplength=210, justify="left",
        )
        self.lbl_updater_status.pack(anchor="w", pady=(3, 0))

        self.btn_check_updater = ctk.CTkButton(
            row, text="Buscar\nactualización", width=110, height=44, corner_radius=10,
            fg_color=COLOR_PANEL_BTN, hover_color=COLOR_PANEL_BTN_HOVER,
            text_color=("#333333", "#EEEEEE"), font=ctk.CTkFont(size=11),
            command=self.start_updater_check_thread,
        )
        self.btn_check_updater.pack(side="right")

    def _build_branches_section(self):
        panel = ctk.CTkFrame(self, fg_color="transparent")
        panel.pack(fill="both", expand=True, padx=20, pady=(0, 18))

        header_row = ctk.CTkFrame(panel, fg_color="transparent")
        header_row.pack(fill="x")
        ctk.CTkLabel(header_row, text="Rama del mod", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkButton(
            header_row, text="↻ Actualizar", width=100, height=28, corner_radius=8,
            fg_color=COLOR_PANEL_BTN, hover_color=COLOR_PANEL_BTN_HOVER,
            text_color=("#333333", "#EEEEEE"), font=ctk.CTkFont(size=11),
            command=self.start_refresh_branches_thread,
        ).pack(side="right")

        self.combo_var = ctk.StringVar(value="Cargando ramas...")
        self.combo = ctk.CTkComboBox(
            panel, variable=self.combo_var, state="disabled", width=340, corner_radius=10,
            command=self.on_branch_select,
        )
        self.combo.pack(pady=(10, 8), fill="x")

        self.progress = ctk.CTkProgressBar(panel, mode="indeterminate", corner_radius=6)
        self.progress.pack(pady=5, fill="x")
        self.progress.start()

        self.lbl_date = ctk.CTkLabel(
            panel, text="Última actualización: --", font=ctk.CTkFont(size=11), text_color=COLOR_MUTED,
        )
        self.lbl_date.pack(pady=(5, 12), anchor="w")

        self.btn_download = ctk.CTkButton(
            panel, text="Descargar e instalar", height=42, corner_radius=10,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"), state="disabled",
            command=self.start_download_thread,
        )
        self.btn_download.pack(fill="x", pady=(0, 10))

        self.lbl_status = ctk.CTkLabel(panel, text="", font=ctk.CTkFont(size=11, weight="bold"), wraplength=330, justify="center")
        self.lbl_status.pack(pady=5)

    # ---------------------------------------------------------
    # Helpers de estado
    # ---------------------------------------------------------
    def set_status(self, message, is_error=False, is_warning=False):
        color = COLOR_ERROR if is_error else COLOR_WARN if is_warning else COLOR_ACCENT
        self.lbl_status.configure(text=message, text_color=color)

    # ---------------------------------------------------------
    # Ramas del mod
    # ---------------------------------------------------------
    def start_refresh_branches_thread(self):
        threading.Thread(target=self.fetch_branches, daemon=True).start()

    def fetch_branches(self):
        try:
            response = requests.get(f"{WORKER_BASE_URL}/builds", headers=HEADERS, timeout=10)
            if response.status_code == 200:
                data = response.json().get("builds", [])
                self.branches_data = {}
                for build in data:
                    label = build.get("branch") or build["slug"]
                    self.branches_data[label] = {
                        "slug": build["slug"],
                        "date": format_date(build.get("committedDate")),
                    }
                self.after(0, self._update_branches_ui_success)
            else:
                self.after(0, self._update_branches_ui_error, f"Error al cargar (código {response.status_code}).")
        except Exception:
            self.after(0, self._update_branches_ui_error, "Error de conexión al cargar ramas.")

    def _update_branches_ui_success(self):
        self.progress.stop()
        self.progress.pack_forget()
        values = list(self.branches_data.keys())
        self.combo.configure(state="readonly", values=values)
        if values:
            self.combo_var.set(values[0])
            self.on_branch_select()
        else:
            self.combo_var.set("No hay builds publicados")

    def _update_branches_ui_error(self, message):
        self.progress.stop()
        self.progress.pack_forget()
        self.combo_var.set("Error de conexión")
        self.set_status(message, is_error=True)

    def on_branch_select(self, choice=None):
        selected = self.combo_var.get()
        if selected in self.branches_data:
            self.lbl_date.configure(text=f"Última actualización: {self.branches_data[selected]['date']}")
            self.btn_download.configure(state="normal")
            self.lbl_status.configure(text="")

    def start_download_thread(self):
        selected = self.combo_var.get()
        if selected not in self.branches_data:
            return
        self.btn_download.configure(text="Descargando...", state="disabled")
        self.set_status("Descargando desde el servidor...")
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
                    self.after(0, self.set_status, "Ya tenés instalada esta versión.", False, True)
                else:
                    os.replace(temp_path, target_path)
                    self.after(0, self.set_status, f"¡Listo! {DLL_NAME} fue actualizado.")
            else:
                self.after(0, self.set_status, f"El archivo no existe (código {response.status_code}).", True)
        except PermissionError:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            self.after(0, self.set_status, "Permiso denegado. Cerrá el juego e intentá de nuevo.", True)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            self.after(0, self.set_status, "Ocurrió un error inesperado al descargar.", True)
        finally:
            self.after(0, lambda: self.btn_download.configure(text="Descargar e instalar", state="normal"))

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
                self.after(0, self._show_updater_available, remote_commit)
        except Exception:
            pass

    def _show_updater_available(self, remote_commit):
        self.lbl_updater_status.configure(text=f"Nueva versión disponible ({remote_commit})", text_color=COLOR_WARN)
        self.btn_check_updater.configure(text="Descargar\nactualización", command=self.start_updater_download_thread)

    def start_updater_download_thread(self):
        self.btn_check_updater.configure(state="disabled")
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
                self.after(0, self._show_restart_button)
            else:
                self.after(0, lambda: self.lbl_updater_status.configure(text="No se pudo descargar la actualización.", text_color=COLOR_ERROR))
        except Exception:
            self.after(0, lambda: self.lbl_updater_status.configure(text="Error al descargar la actualización.", text_color=COLOR_ERROR))

    def _show_restart_button(self):
        self.lbl_updater_status.configure(text="Actualización descargada.", text_color=COLOR_ACCENT)
        self.btn_check_updater.configure(text="Reiniciar\nahora", state="normal", command=self.apply_updater_update)

    def apply_updater_update(self):
        if not self.new_updater_path or not os.path.exists(self.new_updater_path):
            return
        try:
            subprocess.Popen([self.new_updater_path])
        except Exception:
            self.lbl_updater_status.configure(text="No se pudo iniciar la nueva versión.", text_color=COLOR_ERROR)
            return
        self.destroy()


if __name__ == "__main__":
    app = RE4ModUpdater()
    app.mainloop()
