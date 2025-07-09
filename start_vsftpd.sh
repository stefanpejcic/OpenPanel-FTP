#!/bin/sh

print_banner() {
  echo "-------------------------------------------"
  echo "            Starting FTP server            "
  echo "-------------------------------------------"
}

print_banner

# not needed on startup!
#echo "[*] Removing all existing FTP users..."
#grep '/ftp/' /etc/passwd | cut -d':' -f1 | xargs -r -n1 deluser

# Function to determine if a hostname is a FQDN
is_fqdn() {
  if [[ $1 =~ ^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
    return 0
  else
    return 1
  fi
}

# Function to get the server's IP address
get_ip_address() {
  hostname -i
}

# Function to read users from users.list files and create them
create_users() {
  USER_LIST_FILES=$(find /etc/openpanel/ftp/users/ -name 'users.list')

  USER_COUNT=0
  echo "[*] Creating users from users.list files..."
  for USER_LIST_FILE in $USER_LIST_FILES; do
    echo "[*] Processing user list file: $USER_LIST_FILE"
    BASE_DIR=$(dirname "$USER_LIST_FILE")
    while IFS='|' read -r NAME HASHED_PASS FOLDER UID GID; do
      [ -z "$NAME" ] && continue  # Skip empty lines

      echo "[*] Creating user: $NAME"

      GROUP=$NAME

      if [ -z "$FOLDER" ]; then
        FOLDER="/ftp/$NAME"
        echo "    - No folder specified, using default: $FOLDER"
      fi

      # Ensure the folder starts with /home and matches the base directory
      if [[ $FOLDER != /home/* ]] || [[ ! $FOLDER == "$BASE_DIR"* ]]; then
        echo "    - Skipping user $NAME: folder $FOLDER does not match base directory $BASE_DIR or does not start with /home"
        continue
      fi

      if [ ! -z "$UID" ]; then
        UID_OPT="-u $UID"
        if [ -z "$GID" ]; then
          GID=$UID
        fi
        GROUP=$(getent group $GID | cut -d: -f1)
        if [ ! -z "$GROUP" ]; then
          GROUP_OPT="-G $GROUP"
        elif [ ! -z "$GID" ]; then
          echo "    - Creating group $NAME with GID $GID"
          addgroup -g $GID $NAME
          GROUP_OPT="-G $NAME"
        fi
      fi

      echo "    - Adding user with home folder $FOLDER"
      adduser -h "$FOLDER" -s /sbin/nologin $UID_OPT $GROUP_OPT --disabled-password --gecos "" "$NAME"

      echo "    - Setting encrypted password"
      usermod -p "$HASHED_PASS" "$NAME"

      echo "    - Ensuring folder exists and ownership is correct"
      mkdir -p "$FOLDER"
      chown "$NAME:$GROUP" "$FOLDER"

      USER_COUNT=$((USER_COUNT + 1))

      unset NAME HASHED_PASS FOLDER UID GID GROUP UID_OPT GROUP_OPT
    done < "$USER_LIST_FILE"
  done

  if [ "$USER_COUNT" -gt 0 ]; then
    echo "[*] User creation complete: $USER_COUNT users created."
  else
    echo "[*] No users found to create."
  fi
}

# Call the function to create users
create_users

# Set default passive mode port range if not specified
if [ -z "$MIN_PORT" ]; then
  MIN_PORT=21000
fi

if [ -z "$MAX_PORT" ]; then
  MAX_PORT=21010
fi
echo "[*] Passive mode port range: $MIN_PORT-$MAX_PORT"

# Determine the address if not provided
if [ -z "$ADDRESS" ]; then
  HOSTNAME=$(hostname)
  echo "[*] Hostname detected: $HOSTNAME"
  if is_fqdn "$HOSTNAME"; then
    ADDRESS="$HOSTNAME"
    echo "[*] Using hostname as passive address: $ADDRESS"
  else
    ADDRESS=$(get_ip_address)
    echo "[*] Using IP address as passive address: $ADDRESS"
  fi
else
  echo "[*] Using provided passive address: $ADDRESS"
fi

# Configure address and TLS options
if [ ! -z "$ADDRESS" ]; then
  ADDR_OPT="-opasv_address=$ADDRESS"
fi

if [ ! -z "$TLS_CERT" ] || [ ! -z "$TLS_KEY" ]; then
  echo "[*] TLS certificates found, enabling TLS options"
  TLS_OPT="-orsa_cert_file=$TLS_CERT -orsa_private_key_file=$TLS_KEY -ossl_enable=YES -oallow_anon_ssl=NO -oforce_local_data_ssl=YES -oforce_local_logins_ssl=YES -ossl_tlsv1=NO -ossl_sslv2=NO -ossl_sslv3=NO -ossl_ciphers=HIGH"
else
  echo "[*] No TLS certificates found, running without TLS"
fi

# Used to run custom commands inside container
if [ ! -z "$1" ]; then
  echo "[*] Executing custom command: $*"
  exec "$@"
else
  echo "[*] Starting vsftpd and accepting user logins..."
  vsftpd -opasv_min_port=$MIN_PORT -opasv_max_port=$MAX_PORT $ADDR_OPT $TLS_OPT /etc/vsftpd/vsftpd.conf
  [ -d /var/run/vsftpd ] || mkdir /var/run/vsftpd
  pgrep vsftpd | tail -n 1 > /var/run/vsftpd/vsftpd.pid
  exec pidproxy /var/run/vsftpd/vsftpd.pid true
fi
