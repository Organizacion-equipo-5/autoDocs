"""
app/services/notification_service.py
Gestión de notificaciones: in-app, email y (futuro) push.
"""
from datetime import datetime, timezone
from bson import ObjectId
from flask import current_app

from app.repository.notification_repository import NotificationRepository
from app.repository.user_repository import UserRepository
from app.models.notification import NotificationModel


class NotificationService:
    def __init__(self):
        self.notif_repo = NotificationRepository()
        self.user_repo = UserRepository()

    # ------------------------------------------------------------------
    # Crear y enviar notificación
    # ------------------------------------------------------------------
    def crear_notificacion(
        self,
        destinatario_id: str,
        tipo: str,
        titulo: str,
        mensaje: str,
        canal: str = "in_app",
        referencia_id: str = None,
        referencia_tipo: str = "",
    ) -> dict:
        doc = NotificationModel.schema(
            destinatario_id=ObjectId(destinatario_id),
            tipo=tipo,
            titulo=titulo,
            mensaje=mensaje,
            canal=canal,
            referencia_id=ObjectId(referencia_id) if referencia_id else None,
            referencia_tipo=referencia_tipo,
        )
        created = self.notif_repo.create(doc)

        # Intentar envío por email si corresponde
        if canal == "email":
            self._enviar_email(destinatario_id, titulo, mensaje)
            self.notif_repo.update_by_id(
                str(created["_id"]),
                {"enviada": True, "enviado_en": datetime.now(timezone.utc)},
            )
        return NotificationModel.to_response(created)

    # ------------------------------------------------------------------
    # Helpers de notificación automática
    # ------------------------------------------------------------------
    def notificar_omision(self, adulto_id: str, nombre_med: str):
        """Notifica a familiares cuando se omite una toma."""
        adulto = self.user_repo.find_by_id(adulto_id)
        if not adulto:
            return

        nombre_adulto = f"{adulto.get('nombre', '')} {adulto.get('apellido', '')}".strip()
        familiares = self.user_repo.get_familiares_of_adulto(adulto_id)

        for familiar in familiares:
            if not familiar.get("notificaciones", {}).get("email"):
                continue
            self.crear_notificacion(
                destinatario_id=str(familiar["_id"]),
                tipo="toma_omitida",
                titulo=f"Toma omitida: {nombre_med}",
                mensaje=f"{nombre_adulto} omitió tomar {nombre_med}.",
                canal="email",
                referencia_id=adulto_id,
                referencia_tipo="usuario",
            )

    def notificar_recordatorio(self, adulto_id: str, nombre_med: str, horario: str):
        """Recordatorio de toma programada."""
        self.crear_notificacion(
            destinatario_id=adulto_id,
            tipo="recordatorio_medicamento",
            titulo=f"Hora de tomar {nombre_med}",
            mensaje=f"Es hora de tu medicamento: {nombre_med} ({horario}).",
            canal="in_app",
        )

    def notificar_alerta_iot(self, adulto_id: str, tipo_sensor: str, valores: dict):
        """Alerta por lectura anormal de sensor IoT."""
        adulto = self.user_repo.find_by_id(adulto_id)
        if not adulto:
            return
        nombre_adulto = f"{adulto.get('nombre', '')} {adulto.get('apellido', '')}".strip()

        valores_str = ", ".join(f"{k}: {v}" for k, v in valores.items())
        mensaje = f"Alerta de {tipo_sensor}: {valores_str} para {nombre_adulto}."

        # Notificar al adulto
        self.crear_notificacion(
            destinatario_id=adulto_id,
            tipo="alerta_iot",
            titulo=f"Alerta: {tipo_sensor}",
            mensaje=mensaje,
            canal="in_app",
        )

        # Notificar a familiares y médico
        familiares = self.user_repo.get_familiares_of_adulto(adulto_id)
        for persona in familiares:
            self.crear_notificacion(
                destinatario_id=str(persona["_id"]),
                tipo="alerta_iot",
                titulo=f"Alerta IoT: {tipo_sensor}",
                mensaje=mensaje,
                canal="email" if persona.get("notificaciones", {}).get("email") else "in_app",
            )

        if adulto.get("medico_asignado"):
            self.crear_notificacion(
                destinatario_id=str(adulto["medico_asignado"]),
                tipo="alerta_iot",
                titulo=f"Alerta paciente: {tipo_sensor}",
                mensaje=mensaje,
                canal="in_app",
            )

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------
    def mis_notificaciones(self, usuario_id: str, solo_no_leidas: bool = False,
                           page: int = 1, page_size: int = 20) -> dict:
        result = self.notif_repo.find_by_usuario(usuario_id, solo_no_leidas, page, page_size)
        result["items"] = [NotificationModel.to_response(n) for n in result["items"]]
        return result

    def marcar_leida(self, notif_id: str) -> bool:
        return self.notif_repo.marcar_leida(notif_id)

    def marcar_todas_leidas(self, usuario_id: str) -> int:
        return self.notif_repo.marcar_todas_leidas(usuario_id)

    def no_leidas_count(self, usuario_id: str) -> int:
        return self.notif_repo.no_leidas_count(usuario_id)

    # ------------------------------------------------------------------
    # Email (integración Flask-Mail)
    # ------------------------------------------------------------------
    def _enviar_email(self, destinatario_id: str, asunto: str, cuerpo: str):
        try:
            from flask_mail import Message
            from app import mail  # importación diferida para evitar circular imports

            user = self.user_repo.find_by_id(destinatario_id)
            if not user or not user.get("email"):
                return
            if current_app.config.get("TESTING"):
                current_app.logger.info(f"[EMAIL TEST] → {user['email']}: {asunto}")
                return

            msg = Message(subject=asunto, recipients=[user["email"]], body=cuerpo)
            mail.send(msg)
        except Exception as e:
            current_app.logger.error(f"Error enviando email: {e}")
