from __future__ import annotations

import json
import os
import hashlib
from pathlib import Path
from typing import Any


class Storage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.data = root / "data"
        self.docs = root / "docs"
        self.backend = os.environ.get("STORAGE_BACKEND", "json").strip().lower()
        if self.backend not in {"json", "postgres"}:
            raise RuntimeError("STORAGE_BACKEND must be either 'json' or 'postgres'.")
        if self.backend == "postgres":
            self._init_postgres()
        else:
            self._init_json()

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL mode requires the psycopg dependency. "
                "Run: pip install -r requirements.txt"
            ) from exc

        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is required when STORAGE_BACKEND=postgres.")
        return psycopg.connect(database_url)

    def _init_json(self) -> None:
        self.data.mkdir(exist_ok=True)
        self.docs.mkdir(exist_ok=True)
        path = self.data / "catalog.json"
        if not path.exists():
            path.write_text(json.dumps({"items": []}, indent=2), encoding="utf-8")
        scanners_path = self.data / "scanners.json"
        if not scanners_path.exists():
            scanners_path.write_text(json.dumps({"items": []}, indent=2), encoding="utf-8")

    def _init_postgres(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS viewer_instances (
                        slug TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS viewer_scanners (
                        scanner_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        token_hash TEXT NOT NULL,
                        status TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS viewer_documents (
                        slug TEXT PRIMARY KEY REFERENCES viewer_instances(slug)
                            ON DELETE CASCADE,
                        openapi JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

    def read_catalog(self) -> dict[str, Any]:
        if self.backend == "json":
            path = self.data / "catalog.json"
            try:
                return json.loads(path.read_text(encoding="utf-8-sig"))
            except (FileNotFoundError, json.JSONDecodeError):
                return {"items": []}

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT payload FROM viewer_instances ORDER BY LOWER(name)")
                return {"items": [row[0] for row in cursor.fetchall()]}

    def get_item(self, slug: str) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in self.read_catalog().get("items", [])
                if item.get("slug") == slug
            ),
            None,
        )

    def save_item(self, item: dict[str, Any]) -> None:
        if self.backend == "json":
            catalog = self.read_catalog()
            items = [
                existing
                for existing in catalog.get("items", [])
                if existing.get("slug") != item["slug"]
            ]
            items.append(item)
            items.sort(key=lambda existing: existing.get("name", "").lower())
            (self.data / "catalog.json").write_text(
                json.dumps({"items": items}, indent=2), encoding="utf-8"
            )
            return

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO viewer_instances (slug, name, payload)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (slug) DO UPDATE SET
                        name = EXCLUDED.name,
                        payload = EXCLUDED.payload,
                        updated_at = NOW()
                    """,
                    (item["slug"], item["name"], json.dumps(item)),
                )

    def publish(self, item: dict[str, Any], openapi: dict[str, Any]) -> None:
        if self.backend == "json":
            doc_dir = self.docs / item["slug"]
            doc_dir.mkdir(parents=True, exist_ok=True)
            (doc_dir / "openapi.json").write_text(
                json.dumps(openapi, indent=2), encoding="utf-8"
            )
            self.save_item(item)
            return

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO viewer_instances (slug, name, payload)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (slug) DO UPDATE SET
                        name = EXCLUDED.name,
                        payload = EXCLUDED.payload,
                        updated_at = NOW()
                    """,
                    (item["slug"], item["name"], json.dumps(item)),
                )
                cursor.execute(
                    """
                    INSERT INTO viewer_documents (slug, openapi)
                    VALUES (%s, %s)
                    ON CONFLICT (slug) DO UPDATE SET
                        openapi = EXCLUDED.openapi,
                        updated_at = NOW()
                    """,
                    (item["slug"], json.dumps(openapi)),
                )

    def read_document(self, slug: str) -> dict[str, Any] | None:
        if self.backend == "json":
            path = self.docs / slug / "openapi.json"
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT openapi FROM viewer_documents WHERE slug = %s", (slug,)
                )
                row = cursor.fetchone()
                return row[0] if row else None

    def delete(self, slug: str) -> bool:
        if self.backend == "json":
            if self.get_item(slug) is None:
                return False
            catalog = self.read_catalog()
            items = [
                existing
                for existing in catalog.get("items", [])
                if existing.get("slug") != slug
            ]
            (self.data / "catalog.json").write_text(
                json.dumps({"items": items}, indent=2), encoding="utf-8"
            )
            doc_dir = self.docs / slug
            document = doc_dir / "openapi.json"
            if document.exists():
                document.unlink()
            if doc_dir.exists() and not any(doc_dir.iterdir()):
                doc_dir.rmdir()
            return True

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM viewer_instances WHERE slug = %s RETURNING slug", (slug,)
                )
                return cursor.fetchone() is not None

    def read_scanners(self) -> dict[str, Any]:
        if self.backend == "json":
            path = self.data / "scanners.json"
            try:
                return json.loads(path.read_text(encoding="utf-8-sig"))
            except (FileNotFoundError, json.JSONDecodeError):
                return {"items": []}
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT payload FROM viewer_scanners ORDER BY LOWER(name)")
                return {"items": [row[0] for row in cursor.fetchall()]}

    def save_scanner(self, scanner: dict[str, Any]) -> None:
        if self.backend == "json":
            scanners = self.read_scanners()
            items = [
                item
                for item in scanners.get("items", [])
                if item.get("scannerId") != scanner["scannerId"]
            ]
            items.append(scanner)
            items.sort(key=lambda item: item.get("name", "").lower())
            (self.data / "scanners.json").write_text(
                json.dumps({"items": items}, indent=2), encoding="utf-8"
            )
            return
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO viewer_scanners
                        (scanner_id, name, token_hash, status, payload)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (scanner_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        token_hash = EXCLUDED.token_hash,
                        status = EXCLUDED.status,
                        payload = EXCLUDED.payload,
                        updated_at = NOW()
                    """,
                    (
                        scanner["scannerId"],
                        scanner["name"],
                        scanner["tokenHash"],
                        scanner["status"],
                        json.dumps(scanner),
                    ),
                )

    def get_scanner(self, scanner_id: str) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in self.read_scanners().get("items", [])
                if item.get("scannerId") == scanner_id
            ),
            None,
        )

    def authenticate_scanner(self, token: str) -> dict[str, Any] | None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return next(
            (
                item
                for item in self.read_scanners().get("items", [])
                if item.get("tokenHash") == token_hash
            ),
            None,
        )

    def documents_for_scanner(self, scanner_id: str) -> list[dict[str, Any]]:
        return [
            item
            for item in self.read_catalog().get("items", [])
            if item.get("ownerScannerId") == scanner_id
        ]

    def delete_for_scanner(self, slug: str, scanner_id: str) -> bool:
        item = self.get_item(slug)
        if item is None or item.get("ownerScannerId") != scanner_id:
            return False
        return self.delete(slug)

    def delete_scanner(self, scanner_id: str) -> bool:
        if self.backend == "json":
            scanners = self.read_scanners()
            if not any(
                item.get("scannerId") == scanner_id
                for item in scanners.get("items", [])
            ):
                return False
            items = [
                item
                for item in scanners.get("items", [])
                if item.get("scannerId") != scanner_id
            ]
            (self.data / "scanners.json").write_text(
                json.dumps({"items": items}, indent=2), encoding="utf-8"
            )
            return True

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM viewer_scanners WHERE scanner_id = %s RETURNING scanner_id",
                    (scanner_id,),
                )
                return cursor.fetchone() is not None
