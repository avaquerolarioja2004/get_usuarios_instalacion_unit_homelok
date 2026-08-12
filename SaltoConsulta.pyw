import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from consulta_salto import ejecutar_consulta

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "consulta_gui_config.json"


def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    except Exception:
        return {}


def save_config(data):
    try:
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Consultas SALTO Nebula")
        self.root.geometry("820x700")
        self.root.minsize(720, 600)
        self.config = load_config()
        self.queue = queue.Queue()
        self.worker = None
        self.build_ui()
        self.root.after(80, self.poll)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)
        pad = {"padx": 8, "pady": 4}

        creds = ttk.LabelFrame(main, text="Credenciales SALTO Nebula")
        creds.pack(fill="x", **pad)
        ttk.Label(creds, text="Token:").grid(row=0, column=0, sticky="w", **pad)
        self.token = tk.StringVar()
        self.token_entry = ttk.Entry(creds, textvariable=self.token, show="•", width=65)
        self.token_entry.grid(row=0, column=1, sticky="we", **pad)
        self.show = tk.BooleanVar()
        ttk.Checkbutton(creds, text="Mostrar", variable=self.show, command=self.toggle_token).grid(row=0, column=2, sticky="w", **pad)
        creds.columnconfigure(1, weight=1)

        files = ttk.LabelFrame(main, text="Datos de entrada")
        files.pack(fill="x", **pad)
        self.csv = tk.StringVar(value=self.config.get("csv_instalaciones", ""))
        ttk.Label(files, text="instalaciones.csv:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(files, textvariable=self.csv).grid(row=0, column=1, sticky="we", **pad)
        ttk.Button(files, text="Examinar...", command=self.browse_csv).grid(row=0, column=2, **pad)
        files.columnconfigure(1, weight=1)

        mode = ttk.LabelFrame(main, text="Selecciona qué quieres hacer")
        mode.pack(fill="x", **pad)
        self.mode = tk.StringVar(value=self.config.get("modo", "instalacion"))
        ttk.Radiobutton(mode, text="Usuarios por instalación", variable=self.mode, value="instalacion").pack(anchor="w", padx=12, pady=(8, 2))
        ttk.Label(mode, text="Consulta directamente los usuarios de cada instalación.").pack(anchor="w", padx=32, pady=(0, 6))
        ttk.Radiobutton(mode, text="Usuarios por units", variable=self.mode, value="units").pack(anchor="w", padx=12, pady=2)
        ttk.Label(mode, text="Consulta las units y después los usuarios de cada unit, incluyendo los datos de la unit.").pack(anchor="w", padx=32, pady=(0, 8))

        output = ttk.LabelFrame(main, text="Salida")
        output.pack(fill="x", **pad)
        self.out = tk.StringVar(value=self.config.get("salida", str(BASE_DIR / "salidas")))
        ttk.Label(output, text="Guardar CSV en:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(output, textvariable=self.out).grid(row=0, column=1, sticky="we", **pad)
        ttk.Button(output, text="Examinar...", command=self.browse_output).grid(row=0, column=2, **pad)
        output.columnconfigure(1, weight=1)

        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=8)
        self.start = ttk.Button(actions, text="▶ Ejecutar consulta", command=self.start_process)
        self.start.pack(side="left", padx=5)
        ttk.Button(actions, text="🗑 Limpiar log", command=self.clear_log).pack(side="left", padx=5)
        self.progress = ttk.Progressbar(actions, mode="indeterminate")
        self.progress.pack(side="right", fill="x", expand=True, padx=10)

        frame = ttk.LabelFrame(main, text="Log")
        frame.pack(fill="both", expand=True, **pad)
        self.log = scrolledtext.ScrolledText(frame, wrap=tk.WORD, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=5, pady=5)

    def toggle_token(self):
        self.token_entry.configure(show="" if self.show.get() else "•")

    def browse_csv(self):
        p = filedialog.askopenfilename(title="Seleccionar instalaciones.csv", filetypes=[("CSV", "*.csv"), ("Todos", "*.*")])
        if p:
            self.csv.set(p)

    def browse_output(self):
        p = filedialog.askdirectory(title="Seleccionar carpeta de salida")
        if p:
            self.out.set(p)

    def write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def start_process(self):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("Proceso en curso", "Ya hay una consulta ejecutándose.")
            return
        token = self.token.get().strip()
        csv_path = self.csv.get().strip()
        out = self.out.get().strip()
        if not token:
            messagebox.showerror("Falta el token", "Introduce el token de SALTO Nebula.")
            return
        if not csv_path or not Path(csv_path).is_file():
            messagebox.showerror("CSV no encontrado", "Selecciona un instalaciones.csv válido.")
            return
        if not out:
            messagebox.showerror("Falta la salida", "Selecciona una carpeta de salida.")
            return
        self.config.update({"csv_instalaciones": csv_path, "salida": out, "modo": self.mode.get()})
        save_config(self.config)
        self.clear_log()
        self.write_log("Iniciando consulta...\n")
        self.start.configure(state="disabled")
        self.progress.start(10)
        self.worker = threading.Thread(target=self.worker_run, args=(self.mode.get(), csv_path, token, out), daemon=True)
        self.worker.start()

    def worker_run(self, mode, csv_path, token, out):
        try:
            result = ejecutar_consulta(mode, csv_path, token, out, lambda msg: self.queue.put(("log", msg + "\n")))
            self.queue.put(("done", result))
        except Exception as exc:
            self.queue.put(("error", str(exc)))

    def poll(self):
        try:
            while True:
                kind, data = self.queue.get_nowait()
                if kind == "log":
                    self.write_log(data)
                elif kind == "done":
                    self.progress.stop()
                    self.start.configure(state="normal")
                    if data["errores"]:
                        messagebox.showwarning("Proceso terminado", f"Consulta terminada con {data['errores']} error(es).\n\nUsuarios: {data['usuarios']}\nSalida:\n{data['salida']}")
                    else:
                        messagebox.showinfo("Proceso terminado", f"Consulta terminada correctamente.\n\nUsuarios: {data['usuarios']}\nSalida:\n{data['salida']}")
                elif kind == "error":
                    self.progress.stop()
                    self.start.configure(state="normal")
                    self.write_log("\n[ERROR FATAL] " + data + "\n")
                    messagebox.showerror("Error", "El proceso terminó con un error:\n\n" + data)
        except queue.Empty:
            pass
        self.root.after(80, self.poll)

    def close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Cerrar", "Hay una consulta ejecutándose.\n\n¿Quieres cerrar la aplicación?"):
                return
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
