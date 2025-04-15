# FTP module for [OpenPanel](https://openpanel.co)

Small and flexible docker image with vsftpd server + OpenPanel module to allow users to manage ftp sub-users.

### Features

- User account management
- FTP disk quotas
- FTP group management
- User account limits (max accounts per user)
- Web interface integration with OpenPanel/OpenAdmin
- Secure with optional TLS/SSL

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
opencli ftp-add <NEW_USERNAME> <NEW_PASSWORD> <FOLDER> <OPENPANEL_USERNAME> [QUOTA_SOFT_MB] [QUOTA_HARD_MB]
```

To create a new FTP group:
```bash
opencli ftp-group-add <GROUP_NAME> [GID] [MEMBER_LIST_COMMA_SEPARATED]
```

#### OpenPanel Web Interface

The FTP module provides a complete web interface for managing FTP accounts:

- View all FTP accounts
- Create new FTP accounts (with per-user limits)
- Edit accounts (change directory, password, quotas)
- Delete accounts
- Manage FTP groups (admin interface)


#### Standalone Docker

Installation:
```
docker run -d \
    -p "21:21" \
    -p 21000-21010:21000-21010 \
    --restart=always \
    --name=openadmin_ftp \
    -v /home:/home \
    -v /etc/openpanel/ftp/users:/etc/openpanel/ftp/users \
    -v /etc/openpanel/ftp/groups:/etc/openpanel/ftp/groups \
    --memory="1g" --cpus="1" \
    openpanel/ftp
```

Adding accounts:

```
# To create temporary account (until docker restart):
docker exec -it openadmin_ftp sh -c 'echo -e "${PASSWORD}\n${PASSWORD}" | adduser -h $DIRECTORY -s /sbin/nologin $USERNAME'

# To create permanent FTP account with quotas:
echo "$USERNAME|$PASSWORD|$DIRECTORY|||1024|2048" >> /etc/openpanel/ftp/users/users.list
# Format: username|password|directory|uid|gid|quota_soft_mb|quota_hard_mb

# To create a FTP group:
echo "groupname||user1,user2" >> /etc/openpanel/ftp/groups/groups.list
# Format: groupname|gid|comma_separated_members
```

### Security Considerations

- All FTP accounts are isolated to their specified directories
- Optional TLS/SSL encryption for secure transfers (recommended)
- User disk quotas prevent resource abuse
- No anonymous access allowed

### Resource Management

- Each user can have individual disk quotas
  - Soft quota: Warning threshold
  - Hard quota: Maximum allowed storage
- User account limits prevent system abuse
