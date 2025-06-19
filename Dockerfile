# Use official Python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements first to cache dependencies
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your app code
COPY . .

# Expose the port (e.g. Flask default is 5000)
EXPOSE 5000

# Allow selecting script at runtime
ENV APP_FILE=app.py
SHELL ["/bin/bash", "-c"]
CMD python $APP_FILE

