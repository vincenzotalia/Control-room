from __future__ import annotations

from pathlib import Path
from typing import Iterable

from config import (
    AZURE_BLOB_CONNECTION_STRING,
    AZURE_BLOB_CONTAINER,
    FILE_STORAGE_BACKEND,
    STORAGE_ROOT,
)


def _normalize_relative_path(path: str | Path) -> str:
    candidate = Path(path)

    if candidate.is_absolute():
        for root in (STORAGE_ROOT,):
            try:
                candidate = candidate.resolve().relative_to(root.resolve())
                break
            except Exception:
                continue
        else:
            raise ValueError(f"Path outside configured storage roots: {path}")

    parts = []
    for part in candidate.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError(f"Path traversal is not allowed: {path}")
        parts.append(part)

    if not parts:
        raise ValueError("Empty storage path is not allowed")

    return "/".join(parts)


def _cache_path(relative_path: str) -> Path:
    return STORAGE_ROOT / Path(relative_path)


class BaseStorage:
    def save_bytes(self, relative_path: str | Path, payload: bytes, content_type: str | None = None) -> str:
        raise NotImplementedError

    def read_bytes(self, relative_path: str | Path) -> tuple[bytes, str | None]:
        raise NotImplementedError

    def exists(self, relative_path: str | Path) -> bool:
        raise NotImplementedError

    def delete(self, relative_path: str | Path) -> None:
        raise NotImplementedError

    def ensure_local_copy(self, relative_path: str | Path) -> Path:
        raise NotImplementedError

    def list_relative(self, prefix: str | Path) -> Iterable[str]:
        raise NotImplementedError

    def save_upload(self, relative_path: str | Path, upload_file, content_type: str | None = None) -> str:
        upload_file.file.seek(0)
        payload = upload_file.file.read()
        return self.save_bytes(relative_path, payload, content_type=content_type or upload_file.content_type)


class LocalStorage(BaseStorage):
    def _full_path(self, relative_path: str | Path) -> Path:
        return STORAGE_ROOT / Path(_normalize_relative_path(relative_path))

    def save_bytes(self, relative_path: str | Path, payload: bytes, content_type: str | None = None) -> str:
        normalized = _normalize_relative_path(relative_path)
        target = self._full_path(normalized)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return normalized

    def read_bytes(self, relative_path: str | Path) -> tuple[bytes, str | None]:
        target = self._full_path(relative_path)
        return target.read_bytes(), None

    def exists(self, relative_path: str | Path) -> bool:
        return self._full_path(relative_path).exists()

    def delete(self, relative_path: str | Path) -> None:
        target = self._full_path(relative_path)
        if target.exists():
            target.unlink()

    def ensure_local_copy(self, relative_path: str | Path) -> Path:
        return self._full_path(relative_path)

    def list_relative(self, prefix: str | Path) -> Iterable[str]:
        normalized_prefix = _normalize_relative_path(prefix)
        base = self._full_path(normalized_prefix)
        if not base.exists():
            return []
        out: list[str] = []
        for file_path in base.rglob("*"):
            if file_path.is_file():
                out.append(_normalize_relative_path(file_path))
        return out


class AzureBlobStorage(BaseStorage):
    def __init__(self) -> None:
        if not AZURE_BLOB_CONNECTION_STRING:
            raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING must be set for azure_blob storage")

        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError as exc:
            raise RuntimeError(
                "azure-storage-blob is required when WCR_FILE_STORAGE_BACKEND=azure_blob"
            ) from exc

        service = BlobServiceClient.from_connection_string(AZURE_BLOB_CONNECTION_STRING)
        self.container = service.get_container_client(AZURE_BLOB_CONTAINER)
        self.container.create_container(exist_ok=True)

    def _blob_name(self, relative_path: str | Path) -> str:
        return _normalize_relative_path(relative_path)

    def _write_cache(self, relative_path: str, payload: bytes) -> Path:
        target = _cache_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return target

    def save_bytes(self, relative_path: str | Path, payload: bytes, content_type: str | None = None) -> str:
        blob_name = self._blob_name(relative_path)
        kwargs = {"overwrite": True}
        if content_type:
            from azure.storage.blob import ContentSettings

            kwargs["content_settings"] = ContentSettings(content_type=content_type)

        self.container.upload_blob(name=blob_name, data=payload, **kwargs)
        self._write_cache(blob_name, payload)
        return blob_name

    def read_bytes(self, relative_path: str | Path) -> tuple[bytes, str | None]:
        blob_name = self._blob_name(relative_path)
        blob = self.container.get_blob_client(blob_name)
        downloader = blob.download_blob()
        payload = downloader.readall()
        props = blob.get_blob_properties()
        content_type = None
        if props.content_settings:
            content_type = props.content_settings.content_type
        self._write_cache(blob_name, payload)
        return payload, content_type

    def exists(self, relative_path: str | Path) -> bool:
        blob_name = self._blob_name(relative_path)
        return self.container.get_blob_client(blob_name).exists()

    def delete(self, relative_path: str | Path) -> None:
        blob_name = self._blob_name(relative_path)
        blob = self.container.get_blob_client(blob_name)
        if blob.exists():
            blob.delete_blob()

        cached = _cache_path(blob_name)
        if cached.exists():
            cached.unlink()

    def ensure_local_copy(self, relative_path: str | Path) -> Path:
        blob_name = self._blob_name(relative_path)
        cached = _cache_path(blob_name)
        if cached.exists():
            return cached

        payload, _ = self.read_bytes(blob_name)
        return self._write_cache(blob_name, payload)

    def list_relative(self, prefix: str | Path) -> Iterable[str]:
        blob_prefix = self._blob_name(prefix).rstrip("/") + "/"
        return [blob.name for blob in self.container.list_blobs(name_starts_with=blob_prefix)]


_storage_instance: BaseStorage | None = None


def get_file_storage() -> BaseStorage:
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    backend = FILE_STORAGE_BACKEND.strip().lower()
    if backend == "local":
        _storage_instance = LocalStorage()
    elif backend == "azure_blob":
        _storage_instance = AzureBlobStorage()
    else:
        raise RuntimeError(f"Unsupported WCR_FILE_STORAGE_BACKEND: {FILE_STORAGE_BACKEND}")

    return _storage_instance
