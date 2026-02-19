from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    # opcional: se tiver python-dotenv instalado
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


@dataclass(frozen=True)
class Settings:
    # Conexão
    host: str = os.getenv("GAIO_HOST", "198.161.83.155")
    port: int = int(os.getenv("GAIO_PORT", "4222"))
    user: str = os.getenv("GAIO_USER", "ubuntu")
    key_path: str = os.getenv("GAIO_KEY", str(Path.home() / ".ssh" / "srvgaiodb2_qx19ly.pem"))

    # Pasta remota destino (inputs)
    remote_dir: str = os.getenv(
        "GAIO_REMOTE_DIR",
        "/home/ubuntu/gaio-deploy/content/apps/174/assets/inputs",
    )

    # Pastas locais (relativas à raiz do projeto)
    local_files_dir: str = os.getenv("LOCAL_FILES_DIR", "files")
    local_sent_dir: str = os.getenv("LOCAL_SENT_DIR", "sent")
    local_logs_dir: str = os.getenv("LOCAL_LOGS_DIR", "logs")

    # Padrão de seleção de arquivos
    pattern: str = os.getenv("UPLOAD_PATTERN", "*")  # ex: "*.csv"
