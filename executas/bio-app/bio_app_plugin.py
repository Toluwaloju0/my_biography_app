"""Anna Executa backend for Bio Archive.

Biography entries are stored as UTF-8 JSON Lines in ``data/biographies.jsonl``
next to this module. Each line is one record, so appending a memory does not
rewrite earlier entries. This local file is a development persistence layer;
it is not Anna-hosted per-user storage.
"""

from __future__ import annotations

import json
import base64
import binascii
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

DATA_FILE = Path(os.environ.get("BIO_ARCHIVE_DATA_FILE") or (
    Path(__file__).resolve().parent / "data" / "biographies.jsonl"
))
MAX_TEXT_LENGTH = 20_000
MAX_TITLE_LENGTH = 120
MAX_AUDIO_BYTES = 8 * 1024 * 1024

MANIFEST = {
    "name": "tool-dev-bio-app",
    "version": "0.1.0",
    "tools": [
        {
            "name": "transcribe_and_save",
            "description": "Transcribe a microphone recording with Anna and save the transcript as a biography memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Optional memory title."},
                    "audio_base64": {"type": "string", "description": "Base64-encoded microphone audio."},
                    "mime_type": {"type": "string", "description": "Recorded audio MIME type."},
                },
                "required": ["audio_base64", "mime_type"],
                "additionalProperties": False,
            },
        },
        {
            "name": "save_biography",
            "description": "Save a written biography memory to the app's local backend file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Optional memory title."},
                    "text": {"type": "string", "description": "Biography memory to save."},
                    "source": {"type": "string", "enum": ["written", "speech"]},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
        {
            "name": "list_biographies",
            "description": "List saved biography memories, newest first.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "list_titles",
            "description": "List distinct titles already used for biography memories.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    ],
}


def _request_host_audio_transcription(audio_base64: str, mime_type: str) -> dict[str, Any]:
    """Call Anna's audio.transcribe service through Executa reverse RPC."""
    request_id = str(uuid4())
    sys.stdout.write(json.dumps({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "audio/transcribe",
        "params": {"audioBase64": audio_base64},
    }) + "\n")
    sys.stdout.flush()
    for line in sys.stdin:
        envelope = json.loads(line)
        if envelope.get("id") != request_id or "method" in envelope:
            continue
        if "error" in envelope:
            error = envelope["error"]
            raise RuntimeError(error.get("message", "Anna audio transcription failed"))
        result = envelope.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Anna returned an invalid transcription response")
        return result
    raise RuntimeError("Executa host connection closed during transcription")


def _transcribe_and_save(args: dict[str, Any]) -> dict[str, Any]:
    audio_base64 = args.get("audio_base64")
    mime_type = args.get("mime_type")
    if not isinstance(audio_base64, str) or not audio_base64:
        raise ValueError("audio_base64 is required")
    if not isinstance(mime_type, str) or not mime_type.startswith("audio/"):
        raise ValueError("mime_type must identify an audio recording")
    try:
        audio_bytes = base64.b64decode(audio_base64, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("audio_base64 must be valid base64 audio data") from error
    if not audio_bytes:
        raise ValueError("audio recording is empty")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise ValueError(f"audio recording must be {MAX_AUDIO_BYTES // (1024 * 1024)} MiB or smaller")

    transcription = _request_host_audio_transcription(audio_base64, mime_type)
    text = transcription.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Anna did not return any transcribed text")
    saved = _save_biography({"title": args.get("title", ""), "text": text, "source": "speech"})
    return {**saved, "text": text.strip(), "language": transcription.get("language")}


def _read_entries() -> list[dict[str, Any]]:
    """Read valid records, skipping a malformed trailing line if interrupted."""
    if not DATA_FILE.exists():
        return []
    entries: list[dict[str, Any]] = []
    with DATA_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and isinstance(record.get("text"), str):
                entries.append(record)
    return entries


def _save_biography(args: dict[str, Any]) -> dict[str, Any]:
    text = args.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must contain at least one non-whitespace character")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"text must be {MAX_TEXT_LENGTH} characters or fewer")

    title = args.get("title", "")
    if not isinstance(title, str):
        raise ValueError("title must be a string")
    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError(f"title must be {MAX_TITLE_LENGTH} characters or fewer")

    source = args.get("source", "written")
    if source not in {"written", "speech"}:
        raise ValueError("source must be 'written' or 'speech'")

    title = title.strip()
    existing_titles = {
        record.get("title", "").strip().casefold(): record.get("title", "").strip()
        for record in _read_entries()
        if isinstance(record.get("title"), str) and record.get("title", "").strip()
    }
    reused_title = bool(title and title.casefold() in existing_titles)
    if reused_title:
        title = existing_titles[title.casefold()]

    record = {
        "id": str(uuid4()),
        "title": title,
        "text": text.strip(),
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {
        "saved": True,
        "id": record["id"],
        "title": title,
        "reused_title": reused_title,
        "created_at": record["created_at"],
    }


def _list_biographies() -> dict[str, Any]:
    # Return a bounded window so repeated saves cannot exceed the invoke payload.
    entries = _read_entries()[-100:]
    entries.reverse()
    return {"items": entries}


def _list_titles() -> dict[str, Any]:
    """Return unique non-empty titles in most-recently-used order."""
    titles: list[str] = []
    seen: set[str] = set()
    for entry in reversed(_read_entries()):
        title = entry.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        title = title.strip()
        normalized = title.casefold()
        if normalized not in seen:
            titles.append(title)
            seen.add(normalized)
    return {"titles": titles}


def invoke(method: str, args: dict[str, Any]) -> dict[str, Any]:
    """Return the dispatcher contract envelope for every tool invocation."""
    try:
        if method == "save_biography":
            return {"success": True, "data": _save_biography(args)}
        if method == "transcribe_and_save":
            return {"success": True, "data": _transcribe_and_save(args)}
        if method == "list_biographies":
            return {"success": True, "data": _list_biographies()}
        if method == "list_titles":
            return {"success": True, "data": _list_titles()}
        return {"success": False, "error": f"unknown method: {method}"}
    except (OSError, ValueError, RuntimeError) as error:
        return {"success": False, "error": str(error)}


def main() -> None:
    """Serve the Executa JSON-RPC 2.0 stdio protocol."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request_id: Any = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            method = request.get("method")
            if method == "describe":
                result = MANIFEST
            elif method == "health":
                result = {"status": "ready"}
            elif method == "invoke":
                params = request.get("params") or {}
                result = invoke(params.get("tool", ""), params.get("arguments") or {})
            else:
                raise ValueError(f"unknown rpc: {method}")
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as error:  # noqa: BLE001 - keep the stdio process alive
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": str(error)},
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
