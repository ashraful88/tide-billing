# Use Python 3.12 slim image for smaller size
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libc6-dev \
        libpq-dev \
        curl \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -r app && useradd -r -g app app

# Set work directory
WORKDIR /code

# Install Python dependencies
COPY requirements.txt /code/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /code/

# Create necessary directories.
# /code/beat is where celery beat persists its schedule; it must exist (and be
# owned by `app`) in the image so the named volume mounted over it inherits
# that ownership rather than defaulting to root.
RUN mkdir -p /code/staticfiles /code/media /code/logs /code/beat

# Change ownership to app user
RUN chown -R app:app /code

# Switch to app user
USER app

# Collect static files into the same location the runtime volume mounts, so the
# build-time and run-time output agree.
ENV STATIC_ROOT=/code/staticfiles \
    MEDIA_ROOT=/code/media \
    LOG_DIR=/code/logs
RUN python tidebilling/manage.py collectstatic --noinput

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Expose port
EXPOSE 8000

# Default command
CMD ["gunicorn", "--chdir", "tidebilling", "--bind", "0.0.0.0:8000", "--workers", "3", "tidebilling.wsgi:application"]