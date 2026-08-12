import csv
import re
import time
from pathlib import Path
from typing import Callable, Optional

import requests

BASE_URL = "https://nebula.saltoapis.com/v1"
PAGE_SIZE = 1000
PAUSA_ENTRE_LLAMADAS = 0.3


def log(msg: str, callback: Optional[Callable[[str], None]] = None):
    if callback:
        callback(msg)
    else:
        print(msg)


def nombre_fichero_valido(nombre: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", nombre.strip()) or "instalacion_sin_nombre"


def leer_instalaciones(ruta: Path):
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró el CSV de instalaciones:\n{ruta}")
    instalaciones = []
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        for fila in csv.reader(f):
            if not fila or len(fila) < 2:
                continue
            nombre, uid = fila[0].strip(), fila[1].strip()
            if nombre.lower() in ("nombre", "instalacion", "instalación") and uid.lower() in ("uid", "installation_id", "installation_uid"):
                continue
            if nombre and uid:
                instalaciones.append((nombre, uid))
    return instalaciones


def extraer_uid(name: str) -> str:
    return name.rstrip("/").split("/")[-1] if name else ""


def flatten_dict(d: dict, prefix: str = "") -> dict:
    out = {}
    for key, value in d.items():
        if key == "name" and prefix:
            continue
        final_key = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten_dict(value, final_key + "_")) if value else out.__setitem__(final_key, "")
        elif isinstance(value, list):
            out[final_key] = "; ".join(str(x) for x in value)
        else:
            out[final_key] = value
    return out


def paginada(url: str, headers: dict, keys: tuple[str, ...], descripcion: str):
    elementos = []
    params = {"page_size": PAGE_SIZE}
    while True:
        try:
            r = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.RequestException as exc:
            raise RuntimeError(f"{descripcion}: error de conexión: {exc}") from exc
        if r.status_code != 200:
            raise RuntimeError(f"{descripcion}: HTTP {r.status_code} -> {r.text[:500]}")
        try:
            data = r.json()
        except ValueError as exc:
            raise RuntimeError(f"{descripcion}: respuesta JSON no válida") from exc
        pagina = next((data[k] for k in keys if k in data), [])
        if isinstance(pagina, list):
            elementos.extend(pagina)
        token = data.get("next_page_token") or data.get("nextPageToken")
        if not token:
            break
        params["page_token"] = token
        time.sleep(PAUSA_ENTRE_LLAMADAS)
    return elementos


def obtener_usuarios_instalacion(uid, headers):
    return paginada(f"{BASE_URL}/installations/{uid}/users", headers, ("users", "data"), f"Usuarios de {uid}")


def obtener_units(uid, headers):
    return paginada(f"{BASE_URL}/installations/{uid}/units", headers, ("units", "data"), f"Units de {uid}")


def obtener_usuarios_unit(uid, unit_uid, headers):
    return paginada(f"{BASE_URL}/installations/{uid}/units/{unit_uid}/users", headers, ("users", "data"), f"Usuarios de unit {unit_uid}")


def guardar_csv(filas, ruta: Path):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if not filas:
        ruta.write_text("Sin usuarios\n", encoding="utf-8-sig")
        return
    columnas = []
    for fila in filas:
        for key in fila:
            if key not in columnas:
                columnas.append(key)
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(filas)


def ejecutar_consulta(modo: str, csv_instalaciones, token: str, carpeta_salida, callback=None):
    if modo not in ("instalacion", "units"):
        raise ValueError("Modo de consulta no válido")
    if not token.strip():
        raise ValueError("El token es obligatorio")

    instalaciones = leer_instalaciones(Path(csv_instalaciones))
    if not instalaciones:
        raise ValueError("No hay instalaciones válidas en el CSV")

    salida = Path(carpeta_salida)
    salida.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {token.strip()}", "Accept": "application/json"}

    log("========== CONSULTA POR INSTALACIÓN ==========" if modo == "instalacion" else "========== CONSULTA POR UNITS ==========", callback)
    log(f"Instalaciones a consultar: {len(instalaciones)}", callback)

    total_users = total_units = errores = 0

    for i, (nombre, uid) in enumerate(instalaciones, 1):
        log(f"[{i}/{len(instalaciones)}] {nombre} ({uid})", callback)
        try:
            if modo == "instalacion":
                users = obtener_usuarios_instalacion(uid, headers)
                ruta = salida / f"{nombre_fichero_valido(nombre)}.csv"
                guardar_csv(users, ruta)
                total_users += len(users)
                log(f"  -> {len(users)} usuarios guardados en {ruta.name}", callback)
            else:
                units = obtener_units(uid, headers)
                total_units += len(units)
                log(f"  -> {len(units)} units encontradas", callback)
                filas = []
                for j, unit in enumerate(units, 1):
                    unit_uid = extraer_uid(unit.get("name", ""))
                    if not unit_uid:
                        log("    [AVISO] Unit sin UID reconocible; se omite", callback)
                        continue
                    nombre_unit = unit.get("display_name", unit_uid)
                    log(f"    [{j}/{len(units)}] Unit '{nombre_unit}' ({unit_uid})", callback)
                    users = obtener_usuarios_unit(uid, unit_uid, headers)
                    log(f"      -> {len(users)} usuarios", callback)
                    unit_data = flatten_dict({k: v for k, v in unit.items() if k != "name"}, "unit_")
                    unit_data["unit_uid"] = unit_uid
                    for user in users:
                        row = flatten_dict(user)
                        row["user_uid"] = extraer_uid(user.get("name", ""))
                        row.pop("name", None)
                        row.update(unit_data)
                        filas.append(row)
                    time.sleep(PAUSA_ENTRE_LLAMADAS)
                ruta = salida / f"{nombre_fichero_valido(nombre)}.csv"
                guardar_csv(filas, ruta)
                total_users += len(filas)
                log(f"  -> Total {len(filas)} usuarios guardados en {ruta.name}", callback)
        except Exception as exc:
            errores += 1
            log(f"  [ERROR] {nombre}: {exc}", callback)
        time.sleep(PAUSA_ENTRE_LLAMADAS)

    log("", callback)
    log("========== PROCESO TERMINADO ==========", callback)
    log(f"Instalaciones procesadas: {len(instalaciones)}", callback)
    if modo == "units":
        log(f"Units encontradas: {total_units}", callback)
    log(f"Usuarios guardados: {total_users}", callback)
    log(f"Errores: {errores}", callback)
    log(f"Carpeta de salida: {salida}", callback)
    return {"instalaciones": len(instalaciones), "units": total_units, "usuarios": total_users, "errores": errores, "salida": str(salida)}
