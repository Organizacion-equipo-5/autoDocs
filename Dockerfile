FROM python:3.12-slim-bookworm

WORKDIR /app

# System deps for weasyprint (PDF generation), git, and PlantUML (requires Java)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libgdk-pixbuf-2.0-0 libffi-dev \
    git \
    wget \
    nodejs \
    npm \
    openjdk-17-jre-headless \
    graphviz \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install PlantUML
# Version fijada; la descarga es por HTTPS. chmod 644: es un JAR, no un ejecutable.
RUN wget -q -O /usr/local/bin/plantuml.jar https://github.com/plantuml/plantuml/releases/download/v1.2024.5/plantuml-1.2024.5.jar && \
    chmod 644 /usr/local/bin/plantuml.jar

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 300 -r requirements.txt

COPY . .

RUN npm ci --no-audit --no-fund

# Ejecutar como usuario sin privilegios
RUN useradd --create-home --uid 10001 appuser && \
    mkdir -p uploads exports && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "300", "app:create_app()"]