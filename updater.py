import customtkinter as ctk
import requests
import re
import os
import sys
import subprocess
import tempfile
import threading
import webbrowser
import hashlib
from datetime import datetime, timezone

# ==========================================
# CONFIGURACIÓN
# ==========================================
WORKER_BASE_URL = "https://re4mp-worker.insanyteam-devs-8a9.workers.dev"
REPO_URL = "https://gitlab.com/tomasvalero998/re4mp"

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

# Paleta "ámbar de inventario", tal cual la definió Claude Design.
COLOR_BG = "#0C0B08"
COLOR_PANEL = "#17140F"
COLOR_PANEL_BORDER = "#2E2A1F"
COLOR_INNER = "#1D1A14"
COLOR_ACCENT = "#E3A83B"
COLOR_ACCENT_TEXT = "#221706"
COLOR_ACCENT_SOFT_BG = "#2E2712"
COLOR_TITLE = "#F2E8D5"
COLOR_STATE_TITLE = "#E7DACB"
COLOR_MUTED = "#A9977A"
COLOR_MUTED_2 = "#7A6F58"
COLOR_LABEL = "#C9BEA5"
COLOR_BRANCH_BG = "#221E16"
COLOR_BRANCH_NAME = "#D8CDB4"
COLOR_BRANCH_DATE = "#8A7E64"
COLOR_BORDER_BTN = "#3A3325"
COLOR_ONLINE = "#7BAE5B"
COLOR_OFFLINE = "#CB6E1F"
COLOR_ERROR = "#C0463C"
COLOR_ERROR_BG = "#241814"
COLOR_ERROR_BORDER = "#5A3A32"
COLOR_SUCCESS_BG = "#182213"
COLOR_SUCCESS_BORDER = "#3E5A2E"
COLOR_SUCCESS_BTN = "#7BAE5B"

ctk.set_appearance_mode("Dark")
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


