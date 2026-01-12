FROM python:3.11-slim

# set work directory
WORKDIR /app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
# ffmpeg is needed for pydub to work with audio files
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Copy and install Python dependencies
COPY ./requirements.txt /app
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app

# Create necessary directories
RUN mkdir -p uploads reports

# Make scripts executable
RUN chmod +x start.sh start-dev.sh

EXPOSE 8000

CMD ["./start.sh"]
