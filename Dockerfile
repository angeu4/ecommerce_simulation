FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create logs directory and give write permissions
RUN mkdir -p /app/logs && chmod 777 /app/logs

ENV PYTHONPATH=/app

# Run the app with uvicorn, ensuring logs integrate with Python logging
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]