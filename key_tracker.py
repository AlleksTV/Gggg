#!/usr/bin/env python3
"""
Трекер нажатий клавиш с графическим интерфейсом (tkinter + pynput).

- Считает, сколько раз была нажата каждая клавиша за заданный период.
- Длительность периода задаётся в настройках (окно «Настройки»)
  и сохраняется в файл settings.json рядом с программой.
- Счётчики хранятся только в памяти: после перезапуска программы
  они всегда начинаются с нуля.
"""

import json
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

try:
    from pynput import keyboard
except ImportError:  # pragma: no cover
    raise SystemExit(
        "Не найден модуль pynput. Установите его командой:\n"
        "    pip install pynput"
    )

SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "settings.json"
)

DEFAULT_SETTINGS = {
    "duration_value": 60,        # длительность периода
    "duration_unit": "секунды",  # секунды / минуты / часы
    "auto_restart": False,       # автоматически начинать новый период
    "ignore_autorepeat": True,   # не считать автоповтор при удержании клавиши
}

UNITS = {"секунды": 1, "минуты": 60, "часы": 3600}

KEY_NAMES = {
    "space": "Пробел", "enter": "Enter", "backspace": "Backspace",
    "tab": "Tab", "esc": "Esc", "shift": "Shift", "shift_r": "Shift (правый)",
    "ctrl_l": "Ctrl (левый)", "ctrl_r": "Ctrl (правый)", "ctrl": "Ctrl",
    "alt_l": "Alt (левый)", "alt_r": "Alt (правый)", "alt": "Alt",
    "alt_gr": "AltGr", "cmd": "Win/Cmd", "cmd_r": "Win/Cmd (правый)",
    "caps_lock": "Caps Lock", "delete": "Delete", "insert": "Insert",
    "home": "Home", "end": "End", "page_up": "Page Up",
    "page_down": "Page Down", "up": "↑", "down": "↓", "left": "←",
    "right": "→", "print_screen": "Print Screen", "num_lock": "Num Lock",
    "scroll_lock": "Scroll Lock", "pause": "Pause", "menu": "Menu",
}


# --------------------------------------------------------------------------
# Настройки
# --------------------------------------------------------------------------
def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in DEFAULT_SETTINGS:
            if key in data:
                settings[key] = data[key]
    except (OSError, ValueError):
        pass
    if settings["duration_unit"] not in UNITS:
        settings["duration_unit"] = DEFAULT_SETTINGS["duration_unit"]
    try:
        settings["duration_value"] = max(1, int(settings["duration_value"]))
    except (TypeError, ValueError):
        settings["duration_value"] = DEFAULT_SETTINGS["duration_value"]
    return settings


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)


def duration_seconds(settings):
    return settings["duration_value"] * UNITS[settings["duration_unit"]]


# --------------------------------------------------------------------------
# Счётчик нажатий (работает в потоке pynput)
# --------------------------------------------------------------------------
class KeyCounter:
    def __init__(self):
        self._lock = threading.Lock()
        self.counts = {}
        self._pressed = set()
        self.active = False
        self.ignore_autorepeat = True
        self._listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
        self._listener.daemon = True
        self._listener.start()

    @staticmethod
    def key_name(key):
        if isinstance(key, keyboard.KeyCode):
            if key.char is not None and key.char.isprintable():
                return key.char.upper() if key.char.isalpha() else key.char
            if key.vk is not None:
                # Цифры/буквы при зажатом Ctrl приходят как управляющие символы
                if 48 <= key.vk <= 57 or 65 <= key.vk <= 90:
                    return chr(key.vk)
                return f"vk_{key.vk}"
            return "?"
        name = getattr(key, "name", str(key))
        return KEY_NAMES.get(name, name.replace("_", " ").title())

    def _on_press(self, key):
        name = self.key_name(key)
        with self._lock:
            if self.ignore_autorepeat and name in self._pressed:
                return
            self._pressed.add(name)
            if self.active:
                self.counts[name] = self.counts.get(name, 0) + 1

    def _on_release(self, key):
        with self._lock:
            self._pressed.discard(self.key_name(key))

    def snapshot(self):
        with self._lock:
            return dict(self.counts)

    def reset(self):
        with self._lock:
            self.counts.clear()

    def stop(self):
        self._listener.stop()


# --------------------------------------------------------------------------
# Окно настроек
# --------------------------------------------------------------------------
class SettingsDialog(tk.Toplevel):
    def __init__(self, master, settings, on_save):
        super().__init__(master)
        self.title("Настройки")
        self.resizable(False, False)
        self.transient(master)
        self.on_save = on_save

        frm = ttk.Frame(self, padding=15)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Длительность периода подсчёта:").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        self.value_var = tk.StringVar(value=str(settings["duration_value"]))
        ttk.Spinbox(
            frm, from_=1, to=100000, textvariable=self.value_var, width=10
        ).grid(row=1, column=0, sticky="w", pady=5)
        self.unit_var = tk.StringVar(value=settings["duration_unit"])
        ttk.Combobox(
            frm, textvariable=self.unit_var, values=list(UNITS),
            state="readonly", width=10,
        ).grid(row=1, column=1, sticky="w", padx=5, pady=5)

        self.auto_var = tk.BooleanVar(value=settings["auto_restart"])
        ttk.Checkbutton(
            frm, text="По окончании автоматически начинать новый период",
            variable=self.auto_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=2)

        self.repeat_var = tk.BooleanVar(value=settings["ignore_autorepeat"])
        ttk.Checkbutton(
            frm, text="Не считать автоповтор при удержании клавиши",
            variable=self.repeat_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=2)

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Сохранить", command=self._save).pack(side="left", padx=5)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="left")

        self.grab_set()

    def _save(self):
        try:
            value = int(self.value_var.get())
            if value < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Ошибка", "Длительность должна быть целым числом больше 0.",
                parent=self,
            )
            return
        self.on_save({
            "duration_value": value,
            "duration_unit": self.unit_var.get(),
            "auto_restart": self.auto_var.get(),
            "ignore_autorepeat": self.repeat_var.get(),
        })
        self.destroy()


