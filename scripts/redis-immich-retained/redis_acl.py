"""Native Redis ACL text. Passwords and resulting verifiers stay private."""
import hashlib
import re

ACL_PATH = '/opt/bitnami/redis/acl/users.acl'
MAINTENANCE_USER = 'homelab-maintenance'
APPLICATION_COMMANDS = '+@all -config|set -acl'


def users(application_password: bytes, maintenance_password: bytes) -> str:
    if (not isinstance(application_password, bytes) or not isinstance(maintenance_password, bytes)
            or not application_password or not maintenance_password or application_password == maintenance_password):
        raise ValueError('Distinct nonempty private Redis credentials are required')
    return users_from_verifier(hashlib.sha256(application_password).hexdigest(), maintenance_password)


def users_from_verifier(application_sha256: str, maintenance_password: bytes) -> str:
    """Keep an existing password without needing its plaintext for sealing."""
    if (not isinstance(application_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', application_sha256)
            or not isinstance(maintenance_password, bytes) or not maintenance_password):
        raise ValueError('An existing SHA256 verifier and distinct private credential are required')
    maintenance_sha256 = hashlib.sha256(maintenance_password).hexdigest()
    if application_sha256 == maintenance_sha256:
        raise ValueError('Distinct private Redis credentials are required')
    return ('user default on #' + application_sha256 + ' ~* &* ' + APPLICATION_COMMANDS + '\n'
            + 'user ' + MAINTENANCE_USER + ' on #' + maintenance_sha256 + ' ~* &* +@all\n')
