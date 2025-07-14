# Use official Python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    procps \
    libxss1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to cache dependencies
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy your app code
COPY . .

# Railway provides PORT environment variable
ENV PORT=5000
EXPOSE $PORT

# Allow selecting script at runtime
ENV APP_FILE=app.py
SHELL ["/bin/bash", "-c"]
CMD python $APP_FILE

