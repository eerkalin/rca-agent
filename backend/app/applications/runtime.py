from sqlalchemy.orm import Session

from app.applications.repository import ConnectionRepository
from app.security.secrets import SecretCipher


class RuntimeConnectionResolver:
    """Resolve DB-backed connection configuration for provider execution.

    Credentials are decrypted only inside the backend and must never be copied
    into evidence or application context sent to an LLM.
    """

    @staticmethod
    def resolve(db: Session, connection_id: int | None) -> dict:
        if connection_id is None:
            return {"config": {}, "credentials": {}}

        connection = ConnectionRepository.get(db, connection_id)
        if connection is None:
            raise ValueError(f"Connection {connection_id} not found")
        if not connection.enabled:
            raise ValueError(f"Connection {connection_id} is disabled")

        credentials = {}
        if connection.credentials_ciphertext:
            credentials = SecretCipher().decrypt_dict(connection.credentials_ciphertext)

        return {
            "id": connection.id,
            "name": connection.name,
            "provider_type": connection.provider_type,
            "config": connection.config or {},
            "credentials": credentials,
        }
