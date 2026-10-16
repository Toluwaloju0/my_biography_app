// Bio Archive Anna App UI.
import { AnnaAppRuntime } from "/static/anna-apps/_sdk/latest/index.js";

const TOOL_ID = "tool-dev-bio-app";
const els = {
  title: document.getElementById("entry-title"),
  text: document.getElementById("entry-text"),
  save: document.getElementById("save-btn"),
  mic: document.getElementById("mic-btn"),
  status: document.getElementById("status"),
  wordCount: document.getElementById("word-count"),
  titleOptions: document.getElementById("title-options"),
  memoryList: document.getElementById("memory-list"),
  memoryCount: document.getElementById("memory-count"),
};

let anna = null;
let recorder = null;
let recordingStream = null;
let recordingChunks = [];
let entrySource = "written";
let recordingTimer = null;

function setStatus(message, kind = "") {
  els.status.textContent = message;
  els.status.className = `status ${kind}`.trim();
}

function formatTranscriptionError(error) {
  const message = String(error?.message || error || "Unknown transcription error");
  const status = message.match(/\bHTTP\s+(\d{3})\b/i)?.[1];
  const rayId = message.match(/Cloudflare Ray ID:\s*<strong[^>]*>\s*([a-f\d]+)\s*<\/strong>/i)?.[1];
  if (status === "502" || status === "503" || status === "504") {
    const reference = rayId ? ` (reference ${rayId})` : "";
    return `Anna’s transcription service is temporarily unavailable (HTTP ${status}${reference}). Your recording was not saved. Please try again later.`;
  }
  return `Could not transcribe and save this recording: ${message.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").slice(0, 300)}`;
}

function countWords(value) {
  return value.trim() ? value.trim().split(/\s+/u).length : 0;
}

function renderMemories(items) {
  els.memoryList.replaceChildren();
  els.memoryCount.textContent = String(items.length);
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = '<span aria-hidden="true">✦</span><p>Your story begins here.</p><small>Saved memories will appear in this collection.</small>';
    els.memoryList.append(empty);
    return;
  }

  for (const item of items) {
    const card = document.createElement("article");
    card.className = "memory-card";
    const meta = document.createElement("div");
    meta.className = "memory-meta";
    const date = document.createElement("time");
    date.dateTime = item.created_at;
    date.textContent = new Date(item.created_at).toLocaleString(undefined, {
      dateStyle: "medium", timeStyle: "short",
    });
    const source = document.createElement("span");
    source.textContent = item.source === "speech" ? "VOICE TRANSCRIPTION" : "WRITTEN MEMORY";
    meta.append(date, source);
    const heading = document.createElement("h3");
    heading.textContent = item.title || "Untitled memory";
    const body = document.createElement("p");
    body.textContent = item.text;
    card.append(meta, heading, body);
    els.memoryList.append(card);
  }
}

async function loadMemories() {
  if (!anna) return;
  try {
    const result = await anna.tools.invoke({
      tool_id: TOOL_ID,
      method: "list_biographies",
      args: {},
    });
    renderMemories(result?.items || []);
  } catch (error) {
    setStatus(`Could not load saved memories: ${error.message}`, "error");
  }
}

async function loadTitles() {
  if (!anna) return;
  try {
    const result = await anna.tools.invoke({
      tool_id: TOOL_ID,
      method: "list_titles",
      args: {},
    });
    els.titleOptions.replaceChildren();
    for (const title of result?.titles || []) {
      const option = document.createElement("option");
      option.value = title;
      els.titleOptions.append(option);
    }
  } catch (error) {
    // Title suggestions are optional; saving still checks for a matching title.
    console.warn("Could not load saved title suggestions", error);
  }
}

async function saveMemory() {
  const text = els.text.value.trim();
  if (!text) {
    setStatus("Add a few words to your story before saving.", "error");
    els.text.focus();
    return;
  }
  if (!anna) {
    setStatus("Connect to Anna to save this memory.", "error");
    return;
  }

  els.save.disabled = true;
  els.save.querySelector("span:first-child").textContent = "Saving…";
  setStatus("Saving your memory…");
  try {
    const result = await anna.tools.invoke({
      tool_id: TOOL_ID,
      method: "save_biography",
      args: {
        title: els.title.value.trim(),
        text,
        source: entrySource,
      },
    });
    els.text.value = "";
    els.title.value = "";
    entrySource = "written";
    els.wordCount.textContent = "0 words";
    setStatus(
      result?.reused_title
        ? `Added to “${result.title}”.`
        : result?.title
          ? `Created “${result.title}” and saved your memory.`
          : "Your memory has been saved to the app backend file.",
      "success",
    );
    await loadMemories();
    await loadTitles();
  } catch (error) {
    setStatus(`Could not save this memory: ${error.message}`, "error");
  } finally {
    els.save.disabled = false;
    els.save.querySelector("span:first-child").textContent = "Save memory";
  }
}

