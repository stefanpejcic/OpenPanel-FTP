# FTP module for [OpenPanel](https://openpanel.co)

Small and flexible docker image with vsftpd server + OpenPanel module to allow users to manage ftp sub-users.

### Features

- User account management
- User account limits (max accounts per user)
- Web interface integration with OpenPanel/OpenAdmin
- Secure with optional TLS/SSL

> **Note:** Disk quotas are not enforced by the container. All FTP sub-users are always in the OpenPanel user's group. Group management and per-user quotas are not available.

### Usage

This image can be used in two ways:

- as an FTP module for OpenPanel
- as a standalone FTP server

#### OpenPanel Module

To install FTP on OpenPanel server run the following command:

```bash
opencli ftp-setup
```

To create new FTP accounts:

```bash
opencli ftp-add <NEW_USERNAME> <NEW_PASSWORD> <FOLDER> <OPENPANEL_USERNAME>
```

<<<<<<< Updated upstream
#### OpenPanel Web Interface

The FTP module provides a complete web interface for managing FTP accounts:

- View all FTP accounts
- Create new FTP accounts (with per-user limits)
- Edit accounts (change directory, password)
- Delete accounts

#### Standalone Docker
=======
#### standalone Docker
>>>>>>> Stashed changes

Installation:

```
docker run -d \
    -p "21:21" \
    -p 21000-21010:21000-21010 \
    --restart=always \
    --name=openadmin_ftp \
    -v /home:/home \
    -v /etc/openpanel/ftp/users:/etc/openpanel/ftp/users \
    --memory="1g" --cpus="1" \
    openpanel/ftp
```

Adding accounts:

```
# To create temporary account (until docker restart):
docker exec -it openadmin_ftp sh -c 'echo -e "${PASSWORD}\n${PASSWORD}" | adduser -h $DIRECTORY -s /sbin/nologin $USERNAME'

# To create permanent FTP account:
echo "$USERNAME|$PASSWORD|$DIRECTORY|||" >> /etc/openpanel/ftp/users/users.list
# Format: username|password|directory|uid|gid
```

<<<<<<< Updated upstream
### Security Considerations

- All FTP accounts are isolated to their specified directories
- Optional TLS/SSL encryption for secure transfers (recommended)
- No anonymous access allowed

### Resource Management

- User account limits prevent system abuse
=======
---

### Todo:

- quotas
- limits in ftp accounts per user
- create groups
- openpanel interface
- openadmin interface
- additional tweaks: ssl protocols, resource limiting..
>>>>>>> Stashed changes
