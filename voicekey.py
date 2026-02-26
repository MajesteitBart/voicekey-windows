"""
VoiceKey — Push-to-Talk Voice Keyboard (Voxtral)
=================================================
Hold your hotkey, speak, release → text is typed anywhere.

Requirements: sounddevice numpy requests pynput keyboard pyperclip pystray Pillow
"""

import io
import json
import os
import struct
import sys
import threading
import time
import wave

# ---------------------------------------------------------------------------
# Optional-import guards
# ---------------------------------------------------------------------------
try:
    import numpy as np
except ImportError:
    sys.exit("Missing: numpy  →  pip install numpy")

try:
    import sounddevice as sd
except ImportError:
    sys.exit("Missing: sounddevice  →  pip install sounddevice")

try:
    import requests
except ImportError:
    sys.exit("Missing: requests  →  pip install requests")

try:
    from pynput import keyboard as pynput_keyboard
except ImportError:
    sys.exit("Missing: pynput  →  pip install pynput")

try:
    import keyboard as kb
except ImportError:
    sys.exit("Missing: keyboard  →  pip install keyboard")

try:
    import pyperclip
except ImportError:
    sys.exit("Missing: pyperclip  →  pip install pyperclip")

try:
    import pystray
    from pystray import MenuItem, Menu
except ImportError:
    sys.exit("Missing: pystray  →  pip install pystray")

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Missing: Pillow  →  pip install Pillow")

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:
    sys.exit("Missing: tkinter (usually bundled with Python)")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
APP_NAME = "VoiceKey"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "api_key": "",
    "endpoint": "https://api.mistral.ai/v1/audio/transcriptions",
    "model": "voxtral-mini-latest",
    "hotkey": "right alt",
    "language": "auto",
    "paste_mode": True,
    "sample_rate": 16000,
}

HOTKEY_LIST = [
    "right alt",
    "right ctrl",
    "right shift",
    "f13",
    "f14",
    "f15",
    "pause",
    "scroll lock",
]

LANGUAGE_LIST = ["auto", "en", "nl", "de", "fr", "es", "it", "pt", "pl", "ja", "zh"]

# Maps human-readable hotkey names → pynput Key attribute names
PYNPUT_KEY_MAP = {
    "right alt":    "alt_r",
    "right ctrl":   "ctrl_r",
    "right shift":  "shift_r",
    "f13":          "f13",
    "f14":          "f14",
    "f15":          "f15",
    "pause":        "pause",
    "scroll lock":  "scroll_lock",
}

# Icon colours per state
ICON_COLORS = {
    "idle":       (80, 80, 80, 255),
    "recording":  (220, 40, 40, 255),
    "processing": (220, 140, 0, 255),
}

# Minimum audio size to bother sending (< 0.25 s at 16 kHz / int16)
MIN_AUDIO_BYTES = 8000

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load config from disk, falling back to defaults for missing keys."""
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                on_disk = json.load(fh)
            cfg.update(on_disk)
        except Exception:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    """Persist config to disk."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)


# ---------------------------------------------------------------------------
# Windows registry helpers (startup)
# ---------------------------------------------------------------------------

def _get_winreg():
    """Return winreg module or None on non-Windows."""
    try:
        import winreg
        return winreg
    except ImportError:
        return None


def set_startup(enable: bool) -> None:
    """Add/remove VoiceKey from Windows startup registry key."""
    winreg = _get_winreg()
    if winreg is None:
        return
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    exe = sys.executable if not getattr(sys, "frozen", False) else sys.executable
    script = os.path.abspath(__file__) if not getattr(sys, "frozen", False) else ""
    value = f'"{exe}" "{script}"' if script else f'"{exe}"'
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as reg_key:
            if enable:
                winreg.SetValueEx(reg_key, APP_NAME, 0, winreg.REG_SZ, value)
            else:
                try:
                    winreg.DeleteValue(reg_key, APP_NAME)
                except FileNotFoundError:
                    pass
    except Exception:
        pass


