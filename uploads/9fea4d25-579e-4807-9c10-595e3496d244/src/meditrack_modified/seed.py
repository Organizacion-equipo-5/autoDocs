"""
seed.py
Pobla la base de datos con datos de prueba para desarrollo.

Uso: python seed.py
"""
import os
import sys
from datetime import datetime, timezone, timedelta

# Asegura que el path incluye la raíz del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.services.auth_service import AuthService, bcrypt
from app.repository.user_repository import UserRepository
from app.repository.medication_repository import MedicationRepository
from app.models.medication import MedicationModel
from bson import ObjectId


def seed():
    app = create_app()
    with app.app_context():
        user_repo = UserRepository()
        med_repo = MedicationRepository()
        auth_service = AuthService()

        print("🌱 Iniciando seed de MediTrack...\n")

        # ---------------------------------------------------------- #
        # Usuarios                                                     #
        # ---------------------------------------------------------- #
        usuarios = [
            {
                "nombre": "Admin", "apellido": "Sistema",
                "email": "admin@meditrack.com", "password": "Admin123",
                "rol": "admin",
            },
            {
                "nombre": "Don", "apellido": "Roberto",
                "email": "roberto@test.com", "password": "Test1234",
                "rol": "adulto", "telefono": "555-0001",
            },
            {
                "nombre": "María", "apellido": "López",
                "email": "maria@test.com", "password": "Test1234",
                "rol": "familiar", "telefono": "555-0002",
            },
            {
                "nombre": "Dr. Carlos", "apellido": "Ramírez",
                "email": "dr.carlos@test.com", "password": "Test1234",
                "rol": "medico",
            },
        ]

        ids = {}
        for u in usuarios:
            if user_repo.exists({"email": u["email"]}):
                existing = user_repo.find_by_email(u["email"])
                ids[u["rol"]] = str(existing["_id"])
                print(f"  ⚠️  Ya existe: {u['email']}")
                continue
            user, err = auth_service.register(u)
            if err:
                print(f"  ❌ Error creando {u['email']}: {err}")
            else:
                ids[u["rol"]] = user["_id"]
                print(f"  ✅ Usuario creado: {u['email']} ({u['rol']})")

        # ---------------------------------------------------------- #
        # Vínculos                                                     #
        # ---------------------------------------------------------- #
        if "adulto" in ids and "familiar" in ids:
            user_repo.link_familiar(ids["adulto"], ids["familiar"])
            print("\n  🔗 Familiar vinculado a adulto")
        if "adulto" in ids and "medico" in ids:
            user_repo.assign_medico(ids["adulto"], ids["medico"])
            print("  🔗 Médico asignado a adulto")

        # ---------------------------------------------------------- #
        # Medicamentos                                                 #
        # ---------------------------------------------------------- #
        if "adulto" in ids:
            adulto_oid = ObjectId(ids["adulto"])
            meds_data = [
                {
                    "nombre": "Metformina 500mg",
                    "forma": "tableta", "dosis": "1 tableta",
                    "frecuencia": "cada_12h", "horarios": ["08:00", "20:00"],
                    "indicaciones": "Tomar con alimentos", "con_alimentos": True,
                },
                {
                    "nombre": "Losartán 50mg",
                    "forma": "tableta", "dosis": "1 tableta",
                    "frecuencia": "cada_24h", "horarios": ["08:00"],
                    "indicaciones": "Para la presión arterial",
                },
                {
                    "nombre": "Vitamina D3",
                    "forma": "capsula", "dosis": "1 cápsula",
                    "frecuencia": "cada_24h", "horarios": ["08:00"],
                },
            ]
            for md in meds_data:
                doc = MedicationModel.schema(
                    adulto_id=adulto_oid,
                    prescrito_por=ObjectId(ids["medico"]) if "medico" in ids else None,
                    fecha_inicio=datetime.now(timezone.utc) - timedelta(days=30),
                    **md,
                )
                med_repo.create(doc)
                print(f"  💊 Medicamento creado: {md['nombre']}")

        print("\n✨ Seed completado exitosamente!")
        print("\nCredenciales de acceso:")
        print("  Admin:    admin@meditrack.com  / Admin123")
        print("  Adulto:   roberto@test.com     / Test1234")
        print("  Familiar: maria@test.com       / Test1234")
        print("  Médico:   dr.carlos@test.com   / Test1234")


if __name__ == "__main__":
    seed()
