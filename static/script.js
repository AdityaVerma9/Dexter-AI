console.log("streaming script loaded");

// Global variables
let captureCtx = null;
let processor = null;
let sourceNode = null;
let ws = null;
let isRecording = false;
let currentAudioSession = null; 
const sessionId = Math.random().toString(36).substring(7);

// Audio playback state
let audioChunks = [];
let playbackCtx = null;
let playbackTime = 0;
let unlockedPlayback = false;
const JITTER_SECS = 0.12;
const FADE_SECS = 0.006;

// DOM elements
const recordBtn = document.getElementById("record-btn");
const statusEl = document.getElementById("upload-status");

// Settings & Keys Management
const KEYSTORE = 'dexter.keys.v1';

function loadKeys() {
  try { 
    return JSON.parse(localStorage.getItem(KEYSTORE)) || {}; 
  } catch { 
    return {}; 
  }
}

function saveKeys(keys) { 
  localStorage.setItem(KEYSTORE, JSON.stringify(keys)); 
}

function buildWSUrl() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const base = `${proto}//${location.host}/ws/stream`;
  const k = loadKeys();
  const params = new URLSearchParams();
  
  const currentSession = k.session || sessionId;
  params.set('session', currentSession);
  
  if (k.aai) params.set('aai', k.aai);
  if (k.gemini) params.set('gemini', k.gemini);
  if (k.murf) params.set('murf', k.murf);
  if (k.news) params.set('news', k.news);
  if (k.weather) params.set('weather', k.weather);
  
  return `${base}?${params.toString()}`;
}

// Chat UI helpers
let _cachedChatEl = null;
function resolveChatHistoryEl() {
  if (_cachedChatEl) return _cachedChatEl;
  const trySelectors = [
    "#transcription .transcription-text",
    ".transcription-text",
    "#transcription",
    "#transcript"
  ];
  for (const s of trySelectors) {
    try {
      const el = document.querySelector(s);
      if (el) {
        _cachedChatEl = el;
        break;
      }
    } catch (e) { /* ignore */ }
  }
  if (!_cachedChatEl) {
    const fallback = document.createElement("div");
    fallback.className = "transcription-text";
    fallback.textContent = "[transcription placeholder]";
    document.body.appendChild(fallback);
    _cachedChatEl = fallback;
    console.warn("transcription container not found - created fallback");
  }
  return _cachedChatEl;
}

function initializeChatBox() {
  const el = resolveChatHistoryEl();
  if (el) {
    el.innerHTML = "";
    addChatMessage("System", "Dexter's Voice Agent initialized. Ready for surveillance...", "system");
  }
}

// Audio management
function resetAudioChunks() {
  audioChunks = [];
  currentAudioSession = null;
  console.log("Audio chunks reset");
}

function addAudioChunk(audioData, chunkNumber, totalChunks) {
  audioChunks.push({ data: audioData, chunkNumber, timestamp: Date.now() });
  console.log(`Accumulated chunk #${chunkNumber}, total: ${audioChunks.length}`);
}

function appendAudioStatus(message, kind = "info") {
  const prefix = kind === "error" ? "Error" : kind === "success" ? "Success" : "Info";
  console.log(`${prefix}: ${message}`);
  if (statusEl) statusEl.textContent = `${prefix}: ${message}`;
}

async function ensurePlaybackCtx() {
  if (!playbackCtx) playbackCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (playbackCtx.state === "suspended") {
    try { await playbackCtx.resume(); } catch {}
  }
  if (playbackTime === 0) playbackTime = playbackCtx.currentTime + JITTER_SECS;
}

