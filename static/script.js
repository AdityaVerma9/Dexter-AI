/* existing script.js content (unchanged) */
function getSessionId() {
  const urlParams = new URLSearchParams(window.location.search);
  let sessionId = urlParams.get("session_id");
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    urlParams.set("session_id", sessionId);
    window.history.replaceState({}, "", `${window.location.pathname}?${urlParams}`);
  }
  return sessionId;
}

let sessionId = getSessionId();
let mediaRecorder;
let audioChunks = [];
let isRecording = false;

const recordBtn = document.getElementById("record-btn");
const statusDiv = document.getElementById("upload-status");
const transcriptDiv = document.getElementById("transcription");
const downloadLink = document.getElementById("download-link");
const echoAudio = document.getElementById("echo-audio");

recordBtn.addEventListener("click", () => {
  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
});

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    isRecording = true;
    recordBtn.innerText = "⏹ Stop Recording";
    recordBtn.classList.add("recording");
    statusDiv.innerText = "🎙️ Listening...";

    mediaRecorder.ondataavailable = event => {
      audioChunks.push(event.data);
    };

    mediaRecorder.onstop = async () => {
      isRecording = false;
      recordBtn.innerText = "🎤 Start Recording";
      recordBtn.classList.remove("recording");
      statusDiv.innerText = "Processing your question...";

      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      const formData = new FormData();
      formData.append("file", audioBlob, "recording.webm");

      try {
        const response = await fetch(`/agent/chat/${sessionId}`, {
          method: "POST",
          body: formData,
        });

        const result = await response.json();

        if (!response.ok || !result.audio_url) {
          statusDiv.innerText = "⚠️ Something went wrong.";
          return;
        }

        statusDiv.innerText = "✅ Response ready.";
        transcriptDiv.innerText = `You said: ${result.transcription || "(no speech detected)"}

LLM: ${result.llm_response}`;

        echoAudio.src = result.audio_url;
        echoAudio.play();

        downloadLink.href = result.audio_url;
        downloadLink.download = "llm_response.mp3";
        downloadLink.style.display = "inline";

      } catch (error) {
        console.error("Client error:", error);
        statusDiv.innerText = "❌ Network or server error.";
      }
    };

    mediaRecorder.start();
  } catch (error) {
    alert("Microphone access denied or not supported.");
    console.error(error);
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    statusDiv.innerText = "Stopping...";
  }
}