function setMicState(label, hint, { disabled = false, recording = false } = {}) {
  els.mic.disabled = disabled;
  els.mic.setAttribute("aria-pressed", String(recording));
  els.mic.classList.toggle("is-recording", recording);
  els.mic.querySelector("strong").textContent = label;
  document.getElementById("mic-hint").textContent = hint;
}

function stopRecordingTracks() {
  if (recordingTimer) clearTimeout(recordingTimer);
  recordingTimer = null;
  recordingStream?.getTracks().forEach((track) => track.stop());
  recordingStream = null;
  recorder = null;
}

async function transcribeRecording(blob) {
  if (!anna) throw new Error("Connect to Anna before sending a recording.");
  setMicState("Sending audio…", "Anna will transcribe and save it", { disabled: true });
  setStatus("Sending your recording to the Bio Archive backend…");
  try {
    const audioBase64 = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("Could not read the audio recording."));
      reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
      reader.readAsDataURL(blob);
    });
    const result = await anna.tools.invoke({
      tool_id: TOOL_ID,
      method: "transcribe_and_save",
      args: {
        title: els.title.value.trim(),
        audio_base64: audioBase64,
        mime_type: blob.type || "audio/webm",
      },
    });
    els.title.value = "";
    setStatus(
      result?.reused_title
        ? `Transcribed and added to “${result.title}”.`
        : result?.title
          ? `Transcribed and saved under “${result.title}”.`
          : "Transcribed and saved your recording.",
      "success",
    );
    await loadMemories();
    await loadTitles();
  } finally {
    setMicState("Record a memory", "Tap to start, then tap again to send for transcription");
  }
}

async function startRecording() {
  if (!anna) {
    setStatus("Connect through anna-app dev to record and transcribe speech.", "error");
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    setStatus("This browser does not support microphone recording. You can type or paste your story.", "error");
    return;
  }
  try {
    recordingStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const options = {};
    if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
      options.mimeType = "audio/webm;codecs=opus";
    } else if (MediaRecorder.isTypeSupported("audio/webm")) {
      options.mimeType = "audio/webm";
    }
    recordingChunks = [];
    recorder = new MediaRecorder(recordingStream, options);
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data?.size) recordingChunks.push(event.data);
    });
    recorder.addEventListener("stop", async () => {
      const blob = new Blob(recordingChunks, { type: recorder?.mimeType || "audio/webm" });
      recordingChunks = [];
      stopRecordingTracks();
      if (!blob.size) {
        setMicState("Record a memory", "Tap to start, then tap again to transcribe");
        setStatus("No audio was captured. Please try again.", "error");
        return;
      }
      try {
        await transcribeRecording(blob);
      } catch (error) {
        setStatus(formatTranscriptionError(error), "error");
      }
    }, { once: true });
    recorder.start();
    setMicState("Stop recording", "Recording… tap to send for transcription", { recording: true });
    setStatus("Recording. Tap the microphone button again when you are done.");
    // Keep recordings within the platform's synchronous transcription window.
    recordingTimer = setTimeout(() => {
      if (recorder?.state === "recording") recorder.stop();
    }, 120_000);
  } catch (error) {
    stopRecordingTracks();
    setMicState("Record a memory", "Tap to start, then tap again to transcribe");
    setStatus(
      error.name === "NotAllowedError"
        ? "Microphone access was denied. Allow microphone access for Anna, then try again."
        : `Could not start microphone recording: ${error.message}`,
      "error",
    );
  }
}

function toggleRecording() {
  if (recorder?.state === "recording") {
    recorder.stop();
    return;
  }
  void startRecording();
}

async function main() {
  els.text.addEventListener("input", () => {
    els.wordCount.textContent = `${countWords(els.text.value)} words`;
  });
  els.save.addEventListener("click", saveMemory);
  els.title.addEventListener("focus", loadTitles);
  els.mic.addEventListener("click", toggleRecording);

  try {
    anna = await AnnaAppRuntime.connect();
    await anna.window.set_title({ title: "Bio Archive" });
    setStatus("Connected. Your memories are saved in the app backend.");
    await loadMemories();
    await loadTitles();
  } catch {
    setStatus("Standalone preview — connect through anna-app dev to save memories.");
  }
}

main();
