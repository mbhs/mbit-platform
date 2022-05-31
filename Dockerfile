FROM python:3.10-slim-bullseye

RUN apt-get update && apt-get install -y libpq-dev gcc
RUN pip install pipenv

WORKDIR /app
COPY Pipfile ./
RUN pipenv lock --pre --clear
RUN pipenv --three install --system --deploy --ignore-pipfile

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "mbit.asgi:application"]
