import json
import base64
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch


EXECUTA_DIR = Path(__file__).resolve().parents[1] / "executas" / "bio-app"
sys.path.insert(0, str(EXECUTA_DIR))
import bio_app_plugin  # noqa: E402


class SaveTranscriptionTests(unittest.TestCase):
    def test_reverse_rpc_uses_annas_audio_transcribe_host_method(self):
        request_id = "reverse-audio-test"
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"text": "The words Anna heard.", "language": "en"},
        }
        stdout = StringIO()
        with (
            patch.object(bio_app_plugin, "uuid4", return_value=request_id),
            patch("sys.stdout", stdout),
            patch("sys.stdin", StringIO(json.dumps(response) + "\n")),
        ):
            result = bio_app_plugin._request_host_audio_transcription("YWJj", "audio/webm")

        sent = json.loads(stdout.getvalue())
        self.assertEqual(sent["method"], "audio/transcribe")
        self.assertEqual(sent["params"], {"audioBase64": "YWJj"})
        self.assertEqual(result["text"], "The words Anna heard.")

    def test_json_rpc_tool_invoke_persists_transcribed_story(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "biographies.jsonl"
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "invoke",
                "params": {
                    "tool": "save_biography",
                    "arguments": {
                        "title": "A school memory",
                        "text": "My first day at school was bright and noisy.",
                        "source": "speech",
                    },
                },
            }
            stdin = StringIO(json.dumps(request) + "\n")
            stdout = StringIO()
            with (
                patch.object(bio_app_plugin, "DATA_FILE", data_file),
                patch("sys.stdin", stdin),
                patch("sys.stdout", stdout),
            ):
                bio_app_plugin.main()

            response = json.loads(stdout.getvalue())
            self.assertEqual(response["id"], 1)
            self.assertTrue(response["result"]["success"])
            saved = json.loads(data_file.read_text(encoding="utf-8").strip())
            self.assertEqual(saved["source"], "speech")
            self.assertEqual(saved["text"], "My first day at school was bright and noisy.")

    def test_transcript_from_host_transcription_is_saved_as_speech(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "biographies.jsonl"
            with patch.object(bio_app_plugin, "DATA_FILE", data_file):
                result = bio_app_plugin.invoke(
                    "save_biography",
                    {
                        "title": "Grandmother's garden",
                        "text": "She taught me to plant tomatoes after the rain.",
                        "source": "speech",
                    },
                )
                listed = bio_app_plugin.invoke("list_biographies", {})

            self.assertTrue(result["success"])
            self.assertTrue(listed["success"])
            self.assertEqual(len(listed["data"]["items"]), 1)
            saved = listed["data"]["items"][0]
            self.assertEqual(saved["source"], "speech")
            self.assertEqual(saved["title"], "Grandmother's garden")
            self.assertEqual(saved["text"], "She taught me to plant tomatoes after the rain.")
            self.assertTrue(data_file.exists())

    def test_audio_tool_calls_anna_and_saves_returned_transcript(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "biographies.jsonl"
            audio_bytes = b"synthetic test recording"
            encoded = base64.b64encode(audio_bytes).decode("ascii")
            with (
                patch.object(bio_app_plugin, "DATA_FILE", data_file),
                patch.object(
                    bio_app_plugin,
                    "_request_host_audio_transcription",
                    return_value={"text": "A clear story from the recording.", "language": "en"},
                ) as transcribe,
            ):
                result = bio_app_plugin.invoke(
                    "transcribe_and_save",
                    {"title": "A clear story", "audio_base64": encoded, "mime_type": "audio/wav"},
                )

            transcribe.assert_called_once_with(encoded, "audio/wav")
            self.assertTrue(result["success"])
            self.assertEqual(result["data"]["text"], "A clear story from the recording.")
            saved = json.loads(data_file.read_text(encoding="utf-8").strip())
            self.assertEqual(saved["title"], "A clear story")
            self.assertEqual(saved["source"], "speech")
            self.assertEqual(saved["text"], "A clear story from the recording.")

    def test_invalid_audio_is_rejected_before_host_request(self):
        with patch.object(bio_app_plugin, "_request_host_audio_transcription") as transcribe:
            result = bio_app_plugin.invoke(
                "transcribe_and_save",
                {"audio_base64": "not base64!", "mime_type": "audio/webm"},
            )
        self.assertFalse(result["success"])
        self.assertIn("valid base64", result["error"])
        transcribe.assert_not_called()

    def test_rejects_empty_transcription_without_creating_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "biographies.jsonl"
            with patch.object(bio_app_plugin, "DATA_FILE", data_file):
                result = bio_app_plugin.invoke(
                    "save_biography", {"text": "  ", "source": "speech"}
                )
            self.assertFalse(result["success"])
            self.assertIn("text must contain", result["error"])
            self.assertFalse(data_file.exists())


if __name__ == "__main__":
    unittest.main()
