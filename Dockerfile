# Use a lightweight Python base image
FROM python:3.10-slim

# Install system dependencies (FFmpeg, curl, git)
RUN apt-get update && apt-get install -y \
    ffmpeg curl git && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

ENV PORT=8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

