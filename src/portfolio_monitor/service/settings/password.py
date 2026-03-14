import hashlib
import hmac
import secrets
from typing import Protocol


class PasswordHasher(Protocol):
    def hash_password(self, password: str) -> str: ...
    def verify_password(self, password: str, stored: str) -> bool: ...


class PBKDF2PasswordHasher:
    ITERATIONS = 600_000
    ALGORITHM = "pbkdf2:sha256"

    @staticmethod
    def hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            PBKDF2PasswordHasher.ITERATIONS,
        )
        return f"{PBKDF2PasswordHasher.ALGORITHM}:{PBKDF2PasswordHasher.ITERATIONS}${salt.hex()}${dk.hex()}"

    @staticmethod
    def verify_password(password: str, stored: str) -> bool:
        try:
            alg_and_iters, salt_hex, expected_hex = stored.split("$", 2)
            algorithm, iterations_str = alg_and_iters.rsplit(":", 1)
        except ValueError:
            return False

        if algorithm != PBKDF2PasswordHasher.ALGORITHM:
            return False

        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(expected_hex)

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
