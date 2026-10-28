# authwatch: standard library only, so the image is Python and one package.
FROM python:3.14.10-slim@sha256:3cabfd7d7aaf394e6040e79fa1eec6ca1c52b74ed9188650472695d9a9326999

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY authwatch/ /app/authwatch/

# nobody; compose adds the group that can read the auth log.
USER 65534:65534
ENTRYPOINT ["python", "-m", "authwatch"]
