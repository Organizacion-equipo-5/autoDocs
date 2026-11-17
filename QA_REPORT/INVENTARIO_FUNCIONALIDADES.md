# Inventario funcional y estrategia

## Backend Flask/Python

Web SSR y API con MongoDB/JWT. Flujos detectados: registro, login, perfil y recuperación de contraseña; CRUD de proyectos, carga y clonación GitHub; análisis asíncrono, predicciones, ETL y análisis SQL; exportación PDF/HTML/Markdown; pagos/planes, recomendaciones y administración. Integraciones: MongoDB, GitHub, proveedor IA Groq configurable, PayPal y Kroki.

## Flutter

Pantallas: splash, login, registro/términos, home, dashboard, análisis, proyectos, detalle y perfil. Servicios: API Dio, auth, almacenamiento local, selector de archivos y exportación PDF; dependencias de biometría y notificaciones. API base apunta a un host remoto configurado en `lib/utils/constants.dart`.

## Pruebas propuestas

1. Unitarias con mocks y datos sintéticos.
2. Widget/UI en emulador; integrar login, proyectos, análisis y exportación.
3. Pruebas de API y aislamiento entre dos usuarios contra staging/local con MongoDB desechable.
4. k6 gradual (1, 5, 10, 25, 50 y, si es estable, 100/200 VUs) solo en entorno de prueba aprobado.
5. No cargar el endpoint remoto configurado en producción.
