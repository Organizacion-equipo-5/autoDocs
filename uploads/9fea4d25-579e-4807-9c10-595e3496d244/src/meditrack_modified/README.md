# 💊 MediTrack — Sistema de Medicamentos Inteligente

Sistema backend en Flask + MongoDB para ayudar a adultos mayores a gestionar sus medicamentos,
con recordatorios automáticos, registro de tomas, notificaciones a familiares y soporte preparado para IoT.

---

## 🏗️ Estructura del Proyecto

```
meditrack/
├── app/
│   ├── __init__.py              # Application Factory
│   ├── config/
│   │   └── settings.py          # Configuración por entorno (dev/test/prod)
│   ├── controllers/             # Blueprints Flask (endpoints HTTP)
│   │   ├── auth_controller.py
│   │   ├── user_controller.py
│   │   ├── medication_controller.py
│   │   ├── medication_log_controller.py
│   │   ├── iot_controller.py
│   │   └── notification_controller.py
│   ├── services/                # Lógica de negocio
│   │   ├── auth_service.py
│   │   ├── user_service.py
│   │   ├── medication_service.py
│   │   ├── medication_log_service.py
│   │   ├── iot_service.py
│   │   └── notification_service.py
│   ├── repository/              # Acceso a datos (MongoDB)
│   │   ├── base_repository.py
│   │   ├── user_repository.py
│   │   ├── medication_repository.py
│   │   ├── medication_log_repository.py
│   │   ├── iot_repository.py
│   │   └── notification_repository.py
│   ├── models/                  # Esquemas de documentos MongoDB
│   │   ├── user.py
│   │   ├── medication.py
│   │   ├── medication_log.py
│   │   ├── iot_device.py
│   │   └── notification.py
│   ├── middleware/
│   │   └── auth.py              # JWT decorators + control de roles
│   └── utils/
│       ├── responses.py         # Helpers JSON consistentes
│       ├── validators.py        # Validadores reutilizables
│       └── scheduler.py         # APScheduler (recordatorios automáticos)
├── tests/
│   └── test_auth.py
├── run.py                       # Punto de entrada
├── seed.py                      # Datos de prueba
├── requirements.txt
└── .env.example
```

---

## 🚀 Instalación y Configuración

### 1. Clonar y crear entorno virtual

```bash
git clone <repo>
cd meditrack
python -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
# Edita .env con tus valores (MongoDB URI, JWT secret, etc.)
```

### 4. Tener MongoDB corriendo

```bash
# Con Docker:
docker run -d -p 27017:27017 --name mongo mongo:7

# O instala MongoDB Community localmente
```

### 5. Poblar la BD con datos de prueba

```bash
python seed.py
```

### 6. Iniciar el servidor

```bash
python run.py
# → http://localhost:5000/api/v1/health
```

---

## 👥 Roles del Sistema

| Rol | Descripción | Permisos principales |
|-----|-------------|---------------------|
| `admin` | Administrador del sistema | Todo |
| `adulto` | Adulto mayor (paciente) | Ver/registrar sus tomas, ver sus meds |
| `familiar` | Familiar o cuidador | Ver pacientes vinculados, registrar tomas |
| `medico` | Médico tratante | Crear/modificar medicamentos, ver historial |

---

## 📡 Endpoints de la API

### Autenticación `/api/v1/auth`

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/registro` | Crear nueva cuenta |
| POST | `/login` | Iniciar sesión |
| POST | `/refresh` | Renovar access token |
| POST | `/cambiar-password` | Cambiar contraseña |

**Ejemplo login:**
```json
POST /api/v1/auth/login
{
  "email": "roberto@test.com",
  "password": "Test1234"
}
```

### Usuarios `/api/v1/usuarios`

| Método | Ruta | Rol requerido |
|--------|------|---------------|
| GET | `/` | admin |
| GET | `/me` | Cualquiera |
| PUT | `/me` | Cualquiera |
| GET | `/<id>` | admin o propio |
| DELETE | `/<id>` | admin |
| POST | `/<adulto_id>/vincular-familiar/<familiar_id>` | admin, adulto, familiar |
| POST | `/<adulto_id>/asignar-medico/<medico_id>` | admin, medico |
| GET | `/me/pacientes` | familiar, medico |

### Medicamentos `/api/v1/medicamentos`

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/` | Registrar medicamento |
| GET | `/adulto/<id>` | Listar medicamentos de un adulto |
| GET | `/<id>` | Detalle de un medicamento |
| PUT | `/<id>` | Actualizar |
| DELETE | `/<id>` | Desactivar |

