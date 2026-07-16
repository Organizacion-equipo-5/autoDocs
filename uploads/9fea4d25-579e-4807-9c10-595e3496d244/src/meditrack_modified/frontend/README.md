# 🎨 Frontend - MediTrack

Frontend moderno y responsivo para el Sistema de Medicamentos Inteligente MediTrack, desarrollado con HTML5, CSS3 y Vanilla JavaScript (sin frameworks externos).

## ✨ Características

✅ **Interfaz moderna y responsive** - Funciona en desktop, tablet y móvil  
✅ **Sistema de autenticación** - Login seguro con JWT  
✅ **Dashboard** - Panel de control con estadísticas en tiempo real  
✅ **Gestión de medicinas** - Crear, editar y eliminar medicinas  
✅ **Gestión de usuarios** - Administrar perfiles de usuarios  
✅ **Registro de tomas** - Historial de medicinas tomadas  
✅ **Notificaciones** - Sistema de alertas y notificaciones  
✅ **Diseño accesible** - Contraste adecuado y navegación intuitiva  

## 📁 Estructura del Proyecto

```
frontend/
├── index.html           # HTML principal
├── js/
│   ├── api.js          # Comunicación con backend
│   ├── auth.js         # Autenticación
│   ├── ui.js           # Utilidades de UI
│   └── app.js          # Lógica principal
├── css/
│   ├── style.css       # Estilos principales
│   └── responsive.css  # Estilos responsivos
└── assets/             # Imágenes y recursos
```

## 🚀 Inicio Rápido

### 1. Asegúrate que el Backend está corriendo

```bash
# En la raíz del proyecto
python run.py
```

El servidor debe estar disponible en `http://localhost:5000`

### 2. Abrir el Frontend

El frontend se sirve automáticamente desde Flask en:

```
http://localhost:5000/
```

O directamente abriendo `frontend/index.html` en el navegador para desarrollo local.

## 🔐 Credenciales de Prueba

```
Admin:    admin@meditrack.com  / Admin123
Adulto:   roberto@test.com     / Test1234
Familiar: maria@test.com       / Test1234
Médico:   dr.carlos@test.com   / Test1234
```

## 📱 Funcionalidades Principales

### 🔑 Autenticación
- Login con email y contraseña
- Gestión de sesión con JWT
- Logout seguro
- Restauración automática de sesión

### 📊 Dashboard
- Estadísticas de usuarios, medicinas, tomas
- Lista de próximas medicinas a tomar
- Información de tomas pendientes y completadas

### 💊 Gestión de Medicinas
- Crear nuevas medicinas
- Editar medicinas existentes
- Eliminar medicinas
- Visualizar detalles y horarios
- Filtrar por estado (activo/inactivo)

### 👥 Gestión de Usuarios
- Ver lista de usuarios
- Filtrar por rol
- Información de contacto
- Eliminación de usuarios

### 📋 Registro de Tomas
- Historial completo de tomas
- Filtrar por fecha y estado
- Estados: tomado ✅, omitido ❌, retrasado ⏰, pendiente ⏳

### 🔔 Notificaciones
- Centro de notificaciones
- Marcar como leídas
- Badge contador
- Eliminar notificaciones

## 🎯 Componentes Principales

### modules/api.js
Gestiona toda la comunicación con el backend:
```javascript
API.login(email, password)
API.getMedications()
API.createMedication(data)
API.updateMedication(id, data)
API.getUsers()
API.getMedicationLogs()
```

### modules/auth.js
Gestiona autenticación y sesiones:
```javascript
AUTH.login(email, password)
AUTH.logout()
AUTH.getCurrentUser()
AUTH.hasRole(role)
AUTH.isLoggedIn()
```

### modules/ui.js
Utilidades para interfaz:
```javascript
UI.notify(message, type)
UI.showModal(id)
UI.hideModal(id)
UI.showPage(name)
UI.formatDate(date)
```

### modules/app.js
Lógica principal de la aplicación

## 🎨 Diseño y Tema

### Colores
- **Primario**: `#4f46e5` (Azul índigo)
- **Éxito**: `#10b981` (Verde)
- **Peligro**: `#ef4444` (Rojo)
- **Advertencia**: `#f59e0b` (Amarillo)
- **Info**: `#3b82f6` (Azul)

### Tipografía
- Font: Inter, sans-serif
- Responsive: Tamaños ajustados por pantalla

### Responsive
- Desktop: 1200px+
- Tablet: 768px - 1024px
- Móvil: 320px - 767px

## 🔧 Configuración

### Cambiar URL del Backend

Si el backend está en otro servidor, edita `frontend/js/api.js`:

```javascript
// Cambiar esta línea:
baseURL: 'http://localhost:5000/api/v1'

// A tu URL:
baseURL: 'https://tu-servidor.com/api/v1'
```

### Variables de Entorno

El frontend no requiere variables de entorno, pero el backend sí:

```bash
# En .env
FLASK_ENV=development
FLASK_DEBUG=True
MONGO_URI=mongodb://localhost:27017/meditrack
```

## 📱 Optimización Móvil

✅ Viewport configurado  
✅ Touch-friendly buttons (mínimo 44x44px)  
✅ Orientación responsive (portrait + landscape)  
✅ Prevención de zoom en inputs  
✅ Iconos y emojis para mejor UX  

## 🔒 Seguridad

- Tokens JWT almacenados en localStorage
- CORS configurado en backend
- Autenticación en cada petición
- Logout limpia tokens

## 🐛 Troubleshooting

### Error: "No se puede conectar al servidor"

1. Verifica que el backend está corriendo (`python run.py`)
2. Verifica que MongoDB está disponible
3. Verifica la URL en `api.js`
4. Abre la consola del navegador (F12) para ver errores

### Error: "Token expirado"

1. Cierra sesión y vuelve a iniciar
2. El frontend redirige automáticamente al login
3. Los tokens se guardan en localStorage

### Estilos no cargan

1. Limpia el caché del navegador (Ctrl+Shift+Del)
2. Verifica que los archivos CSS existen
3. Abre la consola (F12) para ver errores 404

## 📚 API Endpoints Utilizados

El frontend consume estos endpoints:

```
POST   /api/v1/auth/login
GET    /api/v1/users
POST   /api/v1/users
PUT    /api/v1/users/:id
DELETE /api/v1/users/:id

GET    /api/v1/medications
POST   /api/v1/medications
PUT    /api/v1/medications/:id
DELETE /api/v1/medications/:id

GET    /api/v1/medication-logs
POST   /api/v1/medication-logs
PUT    /api/v1/medication-logs/:id

GET    /api/v1/notifications
PUT    /api/v1/notifications/:id
DELETE /api/v1/notifications/:id

GET    /api/v1/iot/devices
GET    /api/v1/iot/readings
```

## 🚀 Mejoras Futuras

- [ ] Gráficos de estadísticas con Chart.js
- [ ] Exportar reportes (PDF/Excel)
- [ ] Notificaciones push en tiempo real
- [ ] Integración con calendario
- [ ] Tema oscuro
- [ ] Soporte multiidioma
- [ ] PWA (Progressive Web App)

## 📄 Licencia

MIT - Libre para usar y modificar

## 📞 Soporte

¿Problemas? Abre un issue en el repositorio o contacta al equipo de desarrollo.

---

**MediTrack v1.0.0** - Sistema de Medicamentos Inteligente ©2026
