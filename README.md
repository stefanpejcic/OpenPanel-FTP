# FTP module for [OpenPanel](https://openpanel.co)

Small and flexible docker image with vsftpd server + OpenPanel module to allow users to manage ftp sub-users.

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


#### standalone Docker

Installation:
```
docker run -d \
    -p "21:21" \
    -p 21000-21010:21000-21010 \
    --restart=always \
    --name=openadmin_ftp \
    -v /home:/home \
    -v /etc/openpanel/ftp/users:/etc/openpanel/ftp/users
    --memory="1g" --cpus="1" \
    openpanel/ftp
```

Adding accounts:

```
# to create temporary account *(until docker restart):
docker exec -it openadmin_ftp sh -c 'echo -e "${PASSWORD}\n${PASSWORD}" | adduser -h $DIRECTORY -s /sbin/nologin $USERNAME'

# to create permanent ftp account that will be created on docker restart:
echo "$USERNAME|$HASHEDPASSWORD|$DIRECTORY|$UID|$GID" >> /etc/openpanel/ftp/users/users.list
```

-----


### Todo:
- quotas
- limits in ftp accounts per user
- create groups
- openpanel interface
- openadmin interface
- additional tweaks: ssl protocols, resource limiting..
