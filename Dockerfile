ARG BASE_IMG=alpine:3.19.1

FROM $BASE_IMG:3.19.1 AS pidproxy

RUN apk --no-cache add alpine-sdk=1.0.16-r0
WORKDIR /tmp
RUN git clone https://github.com/ZentriaMC/pidproxy.git
WORKDIR /tmp/pidproxy
RUN git checkout 193e5080e3e9b733a59e25d8f7ec84aee374b9bb \
  && sed -i 's/-mtune=generic/-mtune=native/g' Makefile \
  && make \
  && mv pidproxy /usr/bin/pidproxy
WORKDIR /tmp
RUN rm -rf pidproxy \
  && apk del alpine-sdk


FROM ${BASE_IMG}:3.19.1 AS builder
# Build steps here

FROM ${BASE_IMG}:3.19.1
COPY --from=pidproxy /usr/bin/pidproxy /usr/bin/pidproxy
COPY --from=builder /path/to/needed/files /
RUN apk --no-cache add vsftpd=3.0.5-r3 tini=0.19.0-r1

COPY start_vsftpd.sh /bin/start_vsftpd.sh
RUN chmod +x /bin/start_vsftpd.sh
COPY vsftpd.conf /etc/vsftpd/vsftpd.conf

# Create ftp user for the container
RUN addgroup -g 1000 ftpuser && \
    adduser -D -h /ftp -G ftpuser -u 1000 -s /sbin/nologin ftpuser && \
    mkdir -p /ftp/ftp && \
    chown -R ftpuser:ftpuser /ftp

EXPOSE 21 21000-21010
VOLUME /ftp/ftp

HEALTHCHECK --interval=30s --timeout=10s \
  CMD nc -z localhost 21 || exit 1

USER ftpuser

ENTRYPOINT ["/sbin/tini", "--", "/bin/start_vsftpd.sh"]
