import json

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class SecretCipher:
    def __init__(self):
        if not settings.rca_master_key:
            raise RuntimeError(
                "RCA_MASTER_KEY is not configured. Generate a Fernet key and provide it via environment/Kubernetes Secret."
            )
        self._fernet = Fernet(settings.rca_master_key.encode("utf-8"))

    def encrypt_dict(self, value: dict) -> str:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self._fernet.encrypt(payload).decode("utf-8")

    def decrypt_dict(self, ciphertext: str) -> dict:
        try:
            payload = self._fernet.decrypt(ciphertext.encode("utf-8"))
        except InvalidToken as exc:
            raise RuntimeError("Unable to decrypt stored credentials with RCA_MASTER_KEY") from exc
        return json.loads(payload.decode("utf-8"))