async function playAudioChunk(base64Data) {
  try {
    await ensurePlaybackCtx();
    const audioData = Uint8Array.from(atob(base64Data), c => c.charCodeAt(0)).buffer;
    const pcm16 = new Int16Array(audioData);
    const float32 = new Float32Array(pcm16.length);
    
    for (let i = 0; i < pcm16.length; i++) {
      float32[i] = pcm16[i] / 0x8000;
    }

    const audioBuffer = playbackCtx.createBuffer(1, float32.length, 44100);
    audioBuffer.copyToChannel(float32, 0);

    const src = playbackCtx.createBufferSource();
    src.buffer = audioBuffer;
    src.connect(playbackCtx.destination);

    const startAt = Math.max(playbackTime, playbackCtx.currentTime + 0.01);
    src.start(startAt);
    playbackTime = startAt + audioBuffer.duration;

    console.log(`Played PCM chunk (${audioBuffer.duration.toFixed(2)}s)`);
  } catch (err) {
    console.error("Error in playAudioChunk:", err);
  }
}

function acknowledgeAudioData(type, data) {
  const timestamp = new Date().toLocaleTimeString();

  switch (type) {
    case "audio_start":
      console.log(`[${timestamp}] Audio started - Context: ${data.context_id}`);
      resetAudioChunks();
      currentAudioSession = data.context_id;
      ensurePlaybackCtx();
      break;

    case "audio_chunk":
      console.log(`[${timestamp}] Chunk #${data.chunk_number}`);
      addAudioChunk(data.audio, data.chunk_number, data.total_chunks_so_far);
      if (data.audio) playAudioChunk(data.audio);
      break;

    case "audio_complete":
      console.log(`[${timestamp}] Audio complete - ${data.total_chunks} chunks`);
      break;

    case "audio_error":
      console.error(`[${timestamp}] Audio error: ${data.message}`);
      break;
  }
}

// Chat UI
function addChatMessage(sender, text, messageType = null) {
  const el = resolveChatHistoryEl();
  if (!el) return;

  const messageDiv = document.createElement("div");
  messageDiv.classList.add("chat-message");

  const s = (sender || "").toString().toLowerCase();
  if (s === "you" || s === "user") {
    messageDiv.classList.add("user");
  } else if (s === "assistant" || s === "dexter") {
    messageDiv.classList.add("assistant", "dexter");
  } else if (messageType === "system") {
    messageDiv.classList.add("system");
  } else {
    messageDiv.classList.add("assistant");
  }

  const messageContent = document.createElement("div");
  messageContent.classList.add("message-content");

  const senderLabel = document.createElement("div");
  senderLabel.classList.add("sender-label");
  senderLabel.textContent = sender;

  const messageText = document.createElement("div");
  messageText.classList.add("message-text");
  messageText.textContent = text;

  messageContent.appendChild(senderLabel);
  messageContent.appendChild(messageText);
  messageDiv.appendChild(messageContent);

  el.appendChild(messageDiv);
  el.scrollTop = el.scrollHeight;
}

function addTextMessage(text, type) {
  const sender = type === "user" ? "You" : "Assistant";
  addChatMessage(sender, text, type);
}

function appendChatMessage(sender, text) {
  addChatMessage(sender, text);
}

// Weather and News
async function fetchWeather(city) {
  try {
    const k = loadKeys();
    const sessionParam = k.session ? `&session=${encodeURIComponent(k.session)}` : '';
    const url = `/api/weather?city=${encodeURIComponent(city)}${sessionParam}`;
    
    const res = await fetch(url);
    if (!res.ok) {
      const errorText = await res.text().catch(() => "");
      appendAudioStatus(`Weather fetch failed: ${res.status} ${errorText}`, "error");
      return null;
    }

    const json = await res.json();
    const weather = json.ok ? json.weather : json;
    
    if (!weather || json.error) {
      appendAudioStatus(`Weather error: ${json.error || "Unknown error"}`, "error");
      return null;
    }

    console.log("Weather:", weather);
    appendAudioStatus(
      `Weather in ${weather.location || city}: ${weather.temperature_c ?? "N/A"}C, ${weather.condition || "N/A"}`,
      "success"
    );
    return weather;
  } catch (err) {
    console.error("Weather error:", err);
    appendAudioStatus(`Weather error: ${err.message}`, "error");
    return null;
  }
}

