FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY config.py main_orchestrator.py neuro_agent.py web_app.py ./
COPY express_parser.py ingest_graph.py ./
COPY ids_pipeline.py ids_models.py ids_serializer.py ids_validator.py ./
COPY ucks_models.py ucks_pipeline.py ./
COPY templates/ templates/
COPY data/ids.xsd data/ids.xsd
COPY data/ucks_entities/ data/ucks_entities/

# Create output directories
RUN mkdir -p data/ids_output data/ucks_entities

# Cloud Run sets PORT env var (default 8080)
ENV PORT=8080

EXPOSE 8080

CMD exec gunicorn --bind :$PORT --workers 2 --threads 4 --timeout 120 web_app:app
