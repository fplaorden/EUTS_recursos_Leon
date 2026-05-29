# Recursos de Asistencia Social - León

Aplicación web interactiva y contenedorizada para buscar, filtrar y gestionar visualmente los recursos de asistencia social existentes en León, España. La plataforma está estructurada como una Single Page Application (SPA) con diseño moderno y un backend dinámico en Python Flask.

## Características Principales

*   **Mapa Interactivo (Leaflet.js):** Geolocalización de entidades (pines azules) y servicios básicos municipales/CEAS (pines verdes) en el callejero de León.
*   **Filtros Reactivos:** Filtrado instantáneo por Área de Actuación, Colectivo Destinatario, Tipo de Servicio/Prestación y Titularidad (Pública/Privada).
*   **Búsqueda con Autocompletado:** Buscador inteligente que indexa entidades, nombres de servicios y direcciones. Al hacer clic en una sugerencia, se centra el mapa y abre los detalles del recurso.
*   **Listas de Documentación:** Cada servicio incluye una sección específica detallando los documentos necesarios para solicitarlo.
*   **Panel de Administración (CRUD):** Interfaz protegida para añadir, editar o eliminar entidades, servicios y documentación, así como para gestionar las cuentas administrativas.
*   **Recuperación de Contraseña:** Sistema seguro mediante envío de tokens de restablecimiento por correo electrónico.

---

## Estructura del Proyecto

```
EUTS_Recursos_Leon/
├── data/
│   ├── app.db               # Base de datos SQLite (Ingesta inicial de Excel completada)
│   └── geocoding_cache.json # Caché de coordenadas geográficas
├── scripts/
│   ├── geocode_utils.py     # Librería de geolocalización y limpieza de direcciones
│   └── ingest_data.py       # Script de ingesta local (Excel -> SQLite)
├── app/
│   ├── static/
│   │   ├── index.html       # Interfaz pública principal
│   │   ├── admin.html       # Panel CRUD de administración
│   │   ├── login.html       # Iniciar sesión y recuperación de clave
│   │   ├── styles.css       # Hojas de estilo personalizadas (Modo Oscuro/Claro)
│   │   └── app.js           # Lógica frontend y llamadas a la API
│   └── server.py            # Servidor API Flask
├── Dockerfile.app           # Configuración Docker para Flask/Gunicorn
├── Dockerfile.nginx         # Configuración Docker para Nginx/SSL
├── nginx.conf               # Configuración del proxy inverso y redirección HTTPS
├── docker-compose.yml       # Orquestación de contenedores y volúmenes persistentes
└── requirements.txt         # Dependencias Python
```

---

## Ejecución en Local (Desarrollo)

Para arrancar el proyecto de manera local en tu máquina de desarrollo:

1.  Asegúrate de tener instalado Python 3.11+.
2.  Instala las dependencias necesarias:
    ```bash
    pip install -r requirements.txt
    ```
3.  Arranca el servidor local con el script de ayuda:
    ```bash
    python run_server.py
    ```
4.  La web se abrirá automáticamente en: [http://localhost:8000/static/index.html](http://localhost:8000/static/index.html)
5.  Para acceder al panel administrativo, haz clic en **Acceso Administrador** en la esquina superior derecha:
    *   **Usuario/Email:** `admin@leon.es`
    *   **Contraseña:** `admin_password_change_me`

---

## Despliegue en Producción (VPS Linux Ubuntu)

El despliegue está diseñado para realizarse de forma automatizada mediante Docker:

1.  **Clona este repositorio en tu VPS Ubuntu:**
    ```bash
    git clone https://github.com/fplaorden/EUTS_recursos_Leon.git
    cd EUTS_recursos_Leon
    ```
2.  **Instala Docker y Docker Compose si no los tienes:**
    ```bash
    sudo apt update
    sudo apt install -y docker.io docker-compose-v2
    ```
3.  **Configura las variables de entorno (Opcional):**
    Puedes crear un archivo `.env` en la raíz del proyecto para definir la clave secreta y la configuración SMTP para que funcione el correo de recuperación:
    ```ini
    FLASK_SECRET_KEY=tu_clave_secreta_hexadecimal
    SMTP_SERVER=smtp.ejemplo.com
    SMTP_PORT=587
    SMTP_USER=tu_usuario_smtp
    SMTP_PASSWORD=tu_contraseña_smtp
    SMTP_FROM=noreply@leon.es
    ```
    *Nota: Si no se configuran estas variables, la aplicación guardará las solicitudes de recuperación en `data/sent_emails.log` para que puedas visualizarlas allí.*

4.  **Levanta la pila de contenedores:**
    ```bash
    sudo docker compose up --build -d
    ```
    Nginx generará un certificado SSL autofirmado de forma nativa. La base de datos SQLite se almacenará en el volumen persistente `social_db` para asegurar la persistencia de los cambios.

5.  **Acceso:** Abre en tu navegador `https://<IP_DE_TU_VPS>` (acepta el aviso de certificado autofirmado) o `http://<IP_DE_TU_VPS>` (redireccionará automáticamente a HTTPS).
