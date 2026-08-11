import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import requests
import re
import os
import sys
import subprocess
import tempfile
import threading
import time
import webbrowser
import hashlib
from datetime import datetime, timezone

# ==========================================
# CONFIGURACIÓN
# ==========================================
# Este archivo se descarga como texto plano y lo ejecuta launcher.py vía
# runpy, que le inyecta estos nombres ya resueltos en el namespace global
# antes de correr el código. Los try/except son solo para poder correr este
# archivo standalone en desarrollo (python updater_app.py directo).
try:
    CLIENT_API_KEY
except NameError:
    CLIENT_API_KEY = os.environ.get("CLIENT_API_KEY", "")
try:
    WORKER_BASE_URL
except NameError:
    WORKER_BASE_URL = "https://re4mp-worker.insanyteam-devs-8a9.workers.dev"
try:
    APP_DIR
except NameError:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    APP_PY_PATH
except NameError:
    APP_PY_PATH = os.path.abspath(__file__)
try:
    APP_OLD_PY_PATH
except NameError:
    APP_OLD_PY_PATH = os.path.abspath(__file__) + ".old"
try:
    LAUNCHER_PATH
except NameError:
    LAUNCHER_PATH = os.path.abspath(__file__)
try:
    REPO_URL
except NameError:
    REPO_URL = os.environ.get("REPO_URL", "")

# El pipeline reemplaza este placeholder por el commit corto al publicar
# (sed sobre este archivo, no hace falta compilar nada).
UPDATER_APP_VERSION = "__UPDATER_APP_VERSION__"

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


def game_dir() -> str:
    # La carpeta del juego es donde vive launcher.exe (no donde vive este
    # .py, que ahora está en APP_DIR/%LOCALAPPDATA%).
    return os.path.dirname(LAUNCHER_PATH)


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
        # fromisoformat entiende el offset real de la fecha (+HH:MM,
        # -HH:MM, o 'Z'), a diferencia de truncar a los primeros 19
        # caracteres y forzar UTC a ciegas (lo que había antes): la fecha
        # que genera el pipeline (git %cI) viene con el offset local de
        # quien commiteó, no en UTC — truncarla y asumir UTC corría todo
        # el cálculo exactamente por ese offset (3 horas de más para
        # alguien en GMT-3, por ejemplo).
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
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
    return ctk.CTkFont(family="Segoe UI", size=int(round(size)), weight="bold" if bold else "normal")


# ==========================================
# VENTANA NATIVA SIN MARCO (Win32)
# ==========================================
# overrideredirect(True) por sí solo deja la ventana como un WS_POPUP sin
# "owner" a nivel de Windows, y eso hace que no aparezca en la barra de
# tareas, no tome foco al abrir, y a veces se abra detrás de otras
# ventanas. Estas funciones parchean los estilos Win32 reales para que se
# siga comportando como una ventana nativa normal pese a no tener marco.
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _gdi32 = ctypes.windll.gdi32

    _GWL_STYLE = -16
    _GWL_EXSTYLE = -20
    _WS_CAPTION = 0x00C00000
    _WS_THICKFRAME = 0x00040000
    _WS_POPUP = 0x80000000
    _WS_SYSMENU = 0x00080000
    _WS_MINIMIZEBOX = 0x00020000
    _WS_EX_APPWINDOW = 0x00040000
    _WS_EX_TOOLWINDOW = 0x00000080
    _SWP_NOSIZE = 0x0001
    _SWP_NOMOVE = 0x0002
    _SWP_NOZORDER = 0x0004
    _SWP_FRAMECHANGED = 0x0020
    _SW_HIDE = 0
    _SW_SHOW = 5
    _SW_SHOWNORMAL = 1
    _SW_MINIMIZE = 6

    # Firmas explícitas: sin esto, ctypes trata los HWND (punteros de 64
    # bits) como c_int (32 bits) por default, lo que trunca el handle en
    # Windows de 64 bits y produce fallos silenciosos e intermitentes.
    _user32.GetParent.restype = wintypes.HWND
    _user32.GetParent.argtypes = [wintypes.HWND]
    _user32.GetWindowLongPtrW.restype = ctypes.c_longlong
    _user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetWindowLongPtrW.restype = ctypes.c_longlong
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint,
    ]
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetForegroundWindow.restype = wintypes.BOOL
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.SetWindowRgn.restype = ctypes.c_int
    _user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
    _gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
    _gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6


