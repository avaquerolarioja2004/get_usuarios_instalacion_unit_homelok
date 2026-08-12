# SALTO Nebula - Consultas

Aplicación gráfica para consultar información de usuarios de instalaciones SALTO Nebula.

La aplicación reúne en un único programa dos formas de consulta:

1. **Usuarios por instalación**
2. **Usuarios por units**

El usuario puede elegir el modo desde la propia interfaz gráfica, por lo que no es necesario mantener dos ejecutables diferentes.

---

## ⚠️ Software propietario

Este proyecto no se distribuye bajo una licencia de código abierto.

El código puede estar publicado en GitHub para facilitar su consulta, pero **su publicación no concede permiso para utilizar, copiar, modificar, distribuir o desplegar el software**.

Para utilizar este programa, ponte en contacto con el autor y solicita autorización o una licencia de uso.

**Contacto:** `[AÑADE AQUÍ TU EMAIL]`

---

## Funcionalidades

### Usuarios por instalación

Consulta directamente los usuarios de cada instalación mediante la API de SALTO Nebula y genera un CSV independiente para cada instalación.

### Usuarios por units

La aplicación:

1. Consulta las units de cada instalación.
2. Obtiene los usuarios asociados a cada unit.
3. Añade al resultado la información disponible de la unit.
4. Genera un CSV por instalación.

---

## Requisitos

- Windows
- Python 3.10 o superior
- Acceso autorizado a la API de SALTO Nebula
- Token válido de SALTO Nebula

Instala las dependencias con:

```bash
pip install -r requirements.txt
```

---

## Formato de `instalaciones.csv`

El archivo debe contener el nombre de la instalación y su UID.

Ejemplo:

```csv
Nombre instalación,Installation UID
Instalación Test,01HK7WD4WS7V1MSAZ72K5X74AF
Otra instalación,01KZR8FF91N25FQ6031SMYRZRC
```

---

## Ejecutar

Puedes iniciar la aplicación con:

```bash
python SaltoConsulta.pyw
```

o haciendo doble clic en `SaltoConsulta.pyw` desde Windows.

La interfaz permite:

- introducir el token;
- seleccionar `instalaciones.csv`;
- elegir **Usuarios por instalación** o **Usuarios por units**;
- seleccionar la carpeta de salida;
- consultar el progreso mediante el log de la propia ventana.

---

## Crear un único ejecutable

El proyecto incluye `crear_exe.bat`.

Ejecutándolo desde Windows se genera:

```text
dist/
└── SaltoConsulta.exe
```

Este es **un único ejecutable**. Desde él se puede elegir cualquiera de los dos modos de consulta.

---

## Estructura

```text
salto_consultas/
│
├── SaltoConsulta.pyw
├── consulta_salto.py
├── instalaciones.csv
├── requirements.txt
├── crear_exe.bat
├── README.md
└── LICENSE.md
```

---

## Seguridad

**No publiques en GitHub información real o sensible**, incluyendo:

- tokens de SALTO Nebula;
- API keys;
- contraseñas;
- credenciales;
- datos personales reales de usuarios;
- CSV obtenidos de instalaciones reales.

Para ejemplos, utiliza datos ficticios.

---

## Uso autorizado

Este software debe utilizarse únicamente con instalaciones para las que el usuario tenga autorización y con credenciales válidas para consultar la API de SALTO Nebula.

---

## Contacto

Si quieres utilizar este software o necesitas información sobre su funcionamiento:

**Autor:** `[TU NOMBRE / EMPRESA]`  
**Email:** `[TU EMAIL]`

---

## Licencia

Este proyecto está sujeto a los términos de [`LICENSE.md`](LICENSE.md).

**Todos los derechos reservados.**
