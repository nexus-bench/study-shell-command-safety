FROM python:3.12.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git bubblewrap && rm -rf /var/lib/apt/lists/*
COPY corpus.py oracle.py observe.py control.py /observer/
RUN chmod -R go-rwx /observer && mkdir /world
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python3", "/observer/control.py"]
