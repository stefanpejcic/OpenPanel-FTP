#!/bin/sh

#Remove all ftp users
grep '/ftp/' /etc/passwd | cut -d':' -f1 | xargs -r -n1 deluser

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
  hostname -I | awk '{print $1}'
}

# Function to set disk quota for a user
set_user_quota() {
  local USERNAME="$1"
  local SOFT_LIMIT="$2"  # in MB
  local HARD_LIMIT="$3"  # in MB

  # Convert MB to blocks (1 block = 1KB in quota system)
  local SOFT_BLOCKS=$((SOFT_LIMIT * 1024))
  local HARD_BLOCKS=$((HARD_LIMIT * 1024))

  if [ -x "$(command -v setquota)" ]; then
    setquota -u "$USERNAME" $SOFT_BLOCKS $HARD_BLOCKS 0 0 -a
    echo "Quota set for $USERNAME: soft=$SOFT_LIMIT MB, hard=$HARD_LIMIT MB"
  else
    echo "Warning: setquota command not found. Quotas not set for $USERNAME."
  fi
}

# Function to read users from users.list files and create them
create_users() {
  USER_LIST_FILES=$(find /etc/openpanel/ftp/users/ -name 'users.list')

  for USER_LIST_FILE in $USER_LIST_FILES; do
    BASE_DIR=$(dirname "$USER_LIST_FILE")
    while IFS='|' read -r NAME PASS FOLDER UID GID QUOTA_SOFT QUOTA_HARD; do
      [ -z "$NAME" ] && continue  # Skip empty lines

      GROUP=$NAME

      if [ -z "$FOLDER" ]; then
        FOLDER="/ftp/$NAME"
      fi

      # Ensure the folder starts with /home and matches the base directory where users.list is found
      if [[ $FOLDER != /home/* ]] || [[ ! $FOLDER == "$BASE_DIR"* ]]; then
        echo "Skipping user $NAME: folder $FOLDER does not match base directory $BASE_DIR or does not start with /home"
        continue
      fi

      if [ ! -z "$UID" ]; then
        UID_OPT="-u $UID"
        if [ -z "$GID" ]; then
          GID=$UID
        fi
        GROUP=$(getent group "$GID" | cut -d: -f1)
        if [ ! -z "$GROUP" ]; then
          GROUP_OPT="-G $GROUP"
        elif [ ! -z "$GID" ]; then
          addgroup -g "$GID" "$NAME"
          GROUP_OPT="-G $NAME"
        fi
      fi

      echo -e "$PASS\n$PASS" | adduser -h "$FOLDER" -s /sbin/nologin "$UID_OPT" "$GROUP_OPT" "$NAME"
      mkdir -p "$FOLDER"
      chown "$NAME":"$GROUP" "$FOLDER"

      # Set quota if provided
      if [ ! -z "$QUOTA_SOFT" ] && [ ! -z "$QUOTA_HARD" ]; then
        set_user_quota "$NAME" "$QUOTA_SOFT" "$QUOTA_HARD"
      fi

      unset NAME PASS FOLDER UID GID GROUP UID_OPT GROUP_OPT QUOTA_SOFT QUOTA_HARD
    done < "$USER_LIST_FILE"
  done
}

# Function to create and manage FTP groups
create_ftp_groups() {
  GROUP_LIST_FILES=$(find /etc/openpanel/ftp/groups/ -name 'groups.list' 2>/dev/null)

  for GROUP_LIST_FILE in $GROUP_LIST_FILES; do
    while IFS='|' read -r GROUP_NAME GID MEMBERS; do
      [ -z "$GROUP_NAME" ] && continue  # Skip empty lines

      # Create group if it doesn't exist
      if ! getent group "$GROUP_NAME" > /dev/null; then
        if [ ! -z "$GID" ]; then
          addgroup -g "$GID" "$GROUP_NAME"
        else
          addgroup "$GROUP_NAME"
        fi
        echo "Created FTP group: $GROUP_NAME"
      fi

      # Add members to group if specified
      if [ ! -z "$MEMBERS" ]; then
        for MEMBER in $(echo "$MEMBERS" | tr ',' ' '); do
          if id -u "$MEMBER" >/dev/null 2>&1; then
            adduser "$MEMBER" "$GROUP_NAME"
            echo "Added $MEMBER to group $GROUP_NAME"
          else
            echo "Warning: User $MEMBER does not exist, cannot add to group $GROUP_NAME"
          fi
        done
      fi

      unset GROUP_NAME GID MEMBERS
    done < "$GROUP_LIST_FILE"
  done
}

# Call the functions to create users and groups
create_ftp_groups
create_users

# Set default passive mode port range if not specified
if [ -z "$MIN_PORT" ]; then
  MIN_PORT=21000
fi

if [ -z "$MAX_PORT" ]; then
  MAX_PORT=21010
fi

# Determine the address if not provided
if [ -z "$ADDRESS" ]; then
  HOSTNAME=$(hostname)
  if is_fqdn "$HOSTNAME"; then
    ADDRESS="$HOSTNAME"
  else
    ADDRESS=$(get_ip_address)
  fi
fi

# Configure address and TLS options
if [ ! -z "$ADDRESS" ]; then
  ADDR_OPT="-opasv_address=$ADDRESS"
fi

if [ ! -z "$TLS_CERT" ] || [ ! -z "$TLS_KEY" ]; then
  TLS_OPT="-orsa_cert_file=$TLS_CERT -orsa_private_key_file=$TLS_KEY -ossl_enable=YES -oallow_anon_ssl=NO -oforce_local_data_ssl=YES -oforce_local_logins_ssl=YES -ossl_tlsv1=NO -ossl_sslv2=NO -ossl_sslv3=NO -ossl_ciphers=HIGH"
fi

# Used to run custom commands inside container
if [ ! -z "$1" ]; then
  exec "$@"
else
  vsftpd -opasv_min_port="$MIN_PORT" -opasv_max_port="$MAX_PORT" "$ADDR_OPT" "$TLS_OPT" /etc/vsftpd/vsftpd.conf
  [ -d /var/run/vsftpd ] || mkdir /var/run/vsftpd
  pgrep vsftpd | tail -n 1 > /var/run/vsftpd/vsftpd.pid
  exec pidproxy /var/run/vsftpd/vsftpd.pid true
fi