def format_relative(iso_date: str) -> str:
    if not iso_date:
        return "--"
    try:
        dt = datetime.strptime(iso_date[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return iso_date

    delta = datetime.now(timezone.utc) - dt
    seconds = delta.total_seconds()
    if seconds < 60:
        return "hace instantes"
    if seconds < 3600:
        mins = int(seconds // 60)
        return f"hace {mins} min"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"hace {hours} hora{'s' if hours != 1 else ''}"
    days = int(seconds // 86400)
    if days < 30:
        return f"hace {days} día{'s' if days != 1 else ''}"
    if days < 365:
        months = days // 30
        return f"hace {months} mes{'es' if months != 1 else ''}"
    years = days // 365
    return f"hace {years} año{'s' if years != 1 else ''}"


def font(size, bold=False):
    return ctk.CTkFont(family="Segoe UI", size=size, weight="bold" if bold else "normal")


class RE4ModUpdater(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.configure(fg_color=COLOR_BG)
        self.title("RE4MP - Mod Updater")
        self.geometry("440x680")
        self.minsize(400, 580)
        self.resizable(True, True)

        self.branches_data = {}
        self.new_updater_path = None
        self.selected_label = None
        self.selected_slug = None
        self.branch_row_widgets = {}
        self.folder_ok = self._validate_game_folder()

        self._build_card()

        threading.Thread(target=self.check_updater_version, daemon=True).start()
        if self.folder_ok:
            self._show_view("normal")
            threading.Thread(target=self.fetch_branches, daemon=True).start()
        else:
            self._show_view("folder_error")

    # ---------------------------------------------------------
    # Validaciones
    # ---------------------------------------------------------
    def _validate_game_folder(self) -> bool:
        return os.path.exists(os.path.join(app_dir(), GAME_EXE_NAME))

    # ---------------------------------------------------------
    # Estructura general: una sola tarjeta con header + sección de
    # actualización del updater (siempre visibles) + contenido variable.
    # ---------------------------------------------------------
    def _build_card(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=20, pady=20)

        self.card = ctk.CTkFrame(
            outer, fg_color=COLOR_PANEL, border_color=COLOR_PANEL_BORDER, border_width=1, corner_radius=16,
        )
        self.card.pack(fill="both", expand=True)

        self._build_header()
        self._build_updater_section()

        self.content_container = ctk.CTkFrame(self.card, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self._build_view_normal()
        self._build_view_folder_error()
        self._build_view_offline()
        self._build_view_empty()

    def _build_header(self):
        row = ctk.CTkFrame(self.card, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(20, 16))

        badge = ctk.CTkFrame(
            row, width=38, height=38, corner_radius=10, fg_color=COLOR_ACCENT_SOFT_BG,
            border_color=COLOR_ACCENT, border_width=1,
        )
        badge.pack(side="left")
        badge.pack_propagate(False)
        ctk.CTkLabel(badge, text="🧭", font=font(19)).pack(expand=True)

        title_col = ctk.CTkFrame(row, fg_color="transparent")
        title_col.pack(side="left", fill="x", expand=True, padx=(11, 0))
        ctk.CTkLabel(title_col, text="RE4MP", font=font(19, bold=True), text_color=COLOR_TITLE).pack(anchor="w")
        ctk.CTkLabel(title_col, text="Mod Updater", font=font(12), text_color=COLOR_MUTED).pack(anchor="w")

        status_col = ctk.CTkFrame(row, fg_color="transparent")
        status_col.pack(side="right")
        self.status_dot = ctk.CTkLabel(status_col, text="●", font=font(9), text_color=COLOR_MUTED, width=12)
        self.status_dot.pack(side="left")
        self.lbl_online_status = ctk.CTkLabel(status_col, text="Conectando...", font=font(12), text_color=COLOR_MUTED)
        self.lbl_online_status.pack(side="left", padx=(4, 0))

    def _set_online_status(self, online: bool):
        color = COLOR_ONLINE if online else COLOR_OFFLINE
        self.status_dot.configure(text_color=color)
        self.lbl_online_status.configure(text="En línea" if online else "Sin conexión", text_color=color)

    def _build_updater_section(self):
        panel = ctk.CTkFrame(self.card, fg_color=COLOR_INNER, border_color=COLOR_PANEL_BORDER, border_width=1, corner_radius=10)
        panel.pack(fill="x", padx=20, pady=(0, 18))

        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=13, pady=11)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(left, text="Actualización del updater", font=font(12.5, bold=True), text_color=COLOR_LABEL).pack(anchor="w")
        self.lbl_updater_status = ctk.CTkLabel(
            left, text=f"{UPDATER_VERSION} · Estás al día", font=font(11.5), text_color=COLOR_MUTED_2,
            wraplength=200, justify="left",
        )
        self.lbl_updater_status.pack(anchor="w", pady=(2, 0))

        self.btn_check_updater = ctk.CTkButton(
            row, text="Buscar actualización", height=30, corner_radius=7,
            fg_color="transparent", hover_color=COLOR_ACCENT_SOFT_BG, border_color=COLOR_BORDER_BTN, border_width=1,
            text_color=COLOR_MUTED, font=font(11.5, bold=True),
            command=self.start_updater_check_thread,
        )
        self.btn_check_updater.pack(side="right")

        self.updater_progress = ctk.CTkProgressBar(panel, mode="determinate", corner_radius=6, fg_color=COLOR_PANEL_BORDER, progress_color=COLOR_ACCENT, height=7)
        self.updater_progress.set(0)

    # ---------------------------------------------------------
    # Manejo de vistas del contenido variable
    # ---------------------------------------------------------
    def _show_view(self, name):
        for view in (self.view_normal, self.view_folder_error, self.view_offline, self.view_empty):
            view.pack_forget()
        {
            "normal": self.view_normal,
            "folder_error": self.view_folder_error,
            "offline": self.view_offline,
            "empty": self.view_empty,
        }[name].pack(fill="both", expand=True)

    def _build_state_card(self, parent, icon, title, body, btn_text, btn_command, accent_color, bg=COLOR_INNER, border=COLOR_PANEL_BORDER):
        card = ctk.CTkFrame(parent, fg_color=bg, border_color=border, border_width=1, corner_radius=10)
        ctk.CTkLabel(card, text=icon, font=font(30)).pack(pady=(22, 10))
        ctk.CTkLabel(card, text=title, font=font(14, bold=True), text_color=COLOR_STATE_TITLE, wraplength=300, justify="center").pack(pady=(0, 6))
        if body:
            ctk.CTkLabel(card, text=body, font=font(12), text_color=COLOR_MUTED, wraplength=300, justify="center").pack(pady=(0, 14), padx=16)
        if btn_text:
            ctk.CTkButton(
                card, text=btn_text, height=32, corner_radius=7, fg_color="transparent",
                hover_color=COLOR_ACCENT_SOFT_BG, border_color=accent_color, border_width=1,
                text_color=accent_color, font=font(12, bold=True), command=btn_command,
            ).pack(pady=(0, 22))
        return card

    def _build_view_folder_error(self):
        self.view_folder_error = ctk.CTkFrame(self.content_container, fg_color="transparent")
        card = self._build_state_card(
            self.view_folder_error, "📁", "No encontramos Resident Evil 4",
            f"Movés esta app a la misma carpeta que {GAME_EXE_NAME} y la abrís de nuevo.",
            "Ver instrucciones", lambda: webbrowser.open(REPO_URL),
            accent_color=COLOR_ERROR, bg=COLOR_ERROR_BG, border=COLOR_ERROR_BORDER,
        )
        card.pack(fill="both", expand=True)

    def _build_view_offline(self):
        self.view_offline = ctk.CTkFrame(self.content_container, fg_color="transparent")
        card = self._build_state_card(
            self.view_offline, "🔌", "Sin conexión", "Revisá tu internet e intentá de nuevo.",
            "Reintentar", self.start_refresh_branches_thread, accent_color=COLOR_MUTED,
        )
        card.pack(fill="both", expand=True)

    def _build_view_empty(self):
        self.view_empty = ctk.CTkFrame(self.content_container, fg_color="transparent")
        card = self._build_state_card(
            self.view_empty, "📭", "Todavía no hay versiones publicadas", "Volvé a intentar más tarde.",
            "Reintentar", self.start_refresh_branches_thread, accent_color=COLOR_MUTED,
        )
        card.pack(fill="both", expand=True)

    def _build_view_normal(self):
        self.view_normal = ctk.CTkFrame(self.content_container, fg_color="transparent")

        header_row = ctk.CTkFrame(self.view_normal, fg_color="transparent")
        header_row.pack(fill="x")
        ctk.CTkLabel(header_row, text="Elegir rama del mod", font=font(15.5, bold=True), text_color=COLOR_TITLE).pack(side="left")
        ctk.CTkButton(
            header_row, text="↻", width=28, height=28, corner_radius=8,
            fg_color="transparent", hover_color=COLOR_ACCENT_SOFT_BG, border_color=COLOR_BORDER_BTN, border_width=1,
            text_color=COLOR_MUTED, font=font(13, bold=True),
            command=self.start_refresh_branches_thread,
        ).pack(side="right")

        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            self.view_normal, textvariable=self.search_var, placeholder_text="🔍 Buscar rama...",
            fg_color=COLOR_INNER, border_color=COLOR_PANEL_BORDER, border_width=1, corner_radius=8,
            text_color=COLOR_TITLE, placeholder_text_color=COLOR_MUTED_2, height=34,
        )
        self.search_entry.pack(fill="x", pady=(9, 11))
        self.search_var.trace_add("write", lambda *args: self._render_branch_list())

        self.loading_bar = ctk.CTkProgressBar(self.view_normal, mode="indeterminate", corner_radius=6, fg_color=COLOR_PANEL_BORDER, progress_color=COLOR_ACCENT, height=6)

        self.branch_list_frame = ctk.CTkScrollableFrame(self.view_normal, fg_color="transparent", height=210)
        self.branch_list_frame.pack(fill="both", expand=True, pady=(0, 16))

        self.download_controls = ctk.CTkFrame(self.view_normal, fg_color="transparent")
        self.download_controls.pack(fill="x")

        self.btn_download = ctk.CTkButton(
            self.download_controls, text="Descargar", height=44, corner_radius=10,
            fg_color=COLOR_ACCENT, hover_color="#C99432", text_color=COLOR_ACCENT_TEXT,
            font=font(14.5, bold=True), state="disabled", command=self.start_download_thread,
        )
        self.btn_download.pack(fill="x")

        self.lbl_status = ctk.CTkLabel(self.download_controls, text="", font=font(11, bold=True), wraplength=350, justify="center")
        self.lbl_status.pack(pady=(8, 0))

        self.success_panel = self._build_state_card(
            self.view_normal, "✅", "¡Instalado correctamente!", None,
            None, None, accent_color=COLOR_SUCCESS_BTN, bg=COLOR_SUCCESS_BG, border=COLOR_SUCCESS_BORDER,
        )
        ctk.CTkButton(
            self.success_panel, text="🎮 Jugar ahora", height=36, corner_radius=7,
            fg_color=COLOR_SUCCESS_BTN, hover_color="#6BA04A", text_color=COLOR_ACCENT_TEXT,
            font=font(12.5, bold=True), command=self.launch_game,
        ).pack(pady=(0, 22))

    # ---------------------------------------------------------
    # Ramas del mod
    # ---------------------------------------------------------
    def start_refresh_branches_thread(self):
        self._show_view("normal")
        self.loading_bar.pack(fill="x", pady=(0, 8), before=self.branch_list_frame)
        self.loading_bar.start()
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
                        "date": format_relative(build.get("committedDate")),
                    }
                self.after(0, self._update_branches_ui_success)
            else:
                self.after(0, self._update_branches_ui_error)
        except Exception:
            self.after(0, self._update_branches_ui_error)

    def _update_branches_ui_success(self):
        self.loading_bar.stop()
        self.loading_bar.pack_forget()
        self._set_online_status(True)
        if not self.branches_data:
            self._show_view("empty")
            return
        self._show_view("normal")
        self._render_branch_list()
        ordered = self._ordered_branch_labels()
        if ordered:
            self._select_branch(ordered[0])

    def _update_branches_ui_error(self):
        self.loading_bar.stop()
        self.loading_bar.pack_forget()
        self._set_online_status(False)
        self._show_view("offline")

    def _ordered_branch_labels(self):
        priority = {"main": 0, "master": 0, "prd": 1}
        return sorted(self.branches_data.keys(), key=lambda label: (priority.get(label, 2), label.lower()))

    def _render_branch_list(self):
        for widget in self.branch_list_frame.winfo_children():
            widget.destroy()
        self.branch_row_widgets = {}

        query = self.search_var.get().strip().lower()
        labels = [l for l in self._ordered_branch_labels() if query in l.lower()]

        if not labels:
            ctk.CTkLabel(self.branch_list_frame, text="Sin resultados", text_color=COLOR_MUTED, font=font(11)).pack(pady=10)
            return

        for label in labels:
            self._add_branch_row(label)

    def _add_branch_row(self, label):
        is_selected = label == self.selected_label
        row = ctk.CTkFrame(
            self.branch_list_frame, corner_radius=9,
            fg_color=COLOR_ACCENT_SOFT_BG if is_selected else COLOR_BRANCH_BG,
            border_color=COLOR_ACCENT if is_selected else COLOR_PANEL_BORDER,
            border_width=2 if is_selected else 1,
        )
        row.pack(fill="x", pady=3)

        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", padx=13, pady=10)

        text_col = ctk.CTkFrame(inner, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True)
        name_color = COLOR_TITLE if is_selected else COLOR_BRANCH_NAME
        date_color = COLOR_LABEL if is_selected else COLOR_BRANCH_DATE
        ctk.CTkLabel(text_col, text=label, font=font(13, bold=True), text_color=name_color, anchor="w").pack(fill="x")
        ctk.CTkLabel(text_col, text=f"Actualizado {self.branches_data[label]['date']}", font=font(11), text_color=date_color, anchor="w").pack(fill="x")

        if is_selected:
            ctk.CTkLabel(inner, text="●", font=font(13), text_color=COLOR_ACCENT).pack(side="right")

        for widget in (row, inner, text_col):
            widget.bind("<Button-1>", lambda e, l=label: self._select_branch(l))

        self.branch_row_widgets[label] = row

    def _select_branch(self, label):
        if label not in self.branches_data:
            return
        self.selected_label = label
        self.selected_slug = self.branches_data[label]["slug"]
        self.success_panel.pack_forget()
        self.download_controls.pack(fill="x")
        self._render_branch_list()
        self.btn_download.configure(state="normal")
        self.lbl_status.configure(text="")

    def start_download_thread(self):
        if not self.selected_slug:
            return
        self.btn_download.configure(text="Descargando...", state="disabled")
        self.lbl_status.configure(text="Descargando desde el servidor...", text_color=COLOR_MUTED)
        threading.Thread(target=self._process_download, args=(self.selected_slug,), daemon=True).start()

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
                    self.after(0, lambda: self.lbl_status.configure(text="Ya tenés instalada esta versión.", text_color=COLOR_MUTED))
                    self.after(0, lambda: self.btn_download.configure(text="Descargar", state="normal"))
                else:
                    os.replace(temp_path, target_path)
                    self.after(0, self._show_install_success)
            else:
                self.after(0, lambda: self.lbl_status.configure(text=f"El archivo no existe (código {response.status_code}).", text_color=COLOR_ERROR))
                self.after(0, lambda: self.btn_download.configure(text="Descargar", state="normal"))
        except PermissionError:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            self.after(0, lambda: self.lbl_status.configure(text="Permiso denegado. Cerrá el juego e intentá de nuevo.", text_color=COLOR_ERROR))
            self.after(0, lambda: self.btn_download.configure(text="Descargar", state="normal"))
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            self.after(0, lambda: self.lbl_status.configure(text="Ocurrió un error inesperado al descargar.", text_color=COLOR_ERROR))
            self.after(0, lambda: self.btn_download.configure(text="Descargar", state="normal"))

    def _show_install_success(self):
        self.download_controls.pack_forget()
        self.success_panel.pack(fill="both", expand=True)
        self.btn_download.configure(text="Descargar", state="normal")

    def launch_game(self):
        game_path = os.path.join(app_dir(), GAME_EXE_NAME)
        try:
            subprocess.Popen([game_path], cwd=app_dir())
        except Exception:
            pass

    # ---------------------------------------------------------
    # Self-update del propio updater
    # ---------------------------------------------------------
    def start_updater_check_thread(self):
        self.btn_check_updater.configure(state="disabled")
        self.lbl_updater_status.configure(text="Buscando actualización...", text_color=COLOR_MUTED_2)
        threading.Thread(target=self.check_updater_version, daemon=True).start()

    def check_updater_version(self):
        try:
            response = requests.get(f"{WORKER_BASE_URL}/updater/latest", headers=HEADERS, timeout=10)
            if response.status_code != 200:
                self.after(0, self._show_updater_check_error, f"No se pudo verificar (código {response.status_code}).")
                return
            remote_commit = response.json().get("commit")
            if remote_commit and remote_commit != UPDATER_VERSION:
                self.after(0, self._show_updater_available, remote_commit)
            else:
                self.after(0, self._show_updater_up_to_date)
        except Exception:
            self.after(0, self._show_updater_check_error, "Error de conexión al verificar.")

    def _show_updater_up_to_date(self):
        self.lbl_updater_status.configure(text=f"{UPDATER_VERSION} · Estás al día", text_color=COLOR_MUTED_2)
        self.btn_check_updater.configure(state="normal")

    def _show_updater_check_error(self, message):
        self.lbl_updater_status.configure(text=message, text_color=COLOR_ERROR)
        self.btn_check_updater.configure(state="normal")

    def _show_updater_available(self, remote_commit):
        self.lbl_updater_status.configure(text=f"Nueva versión disponible ({remote_commit})", text_color=COLOR_ACCENT)
        self.btn_check_updater.configure(text="Descargar actualización", state="normal", command=self.start_updater_download_thread)

    def start_updater_download_thread(self):
        self.btn_check_updater.configure(state="disabled", text="Descargando...")
        self.lbl_updater_status.configure(text="Descargando actualización...", text_color=COLOR_MUTED_2)
        self.updater_progress.set(0)
        self.updater_progress.pack(fill="x", padx=13, pady=(0, 11))
        threading.Thread(target=self._download_new_updater, daemon=True).start()

    def _download_new_updater(self):
        # A la carpeta temporal de Windows, no al lado del .exe actual: un
        # .exe escribiendo otro .exe en su propia carpeta es un patrón que
        # varios antivirus tratan como sospechoso.
        new_path = os.path.join(tempfile.gettempdir(), "re4mp_updater_new.exe")
        try:
            response = requests.get(f"{WORKER_BASE_URL}/updater/download", headers=HEADERS, stream=True, timeout=20)
            if response.status_code == 200:
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                with open(new_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=524288):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            self.after(0, self.updater_progress.set, downloaded / total)
                self.new_updater_path = new_path
                self.after(0, self._show_restart_button)
            else:
                self.after(0, lambda: self._show_updater_download_error("No se pudo descargar la actualización."))
        except Exception:
            self.after(0, lambda: self._show_updater_download_error("Error al descargar la actualización."))

    def _show_updater_download_error(self, message):
        self.updater_progress.pack_forget()
        self.lbl_updater_status.configure(text=message, text_color=COLOR_ERROR)
        self.btn_check_updater.configure(state="normal", text="Buscar actualización", command=self.start_updater_check_thread)

    def _show_restart_button(self):
        self.updater_progress.pack_forget()
        self.lbl_updater_status.configure(text="Actualización lista para instalar.", text_color=COLOR_ONLINE)
        self.btn_check_updater.configure(text="Reiniciar ahora", state="normal", command=self.apply_updater_update)

    def apply_updater_update(self):
        if not self.new_updater_path or not os.path.exists(self.new_updater_path):
            return

        if not getattr(sys, "frozen", False):
            subprocess.Popen([self.new_updater_path])
            self.destroy()
            return

        current_exe = sys.executable

        batch_path = os.path.join(tempfile.gettempdir(), "re4mp_updater_swap.bat")
        batch_content = (
            "@echo off\r\n"
            "setlocal\r\n"
            "set \"OLD_EXE=%~1\"\r\n"
            "set \"NEW_EXE=%~2\"\r\n"
            "set \"PID=%~3\"\r\n"
            ":waitloop\r\n"
            "tasklist /FI \"PID eq %PID%\" | find \"%PID%\" >nul\r\n"
            "if not errorlevel 1 (\r\n"
            "    timeout /t 1 /nobreak >nul\r\n"
            "    goto waitloop\r\n"
            ")\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            "del /f /q \"%OLD_EXE%\"\r\n"
            "move /y \"%NEW_EXE%\" \"%OLD_EXE%\"\r\n"
            "timeout /t 6 /nobreak >nul\r\n"
            "start \"\" \"%OLD_EXE%\"\r\n"
            "del \"%~f0\"\r\n"
        )
        try:
            with open(batch_path, "w") as f:
                f.write(batch_content)
            subprocess.Popen(
                ["cmd", "/c", batch_path, current_exe, self.new_updater_path, str(os.getpid())],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            self.lbl_updater_status.configure(text="No se pudo iniciar la actualización.", text_color=COLOR_ERROR)
            return

        self.destroy()


if __name__ == "__main__":
    app = RE4ModUpdater()
    app.mainloop()