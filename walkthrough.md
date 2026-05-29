# Guía del Proyecto: Recursos de Asistencia Social de León

Una aplicación web completamente contenedorizada para visualizar, buscar, filtrar y gestionar los recursos de asistencia social en León, España, basada en un backend dinámico en Python Flask y una Single Page Application (SPA) moderna en HTML5/CSS3/JS.

## Características Clave

1. **Mapa Interactivo con Leaflet.js**: Muestra todas las entidades y servicios básicos municipales (CEAS / Centros de Salud) con marcadores personalizados de colores (Azul para entidades, Verde para CEAS). Al hacer clic en un pin, el mapa se centra y se muestra un resumen con un enlace a los detalles.
2. **Filtros Avanzados y Reactivos**: Filtra al instante por **Área**, **Colectivo**, **Tipo de Servicio** y **Titularidad** (Pública o Privada) directamente en la interfaz sin recargar la página.
3. **Búsqueda Inteligente Autocompletable**: Sugiere nombres de entidades, servicios o ubicaciones a medida que escribes. Al seleccionar una sugerencia, el mapa se desplaza al recurso y abre sus detalles.
4. **Detalles Completos con Listas de Documentación**: Al hacer clic en un recurso se muestran sus datos de contacto, horarios, costes, condiciones de admisión y una sección dedicada con bordes discontinuos que detalla la **documentación requerida** (cargada dinámicamente desde la base de datos).
5. **Panel de Control y Gestión Administrativa**:
   - Acceso seguro mediante inicio de sesión (`/static/login.html`) con encriptación PBKDF2.
   - Panel CRUD completo (`/static/admin.html`) para crear, modificar o eliminar entidades, servicios y documentación.
   - Gestión de cuentas de administradores para registrar o eliminar perfiles.
   - Sistema de recuperación de contraseña mediante un token enviado por correo (o registrado en `data/sent_emails.log` si no hay SMTP configurado).
6. **Despliegue de Producción con Docker**: Preparado para funcionar en un entorno de doble contenedor (Flask + Proxy inverso de Nginx + certificados SSL) con volúmenes de Docker para persistencia en un VPS Ubuntu.

---

## Esquema de Base de Datos SQLite (`data/app.db`)

Hemos migrado las tablas originales de Excel a una base de datos SQLite relacional:
- **`users`**: Gestiona las cuentas administrativas (`id`, `username`, `email`, `password_hash`, `created_at`).
- **`recovery_tokens`**: Guarda los tokens de recuperación de contraseñas (`id`, `user_id`, `token`, `expires_at`, `used`).
- **`entidades`**: Almacena los perfiles de instituciones o centros (`id`, `nombre`, `tipo_entidad`, `direccion`, `cp`, `localidad`, `titularidad`, `telefono`, `telefono2`, `fax`, `email`, `web`, `ceas`, `area`, `colectivo`, `latitude`, `longitude`).
- **`servicios`**: Almacena los programas y prestaciones que ofrece cada entidad (`id`, `entidad_id`, `nombre`, `tipo_servicio`, `tipo_registro`, `descripcion_corta`, `descripcion_larga`, `plazas`, `cita_previa`, `horario`, `condiciones_admision`, `aportacion_beneficiario`, `direccion`, `finalidad`).
- **`documentacion`**: Almacena los nombres de los documentos requeridos para cada servicio (`id`, `servicio_id`, `nombre_documento`).
- **`servicios_basicos`**: Almacena las zonas CEAS públicas y centros de salud de León (`id`, `tipo`, `nombre`, `direccion`, `cp`, `ciudad`, `telefono`, `email`, `telefono2`, `telefono3`, `telefono4`, `latitude`, `longitude`).

---

## Cómo Ejecutar en Local (Desarrollo)

Para probar la aplicación en tu ordenador:

1. **Base de Datos Lista**: Los datos de Excel ya han sido importados en `data/app.db` con todas las coordenadas precalculadas.
2. **Iniciar el Servidor Local**:
   Ejecuta el script desde la raíz del espacio de trabajo:
   ```bash
   python run_server.py
   ```
   Esto levantará el servidor Flask en `http://localhost:8000` y abrirá automáticamente tu navegador web por defecto en:
   [http://localhost:8000/static/index.html](http://localhost:8000/static/index.html)

3. **Iniciar Sesión como Administrador**:
   - Ve a la esquina superior derecha y haz clic en **Acceso Administrador**.
   - Usa las credenciales por defecto creadas en la ingesta:
     - **Email:** `admin@leon.es`
     - **Contraseña:** `admin_password_change_me`
   - *Consejo:* Una vez logueado, haz clic en el icono de la llave para cambiar tu contraseña, o navega a la pestaña de "Administradores" para registrar nuevas cuentas.

4. **Probar la Recuperación de Contraseña**:
   - En la pantalla de login, haz clic en **¿Olvidó su contraseña?** e introduce `admin@leon.es`.
   - Abre el archivo [data/sent_emails.log](file:///g:/Mi%20unidad/Antigravity_fpl/EUTS_Recursos_Leon/data/sent_emails.log). Encontrarás el registro del correo enviado con el enlace de recuperación.
   - Copia y pega ese enlace en tu navegador para simular el restablecimiento.

---

## Cómo Desplegar en Producción (VPS Linux Ubuntu)

Como la base de datos `data/app.db` ya está precalculada con las coordenadas en local, subirla a producción en tu VPS es muy sencillo:

1. **Subir los Archivos**: Copia los siguientes archivos al servidor VPS:
   - `Dockerfile.app`
   - `Dockerfile.nginx`
   - `docker-compose.yml`
   - `nginx.conf`
   - `requirements.txt`
   - Carpeta `app/` (código del servidor y archivos estáticos)
   - Carpeta `data/` (base de datos SQLite `app.db` y caché)
   - Carpeta `scripts/` (opcional)

2. **Instalar Docker en el VPS**:
   Si no tienes instalado Docker en tu servidor Ubuntu, ejecuta:
   ```bash
   sudo apt update
   sudo apt install -y docker.io docker-compose-v2
   ```

3. **Configurar Variables de Entorno (Opcional)**:
   Si deseas activar el envío real de correos de recuperación, configura estas variables (por ejemplo, en un archivo `.env` en la raíz):
   ```ini
   FLASK_SECRET_KEY=genera_una_clave_hexagonal_segura
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=tu_correo@gmail.com
   SMTP_PASSWORD=tu_contraseña_de_aplicacion
   SMTP_FROM=noreply@leon.es
   ```

4. **Iniciar los Servicios de Producción**:
   Ejecuta el siguiente comando en la raíz del proyecto en tu VPS:
   ```bash
   sudo docker compose up --build -d
   ```
   Esto compilará la API de Flask, configurará el servidor Nginx con certificado SSL autofirmado exponiendo los puertos `80` y `443` en el VPS, y creará un volumen de datos persistente llamado `social_db` para que no se pierdan los cambios de base de datos en las actualizaciones.

5. **Acceder a la Aplicación**:
   Entra en tu navegador a `https://<IP_DE_TU_VPS>` (puedes aceptar la advertencia del certificado autofirmado) y la plataforma estará en producción y completamente funcional.
