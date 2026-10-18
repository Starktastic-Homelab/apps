"""Native Redis ACL text. Passwords and resulting verifiers stay private."""
import hashlib

ACL_PATH = '/opt/bitnami/redis/acl/users.acl'
MAINTENANCE_USER = 'homelab-maintenance'
APPLICATION_COMMANDS = '+@all -config|set -acl'


def users(application_password: bytes, maintenance_password: bytes) -> str:
    if (not isinstance(application_password, bytes) or not isinstance(maintenance_password, bytes)
            or not application_password or not maintenance_password or application_password == maintenance_password):
        raise ValueError('Distinct nonempty private Redis credentials are required')
    def verifier(value):
        return '#' + hashlib.sha256(value).hexdigest()
    return ('user default on ' + verifier(application_password) + ' ~* &* ' + APPLICATION_COMMANDS + '\n'
            + 'user ' + MAINTENANCE_USER + ' on ' + verifier(maintenance_password) + ' ~* &* +@all\n')
