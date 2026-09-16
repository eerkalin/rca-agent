from fastapi import APIRouter, HTTPException

from app.applications.repository import ConnectionRepository
from app.applications.schemas import ConnectionCredentialsUpdate
from app.db.session import SessionLocal
from app.security.secrets import SecretCipher


router = APIRouter(tags=["connections"])


@router.put("/connections/{connection_id}/credentials")
async def set_connection_credentials(
    connection_id: int,
    request: ConnectionCredentialsUpdate,
):
    with SessionLocal() as db:
        connection = ConnectionRepository.get(db, connection_id)
        if connection is None:
            raise HTTPException(status_code=404, detail="Connection not found")

        try:
            ciphertext = SecretCipher().encrypt_dict(request.credentials)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        connection.credentials_ciphertext = ciphertext
        db.commit()
        return {
            "connection_id": connection_id,
            "credentials_saved": True,
        }


@router.delete("/connections/{connection_id}/credentials")
async def delete_connection_credentials(connection_id: int):
    with SessionLocal() as db:
        connection = ConnectionRepository.get(db, connection_id)
        if connection is None:
            raise HTTPException(status_code=404, detail="Connection not found")
        connection.credentials_ciphertext = None
        db.commit()
        return {
            "connection_id": connection_id,
            "credentials_deleted": True,
        }
