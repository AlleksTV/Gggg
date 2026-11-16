import time
import tkinter as tk

start = None   # время запуска (None — остановлен)
passed = 0     # накопленное время


def toggle():
    global start, passed
    if start is None:
        start = time.time()
    else:
        passed += time.time() - start
        start = None


def reset():
    global start, passed
    start, passed = None, 0


def update():
    t = passed + (time.time() - start if start else 0)
    label.config(text=f"{int(t // 60):02d}:{t % 60:05.2f}")
    root.after(50, update)


root = tk.Tk()
root.title("Секундомер")
label = tk.Label(root, font=("Arial", 40))
label.pack()
tk.Button(root, text="Старт / Стоп", command=toggle).pack(side="left")
tk.Button(root, text="Сброс", command=reset).pack(side="right")
update()
root.mainloop()
