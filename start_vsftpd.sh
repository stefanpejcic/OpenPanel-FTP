#!/bin/bash
set -euo pipefail

# Constants
readonly CONFIG_FILE="/etc/vsftpd/vsftpd.conf"
readonly VSFTPD_BIN="/usr/sbin/vsftpd"
readonly MIN_PORT=30000
readonly MAX_PORT=31000

# Performance optimizations
ulimit -n 65535  # Increase open file limit
ulimit -s 8192   # Optimize stack size

log() {
    printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${1-}" >&2
}

fail() {
    log "ERROR: ${1-}"
    exit "${2-1}"
}

validate_file() {
    local file="${1-}"
    [[ -f "${file}" ]] || fail "File not found: ${file}"
    [[ -r "${file}" ]] || fail "File not readable: ${file}"
}

setup_tls() {
    local cert="${1-}" key="${2-}"
    validate_file "${cert}"
    validate_file "${key}"

    printf '%s ' \
        "-orsa_cert_file=${cert}" \
        "-orsa_private_key_file=${key}" \
        "-ossl_enable=YES" \
        "-oforce_local_data_ssl=YES" \
        "-oforce_local_logins_ssl=YES" \
        "-ossl_ciphers=HIGH"
}

# Ensure necessary directories exist
mkdir -p /etc/vsftpd || true
mkdir -p /var/log/vsftpd || true
mkdir -p /etc/openpanel/ftp/users || true
touch /var/log/vsftpd/vsftpd.log || true
chmod 644 /var/log/vsftpd/vsftpd.log || true

generate_user_config() {
    local owner="$1"
    local username="$2"
    local directory="$3"
    local user_config_dir="/etc/vsftpd/users_config/${owner}"
    local user_config_file="${user_config_dir}/${username}"

    mkdir -p "${user_config_dir}"

    cat << EOF > "${user_config_file}"
local_root=${directory}
write_enable=YES
chroot_local_user=YES
allow_writeable_chroot=YES
EOF

    echo "Generated config for ${username} (${owner}) at ${user_config_file}"
}

update_vsftpd_db() {
    echo "Updating vsftpd user database..."
    local db_file="/etc/vsftpd/virtual_users.db"
    local txt_file="/etc/vsftpd/virtual_users.txt"

    true > "${txt_file}"
    rm -f "${db_file}"

    if [[ -d "/etc/openpanel/ftp/users" ]]; then
        find "/etc/openpanel/ftp/users" -mindepth 1 -maxdepth 1 -type d | while read -r user_dir; do
            local owner
            owner=$(basename "${user_dir}")
            local user_list="${user_dir}/users.list"

            if [[ -f "${user_list}" ]]; then
                while IFS='|' read -r username password_hash directory || [[ -n "${username}" ]]; do
                    if [[ -n "${username}" ]] && [[ -n "${password_hash}" ]]; then
                        echo "Processing FTP user: ${username} for owner: ${owner}"
                        echo "${username}" >> "${txt_file}"
                        echo "${password_hash}" >> "${txt_file}"

                        local ftp_dir="${directory:-/ftp/${username}}"
                        generate_user_config "${owner}" "${username}" "${ftp_dir}"
                    else
                        echo "Skipping invalid line in ${user_list}"
                    fi
                done < "${user_list}"
            fi
        done
    fi

    if [[ -s "${txt_file}" ]]; then
        db_load -T -t hash -f "${txt_file}" "${db_file}"
        chmod 600 "${txt_file}" "${db_file}"
        echo "vsftpd user database updated successfully."
    else
        echo "No users found to update the database."
        touch "${db_file}"
        chmod 600 "${db_file}"
    fi
}

update_vsftpd_db

main() {
    command -v "${VSFTPD_BIN}" >/dev/null 2>&1 || fail "vsftpd not found"
    validate_file "${CONFIG_FILE}"

    local tls_opts=""
    if [[ -n "${TLS_CERT-}" ]] && [[ -n "${TLS_KEY-}" ]]; then
        tls_opts=$(setup_tls "${TLS_CERT}" "${TLS_KEY}") || fail "TLS setup failed"
    fi

    local port_opts="-opasv_min_port=${MIN_PORT} -opasv_max_port=${MAX_PORT}"

    true > "${CONFIG_FILE}"

    cat << EOF >> "${CONFIG_FILE}"
listen=YES
listen_ipv6=NO

anonymous_enable=NO
local_enable=YES
write_enable=YES
dirmessage_enable=YES
use_localtime=YES
xferlog_enable=YES
connect_from_port_20=YES

xferlog_file=/var/log/vsftpd/vsftpd.log
xferlog_std_format=YES
log_ftp_protocol=YES

seccomp_sandbox=NO

pam_service_name=vsftpd
guest_enable=YES
guest_username=vsftpd
virtual_use_local_privs=YES
user_config_dir=/etc/vsftpd/users_config

ls_recurse_enable=YES

pasv_enable=YES
EOF

    if [[ -n "${PASV_ADDRESS:-}" ]]; then
        echo "pasv_address=${PASV_ADDRESS}" >> "${CONFIG_FILE}"
    fi

    if [[ -n "${PASV_MIN_PORT:-}" ]] && [[ -n "${PASV_MAX_PORT:-}" ]]; then
        echo "pasv_min_port=${PASV_MIN_PORT}" >> "${CONFIG_FILE}"
        echo "pasv_max_port=${PASV_MAX_PORT}" >> "${CONFIG_FILE}"
    fi

    if [[ -n "${SSL_ENABLE:-}" ]] && [[ "${SSL_ENABLE}" = "YES" ]]; then
        echo "ssl_enable=YES" >> "${CONFIG_FILE}"
        echo "allow_anon_ssl=NO" >> "${CONFIG_FILE}"
        echo "force_local_data_ssl=YES" >> "${CONFIG_FILE}"
        echo "force_local_logins_ssl=YES" >> "${CONFIG_FILE}"
        echo "ssl_tlsv1=YES" >> "${CONFIG_FILE}"
        echo "ssl_sslv2=NO" >> "${CONFIG_FILE}"
        echo "ssl_sslv3=NO" >> "${CONFIG_FILE}"
        echo "require_ssl_reuse=NO" >> "${CONFIG_FILE}"
        echo "ssl_ciphers=HIGH" >> "${CONFIG_FILE}"
        if [[ -f "/etc/vsftpd/certs/vsftpd.pem" ]]; then
            echo "rsa_cert_file=/etc/vsftpd/certs/vsftpd.pem" >> "${CONFIG_FILE}"
        else
            echo "Warning: SSL enabled but certificate file /etc/vsftpd/certs/vsftpd.pem not found." >&2
        fi
    fi

    log "Starting vsftpd..."
    exec "${VSFTPD_BIN}" "${tls_opts}" "${port_opts}" "${CONFIG_FILE}"
}

main "$@"
