# Doors, for an online demo: the server of this repository, in recorded mode.
#
#   docker build -t doors .
#   docker run --rm -p 8000:8000 doors        # then open http://127.0.0.1:8000/
#
# No key and no secret go into the image or into its configuration. The server starts in recorded mode (DOORS_AI=recorded):
# no request leaves the container, whatever else the environment holds.
FROM python:3.12.15-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    DOORS_AI=recorded \
    PORT=8000

WORKDIR /app

# The dependencies first: this layer is built again only when requirements.txt changes.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# The rest of the repository, less what .dockerignore keeps out.
COPY . .

# The server runs as a user with no rights over the files, and writes nothing: recorded mode keeps no log and no file.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin doors
USER doors

EXPOSE 8000

# It listens on every interface, on the port the platform gives in $PORT (Render sets it; 8000 here by default).
# `exec` makes the server itself the process that receives the stop signal of the platform.
CMD ["sh", "-c", "exec python -m api --host 0.0.0.0 --port ${PORT}"]
