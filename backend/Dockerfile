FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# pywebview requires some system libraries even for import
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libgirepository1.0-dev \
    libcairo2-dev \
    pkg-config \
    gir1.2-gtk-3.0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from the root context
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ backend/

# setup config
# We copy the example config as a default.
# The actual config can be mounted at runtime.
COPY cfg.json.example cfg.json

# Environment variables
ENV FLASK_APP=backend.app
ENV PYTHONPATH=/app
ENV UNBUFFERED=1

# Expose port
EXPOSE 5000

# Command to run the application
CMD ["flask", "run", "--host=0.0.0.0"]
