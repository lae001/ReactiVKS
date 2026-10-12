"""Сгенерировать закрытый ключ RS256 для auth-service и (по желанию) его публичную часть.

    uv run python scripts/gen_jwt_key.py                        # secrets/jwt-private.pem
    uv run python scripts/gen_jwt_key.py --out secrets/next.pem --public-out secrets/next.pub.pem

Существующий файл не перезаписывается: ``kid`` выводится из ключа, и замена ключа сделала бы непроверяемыми все уже
выданные токены. Файлы создаются с правами 0600; каталог ``backend/secrets/`` исключен из git.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEY_SIZE_BITS = 2048


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("secrets/jwt-private.pem"), help="файл закрытого ключа")
    parser.add_argument("--public-out", type=Path, help="файл публичного ключа (для ротации)")
    arguments = parser.parse_args()

    if arguments.out.exists():
        sys.stderr.write(f"{arguments.out} уже существует – не перезаписываю\n")
        return 1

    key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE_BITS)
    _write(
        arguments.out,
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    )
    if arguments.public_out is not None:
        _write(
            arguments.public_out,
            key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ),
        )
    sys.stdout.write(f"ключ записан в {arguments.out}\n")
    return 0


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as file:
        file.write(content)


if __name__ == "__main__":
    raise SystemExit(main())
