"""Monitoreo de AutoDocs AI.

Expone:
  GET /health   -> estado del servicio (para Render, UptimeRobot, etc.)
  GET /metrics  -> metricas en formato de texto Prometheus

No requiere dependencias adicionales: los contadores viven en memoria
por proceso (gunicorn usa 2 workers, cada uno reporta los suyos).
"""
import os
import threading
import time
from collections import defaultdict

from flask import Blueprint, Response, current_app, g, jsonify, request

monitoring_bp = Blueprint("monitoring", __name__)

_STARTED_AT = time.time()
_LOCK = threading.Lock()
_REQUESTS = defaultdict(int)          # (metodo, codigo) -> total
_LATENCY_SUM = defaultdict(float)     # metodo -> segundos acumulados
_LATENCY_COUNT = defaultdict(int)     # metodo -> peticiones medidas
_ERRORS_5XX = 0

_SKIP_PATHS = ("/health", "/metrics", "/static/")


def _check_mongo():
    """Devuelve ('up'|'down', milisegundos)."""
    start = time.perf_counter()
    try:
        from pymongo import MongoClient

        client = MongoClient(
            current_app.config["MONGO_URI"], serverSelectionTimeoutMS=1500
        )
        client.admin.command("ping")
        client.close()
        status = "up"
    except Exception:
        status = "down"
    return status, round((time.perf_counter() - start) * 1000, 1)


@monitoring_bp.route("/health")
def health():
    mongo_status, mongo_ms = _check_mongo()
    ok = mongo_status == "up"
    body = {
        "status": "ok" if ok else "degraded",
        "version": os.environ.get("APP_VERSION", "dev"),
        "uptime_seconds": int(time.time() - _STARTED_AT),
        "checks": {"mongodb": {"status": mongo_status, "latency_ms": mongo_ms}},
    }
    return jsonify(body), (200 if ok else 503)


@monitoring_bp.route("/metrics")
def metrics():
    lines = [
        "# HELP autodocs_uptime_seconds Segundos desde el arranque del proceso.",
        "# TYPE autodocs_uptime_seconds gauge",
        f"autodocs_uptime_seconds {int(time.time() - _STARTED_AT)}",
        "# HELP autodocs_http_requests_total Peticiones HTTP por metodo y codigo.",
        "# TYPE autodocs_http_requests_total counter",
    ]
    with _LOCK:
        for (method, code), total in sorted(_REQUESTS.items()):
            lines.append(
                f'autodocs_http_requests_total{{method="{method}",status="{code}"}} {total}'
            )
        lines += [
            "# HELP autodocs_http_request_duration_seconds_sum Tiempo total de respuesta.",
            "# TYPE autodocs_http_request_duration_seconds_sum counter",
        ]
        for method, total in sorted(_LATENCY_SUM.items()):
            lines.append(
                f'autodocs_http_request_duration_seconds_sum{{method="{method}"}} {total:.6f}'
            )
        lines += [
            "# HELP autodocs_http_request_duration_seconds_count Peticiones medidas.",
            "# TYPE autodocs_http_request_duration_seconds_count counter",
        ]
        for method, total in sorted(_LATENCY_COUNT.items()):
            lines.append(
                f'autodocs_http_request_duration_seconds_count{{method="{method}"}} {total}'
            )
        lines += [
            "# HELP autodocs_http_errors_5xx_total Respuestas con error de servidor.",
            "# TYPE autodocs_http_errors_5xx_total counter",
            f"autodocs_http_errors_5xx_total {_ERRORS_5XX}",
        ]
    return Response("\n".join(lines) + "\n", mimetype="text/plain; version=0.0.4")


def init_monitoring(app):
    """Registra el blueprint y los hooks que miden cada peticion."""
    app.register_blueprint(monitoring_bp)

    @app.before_request
    def _start_timer():
        g._t0 = time.perf_counter()

    @app.after_request
    def _record(response):
        global _ERRORS_5XX
        if request.path.startswith(_SKIP_PATHS):
            return response
        elapsed = time.perf_counter() - getattr(g, "_t0", time.perf_counter())
        with _LOCK:
            _REQUESTS[(request.method, response.status_code)] += 1
            _LATENCY_SUM[request.method] += elapsed
            _LATENCY_COUNT[request.method] += 1
            if response.status_code >= 500:
                _ERRORS_5XX += 1
        return response
