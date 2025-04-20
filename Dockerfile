ARG BASE_IMG=alpine:3.19.1

# Build stage
FROM alpine:3.19.1 AS builder
RUN apk --no-cache add alpine-sdk=1.0.16-r0
WORKDIR /build
RUN git clone --depth 1 --single-branch "https://github.com/ZentriaMC/pidproxy.git" . && \
    sed -i 's/-mtune=generic/-mtune=native/g' Makefile && \
    make "-j$(nproc)" && \
    strip pidproxy

# Final stage
FROM alpine:3.19.1
RUN apk --no-cache --update --no-progress add \
    vsftpd=3.0.5-r3 \
    tini=0.19.0-r1 && \
    rm -rf /var/cache/apk/* && \
    mkdir -p /ftp/ftp && \
    addgroup -g 1000 ftpuser && \
    adduser -D -h /ftp -G ftpuser -u 1000 -s /sbin/nologin ftpuser && \
    chown -R ftpuser:ftpuser /ftp

COPY --from=builder /build/pidproxy /usr/bin/pidproxy
COPY start_vsftpd.sh /bin/
COPY vsftpd.conf /etc/vsftpd/

RUN chmod +x /bin/start_vsftpd.sh

# TCP control port and passive port range
EXPOSE 21 30000-31000

# Mount point for FTP directory
VOLUME /ftp/ftp

# Resource limits
ENV VSFTPD_MAX_CLIENTS=200 \
    VSFTPD_MAX_PER_IP=20 \
    GOMAXPROCS=2

# Use tini as init system
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/bin/start_vsftpd.sh"]

# Health check with minimal overhead
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD nc -w 2 -zv localhost 21 || exit 1

# Set user for better security
USER ftpuser
