import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    memory_limit: str = "4GB"
    threads: int = 2
    temp_limit: str = "20GB"
    max_upload_gb: float = 10
    api_key: str = ""
    ai_model: str = ""
    ai_timeout: int = 60
    max_instruction_chars: int = 4000

    @classmethod
    def from_env(cls):
        return cls(
            data_dir=Path(os.getenv("DSW_DATA_DIR", str(ROOT / "data"))).resolve(),
            memory_limit=os.getenv("DSW_MEMORY_LIMIT", "4GB"),
            threads=int(os.getenv("DSW_THREADS", "2")),
            temp_limit=os.getenv("DSW_TEMP_LIMIT", "20GB"),
            max_upload_gb=float(os.getenv("DSW_MAX_UPLOAD_GB", "10")),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            ai_model=os.getenv("OPENAI_MODEL", ""),
        )
