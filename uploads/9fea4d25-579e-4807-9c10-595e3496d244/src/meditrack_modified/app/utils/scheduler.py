"""
app/utils/scheduler.py
Scheduler de tareas periódicas con APScheduler.
Actualmente: recordatorios de medicamentos y detección de omisiones.
"""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    scheduler = BackgroundScheduler(timezone="UTC")
    SCHEDULER_AVAILABLE = True
except ImportError as e:
    BackgroundScheduler = None
    CronTrigger = None
    scheduler = None
    SCHEDULER_AVAILABLE = False
    logger.warning(
        "APScheduler no está instalado. Las tareas programadas no se ejecutarán. "
        "Para habilitarlas, instala APScheduler en tu entorno."
    )


def init_scheduler(app):
    """Inicializa y arranca el scheduler dentro del contexto de la app."""
    if not SCHEDULER_AVAILABLE:
        logger.warning(
            "Scheduler omitido porque APScheduler no está disponible."
        )
        return

    def recordatorios_medicamentos():
        """Cada minuto revisa qué medicamentos toca tomar en los próximos 5 min."""
        with app.app_context():
            try:
                from app.repository.medication_repository import MedicationRepository
                from app.services.notification_service import NotificationService

                repo = MedicationRepository()
                notif_service = NotificationService()
                ahora = datetime.now(timezone.utc)
                hora_actual = ahora.strftime("%H:%M")

                # Compara horarios de medicamentos activos
                meds = repo.find_activos_con_horario()
                for med in meds:
                    if hora_actual in med.get("horarios", []):
                        adulto_id = str(med["adulto_id"])
                        notif_service.notificar_recordatorio(
                            adulto_id, med["nombre"], hora_actual
                        )
            except Exception as e:
                logger.error(f"Error en recordatorios_medicamentos: {e}")

    def detectar_omisiones():
        """Cada hora busca tomas programadas sin registrar en las últimas 2 horas."""
        with app.app_context():
            try:
                from app.repository.medication_log_repository import MedicationLogRepository
                from app.repository.user_repository import UserRepository
                from app.services.notification_service import NotificationService

                log_repo = MedicationLogRepository()
                user_repo = UserRepository()
                notif_service = NotificationService()

                adultos = user_repo.find_by_rol("adulto")
                for adulto in adultos:
                    adulto_id = str(adulto["_id"])
                    omisiones = log_repo.omisiones_recientes(adulto_id, horas=2)
                    if omisiones:
                        for om in omisiones:
                            from app.repository.medication_repository import MedicationRepository
                            med = MedicationRepository().find_by_id(str(om["medicamento_id"]))
                            if med:
                                notif_service.notificar_omision(adulto_id, med["nombre"])
            except Exception as e:
                logger.error(f"Error en detectar_omisiones: {e}")

    # Registrar jobs
    scheduler.add_job(
        recordatorios_medicamentos,
        CronTrigger(minute="*"),          # cada minuto
        id="recordatorios",
        replace_existing=True,
        misfire_grace_time=30,
    )
    scheduler.add_job(
        detectar_omisiones,
        CronTrigger(minute="0"),          # al inicio de cada hora
        id="omisiones",
        replace_existing=True,
        misfire_grace_time=60,
    )

    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler iniciado: recordatorios y detección de omisiones activos.")
