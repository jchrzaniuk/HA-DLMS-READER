FROM python:3.13.9-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DLMS_DATA=/data DLMS_BIND=0.0.0.0
WORKDIR /opt/dlms
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["python", "-m", "app"]