def _win_top_level_hwnd(root) -> int:
    # Tk expone un HWND "de dibujo" interno vía winfo_id(); el HWND real
    # del top-level que administra Windows es el padre de ese.
    root.update_idletasks()
    child = wintypes.HWND(root.winfo_id())
    parent = _user32.GetParent(child)
    return parent if parent else child.value


def apply_borderless_native_window(root):
    if not IS_WINDOWS:
        return
    root.update_idletasks()
    hwnd = _win_top_level_hwnd(root)

    _user32.ShowWindow(hwnd, _SW_HIDE)

    style = _user32.GetWindowLongPtrW(hwnd, _GWL_STYLE)
    style &= ~(_WS_CAPTION | _WS_THICKFRAME)
    style |= _WS_POPUP | _WS_SYSMENU | _WS_MINIMIZEBOX
    _user32.SetWindowLongPtrW(hwnd, _GWL_STYLE, style)

    # Lo que realmente trae de vuelta el ícono en la barra de tareas.
    ex_style = _user32.GetWindowLongPtrW(hwnd, _GWL_EXSTYLE)
    ex_style &= ~_WS_EX_TOOLWINDOW
    ex_style |= _WS_EX_APPWINDOW
    _user32.SetWindowLongPtrW(hwnd, _GWL_EXSTYLE, ex_style)

    _user32.SetWindowPos(
        hwnd, None, 0, 0, 0, 0,
        _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER | _SWP_FRAMECHANGED,
    )

    _user32.ShowWindow(hwnd, _SW_SHOW)
    win_bring_to_front(root)


def apply_rounded_corners(root, radius=16):
    """
    La tarjeta ya se dibuja redondeada por software (customtkinter), pero
    la ventana de Windows en sí seguía siendo un rectángulo — quedaban
    triangulitos del fondo oscuro asomando en las esquinas. Esto recorta
    la forma real del HWND con una región de esquinas curvas, para que
    coincida.

    Nota honesta: usa las dimensiones físicas reales de la ventana
    (GetWindowRect, no winfo_width/height de Tk, que puede estar en otro
    espacio de coordenadas si Windows está escalado a más del 100%), pero
    el radio en sí no se ajusta por DPI — en pantallas con escalado
    distinto de 100% puede no calzar pixel-perfecto con el radio de la
    tarjeta interna.
    """
    if not IS_WINDOWS:
        return
    root.update_idletasks()
    hwnd = _win_top_level_hwnd(root)
    rect = wintypes.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    region = _gdi32.CreateRoundRectRgn(0, 0, width, height, radius * 2, radius * 2)
    _user32.SetWindowRgn(hwnd, region, True)


def win_bring_to_front(root):
    if not IS_WINDOWS:
        root.lift()
        root.focus_force()
        return
    root.update_idletasks()
    hwnd = _win_top_level_hwnd(root)
    _user32.ShowWindow(hwnd, _SW_SHOWNORMAL)
    _user32.SetForegroundWindow(hwnd)
    root.lift()
    root.focus_force()
    # SetForegroundWindow puede fallar en silencio si Windows considera que
    # "pasó demasiado tiempo" desde el último input del usuario (nuestro
    # caso: el launcher tarda un toque bajando updater_app.py antes de
    # llegar acá). Togglear -topmost no tiene esa restricción y es el
    # workaround estándar de Tkinter para este problema puntual.
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))


