import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("microphone recordings are sent to the backend Executa", async () => {
  const app = await readFile(new URL("../bundle/app.js", import.meta.url), "utf8");
  assert.match(app, /method:\s*"transcribe_and_save"/);
  assert.match(app, /audio_base64:\s*audioBase64/);
  assert.match(app, /mime_type:\s*blob\.type/);
  assert.doesNotMatch(app, /anna\.audio\.transcribe/);
  assert.doesNotMatch(app, /from ["']\.\/audio\.js["']/);
});

test("manifest grants audio transcription and backend tool invocation", async () => {
  const manifest = JSON.parse(
    await readFile(new URL("../manifest.json", import.meta.url), "utf8"),
  );
  assert.deepEqual(manifest.ui.host_api.audio, ["transcribe"]);
  assert.ok(manifest.host_capabilities.includes("llm.audio.speak"));
  assert.ok(manifest.ui.host_api.tools.includes("tool-dev-bio-app"));
});

test("standalone audio helper has been removed", async () => {
  await assert.rejects(readFile(new URL("../bundle/audio.js", import.meta.url)));
});

test("transcription gateway errors are shortened and retain a support reference", async () => {
  const app = await readFile(new URL("../bundle/app.js", import.meta.url), "utf8");
  assert.match(app, /Anna’s transcription service is temporarily unavailable/);
  assert.match(app, /Cloudflare Ray ID:/);
  assert.match(app, /Your recording was not saved/);
});
