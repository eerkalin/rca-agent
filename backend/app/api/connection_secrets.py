import logging

from fastapi import APIRouter, HTTPException

from app.applications.repository import ConnectionRepository
from app.applications.schemas import ConnectionCredentialsUpdate
from app.db.session import SessionLocal
from app.observability.logging import log_event
from app.security.secrets import SecretCipher


router = APIRouter(tags=["connections"])
logger = logging.getLogger(__name__)


@router.put("/connections/{connection_id}/credentials")
async def set_connection_credentials(
    connection_id: int,
    request: ConnectionCredentialsUpdate,
):
    with SessionLocal() as db:
        connection = ConnectionRepository.get(db, connection_id)
        if connection is None:
            log_event(logger, logging.WARNING, "connection.credentials.not_found", "Credential update requested for missing connection", connection_id=connection_id)
            raise HTTPException(status_code=404, detail="Connection not found")

        credential_keys = sorted(request.credentials.keys())
        log_event(logger, logging.INFO, "connection.credentials.update.start", "Updating encrypted connection credentials", connection_id=connection_id, connection_name=connection.name, provider_type=connection.provider_type, credential_keys=credential_keys)
        try:
            ciphertext = SecretCipher().encrypt_dict(request.credentials)
        except RuntimeError as exc:
            log_event(logger, logging.ERROR, "connection.credentials.update.failure", "Failed to encrypt connection credentials", connection_id=connection_id, provider_type=connection.provider_type, error_type=type(exc).__name__, error=str(exc))
            logger.exception("Failed to encrypt connection credentials connection_id=%s", connection_id)
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        connection.credentials_ciphertext = ciphertext
        db.commit()
        log_event(logger, logging.INFO, "connection.credentials.update.success", "Encrypted connection credentials saved", connection_id=connection_id, connection_name=connection.name, provider_type=connection.provider_type, credential_keys=credential_keys)
        return {"connection_id": connection_id, "credentials_saved": True}


@router.delete("/connections/{connection_id}/credentials")
async def delete_connection_credentials(connection_id: int):
    with SessionLocal() as db:
        connection = ConnectionRepository.get(db, connection_id)
        if connection is None:
            log_event(logger, logging.WARNING, "connection.credentials.not_found", "Credential deletion requested for missing connection", connection_id=connection_id)
            raise HTTPException(status_code=404, detail="Connection not found")
        connection.credentials_ciphertext = None
        db.commit()
        log_event(logger, logging.INFO, "connection.credentials.delete.success", "Encrypted connection credentials deleted", connection_id=connection_id, connection_name=connection.name, provider_type=connection.provider_type)
        return {"connection_id": connection_id, "credentials_deleted": True}