async function fetchNews() {
  try {
    const k = loadKeys();
    const sessionParam = k.session ? `&session=${encodeURIComponent(k.session)}` : '';
    const res = await fetch(`/api/news?country=us${sessionParam}`);
    
    if (!res.ok) {
      appendChatMessage("Assistant", "Sorry, I couldn't fetch the news right now.");
      return;
    }
    
    const json = await res.json();
    if (json.ok && Array.isArray(json.news)) {
      appendChatMessage("Assistant", "Here are the latest headlines:");
      renderNewsList(json.news);
    } else {
      appendChatMessage("Assistant", `News error: ${json.error || "Unknown error"}`);
    }
  } catch (err) {
    console.error("News fetch failed", err);
    appendChatMessage("Assistant", "Sorry, I couldn't fetch the news right now.");
  }
}

function renderWeatherCard(data) {
  const el = resolveChatHistoryEl();
  if (!el) return;

  const wrapper = document.createElement("div");
  wrapper.className = "message received weather-card";

  const title = document.createElement("div");
  title.style.fontWeight = "600";
  title.textContent = `Weather - ${data.location || "Unknown"}, ${data.country || ""}`;

  const desc = document.createElement("div");
  desc.textContent = data.condition || "No description";

  const metrics = document.createElement("div");
  metrics.style.marginTop = "0.3rem";
  metrics.textContent = `Temp: ${data.temperature_c ?? "N/A"}C`;

  wrapper.appendChild(title);
  wrapper.appendChild(desc);
  wrapper.appendChild(metrics);
  el.appendChild(wrapper);
  el.scrollTop = el.scrollHeight;
}

function renderNewsList(articles) {
  const el = resolveChatHistoryEl();
  if (!el) return;
  const wrapper = document.createElement("div");
  wrapper.className = "message received news-list";

  const title = document.createElement("div");
  title.style.fontWeight = "600";
  title.textContent = "Top headlines";

  wrapper.appendChild(title);

  if (!Array.isArray(articles) || articles.length === 0) {
    const none = document.createElement("div");
    none.textContent = "No headlines available.";
    wrapper.appendChild(none);
  } else {
    const list = document.createElement("div");
    list.style.marginTop = "0.4rem";
    for (const a of articles) {
      const item = document.createElement("div");
      item.style.marginTop = "0.45rem";

      const link = document.createElement("a");
      link.href = a.url || "#";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = a.title || "(no title)";

      const source = document.createElement("div");
      source.style.fontSize = "0.85rem";
      source.style.color = "#ccc";
      source.textContent = a.source || "";

      item.appendChild(link);
      item.appendChild(source);
      list.appendChild(item);
    }
    wrapper.appendChild(list);
  }

  el.appendChild(wrapper);
  el.scrollTop = el.scrollHeight;
}

function handleUserIntent(text) {
  const lower = text.toLowerCase();
  if (lower.includes("weather")) {
    fetchWeather("London");
  } else if (lower.includes("news") || lower.includes("headlines") || lower.includes("latest")) {
    fetchNews();
  }
}

// Audio utils
function downsampleBuffer(buffer, originalRate, targetRate) {
  if (originalRate === targetRate) return buffer;
  const ratio = originalRate / targetRate;
  const newLen = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLen);
  let offsetResult = 0, offsetBuffer = 0;
  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let accum = 0, count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
      accum += buffer[i]; count++;
    }
    result[offsetResult] = count ? accum / count : 0;
    offsetResult++; offsetBuffer = nextOffsetBuffer;
  }
  return result;
}

function floatTo16BitPCM(float32Array) {
  const buffer = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buffer);
  let offset = 0;
  for (let i = 0; i < float32Array.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Int16Array(buffer);
}