def is_startup_enabled() -> bool:
    """Return True if VoiceKey is in the Windows startup registry."""
    winreg = _get_winreg()
    if winreg is None:
        return False
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as reg_key:
            winreg.QueryValueEx(reg_key, APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Icon generation
# ---------------------------------------------------------------------------

def make_icon(state: str = "idle") -> Image.Image:
    """Generate a 64×64 RGBA PIL image: coloured circle with 'V'."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = ICON_COLORS.get(state, ICON_COLORS["idle"])
    # Draw filled circle
    margin = 4
    draw.ellipse([margin, margin, size - margin, size - margin], fill=color)
    # Draw "V" letter in white
    font = None
    try:
        # Try to load a reasonable font; fall back to default
        font = ImageFont.truetype("arial.ttf", 36)
    except Exception:
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
    text = "V"
    if font:
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except AttributeError:
            # Older Pillow
            tw, th = draw.textsize(text, font=font)  # type: ignore[attr-defined]
        tx = (size - tw) // 2
        ty = (size - th) // 2 - 2
        draw.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)
    return img


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def record_to_wav(audio_frames: list, sample_rate: int) -> bytes:
    """Convert a list of numpy int16 chunks into WAV bytes (in-memory)."""
    if not audio_frames:
        return b""
    pcm = np.concatenate(audio_frames, axis=0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

def transcribe(wav_bytes: bytes, cfg: dict) -> str:
    """POST WAV audio to Voxtral API, return transcribed text."""
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    data = {"model": cfg["model"]}
    if cfg.get("language") and cfg["language"] != "auto":
        data["language"] = cfg["language"]
    files = {"file": ("audio.wav", io.BytesIO(wav_bytes), "audio/wav")}
    resp = requests.post(
        cfg["endpoint"],
        headers=headers,
        data=data,
        files=files,
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()
    return result.get("text", "").strip()


# ---------------------------------------------------------------------------
# Text output
# ---------------------------------------------------------------------------

def type_text(text: str, paste_mode: bool) -> None:
    """Type or paste text at the current cursor position."""
    if not text:
        return
    if paste_mode:
        pyperclip.copy(text)
        # Small delay so clipboard is ready
        time.sleep(0.05)
        kb.send("ctrl+v")
    else:
        kb.write(text, delay=0.005)


# ---------------------------------------------------------------------------
# Settings window (tkinter, dark theme)
# ---------------------------------------------------------------------------

class SettingsWindow:
    """Dark-themed tkinter settings dialog."""

    BG = "#1e1e1e"
    FG = "#d4d4d4"
    ENTRY_BG = "#2d2d2d"
    ACCENT = "#0e639c"
    BTN_BG = "#3a3a3a"

    def __init__(self, app: "VoiceKeyApp"):
        self.app = app
        self._win: tk.Tk | None = None

    def open(self) -> None:
        if self._win is not None:
            try:
                self._win.lift()
                self._win.focus_force()
                return
            except tk.TclError:
                self._win = None

        cfg = self.app.cfg

        win = tk.Tk()
        self._win = win
        win.title(f"{APP_NAME} Settings")
        win.resizable(False, False)
        win.configure(bg=self.BG)
        win.protocol("WM_DELETE_WINDOW", self._on_close)

        pad = {"padx": 12, "pady": 6}

        def label(text, row):
            tk.Label(win, text=text, bg=self.BG, fg=self.FG, anchor="w").grid(
                row=row, column=0, sticky="w", **pad
            )

        def entry(row, show=None):
            e = tk.Entry(win, bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG,
                         relief="flat", width=42, show=show or "")
            e.grid(row=row, column=1, sticky="ew", **pad)
            return e

        def combo(values, row):
            var = tk.StringVar(win)
            c = ttk.Combobox(win, textvariable=var, values=values, state="readonly",
                             width=40)
            c.grid(row=row, column=1, sticky="ew", **pad)
            return var, c

        # Style combobox to match dark theme (best-effort)
        style = ttk.Style(win)
        style.theme_use("clam")
        style.configure("TCombobox",
                        fieldbackground=self.ENTRY_BG,
                        background=self.BTN_BG,
                        foreground=self.FG,
                        selectbackground=self.ACCENT,
                        selectforeground=self.FG)

        row = 0

        # API Key
        label("API Key:", row)
        e_apikey = entry(row, show="•")
        e_apikey.insert(0, cfg.get("api_key", ""))
        row += 1

        # Endpoint
        label("Endpoint:", row)
        e_endpoint = entry(row)
        e_endpoint.insert(0, cfg.get("endpoint", DEFAULT_CONFIG["endpoint"]))
        row += 1

        # Model
        label("Model:", row)
        e_model = entry(row)
        e_model.insert(0, cfg.get("model", DEFAULT_CONFIG["model"]))
        row += 1

        # Hotkey
        label("Hotkey:", row)
        v_hotkey, c_hotkey = combo(HOTKEY_LIST, row)
        v_hotkey.set(cfg.get("hotkey", DEFAULT_CONFIG["hotkey"]))
        row += 1

        # Language
        label("Language:", row)
        v_lang, c_lang = combo(LANGUAGE_LIST, row)
        v_lang.set(cfg.get("language", DEFAULT_CONFIG["language"]))
        row += 1

        # Paste mode
        v_paste = tk.BooleanVar(win, value=cfg.get("paste_mode", True))
        cb_paste = tk.Checkbutton(win, text="Paste mode (faster)",
                                  variable=v_paste,
                                  bg=self.BG, fg=self.FG,
                                  selectcolor=self.ENTRY_BG,
                                  activebackground=self.BG, activeforeground=self.FG)
        cb_paste.grid(row=row, column=1, sticky="w", **pad)
        row += 1

        # Start with Windows
        v_startup = tk.BooleanVar(win, value=is_startup_enabled())
        cb_startup = tk.Checkbutton(win, text="Start with Windows",
                                    variable=v_startup,
                                    bg=self.BG, fg=self.FG,
                                    selectcolor=self.ENTRY_BG,
                                    activebackground=self.BG, activeforeground=self.FG)
        cb_startup.grid(row=row, column=1, sticky="w", **pad)
        row += 1

        # Buttons
        btn_frame = tk.Frame(win, bg=self.BG)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=12)

        def save():
            new_cfg = dict(cfg)
            new_cfg["api_key"] = e_apikey.get().strip()
            new_cfg["endpoint"] = e_endpoint.get().strip()
            new_cfg["model"] = e_model.get().strip()
            new_cfg["hotkey"] = v_hotkey.get()
            new_cfg["language"] = v_lang.get()
            new_cfg["paste_mode"] = v_paste.get()
            save_config(new_cfg)
            self.app.cfg = new_cfg
            set_startup(v_startup.get())
            # Restart hotkey listener with new hotkey
            self.app.restart_listener()
            self._on_close()

        tk.Button(btn_frame, text="Save", command=save,
                  bg=self.ACCENT, fg="white", relief="flat",
                  padx=18, pady=4).pack(side="left", padx=6)

        tk.Button(btn_frame, text="Cancel", command=self._on_close,
                  bg=self.BTN_BG, fg=self.FG, relief="flat",
                  padx=18, pady=4).pack(side="left", padx=6)

        win.columnconfigure(1, weight=1)
        win.eval("tk::PlaceWindow . center")
        win.mainloop()
        self._win = None

    def _on_close(self):
        if self._win:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None


# ---------------------------------------------------------------------------
# Core application
# ---------------------------------------------------------------------------

class VoiceKeyApp:
    """Main application: manages tray icon, hotkey listener, recording."""

    def __init__(self):
        self.cfg = load_config()
        # Auto-register for Windows startup on first run (user can disable in Settings)
        if not is_startup_enabled():
            set_startup(True)
        self._state = "idle"
        self._recording = False
        self._down = False          # debounce flag for key-repeat
        self._audio_frames: list = []
        self._stream: sd.InputStream | None = None
        self._tray: pystray.Icon | None = None
        self._listener: pynput_keyboard.Listener | None = None
        self._settings = SettingsWindow(self)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # State / icon management
    # ------------------------------------------------------------------

    def _set_state(self, state: str) -> None:
        """Update internal state and refresh tray icon + tooltip."""
        self._state = state
        labels = {
            "idle":       f"{APP_NAME} — Idle",
            "recording":  f"{APP_NAME} — Recording...",
            "processing": f"{APP_NAME} — Processing...",
        }
        tooltip = labels.get(state, APP_NAME)
        if self._tray:
            self._tray.icon = make_icon(state)
            self._tray.title = tooltip

    # ------------------------------------------------------------------
    # Hotkey listener
    # ------------------------------------------------------------------

    def _resolve_pynput_key(self, hotkey_name: str):
        """Return the pynput Key object for the given hotkey name."""
        attr = PYNPUT_KEY_MAP.get(hotkey_name.lower())
        if attr:
            return getattr(pynput_keyboard.Key, attr, None)
        return None

    def _on_press(self, key) -> None:
        """Called by pynput on any key press."""
        if self._down:
            return  # debounce repeated key-down events
        target = self._resolve_pynput_key(self.cfg.get("hotkey", "right alt"))
        if target is None:
            return
        if key == target:
            self._down = True
            self._start_recording()

    def _on_release(self, key) -> None:
        """Called by pynput on any key release."""
        target = self._resolve_pynput_key(self.cfg.get("hotkey", "right alt"))
        if target is None:
            return
        if key == target and self._down:
            self._down = False
            self._stop_recording()

    def start_listener(self) -> None:
        """Start the pynput keyboard listener in a daemon thread."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
        self._listener = pynput_keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def restart_listener(self) -> None:
        """Stop and restart the listener (called after hotkey config change)."""
        self._down = False
        self.start_listener()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def _audio_callback(self, indata: np.ndarray, frames: int,
                        time_info, status) -> None:
        """sounddevice callback — appends audio frames to buffer."""
        if self._recording:
            self._audio_frames.append(indata.copy())

    def _start_recording(self) -> None:
        with self._lock:
            if self._recording:
                return
            self._recording = True
            self._audio_frames = []
        self._set_state("recording")
        try:
            sr = int(self.cfg.get("sample_rate", 16000))
            self._stream = sd.InputStream(
                samplerate=sr,
                channels=1,
                dtype="int16",
                callback=self._audio_callback,
            )
            self._stream.start()
        except Exception as exc:
            self._recording = False
            self._set_state("idle")
            self._notify_error(f"Microphone error: {exc}")

    def _stop_recording(self) -> None:
        with self._lock:
            if not self._recording:
                return
            self._recording = False

        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        frames = list(self._audio_frames)
        self._audio_frames = []

        # Run transcription in a background daemon thread
        t = threading.Thread(target=self._transcribe_and_type, args=(frames,), daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Transcription & typing
    # ------------------------------------------------------------------

    def _transcribe_and_type(self, frames: list) -> None:
        """Background: convert frames → WAV → Voxtral → type text."""
        self._set_state("processing")
        try:
            sr = int(self.cfg.get("sample_rate", 16000))
            wav_bytes = record_to_wav(frames, sr)

            if len(wav_bytes) < MIN_AUDIO_BYTES:
                # Too short — ignore silently
                self._set_state("idle")
                return

            if not self.cfg.get("api_key"):
                self._notify_error("No API key set. Open Settings to configure.")
                self._set_state("idle")
                return

            text = transcribe(wav_bytes, self.cfg)
            if text:
                # Small delay so user has time to focus the target window
                time.sleep(0.1)
                type_text(text, self.cfg.get("paste_mode", True))
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else "?"
            self._notify_error(f"API error {code}: {exc.response.text[:120] if exc.response else exc}")
        except requests.ConnectionError:
            self._notify_error("Network error — check internet connection.")
        except Exception as exc:
            self._notify_error(f"Transcription failed: {exc}")
        finally:
            self._set_state("idle")

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def _notify_error(self, message: str) -> None:
        """Show a tray notification."""
        if self._tray:
            try:
                self._tray.notify(message, title=f"{APP_NAME} — Error")
            except Exception:
                pass  # notify not supported on all platforms

    # ------------------------------------------------------------------
    # Tray menu callbacks
    # ------------------------------------------------------------------

    def _open_settings(self, icon=None, item=None) -> None:
        t = threading.Thread(target=self._settings.open, daemon=True)
        t.start()

    def _quit(self, icon=None, item=None) -> None:
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
        if self._tray:
            self._tray.stop()
        os._exit(0)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Build tray icon and start the application."""
        # Prompt for API key on first run
        if not self.cfg.get("api_key"):
            threading.Thread(target=self._first_run_prompt, daemon=True).start()

        self.start_listener()

        icon_image = make_icon("idle")
        menu = Menu(
            MenuItem("Settings", self._open_settings),
            Menu.SEPARATOR,
            MenuItem("Quit", self._quit),
        )
        self._tray = pystray.Icon(
            APP_NAME,
            icon=icon_image,
            title=f"{APP_NAME} — Idle",
            menu=menu,
        )
        self._tray.run()

    def _first_run_prompt(self) -> None:
        """Show a reminder to configure the API key."""
        time.sleep(2)
        self._notify_error("Welcome! Please open Settings and enter your Mistral API key.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = VoiceKeyApp()
    app.run()
