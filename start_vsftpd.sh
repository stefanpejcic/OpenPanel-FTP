#!/bin/bash -e

# Use set -euo pipefail for better error handling
set -euo pipefail

#Remove all ftp users
grep '/ftp/' /etc/passwd | cut -d':' -f1 | xargs -r -n1 deluser

# Function to determine if a hostname is a FQDN
is_fqdn() {
	if echo "$1" | grep -E '^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$' >/dev/null; then
		return 0
	else
		return 1
	fi
}

# Function to get the server's IP address
get_ip_address() {
	hostname -I | awk '{print $1}'
}

# Function to read users from users.list files and create them
create_users() {
	USER_LIST_FILES=$(find /etc/openpanel/ftp/users/ -name 'users.list')

<<<<<<< Updated upstream
  for USER_LIST_FILE in $USER_LIST_FILES; do
    BASE_DIR=$(dirname "$USER_LIST_FILE")
    OWNER=$(basename "$BASE_DIR")
    while IFS='|' read -r NAME PASS FOLDER UID GID QUOTA_SOFT QUOTA_HARD; do
      [ -z "$NAME" ] && continue  # Skip empty lines

      # All sub-users are in the OpenPanel user's group
      GROUP=$OWNER
=======
	for USER_LIST_FILE in ${USER_LIST_FILES}; do
		BASE_DIR=$(dirname "${USER_LIST_FILE}")
		while IFS='|' read -r NAME PASS FOLDER UID GID; do
			[[ -z ${NAME} ]] && continue # Skip empty lines

			GROUP=${NAME}
>>>>>>> Stashed changes

			if [[ -z ${FOLDER} ]]; then
				FOLDER="/ftp/${NAME}"
			fi

			# Ensure the folder starts with /home and matches the base directory where users.list is found
			if [[ -z "$(echo "${FOLDER}" | grep -E "^/home/")" ]] || [[ -z "$(echo "${FOLDER}" | grep -E "^${BASE_DIR}")" ]]; then
				echo "Skipping user ${NAME}: folder ${FOLDER} does not match base directory ${BASE_DIR} or does not start with /home"
				continue
			fi

<<<<<<< Updated upstream
      # Always use the OpenPanel user's group
      if ! getent group "$GROUP" > /dev/null; then
        addgroup "$GROUP"
      fi

      echo -e "$PASS\n$PASS" | adduser -h "$FOLDER" -s /sbin/nologin "$NAME" -G "$GROUP"
      mkdir -p "$FOLDER"
      chown "$NAME":"$GROUP" "$FOLDER"
      unset NAME PASS FOLDER UID GID GROUP QUOTA_SOFT QUOTA_HARD
    done < "$USER_LIST_FILE"
  done
=======
			if [[ -n ${UID} ]]; then
				UID_OPT="-u ${UID}"
				if [[ -z ${GID} ]]; then
					GID=${UID}
				fi
				GROUP=$(getent group "${GID}" | cut -d: -f1)
				if [[ -n ${GROUP} ]]; then
					GROUP_OPT="-G ${GROUP}"
				elif [[ -n ${GID} ]]; then
					addgroup -g "${GID}" "${NAME}"
					GROUP_OPT="-G ${NAME}"
				fi
			fi

			echo -e "${PASS}\n${PASS}" | adduser -h "${FOLDER}" -s /sbin/nologin "${UID_OPT}" "${GROUP_OPT}" "${NAME}"
			mkdir -p "${FOLDER}"
			chown "${NAME}":"${GROUP}" "${FOLDER}"
			unset NAME PASS FOLDER UID GID GROUP UID_OPT GROUP_OPT
		done <"${USER_LIST_FILE}"
	done
>>>>>>> Stashed changes
}

# Call the function to create users
create_users

# Set default passive mode port range if not specified
if [[ -z ${MIN_PORT} ]]; then
	MIN_PORT=21000
fi

if [[ -z ${MAX_PORT} ]]; then
	MAX_PORT=21010
fi

# Determine the address if not provided
if [[ -z ${ADDRESS} ]]; then
	HOSTNAME=$(hostname)
	if is_fqdn "${HOSTNAME}"; then
		ADDRESS="${HOSTNAME}"
	else
		ADDRESS=$(get_ip_address)
	fi
fi

# Configure address and TLS options
if [[ -n ${ADDRESS} ]]; then
	ADDR_OPT="-opasv_address=${ADDRESS}"
else
<<<<<<< Updated upstream
  vsftpd -opasv_min_port="$MIN_PORT" -opasv_max_port="$MAX_PORT" "$ADDR_OPT" "$TLS_OPT" /etc/vsftpd/vsftpd.conf
  [ -d /var/run/vsftpd ] || mkdir /var/run/vsftpd
  pgrep vsftpd | tail -n 1 > /var/run/vsftpd/vsftpd.pid
  exec pidproxy /var/run/vsftpd/vsftpd.pid true
=======
	ADDR_OPT=""
>>>>>>> Stashed changes
fi

# Initialize TLS_OPT variable
TLS_OPT=""
if [[ -n ${TLS_CERT} ]] || [[ -n ${TLS_KEY} ]]; then
	# Define TLS options as a space-separated string
	TLS_OPT="-orsa_cert_file=${TLS_CERT} -orsa_private_key_file=${TLS_KEY} -ossl_enable=YES -oallow_anon_ssl=NO -oforce_local_data_ssl=YES -oforce_local_logins_ssl=YES -ossl_tlsv1=NO -ossl_sslv2=NO -ossl_sslv3=NO -ossl_ciphers=HIGH"
fi

# Check if vsftpd config file exists
if [[ ! -f /etc/vsftpd.conf ]]; then
	echo "Config file not found" >&2
	exit 1
fi

# Set resource limits (before running vsftpd)
echo "ulimit -n 1024" >>/etc/profile.d/resource-limits.sh

# Run vsftpd with the config file (using exec as the final command)
exec vsftpd "${ADDR_OPT-}" "${TLS_OPT-}" /etc/vsftpd.conf
# Note: The HEALTHCHECK line is a Docker instruction and should be in the Dockerfile, not here
