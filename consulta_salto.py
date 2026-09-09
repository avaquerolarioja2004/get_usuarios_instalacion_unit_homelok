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


def obtener_access_rights_usuario(user_name, headers):
    """Lista los derechos de acceso (access-rights) asignados a un usuario.

    Usa el 'name' completo del usuario tal cual lo devuelve la API
    (p.ej. 'installations/X/users/Y' o 'installations/X/units/Z/users/Y'),
    en vez de reconstruir la ruta asumiendo que siempre cuelga
    directamente de la instalación. Los usuarios de una unit NO viven en
    installations/{id}/users/{id}, sino anidados bajo su unit, así que
    reconstruir la ruta a mano daba 404 para ellos.
    """
    return paginada(
        f"{BASE_URL}/{user_name}/access-rights",
        headers,
        ("user_access_rights", "data"),
        f"Access rights de usuario {user_name}",
    )


def obtener_iam_policies(uid, headers):
    """Lista todas las políticas IAM de la instalación (member -> roles)."""
    return paginada(f"{BASE_URL}/installations/{uid}/iam-policies", headers, ("policies", "data"), f"Políticas IAM de {uid}")


def obtener_iam_policies_unit(uid, unit_uid, headers):
    """Lista las políticas IAM propias de una unit (roles asignados solo sobre esa unit)."""
    return paginada(
        f"{BASE_URL}/installations/{uid}/units/{unit_uid}/iam-policies",
        headers,
        ("policies", "data"),
        f"Políticas IAM de unit {unit_uid}",
    )


def construir_mapa_roles(policies):
    """Devuelve {member: [roles]} a partir de la lista de políticas IAM.
    El 'member' puede venir como email (caso normal) o como resource name
    del usuario, según la instalación; se guarda tal cual y en minúsculas
    para poder cruzarlo de las dos formas."""
    mapa = {}
    for p in policies:
        member = p.get("member")
        if not member:
            continue
        mapa.setdefault(member.strip().lower(), []).extend(p.get("roles", []))
    return mapa


def roles_de_usuario(mapa_roles, user):
    """Busca los roles de un usuario probando primero por email y luego por
    resource name, ya que el campo 'member' de iam-policies puede venir en
    cualquiera de los dos formatos según la instalación."""
    email = (user.get("email") or "").strip().lower()
    name = (user.get("name") or "").strip().lower()
    roles = mapa_roles.get(email) or mapa_roles.get(name) or []
    return roles


def resumir_access_rights(access_rights):
    """Convierte la lista de user_access_rights en un texto legible 'A; B; C'."""
    nombres = []
    for ar in access_rights:
        nombre = ar.get("display_name") or extraer_uid(ar.get("access_right", "")) or extraer_uid(ar.get("name", ""))
        if nombre:
            nombres.append(nombre)
    return "; ".join(nombres)


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


def ejecutar_get_units(instalacion_uid: str, token: str, carpeta_salida, callback=None):
    """Obtiene únicamente las units de UNA instalación (sin usuarios) y las
    guarda en un CSV. Pensado para el modo 'Obtener units' de la GUI, donde
    el usuario escribe directamente el UID de la instalación en vez de
    aportar un CSV con varias instalaciones."""
    if not token.strip():
        raise ValueError("El token es obligatorio")
    uid = instalacion_uid.strip()
    if not uid:
        raise ValueError("El UID de la instalación es obligatorio")

    salida = Path(carpeta_salida)
    salida.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {token.strip()}", "Accept": "application/json"}

    log("========== OBTENER UNITS DE UNA INSTALACIÓN ==========", callback)
    log(f"Instalación: {uid}", callback)

    units = obtener_units(uid, headers)
    log(f"-> {len(units)} units encontradas", callback)

    filas = []
    for unit in units:
        unit_uid = extraer_uid(unit.get("name", ""))
        row = flatten_dict({k: v for k, v in unit.items() if k != "name"})
        row["unit_uid"] = unit_uid
        filas.append(row)

    ruta = salida / f"units_{nombre_fichero_valido(uid)}.csv"
    guardar_csv(filas, ruta)

    log("", callback)
    log("========== PROCESO TERMINADO ==========", callback)
    log(f"Units guardadas: {len(filas)}", callback)
    log(f"Carpeta de salida: {salida}", callback)
    return {"instalaciones": 1, "units": len(filas), "usuarios": 0, "errores": 0, "salida": str(salida)}


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
            # Roles IAM de la instalación: se piden una sola vez y se cruzan por usuario
            try:
                policies = obtener_iam_policies(uid, headers)
                roles_por_miembro = construir_mapa_roles(policies)
            except Exception as exc:
                log(f"  [AVISO] No se pudieron obtener las políticas IAM: {exc}", callback)
                roles_por_miembro = {}

            if modo == "instalacion":
                users = obtener_usuarios_instalacion(uid, headers)
                filas = []
                for k, user in enumerate(users, 1):
                    user_name = user.get("name", "")
                    user_uid = extraer_uid(user_name)
                    try:
                        access_rights = obtener_access_rights_usuario(user_name, headers)
                    except Exception as exc:
                        log(f"    [AVISO] No se pudieron obtener los access rights de {user.get('display_name', user_uid)}: {exc}", callback)
                        access_rights = []
                    row = flatten_dict(user)
                    row["user_uid"] = user_uid
                    row.pop("name", None)
                    row["roles"] = "; ".join(roles_de_usuario(roles_por_miembro, user)) or "Usuario"
                    row["access_rights"] = resumir_access_rights(access_rights) or "(sin access rights)"
                    filas.append(row)
                    if k % 25 == 0:
                        log(f"    ... {k}/{len(users)} usuarios procesados", callback)
                    time.sleep(PAUSA_ENTRE_LLAMADAS)
                ruta = salida / f"{nombre_fichero_valido(nombre)}.csv"
                guardar_csv(filas, ruta)
                total_users += len(filas)
                log(f"  -> {len(filas)} usuarios guardados en {ruta.name}", callback)
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
                    try:
                        policies_unit = obtener_iam_policies_unit(uid, unit_uid, headers)
                        roles_unit_por_miembro = construir_mapa_roles(policies_unit)
                    except Exception as exc:
                        log(f"      [AVISO] No se pudieron obtener las políticas IAM de la unit: {exc}", callback)
                        roles_unit_por_miembro = {}
                    users = obtener_usuarios_unit(uid, unit_uid, headers)
                    log(f"      -> {len(users)} usuarios", callback)
                    unit_data = flatten_dict({k: v for k, v in unit.items() if k != "name"}, "unit_")
                    unit_data["unit_uid"] = unit_uid
                    for user in users:
                        user_name = user.get("name", "")
                        user_uid = extraer_uid(user_name)
                        try:
                            access_rights = obtener_access_rights_usuario(user_name, headers)
                        except Exception as exc:
                            log(f"      [AVISO] No se pudieron obtener los access rights de {user.get('display_name', user_uid)}: {exc}", callback)
                            access_rights = []
                        row = flatten_dict(user)
                        row["user_uid"] = user_uid
                        row.pop("name", None)
                        roles_instalacion = roles_de_usuario(roles_por_miembro, user)
                        roles_unit = roles_de_usuario(roles_unit_por_miembro, user)
                        partes_roles = []
                        if roles_instalacion:
                            partes_roles.append("instalación: " + ", ".join(roles_instalacion))
                        if roles_unit:
                            partes_roles.append("unit: " + ", ".join(roles_unit))
                        row["roles"] = "; ".join(partes_roles) or "Usuario"
                        row["access_rights"] = resumir_access_rights(access_rights) or "(sin access rights)"
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