# --------------------------------------------------------------------------
# Главное окно
# --------------------------------------------------------------------------
class TrackerApp(tk.Tk):
    REFRESH_MS = 200

    def __init__(self):
        super().__init__()
        self.title("Трекер нажатий клавиш")
        self.geometry("480x560")
        self.minsize(380, 400)

        self.settings = load_settings()
        self.counter = KeyCounter()
        self.counter.ignore_autorepeat = self.settings["ignore_autorepeat"]

        self.end_time = None   # время окончания текущего периода
        self.finished = False
        self._last_counts = None

        self._build_ui()
        self._update_period_label()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(self.REFRESH_MS, self._tick)

    # ---------------- интерфейс ----------------
    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        self.period_label = ttk.Label(top, font=("TkDefaultFont", 10))
        self.period_label.pack(anchor="w")

        self.timer_label = ttk.Label(
            top, text="Остаток: —", font=("TkDefaultFont", 16, "bold")
        )
        self.timer_label.pack(anchor="w", pady=(5, 0))

        self.status_label = ttk.Label(top, text="Статус: остановлено")
        self.status_label.pack(anchor="w")

        self.total_label = ttk.Label(top, text="Всего нажатий: 0")
        self.total_label.pack(anchor="w")

        btns = ttk.Frame(self, padding=(10, 0))
        btns.pack(fill="x")
        self.start_btn = ttk.Button(btns, text="▶ Старт", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(btns, text="■ Стоп", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=5)
        ttk.Button(btns, text="Сбросить", command=self.reset).pack(side="left")
        ttk.Button(btns, text="⚙ Настройки", command=self.open_settings).pack(side="right")

        table_frame = ttk.Frame(self, padding=10)
        table_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            table_frame, columns=("key", "count"), show="headings"
        )
        self.tree.heading("key", text="Клавиша")
        self.tree.heading("count", text="Нажатий")
        self.tree.column("key", width=250, anchor="w")
        self.tree.column("count", width=100, anchor="center")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _update_period_label(self):
        s = self.settings
        text = f"Период подсчёта: {s['duration_value']} {s['duration_unit']}"
        if s["auto_restart"]:
            text += " (с автоповтором)"
        self.period_label.config(text=text)

    # ---------------- управление ----------------
    def start(self):
        self.counter.reset()
        self.end_time = time.monotonic() + duration_seconds(self.settings)
        self.finished = False
        self.counter.active = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_label.config(text="Статус: идёт подсчёт")

    def stop(self, finished=False):
        self.counter.active = False
        self.end_time = None
        self.finished = finished
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_label.config(
            text="Статус: период завершён" if finished else "Статус: остановлено"
        )
        self.timer_label.config(text="Остаток: 00:00:00" if finished else "Остаток: —")

    def reset(self):
        self.counter.reset()
        if self.counter.active:
            self.end_time = time.monotonic() + duration_seconds(self.settings)

    def open_settings(self):
        SettingsDialog(self, self.settings, self._apply_settings)

    def _apply_settings(self, new_settings):
        self.settings = new_settings
        self.counter.ignore_autorepeat = new_settings["ignore_autorepeat"]
        try:
            save_settings(new_settings)
        except OSError as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки:\n{e}")
        self._update_period_label()

    # ---------------- обновление ----------------
    def _tick(self):
        if self.end_time is not None:
            remaining = self.end_time - time.monotonic()
            if remaining <= 0:
                if self.settings["auto_restart"]:
                    total = sum(self.counter.snapshot().values())
                    self.start()
                    self.status_label.config(
                        text=f"Статус: идёт подсчёт (прошлый период: {total} нажатий)"
                    )
                else:
                    self.stop(finished=True)
            else:
                secs = int(remaining + 0.999)
                h, rem = divmod(secs, 3600)
                m, s = divmod(rem, 60)
                self.timer_label.config(text=f"Остаток: {h:02d}:{m:02d}:{s:02d}")
        self._refresh_table()
        self.after(self.REFRESH_MS, self._tick)

    def _refresh_table(self):
        counts = self.counter.snapshot()
        if counts == self._last_counts:
            return
        self._last_counts = counts
        rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        self.tree.delete(*self.tree.get_children())
        for name, count in rows:
            self.tree.insert("", "end", values=(name, count))
        self.total_label.config(text=f"Всего нажатий: {sum(counts.values())}")

    def _on_close(self):
        self.counter.stop()
        self.destroy()


if __name__ == "__main__":
    TrackerApp().mainloop()
