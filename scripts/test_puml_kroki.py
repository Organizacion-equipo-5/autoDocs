import urllib.request
import urllib.error

def test_puml(name, puml):
    print(f"\nProbando diagrama: {name}")
    try:
        req = urllib.request.Request(
            "https://kroki.io/plantuml/png",
            data=puml.encode("utf-8"),
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "image/png"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            print(f"[EXITO Kroki] Status: {resp.status}, bytes: {len(data)}, PNG valid: {data.startswith(b'\x89PNG')}")
    except urllib.error.HTTPError as e:
        print(f"[ERROR Kroki] HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}")
    except Exception as e:
        print(f"[ERROR Kroki] {e}")

infra_puml = """@startuml
skinparam componentStyle rectangle
package "Cliente / Frontend" {
  [Navegador Web] as browser
  [App Móvil] as mobile
  [CLI / Clientes API] as cli
}
package "API / Backend" {
  [Controladores / Rutas] as routes
  [Servicios / Lógica de Negocio] as logic
  routes --> logic
}
database "Base de Datos" as db
database "Caché en Memoria" as cache
[Servicios Externos / APIs] as ext
logic --> db
logic --> cache
logic --> ext
browser --> routes
mobile --> routes
cli --> routes
@enduml"""

use_case_puml = """@startuml
left to right direction
actor "Usuario / Cliente" as user
rectangle "Sistema AutoDocs" {
  usecase "Autenticarse" as UC1
  usecase "Listar Proyectos" as UC2
  usecase "Generar Documentación" as UC3
  usecase "Exportar PDF" as UC4
}
user --> UC1
user --> UC2
user --> UC3
user --> UC4
@enduml"""

class_puml = """@startuml
class "UserModel" {
  +verify_password()
  +to_dict()
}
class "ProjectModel" {
  +save()
  +delete()
}
@enduml"""

star_puml = """@startuml
skinparam backgroundColor #FEFEFE
skinparam rectangle {
  BorderColor #3b82f6
  BackgroundColor #f8fafc
}
title Diagrama Estrella de Data Warehouse

rectangle "UserModel" as fact <<Fact Table>> {
  **Fact Table**
  -- verify_password
}

rectangle "ProjectModel" as projectmodel <<Dimension>> {
  **Dimension**
  -- save
}

projectmodel --> fact : FK
@enduml"""

test_puml("Infraestructura", infra_puml)
test_puml("Casos de Uso", use_case_puml)
test_puml("Clases", class_puml)
test_puml("Estrella", star_puml)