// Recording functions
async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    captureCtx = new (window.AudioContext || window.webkitAudioContext)();
    const inputSampleRate = captureCtx.sampleRate || 48000;

    sourceNode = captureCtx.createMediaStreamSource(stream);
    processor = captureCtx.createScriptProcessor(4096, 1, 1);

    const wsUrl = buildWSUrl();
    console.log("Connecting to:", wsUrl);
    
    ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      console.log("WS connected with API keys");
      if (statusEl) statusEl.textContent = "Listening...";

      sourceNode.connect(processor);
      processor.connect(captureCtx.destination);

      processor.onaudioprocess = (event) => {
        const inputData = event.inputBuffer.getChannelData(0);
        const downsampled = downsampleBuffer(inputData, inputSampleRate, 16000);
        const pcm16 = floatTo16BitPCM(downsampled);
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(pcm16.buffer);
      };

      isRecording = true;
      recordBtn.classList.add("recording");
      recordBtn.innerText = "Stop";
    };

    ws.onmessage = (evt) => {
      let data = null;
      try {
        data = JSON.parse(evt.data);
      } catch (err) {
        console.warn("WS parse failed:", err);
        return;
      }
    
      const tryHandleUserIntent = async (text) => {
        if (!text) return;
        try {
          await handleUserIntent(text);
        } catch (e) {
          console.warn("handleUserIntent error:", e);
        }
      };
    
      try {
        if (data.type === "partial") {
          if (statusEl) statusEl.textContent = `... ${data.text}`;
    
        } else if (data.type === "transcript") {
          if (statusEl) statusEl.textContent = `Heard: ${data.text}`;
          if (data.end_of_turn) appendChatMessage("You", data.text);
    
        } else if (data.type === "turn_end") {
          console.log("End of turn:", data);
          if (statusEl) statusEl.textContent = "Waiting for assistant...";
    
        } else if (data.type === "assistant") {
          appendChatMessage("Assistant", data.text);
          tryHandleUserIntent(data.text);
    
        } else if (data.type === "llm_chunk") {
          console.log("LLM chunk:", data.text);
    
        } else if (data.type === "llm_response") {
          appendChatMessage("Assistant", data.text);
          tryHandleUserIntent(data.text);
    
        } else if (data.type === "audio_start") {
          acknowledgeAudioData("audio_start", data);
          appendAudioStatus("Starting audio generation...");
    
        } else if (data.type === "audio_chunk") {
          acknowledgeAudioData("audio_chunk", data);
    
        } else if (data.type === "audio_complete") {
          acknowledgeAudioData("audio_complete", data);
          appendAudioStatus(`Audio complete! Received ${audioChunks.length} chunks.`, "success");
    
        } else if (data.type === "audio_error") {
          acknowledgeAudioData("audio_error", data);
          appendAudioStatus(`Audio generation failed: ${data.message}`, "error");
    
        } else if (data.type === "error") {
          console.error("Server error:", data.message);
          if (statusEl) statusEl.textContent = `Error: ${data.message}`;
          addTextMessage(`Error: ${data.message}`, "error");
    
        } else if (data.type === "info") {
          if (statusEl) statusEl.textContent = `Info: ${data.message}`;
    
        } else if (data.type === "echo") {
          console.log("Echo:", data.text);
    
        } else if (data.type === "weather") {
          if (data.text) appendChatMessage("Assistant", data.text);
          try {
            const weatherObj = data.data || data.payload || null;
            if (weatherObj) {
              const summary = `Weather in ${weatherObj.location || "Unknown"}, ${weatherObj.country || ""}: ` +
                              `${weatherObj.condition || "N/A"}, ${weatherObj.temperature_c ?? "N/A"}C`;
              appendAudioStatus(summary, "success");
              renderWeatherCard(weatherObj);
            }
          } catch (e) {
            console.error("Failed rendering weather:", e);
          }
          tryHandleUserIntent(data.text);
    
        } else if (data.type === "news") {
          if (data.text) appendChatMessage("Assistant", data.text);
          try {
            let articles = [];
            if (Array.isArray(data.data)) articles = data.data;
            else if (Array.isArray(data.data?.articles)) articles = data.data.articles;
            else if (Array.isArray(data.articles)) articles = data.articles;
    
            if (articles.length > 0) renderNewsList(articles);
            else console.warn("News message had no articles array");
          } catch (e) {
            console.error("Failed rendering news:", e);
          }
          tryHandleUserIntent(data.text);
    
        } else {
          console.log("WS msg (unhandled):", data);
        }
      } catch (err) {
        console.error("Exception in ws.onmessage:", err);
      }
    };
    
    ws.onerror = (err) => {
      console.error("WS error", err);
      if (statusEl) statusEl.textContent = "Connection error";
    };

    ws.onclose = (event) => {
      console.log("WS closed:", event.code, event.reason);
      if (statusEl) statusEl.textContent = "Disconnected";
      
      if (isRecording) {
        setTimeout(() => {
          console.log("Auto-reconnecting WebSocket...");
          startRecording();
        }, 1000);
      }
    };

  } catch (err) {
    console.error("Mic error:", err);
    alert("Microphone access denied or not available.");
  }
}

