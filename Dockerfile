# A Docker image capable of running all GRR components.
#
# See https://hub.docker.com/r/grrdocker/grr/
#
# We have configured Travis to trigger an image build every time a new server
# deb is been uploaded to GCS.
#
# Run the container with:
#
# docker run \
#    -e EXTERNAL_HOSTNAME="localhost" \
#    -e ADMIN_PASSWORD="demo" \
#    -p 0.0.0.0:8000:8000 \
#    -p 0.0.0.0:8080:8080 \
#    grrdocker/grr

FROM ubuntu:xenial

LABEL org.opencontainers.image.source https://github.com/nexus-lab/relf-server

WORKDIR /grr

SHELL [ "/bin/bash", "-c" ]

RUN apt-get update && \
    apt-get install -y \
    fakeroot \
    debhelper \
    libffi-dev \
    libssl-dev \
    python-dev \
    python-pip \
    openjdk-8-jdk \
    zip \
    git \
    devscripts \
    dh-systemd \
    libc6-i386 \
    lib32z1 \
    curl && \
    rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_7.x | /bin/bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN pip install pip==20.3.4

RUN cd /usr && \
    curl -fsSLO "https://github.com/google/protobuf/releases/download/v3.3.0/protoc-3.3.0-linux-x86_64.zip" && \
    unzip protoc-3.3.0-linux-x86_64.zip && \
    rm protoc-3.3.0-linux-x86_64.zip

ADD . /grr

RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir -e grr/config/grr-response-client/ && \
    pip install --no-cache-dir -e api_client/python/ && \
    pip install --no-cache-dir -e grr/config/grr-response-server/ && \
    pip install --no-cache-dir -e grr/config/grr-response-test/ && \
    python makefile.py && \
    cd grr/artifacts && python makefile.py && cd -

RUN mkdir -p /etc/grr && cp install_data/etc/* /etc/grr

EXPOSE 8000
EXPOSE 8080

VOLUME /etc/grr
VOLUME /var/log
VOLUME /var/grr-datastore

ENTRYPOINT [ "/grr/scripts/docker-entrypoint.sh" ]

CMD [ "grr" ]
