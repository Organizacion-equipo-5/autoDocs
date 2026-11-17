# Resultados de seguridad — backend

Revisión estática solamente; no hubo ataques ni llamadas dinámicas.

- Alto, potencial: URI MongoDB con credenciales como valor predeterminado en `config.py`. No se copia el valor aquí. Rotar si sigue activo y retirar del código.
- Alto condicionado: depuración activa si falta `FLASK_DEBUG`; comprobar entorno desplegado.
- Medio condicionado: CORS `*` en `/api/*`; limitar orígenes.
- No comprobados: acceso horizontal entre usuarios, manipulación de IDs, protección de todos los endpoints y restablecimiento de contraseña. Probar con cuentas sintéticas en staging.