function stopRecording() {
  isRecording = false; 
  
  if (ws && ws.readyState === WebSocket.OPEN) {
    try { ws.send("__stop"); } catch {}
    try { ws.close(); } catch {}
  }
  
  if (processor) {
    try {
      processor.disconnect();
      processor.onaudioprocess = null;
    } catch {}
    processor = null;
  }
  
  if (sourceNode) {
    try { sourceNode.disconnect(); } catch {}
    sourceNode = null;
  }
  
  if (captureCtx) {
    try { captureCtx.close(); } catch {}
    captureCtx = null;
  }

  recordBtn.classList.remove("recording");
  recordBtn.innerText = "Record";
  if (statusEl) statusEl.textContent = "Processing...";
}

// Settings modal
function initializeSettingsModal() {
  const modal = document.getElementById('settings-modal');
  const settingsBtn = document.getElementById('settings-btn');
  const cancelBtn = document.getElementById('settings-cancel');
  const saveBtn = document.getElementById('settings-save');
  const backdrop = modal?.querySelector('.modal__backdrop');
  
  if (!modal || !settingsBtn) {
    console.warn("Settings modal elements not found");
    return;
  }
  
  function fillForm() {
    const k = loadKeys();
    const elements = [
      ['key-aai', k.aai || ''],
      ['key-gemini', k.gemini || ''],
      ['key-murf', k.murf || ''],
      ['key-news', k.news || ''],
      ['key-weather', k.weather || ''],
      ['session-id', k.session || sessionId]
    ];
    
    elements.forEach(([id, value]) => {
      const el = document.getElementById(id);
      if (el) el.value = value;
    });
  }
  
  function openModal() {
    fillForm();
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  }
  
  function closeModal() {
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  }
  
  settingsBtn.addEventListener('click', openModal);
  if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
  if (backdrop) backdrop.addEventListener('click', closeModal);
  
  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      const keys = {
        aai: document.getElementById('key-aai')?.value?.trim() || '',
        gemini: document.getElementById('key-gemini')?.value?.trim() || '',
        murf: document.getElementById('key-murf')?.value?.trim() || '',
        news: document.getElementById('key-news')?.value?.trim() || '',
        weather: document.getElementById('key-weather')?.value?.trim() || '',
        session: document.getElementById('session-id')?.value?.trim() || sessionId
      };
      
      saveKeys(keys);
      console.log("API keys saved:", Object.keys(keys).filter(k => keys[k]));
      closeModal();
      
      if (ws && ws.readyState === WebSocket.OPEN) {
        console.log("Reconnecting WebSocket with updated keys...");
        try { ws.close(); } catch {}
      }
    });
  }
}

// Event listeners
if (recordBtn) {
  recordBtn.addEventListener("click", async () => {
    if (!unlockedPlayback) {
      await ensurePlaybackCtx();
      unlockedPlayback = true;
    }
    if (!isRecording) startRecording();
    else stopRecording();
  });
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  initializeChatBox();
  initializeSettingsModal();
});

// Fallback initialization if DOMContentLoaded already fired
if (document.readyState === 'loading') {
  // Wait for DOMContentLoaded
} else {
  // DOM already loaded
  initializeChatBox();
  initializeSettingsModal();
}