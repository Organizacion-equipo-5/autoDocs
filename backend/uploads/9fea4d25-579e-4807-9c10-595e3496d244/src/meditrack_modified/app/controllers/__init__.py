from .auth_controller import auth_bp
from .user_controller import user_bp
from .medication_controller import med_bp
from .medication_log_controller import log_bp
from .iot_controller import iot_bp
from .notification_controller import notif_bp

__all__ = ["auth_bp", "user_bp", "med_bp", "log_bp", "iot_bp", "notif_bp"]
