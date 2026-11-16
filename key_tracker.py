import json
import time
import tkinter as tk
from pynput import keyboard

SETTINGS_FILE = "settings.json"

# Загружаем время из настроек (по умолчанию 60 секунд)
try:
    seconds = json.load(open(SETTINGS_FILE))["seconds"]
except Exception:
    seconds = 60

counts = {}        # клавиша -> количество нажатий (после перезапуска пусто)
end_time = 0       # когда закончится подсчёт


def on_press(key):
    if time.time() < end_time:
        name = key.char if hasattr(key, "char") and key.char else str(key).replace("Key.", "")
        counts[name] = counts.get(name, 0) + 1


def start():
    global end_time, seconds
    seconds = int(entry.get())
    json.dump({"seconds": seconds}, open(SETTINGS_FILE, "w"))  # сохраняем настройку
    counts.clear()
    end_time = time.time() + seconds


def update():
    left = max(0, int(end_time - time.time()))
    timer.config(text=f"Осталось: {left} сек")
    text.delete("1.0", "end")
    for key, n in sorted(dict(counts).items(), key=lambda x: -x[1]):
        text.insert("end", f"{key}: {n}\n")
    root.after(300, update)


root = tk.Tk()
root.title("Счётчик клавиш")

tk.Label(root, text="Время (сек):").pack()
entry = tk.Entry(root)
entry.insert(0, str(seconds))
entry.pack()
tk.Button(root, text="Старт", command=start).pack()
timer = tk.Label(root, text="Осталось: 0 сек")
timer.pack()
text = tk.Text(root, width=30, height=20)
text.pack()

keyboard.Listener(on_press=on_press, daemon=True).start()
update()
root.mainloop()