**Ejemplo crear medicamento:**
```json
POST /api/v1/medicamentos/
Authorization: Bearer <token>
{
  "adulto_id": "...",
  "nombre": "Metformina 500mg",
  "forma": "tableta",
  "dosis": "1 tableta",
  "frecuencia": "cada_12h",
  "horarios": ["08:00", "20:00"],
  "fecha_inicio": "2025-01-01",
  "con_alimentos": true,
  "indicaciones": "Tomar con alimentos"
}
```

### Tomas `/api/v1/tomas`

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/` | Registrar toma |
| GET | `/adulto/<id>` | Historial paginado |
| GET | `/adulto/<id>/hoy` | Tomas del día |
| GET | `/adulto/<id>/adherencia?dias=30` | % de adherencia |

**Ejemplo registrar toma:**
```json
POST /api/v1/tomas/
{
  "medicamento_id": "...",
  "adulto_id": "...",
  "estado": "tomado",
  "hora_programada": "2025-01-15T08:00:00",
  "notas": "Tomado con desayuno"
}
```
Estados disponibles: `tomado | omitido | retrasado | pendiente`

### IoT `/api/v1/iot` (API lista, MQTT configurable)

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/dispositivos` | Registrar dispositivo |
| GET | `/dispositivos/adulto/<id>` | Listar dispositivos |
| POST | `/dispositivos/<id>/lectura` | Registrar lectura |
| GET | `/dispositivos/<id>/lecturas` | Historial de lecturas |
| GET | `/dispositivos/<id>/ultima-lectura` | Última lectura |
| GET | `/alertas/adulto/<id>` | Alertas recientes |
| GET | `/estado` | Estado del módulo IoT (admin) |

**Ejemplo registrar lectura de oxímetro:**
```json
POST /api/v1/iot/dispositivos/<device_id>/lectura
{
  "adulto_id": "...",
  "valores": { "spo2": 98, "pulso": 72 },
  "unidades": { "spo2": "%", "pulso": "bpm" }
}
```

Dispositivos soportados: `oximetro | glucometro | tensiómetro | bascula | pastillero_iot | pulsera_actividad | termometro`

### Notificaciones `/api/v1/notificaciones`

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Mis notificaciones |
| GET | `/conteo` | Total de no leídas |
| PUT | `/<id>/leida` | Marcar como leída |
| PUT | `/todas-leidas` | Marcar todas como leídas |

---

## 🔔 Sistema de Recordatorios Automáticos

El scheduler (APScheduler) corre en background:
- **Cada minuto**: revisa medicamentos activos y envía recordatorio si el horario coincide.
- **Cada hora**: detecta tomas omitidas y notifica a familiares vinculados.

---

## 📡 IoT — Implementación Futura

El módulo IoT está **completamente implementado en API REST**.  
Para activar la conexión MQTT real:

1. Instalar: `pip install paho-mqtt`
2. Configurar en `.env`:
   ```
   IOT_ENABLED=True
   IOT_BROKER_HOST=tu.broker.mqtt
   IOT_BROKER_PORT=1883
   ```
3. Implementar `app/utils/mqtt_client.py`
4. Descomentar el código en `iot_service.py → conectar_mqtt()`

**Umbrales de alerta automática configurados:**
- Oxímetro: SpO2 < 90% o > 100%, Pulso < 40 o > 120 bpm
- Glucómetro: Glucosa < 70 o > 180 mg/dL
- Tensiómetro: Sistólica < 90 o > 140, Diastólica < 60 o > 90
- Termómetro: Temperatura < 35°C o > 37.5°C

---

## 🧪 Pruebas

```bash
# Requiere MongoDB corriendo
pytest tests/ -v
```

---

## 📧 Notificaciones por Email

Configura en `.env`:
```
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=tu@gmail.com
MAIL_PASSWORD=tu_app_password
```

Para Gmail, usa una [contraseña de aplicación](https://myaccount.google.com/apppasswords).

---

## 🌐 Variables de entorno completas

Ver `.env.example` para la lista completa de variables configurables.
