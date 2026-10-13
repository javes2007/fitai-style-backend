# FitAI Style Backend — seguridad

## Variables y secretos
- Nunca confirmes `.env`, claves de proveedores, contraseñas, JWT secrets ni credenciales de Firebase Admin.
- En Render define `SECRET_KEY`, credenciales MySQL, claves de IA y credenciales Firebase en Environment/Secret Files.
- Si una credencial real estuvo en Git, quitarla del último commit no basta: revócala/rotála y, si corresponde, limpia el historial.
- La Firebase Web API key del frontend forma parte de la configuración pública del cliente; no es una contraseña de servidor. Restringe sus APIs y dominios en Google Cloud/Firebase y configura reglas de Firebase.

## Base de datos
La API actual usa **MySQL**, no PostgreSQL/Supabase. MySQL no ofrece Row-Level Security (RLS) equivalente por tabla como política nativa de PostgreSQL. El aislamiento se implementa en el servidor con JWT verificados, consultas acotadas a `g.id_usuario`, consultas parametrizadas y un usuario MySQL de mínimo privilegio. No existe una “clave pública de base de datos” que deba ir al navegador: nunca expongas credenciales MySQL. Para habilitar RLS real habría que migrar a una plataforma que lo soporte y definir políticas por tabla.

## Sesiones
El backend emite JWT Bearer y el frontend actual los guarda en localStorage; por tanto, actualmente no se usa una cookie de sesión HttpOnly. No almacenes contraseñas en el navegador. La migración recomendada es pasar la sesión a cookie `Secure; HttpOnly; SameSite=Lax` con protección CSRF y CORS coordinados; no se debe activar parcialmente.

## Protección aplicada por código
- Cabeceras defensivas, HSTS y redirección HTTPS en despliegue.
- Límite global de solicitudes y límites específicos en login/registro/contacto/IA.
- Tamaño máximo de request/form y límites de subida de imágenes.
- Contraseñas con hash Werkzeug (no reversible).
- Rutas sensibles con JWT y autorización por propietario donde ya está implementada.
- Respuestas genéricas para errores internos y no-cache en endpoints de autenticación.

## Operación obligatoria antes de producción
1. Configura una `SECRET_KEY` fuerte y única en Render; el servicio falla al iniciar si falta.
2. Define `FRONTEND_ORIGINS` con dominios HTTPS reales.
3. Configura `RATELIMIT_STORAGE_URI` con Redis gestionado si escalas a más de un proceso/instancia.
4. Crea un usuario MySQL dedicado (no root) con permisos mínimos; configura `DB_SSL_CA` para validar TLS cuando el proveedor lo requiera y activa cifrado en reposo en el proveedor. El backend registra consultas lentas por huella hash y duración sin imprimir SQL ni parámetros; configura también el slow query log/monitorización del proveedor MySQL.
5. Revisa reglas de Firebase/Storage y restringe la Firebase Web API key por dominio y API.
6. Revisa el reporte de Gitleaks y rota cualquier secreto que se detecte.
7. Espera a que GitHub Actions termine las comprobaciones; no se declara auditoría aprobada hasta entonces.