class RE4ModUpdater(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.configure(fg_color=COLOR_BG)
        self.title("RE4MP - Mod Updater")
        self.geometry("440x680")
        self.minsize(440, 680)
        self.resizable(False, False)
        self.overrideredirect(True)

        self.branches_data = {}
        self.new_app_content = None
        self.selected_label = None
        self.selected_slug = None
        self.branch_row_widgets = {}
        self._destroyed = False
        self._is_fading = False
        self.folder_ok = self._validate_game_folder()

        self._build_card()
        apply_borderless_native_window(self)
        apply_rounded_corners(self)
        # <Map>/<Unmap> de Tk no son confiables para detectar minimizado o
        # restaurado en una ventana WS_POPUP sin marco (no se disparan de
        # forma consistente en este contexto). En vez de depender de esos
        # eventos, consultamos el estado real de Windows por polling.
        self._was_iconic = False
        self._poll_iconic_state()

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
        return os.path.exists(os.path.join(game_dir(), GAME_EXE_NAME))

    # ---------------------------------------------------------
    # Estructura general: una sola tarjeta con header + sección de
    # actualización del updater (siempre visibles) + contenido variable.
    # ---------------------------------------------------------
    def _build_card(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=3, pady=3)

        self.card = ctk.CTkFrame(
            outer, fg_color=COLOR_PANEL, border_color=COLOR_PANEL_BORDER, border_width=1, corner_radius=16,
        )
        self.card.pack(fill="both", expand=True)

        self._build_titlebar()
        self._build_header()
        self._build_updater_section()

        self.content_container = ctk.CTkFrame(self.card, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self._build_view_normal()
        self._build_view_folder_error()
        self._build_view_offline()
        self._build_view_empty()

    def _start_drag(self, event):
        self._drag_offset_x = event.x_root - self.winfo_x()
        self._drag_offset_y = event.y_root - self.winfo_y()

    def _do_drag(self, event):
        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        self.geometry(f"+{x}+{y}")

    def destroy(self):
        self._destroyed = True
        super().destroy()

    def minimize(self):
        self._fade_out(callback=self._do_native_minimize)

    def _do_native_minimize(self):
        if IS_WINDOWS:
            hwnd = _win_top_level_hwnd(self)
            _user32.ShowWindow(hwnd, _SW_MINIMIZE)
        else:
            self.iconify()
        # El watcher (_poll_iconic_state) es quien detecta la transición y
        # dispara el fade-in al restaurar — funciona sin importar si el
        # minimizado se disparó desde nuestro botón, la barra de tareas, o
        # el menú de sistema, porque no depende de ningún evento de Tk.

    def _poll_iconic_state(self):
        if IS_WINDOWS and not self._destroyed:
            hwnd = _win_top_level_hwnd(self)
            is_iconic = bool(_user32.IsIconic(hwnd))
            if is_iconic and not self._was_iconic:
                # Se acaba de minimizar (por cualquier vía). Si vino de
                # nuestro botón ya está en alpha 0 por el fade-out; si vino
                # de afuera (taskbar/menú de sistema) no hubo fade previo,
                # así que forzamos alpha 0 acá para no dejar nada visible
                # "colgado" detrás.
                self.attributes("-alpha", 0.0)
            elif not is_iconic and self._was_iconic:
                # Se acaba de restaurar.
                self._fade_in()
            self._was_iconic = is_iconic
        if not self._destroyed:
            self.after(250, self._poll_iconic_state)

    def _fade_out(self, callback, steps=8, delay=15):
        if self._is_fading:
            return
        self._is_fading = True

        def step(i):
            if i > steps:
                self._is_fading = False
                callback()
                return
            self.attributes("-alpha", max(0.0, 1.0 - i / steps))
            self.after(delay, lambda: step(i + 1))
        step(0)

    def _fade_in(self, steps=8, delay=15):
        if self._is_fading:
            return
        self._is_fading = True

        def step(i):
            self.attributes("-alpha", min(1.0, i / steps))
            if i < steps:
                self.after(delay, lambda: step(i + 1))
            else:
                self._is_fading = False
        step(0)

    def _build_titlebar(self):
        # Barra fina y sutil, separada de la tarjeta de marca de abajo:
        # esta es la única zona de arrastre real, con hover en vez de
        # cambio de cursor como referencia visual de que ahí se agarra.
        bar = ctk.CTkFrame(self.card, fg_color=COLOR_PANEL, corner_radius=10, height=30)
        bar.pack(fill="x", padx=1, pady=(1, 0))
        bar.pack_propagate(False)

        def on_enter(_event=None):
            bar.configure(fg_color=COLOR_INNER)

        def on_leave(_event=None):
            bar.configure(fg_color=COLOR_PANEL)

        bar.bind("<ButtonPress-1>", self._start_drag)
        bar.bind("<B1-Motion>", self._do_drag)
        bar.bind("<Enter>", on_enter)
        bar.bind("<Leave>", on_leave)

        btn_row = ctk.CTkFrame(bar, fg_color="transparent")
        btn_row.pack(side="right", padx=6, pady=3)

        close_btn = ctk.CTkButton(
            btn_row, text="✕", width=22, height=22, corner_radius=11,
            fg_color="transparent", hover_color=COLOR_ERROR_BG, text_color=COLOR_MUTED,
            font=font(11, bold=True), command=self.destroy,
        )
        close_btn.pack(side="right")

        minimize_btn = ctk.CTkButton(
            btn_row, text="—", width=22, height=22, corner_radius=11,
            fg_color="transparent", hover_color=COLOR_PANEL_BORDER, text_color=COLOR_MUTED,
            font=font(11, bold=True), command=self.minimize,
        )
        minimize_btn.pack(side="right", padx=(0, 4))

    def _build_header(self):
        row = ctk.CTkFrame(self.card, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(14, 16))

        badge = ctk.CTkFrame(
            row, width=38, height=38, corner_radius=10, fg_color=COLOR_ACCENT_SOFT_BG,
            border_color=COLOR_ACCENT, border_width=1,
        )
        badge.pack(side="left")
        badge.pack_propagate(False)
        badge_lbl = ctk.CTkLabel(badge, text="🧭", font=font(19))
        # pack(expand=True) lo centra según las métricas de 'Segoe UI', pero
        # el emoji en sí se renderiza con la fuente de reemplazo Segoe UI
        # Emoji, que tiene otro alto/descenso — visualmente queda corrido
        # hacia abajo si se centra "a ciegas". Se compensa con place().
        badge_lbl.place(relx=0.5, rely=0.46, anchor="center")

        title_col = ctk.CTkFrame(row, fg_color="transparent")
        title_col.pack(side="left", fill="x", expand=True, padx=(11, 0))
        title_lbl = ctk.CTkLabel(title_col, text="RE4MP", font=font(19, bold=True), text_color=COLOR_TITLE)
        title_lbl.pack(anchor="w")
        subtitle_lbl = ctk.CTkLabel(title_col, text="Mod Updater", font=font(12), text_color=COLOR_MUTED)
        subtitle_lbl.pack(anchor="w")

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
            left, text=f"{UPDATER_APP_VERSION} · Estás al día", font=font(11.5), text_color=COLOR_MUTED_2,
            wraplength=200, justify="left",
        )
        self.lbl_updater_status.pack(anchor="w", pady=(2, 0))

        # --- DIAGNÓSTICO TEMPORAL, sacar una vez confirmado el fix de _MEIPASS2 ---
        meipass2_status = "presente ⚠️" if os.environ.get("_MEIPASS2") else "no está ✅"
        ctk.CTkLabel(
            left, text=f"[debug] _MEIPASS2: {meipass2_status}", font=font(9), text_color=COLOR_MUTED_2,
        ).pack(anchor="w")
        # --- fin diagnóstico temporal ---

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

    def fetch_branches(self, retry_on_failure=True):
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
                self._handle_fetch_failure(retry_on_failure)
        except Exception:
            self._handle_fetch_failure(retry_on_failure)

    def _handle_fetch_failure(self, retry_on_failure):
        if retry_on_failure:
            # Un solo reintento antes de rendirse: sospecha de que un
            # proceso recién arrancado (típicamente justo después del
            # self-update) puede tener su primera conexión demorada por
            # inspección de antivirus/firewall — el segundo intento, un
            # instante después, suele andar bien.
            time.sleep(1.5)
            self.fetch_branches(retry_on_failure=False)
        else:
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
        name_lbl = ctk.CTkLabel(text_col, text=label, font=font(13, bold=True), text_color=name_color, anchor="w")
        name_lbl.pack(fill="x")
        date_lbl = ctk.CTkLabel(text_col, text=f"Actualizado {self.branches_data[label]['date']}", font=font(11), text_color=date_color, anchor="w")
        date_lbl.pack(fill="x")

        dot_lbl = None
        if is_selected:
            dot_lbl = ctk.CTkLabel(inner, text="●", font=font(13), text_color=COLOR_ACCENT)
            dot_lbl.pack(side="right")

        for widget in (row, inner, text_col, name_lbl, date_lbl):
            widget.bind("<Button-1>", lambda e, l=label: self._select_branch(l))

        self.branch_row_widgets[label] = {"row": row, "inner": inner, "name_lbl": name_lbl, "date_lbl": date_lbl, "dot_lbl": dot_lbl}

    def _restyle_row(self, label, selected):
        refs = self.branch_row_widgets.get(label)
        if not refs:
            return  # la fila no está actualmente renderizada (ej: filtrada por búsqueda)

        refs["row"].configure(
            fg_color=COLOR_ACCENT_SOFT_BG if selected else COLOR_BRANCH_BG,
            border_color=COLOR_ACCENT if selected else COLOR_PANEL_BORDER,
            border_width=2 if selected else 1,
        )
        refs["name_lbl"].configure(text_color=COLOR_TITLE if selected else COLOR_BRANCH_NAME)
        refs["date_lbl"].configure(text_color=COLOR_LABEL if selected else COLOR_BRANCH_DATE)

        if selected and refs["dot_lbl"] is None:
            dot = ctk.CTkLabel(refs["inner"], text="●", font=font(13), text_color=COLOR_ACCENT)
            dot.pack(side="right")
            dot.bind("<Button-1>", lambda e, l=label: self._select_branch(l))
            refs["dot_lbl"] = dot
        elif not selected and refs["dot_lbl"] is not None:
            refs["dot_lbl"].destroy()
            refs["dot_lbl"] = None

    def _select_branch(self, label):
        if label not in self.branches_data:
            return
        previous = self.selected_label
        self.selected_label = label
        self.selected_slug = self.branches_data[label]["slug"]
        self.success_panel.pack_forget()
        self.download_controls.pack(fill="x")
        if previous and previous != label:
            self._restyle_row(previous, selected=False)
        self._restyle_row(label, selected=True)
        self.btn_download.configure(state="normal")
        self.lbl_status.configure(text="")

    def start_download_thread(self):
        if not self.selected_slug:
            return
        self.btn_download.configure(text="Descargando...", state="disabled")
        self.lbl_status.configure(text="Descargando desde el servidor...", text_color=COLOR_MUTED)
        threading.Thread(target=self._process_download, args=(self.selected_slug,), daemon=True).start()

    def _process_download(self, slug):
        target_path = os.path.join(game_dir(), DLL_NAME)
        temp_path = os.path.join(game_dir(), f"{DLL_NAME}.tmp")

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
        game_path = os.path.join(game_dir(), GAME_EXE_NAME)
        try:
            subprocess.Popen([game_path], cwd=game_dir())
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
            response = requests.get(f"{WORKER_BASE_URL}/updater/app/latest", headers=HEADERS, timeout=10)
            if response.status_code != 200:
                self.after(0, self._show_updater_check_error, f"No se pudo verificar (código {response.status_code}).")
                return
            remote_commit = response.json().get("commit")
            if remote_commit and remote_commit != UPDATER_APP_VERSION:
                self.after(0, self._show_updater_available, remote_commit)
            else:
                self.after(0, self._show_updater_up_to_date)
        except Exception:
            self.after(0, self._show_updater_check_error, "Error de conexión al verificar.")

    def _show_updater_up_to_date(self):
        self.lbl_updater_status.configure(text=f"{UPDATER_APP_VERSION} · Estás al día", text_color=COLOR_MUTED_2)
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
        try:
            response = requests.get(f"{WORKER_BASE_URL}/updater/app/download", headers=HEADERS, stream=True, timeout=20)
            if response.status_code == 200:
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                chunks = []
                for chunk in response.iter_content(chunk_size=65536):
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    if total:
                        self.after(0, self.updater_progress.set, downloaded / total)
                # Se guarda en memoria, no en un archivo temporal: al ser
                # texto plano no hay ningún problema de bloqueo/antivirus
                # como había con el .exe, así que no hace falta la cautela
                # de antes — se escribe directo al aplicar el reinicio.
                self.new_app_content = b"".join(chunks)
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
        if not self.new_app_content:
            return
        try:
            # Respaldo antes de sobreescribir: esta versión actual llegó a
            # correr lo suficiente como para descargar y aplicar un update,
            # así que es un candidato razonable de "última versión que
            # anduvo bien" si la nueva resulta estar rota. El launcher cae
            # acá automáticamente si la nueva falla al arrancar 3 veces
            # seguidas.
            if os.path.exists(APP_PY_PATH):
                with open(APP_PY_PATH, "rb") as f:
                    current_content = f.read()
                with open(APP_OLD_PY_PATH, "wb") as f:
                    f.write(current_content)

            # Sobreescribir el .py en disco no genera ningún conflicto: este
            # proceso ya lo tiene compilado en memoria (bytecode), nada lo
            # sigue leyendo del archivo — a diferencia de un .exe en
            # ejecución, que Windows mantiene bloqueado mientras corre.
            with open(APP_PY_PATH, "wb") as f:
                f.write(self.new_app_content)
        except Exception:
            self.lbl_updater_status.configure(text="No se pudo guardar la actualización.", text_color=COLOR_ERROR)
            return

        try:
            # _MEIPASS2 es una variable interna que el bootloader de
            # PyInstaller usa para saber dónde extrajo sus archivos —
            # igual la sacamos por las dudas, aunque el problema real
            # resultó ser más de fondo (ver abajo).
            env = os.environ.copy()
            env.pop("_MEIPASS2", None)

            if getattr(sys, "frozen", False):
                # No lanzamos LAUNCHER_PATH directo con Popen: eso lo deja
                # como hijo directo de ESTE proceso, que es el mismo
                # bootloader de PyInstaller a punto de cerrarse — y ahí
                # compiten por handles/recursos del runtime empaquetado
                # (de ahí el error "Failed to remove temporary directory"
                # y las conexiones rotas pese a que _MEIPASS2 ya estaba
                # limpio). Pasarlo por `cmd /c start` lo desacopla del
                # todo: nace como hijo de cmd.exe, un proceso neutral que
                # no tiene nada que ver con nuestro bootloader.
                subprocess.Popen(
                    ["cmd", "/c", "start", "", LAUNCHER_PATH],
                    env=env, creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                subprocess.Popen([sys.executable, LAUNCHER_PATH], env=env)
        except Exception:
            self.lbl_updater_status.configure(text="No se pudo reiniciar. Abrí el updater de nuevo a mano.", text_color=COLOR_ERROR)
            return

        # Pequeño margen antes de cerrarnos: nos aseguramos de que el
        # comando `start` ya haya quedado registrado en el sistema antes
        # de que este proceso empiece a desaparecer.
        self.after(200, self.destroy)


# ---------------------------------------------------------
# Instancia única: evita que se abran dos updaters al mismo tiempo (por
# ejemplo, doble click accidental). Usa un archivo de lock con el PID en la
# carpeta temporal; si el proceso dueño del lock ya no existe (crash previo
# sin limpiar), lo pisa y sigue en vez de quedar bloqueado para siempre.
# ---------------------------------------------------------
def _lock_path():
    return os.path.join(tempfile.gettempdir(), "re4mp_updater.lock")


def _pid_is_running(pid: int) -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return str(pid) in result.stdout
    except Exception:
        return False


def acquire_single_instance_lock() -> bool:
    path = _lock_path()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                old_pid = int(f.read().strip())
            if _pid_is_running(old_pid):
                return False
        except Exception:
            pass  # lock file corrupto o ilegible: lo pisamos y seguimos
    with open(path, "w") as f:
        f.write(str(os.getpid()))
    return True


def release_single_instance_lock():
    path = _lock_path()
    try:
        with open(path, "r") as f:
            if int(f.read().strip()) == os.getpid():
                os.remove(path)
    except Exception:
        pass


if __name__ == "__main__":
    if not acquire_single_instance_lock():
        _root = tk.Tk()
        _root.withdraw()
        messagebox.showinfo("RE4MP Updater", "Ya hay una instancia del updater abierta.")
        _root.destroy()
        sys.exit(0)

    try:
        app = RE4ModUpdater()
        app.mainloop()
    finally:
        release_single_instance_lock()