ARG REPOSITORY=harnesssolutionfactory/
ARG IMAGE=harness-python-api-sdk
ARG BASE_TAG=latest
ARG MODULE=src

FROM ${REPOSITORY}${IMAGE}:${BASE_TAG} AS base

FROM base AS test
WORKDIR /app
COPY /requirements.txt /app/requirements.txt
RUN python -m pip install -r requirements.txt
COPY . /app/

FROM base AS release
WORKDIR /app
COPY /requirements.txt /app/requirements.txt
RUN python -m pip install -r requirements.txt
COPY . /app/
COPY config.toml /app/
ENTRYPOINT ["python","/app/main.py"]

USER 1000
