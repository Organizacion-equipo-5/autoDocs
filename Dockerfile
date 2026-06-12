FROM python:3.12-slim

WORKDIR /app

# System deps for weasyprint (PDF generation), git, and PlantUML (requires Java)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libgdk-pixbuf-xlib-2.0-0 libffi-dev \
    git \
    wget \
    nodejs \
    npm \
    openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# Install PlantUML
RUN wget -O /usr/local/bin/plantuml.jar https://github.com/plantuml/plantuml/releases/download/v1.2024.5/plantuml-1.2024.5.jar && \
    chmod +x /usr/local/bin/plantuml.jar

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 300 -r requirements.txt

COPY . .

RUN npm install --no-audit --no-fund

RUN mkdir -p uploads exports

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:create_app()"]