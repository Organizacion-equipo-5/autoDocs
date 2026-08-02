# 🗄️ Configuración de MongoDB en MediTrack

## 📋 Descripción

MediTrack usa **MongoDB** como base de datos. La configuración automática se encarga de:

1. ✅ Conectar a MongoDB
2. ✅ Crear la base de datos (`meditrack`) si no existe
3. ✅ Crear todas las colecciones automáticamente
4. ✅ Crear índices para optimizar búsquedas
5. ✅ Manejar errores de conexión de forma robusta

## 🚀 Instalación de MongoDB

### Opción 1: MongoDB Community Edition (Local)

**Windows:**
```powershell
# Descargar desde: https://www.mongodb.com/try/download/community
# Ejecutar el instalador .msi
# MongoDB se instala como servicio y se ejecuta automáticamente
```

**macOS (con Homebrew):**
```bash
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install -y mongodb
sudo systemctl start mongodb
```

### Opción 2: Docker (Recomendado para desarrollo)

```bash
docker run -d \
  --name meditrack-mongo \
  -p 27017:27017 \
  -e MONGO_INITDB_DATABASE=meditrack \
  mongo:latest
```

### Opción 3: MongoDB Atlas (Cloud)

1. Ir a https://www.mongodb.com/cloud/atlas
2. Crear cuenta y proyecto
3. Crear un cluster gratuito
4. Copiar la cadena de conexión
5. Actualizar `MONGO_URI` en `.env`:
   ```
   MONGO_URI=mongodb+srv://usuario:contraseña@cluster.mongodb.net/meditrack
   ```

## 🔧 Configuración en el Proyecto

### 1. Crear archivo `.env`

Copia `.env.example` como `.env`:
```bash
cp .env.example .env
```

Edita los valores:
```env
# MongoDB - Local
MONGO_URI=mongodb://localhost:27017/meditrack
MONGO_DB_NAME=meditrack

# MongoDB - Atlas (ejemplo)
# MONGO_URI=mongodb+srv://usuario:contraseña@cluster.mongodb.net/meditrack
# MONGO_DB_NAME=meditrack
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Ejecutar la aplicación

```bash
python run.py
```

El script automáticamente:
- ✅ Se conecta a MongoDB
- ✅ Crea la BD si no existe
- ✅ Crea todas las colecciones e índices
- ✅ Muestra mensajes de estado

## 📚 Archivos de Configuración

| Archivo | Descripción |
|---------|-------------|
| `app/db.py` | Conexión centralizada a MongoDB |
| `app/__init__.py` | Factory de Flask (incluye inicialización de BD) |
| `.env` | Variables de entorno (no subir a Git) |
| `.env.example` | Template de variables (subir a Git) |
| `run.py` | Punto de entrada con verificación de MongoDB |

## 🔌 Uso en Repositorios y Servicios

### Acceder a la BD:

```python
from app import db

# Obtener la instancia de la BD
database = db.get_db()

# Usar colecciones
users_collection = database['users']
users_collection.insert_one({...})
```

### En Repositorios (heredan de BaseRepository):

```python
from app.repository.base_repository import BaseRepository

class UserRepository(BaseRepository):
    COLLECTION_NAME = 'users'
    
    def find_by_email(self, email):
        return self.find_one({"email": email})
```

## 📊 Colecciones Automáticas

Se crean automáticamente al iniciar:

```
meditrack/
├── users (índice único en email)
├── medications
├── medication_logs
├── iot_devices
├── iot_readings
└── notifications
```

## 🧪 Testing y Seed

### Poblar con datos de prueba:

```bash
python seed.py
```

Credenciales de prueba:
- **Admin:** admin@meditrack.com / Admin123
- **Adulto:** roberto@test.com / Test1234
- **Familiar:** maria@test.com / Test1234
- **Médico:** dr.carlos@test.com / Test1234

## 🐛 Troubleshooting

### Error: "No se pudo conectar a MongoDB"

```
❌ CRITICAL: No se pudo conectar a MongoDB
⚠️  Asegúrate de que MongoDB está corriendo
```

**Solución:**
1. Verifica que MongoDB está corriendo: `mongod` o `docker ps`
2. Verifica `MONGO_URI` en `.env`
3. Verifica puertos: MongoDB usa `27017` por defecto
4. Si usas Atlas, verifica credenciales y whitelist de IP

### Error: "ModuleNotFoundError: No module named 'pymongo'"

```bash
pip install pymongo
# O instala todas las dependencias:
pip install -r requirements.txt
```

### Las colecciones no se crean

Verifica que `app/db.py` se ejecuta:
- Revisa los logs al iniciar `python run.py`
- Verifica que tienes permisos para crear BD en MongoDB
- Intenta conectarte directamente: `mongosh`

## 🔐 Seguridad

### Para producción:

1. Usa MongoDB Atlas con autenticación
2. Configura IP whitelist
3. Usa `MONGO_URI` con credenciales seguras
4. Nunca commits credenciales en Git
5. Activa autenticación en MongoDB local

### .env (nunca commits esto)

```bash
# Archivo .env - NO subir a Git
MONGO_URI=mongodb+srv://usuario:PASSWORD@cluster.mongodb.net/meditrack
```

## 📖 Enlaces útiles

- [MongoDB Docs](https://docs.mongodb.com/)
- [PyMongo](https://pymongo.readthedocs.io/)
- [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
- [MongoDB Docker](https://hub.docker.com/_/mongo)

---

**¿Problemas?** Revisa los logs en la terminal al ejecutar `python run.py`
