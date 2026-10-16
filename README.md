# Bio Archive

Bio Archive is an Anna App for writing and keeping personal memories. The title field suggests titles already in the backend; saving a title matches existing titles without regard to capitalization or creates a new title when there is no match. The UI calls the bundled Python Executa to append each entry to a local JSON Lines file and loads saved entries when it opens.

## Run locally

```bash
anna-app validate
anna-app dev
```

The Executa writes records to `executas/bio-app/data/biographies.jsonl` on the machine where its backend process runs. The data directory is ignored by Git so personal biography text is not committed accidentally. This is a local development store, not Anna-hosted per-user cloud storage.

## Voice input

The microphone button records audio in the browser and sends its base64 bytes and MIME type to the Executa `transcribe_and_save` function. The Executa calls Anna's `audio/transcribe` service over reverse RPC, then saves the returned transcript as `source: "speech"` in the same local JSON Lines file used for typed memories. The UI never invokes transcription directly. The manifest declares `ui.host_api.audio: ["transcribe"]` and the media ACL capability `host_capabilities: ["llm.audio.speak"]`; Anna also requires the user's app media grant. Microphone access depends on browser permission and the Anna app container's microphone support.

The generated WAV fixtures in `tests/fixtures/` are synthetic silence and tone samples, not spoken language. Run `node --test tests/audio.test.mjs` and `executas/bio-app/.venv/Scripts/python.exe -m unittest discover -s tests -p test_bio_app_plugin.py -v` to verify payload routing and the backend save path with a mocked Anna response. These tests do not call Anna's live transcription service.
