/* =========================================================
   Flask Video Editor – Front-end logic
   ========================================================= */

let currentFileId = null;

// ── helpers ────────────────────────────────────────────────

function setStatus(el, msg, type = "") {
  el.textContent = msg;
  el.className = "status " + type;
}

function fmtBytes(b) {
  if (b < 1024) return b + " B";
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + " KB";
  return (b / 1024 / 1024).toFixed(1) + " MB";
}

function fmtDuration(s) {
  if (!s) return "—";
  const h = Math.floor(s / 3600).toString().padStart(2, "0");
  const m = Math.floor((s % 3600) / 60).toString().padStart(2, "0");
  const sec = (s % 60).toFixed(1).toString().padStart(4, "0");
  return `${h}:${m}:${sec}`;
}

async function apiFetch(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

function enableActionButtons(enabled) {
  ["splitBtn", "trimBtn", "audioBtn", "convertBtn", "replaceAudioBtn", "mixAudioBtn"].forEach(id => {
    document.getElementById(id).disabled = !enabled;
  });
}

// ── Upload ─────────────────────────────────────────────────

document.getElementById("uploadBtn").addEventListener("click", async () => {
  const fileInput = document.getElementById("videoFile");
  const status = document.getElementById("uploadStatus");
  const infoBox = document.getElementById("videoInfo");

  if (!fileInput.files.length) {
    setStatus(status, "Please select a file first.", "err");
    return;
  }

  // Sanitise the filename to ASCII-only to avoid a browser DOMException
  // ("The string did not match the expected pattern") thrown by FormData
  // when the file name contains Unicode characters (e.g. …, CJK, emoji).
  const rawFile = fileInput.files[0];
  const ext = rawFile.name.includes(".") ? rawFile.name.slice(rawFile.name.lastIndexOf(".")) : "";
  const safeFile = new File([rawFile], "upload" + ext, { type: rawFile.type });

  const formData = new FormData();
  formData.append("file", safeFile);
  setStatus(status, "Uploading…", "loading");

  try {
    const res = await fetch("/upload", { method: "POST", body: formData });
    const data = await res.json();
    if (data.error) { setStatus(status, "Error: " + data.error, "err"); return; }

    currentFileId = data.file_id;
    setStatus(status, `Uploaded: ${data.file_id}`, "ok");
    enableActionButtons(true);

    const info = data.info || {};
    infoBox.innerHTML = `
      <b>File ID:</b> <span>${data.file_id}</span><br>
      <b>Duration:</b> <span>${fmtDuration(info.duration)}</span> &nbsp;
      <b>Resolution:</b> <span>${info.width || "?"}×${info.height || "?"}</span> &nbsp;
      <b>Size:</b> <span>${fmtBytes(info.size || 0)}</span><br>
      <b>Format:</b> <span>${info.format || "?"}</span>
    `;
    infoBox.classList.remove("hidden");
  } catch (e) {
    setStatus(status, "Upload failed: " + e.message, "err");
  }
});

// ── Split ──────────────────────────────────────────────────

let segmentCount = 0;

function addSegmentRow(start = "", end = "", label = "") {
  segmentCount++;
  const idx = segmentCount;
  const div = document.createElement("div");
  div.className = "segment";
  div.dataset.idx = idx;
  div.innerHTML = `
    <input type="text" placeholder="Start (00:00:00)" value="${start}" class="seg-start" title="Start time" />
    <input type="text" placeholder="End (00:00:10)"   value="${end}"   class="seg-end"   title="End time" />
    <input type="text" placeholder="Label"            value="${label}" class="label-input seg-label" title="Label" />
    <button onclick="this.closest('.segment').remove()">✕</button>
  `;
  document.getElementById("segmentList").appendChild(div);
}

document.getElementById("addSegmentBtn").addEventListener("click", () => addSegmentRow());

// Pre-populate with one example segment
addSegmentRow("00:00:00", "00:00:30", "part1");

document.getElementById("splitBtn").addEventListener("click", async () => {
  const status = document.getElementById("splitStatus");
  const resultsEl = document.getElementById("splitResults");

  if (!currentFileId) { setStatus(status, "No file uploaded.", "err"); return; }

  const rows = document.querySelectorAll(".segment");
  const segments = Array.from(rows).map(row => ({
    start: row.querySelector(".seg-start").value.trim(),
    end:   row.querySelector(".seg-end").value.trim() || undefined,
    label: row.querySelector(".seg-label").value.trim() || "segment",
  }));

  if (!segments.length) { setStatus(status, "Add at least one segment.", "err"); return; }

  setStatus(status, "Splitting…", "loading");
  try {
    const data = await apiFetch("/split", { file_id: currentFileId, segments });
    if (data.error) { setStatus(status, "Error: " + data.error, "err"); return; }

    setStatus(status, `Done — ${data.results.length} segment(s).`, "ok");
    resultsEl.innerHTML = data.results.map(r =>
      r.error
        ? `<div class="result-item"><span style="color:#f87171">${r.label}: ${r.error}</span></div>`
        : `<div class="result-item">
             <span>${r.label} (${r.start} → ${r.end || "end"})</span>
             <a href="/download/outputs/${r.output_id}" download>Download</a>
           </div>`
    ).join("");
    resultsEl.classList.remove("hidden");
  } catch (e) {
    setStatus(status, "Error: " + e.message, "err");
  }
});

// ── Merge ──────────────────────────────────────────────────

document.getElementById("mergeBtn").addEventListener("click", async () => {
  const status = document.getElementById("mergeStatus");
  const ids = document.getElementById("mergeIds").value
    .split("\n").map(s => s.trim()).filter(Boolean);
  const source = document.querySelector('input[name="mergeSource"]:checked').value;

  if (ids.length < 2) { setStatus(status, "Enter at least two file IDs.", "err"); return; }

  setStatus(status, "Merging…", "loading");
  try {
    const data = await apiFetch("/merge", { file_ids: ids, source });
    if (data.error) { setStatus(status, "Error: " + data.error, "err"); return; }
    setStatus(
      status,
      `Merged → <a href="/download/outputs/${data.output_id}" download style="color:#60a5fa">${data.output_id}</a>`,
      "ok"
    );
    document.getElementById("mergeStatus").innerHTML = document.getElementById("mergeStatus").textContent
      .replace(data.output_id, `<a href="/download/outputs/${data.output_id}" download style="color:#60a5fa">${data.output_id}</a>`);
    // re-set with HTML
    document.getElementById("mergeStatus").innerHTML =
      `Merged → <a href="/download/outputs/${data.output_id}" download style="color:#60a5fa">${data.output_id}</a>`;
    document.getElementById("mergeStatus").className = "status ok";
  } catch (e) {
    setStatus(status, "Error: " + e.message, "err");
  }
});

// ── Trim ───────────────────────────────────────────────────

document.getElementById("trimBtn").addEventListener("click", async () => {
  const status = document.getElementById("trimStatus");
  if (!currentFileId) { setStatus(status, "No file uploaded.", "err"); return; }

  const start = document.getElementById("trimStart").value.trim() || "0";
  const end   = document.getElementById("trimEnd").value.trim() || undefined;

  setStatus(status, "Trimming…", "loading");
  try {
    const data = await apiFetch("/trim", { file_id: currentFileId, start, end });
    if (data.error) { setStatus(status, "Error: " + data.error, "err"); return; }
    document.getElementById("trimStatus").innerHTML =
      `Done → <a href="/download/outputs/${data.output_id}" download style="color:#60a5fa">${data.output_id}</a>`;
    document.getElementById("trimStatus").className = "status ok";
  } catch (e) {
    setStatus(status, "Error: " + e.message, "err");
  }
});

// ── Extract Audio ──────────────────────────────────────────

document.getElementById("audioBtn").addEventListener("click", async () => {
  const status = document.getElementById("audioStatus");
  if (!currentFileId) { setStatus(status, "No file uploaded.", "err"); return; }

  const format = document.getElementById("audioFormat").value;
  setStatus(status, "Extracting…", "loading");
  try {
    const data = await apiFetch("/extract-audio", { file_id: currentFileId, format });
    if (data.error) { setStatus(status, "Error: " + data.error, "err"); return; }
    document.getElementById("audioStatus").innerHTML =
      `Done → <a href="/download/outputs/${data.output_id}" download style="color:#60a5fa">${data.output_id}</a>`;
    document.getElementById("audioStatus").className = "status ok";
  } catch (e) {
    setStatus(status, "Error: " + e.message, "err");
  }
});

// ── Convert ────────────────────────────────────────────────

document.getElementById("convertBtn").addEventListener("click", async () => {
  const status = document.getElementById("convertStatus");
  if (!currentFileId) { setStatus(status, "No file uploaded.", "err"); return; }

  const format     = document.getElementById("convertFormat").value;
  const resolution = document.getElementById("convertRes").value || undefined;

  setStatus(status, "Converting…", "loading");
  try {
    const data = await apiFetch("/convert", { file_id: currentFileId, format, resolution });
    if (data.error) { setStatus(status, "Error: " + data.error, "err"); return; }
    document.getElementById("convertStatus").innerHTML =
      `Done → <a href="/download/outputs/${data.output_id}" download style="color:#60a5fa">${data.output_id}</a>`;
    document.getElementById("convertStatus").className = "status ok";
  } catch (e) {
    setStatus(status, "Error: " + e.message, "err");
  }
});

// ── Output list ────────────────────────────────────────────

async function refreshOutputs() {
  const list = document.getElementById("outputList");
  try {
    const res = await fetch("/list-outputs");
    const files = await res.json();
    if (!files.length) { list.innerHTML = "<p style='color:#64748b;font-size:.85rem'>No output files yet.</p>"; return; }
    list.innerHTML = files.map(f =>
      `<div class="output-item">
         <span class="name">${f.name}</span>
         <span class="size">${fmtBytes(f.size)}</span>
         <a href="/download/outputs/${f.name}" download>Download</a>
       </div>`
    ).join("");
  } catch (e) {
    list.innerHTML = `<p style='color:#f87171'>Failed to load: ${e.message}</p>`;
  }
}

document.getElementById("refreshOutputsBtn").addEventListener("click", refreshOutputs);
refreshOutputs();

// ── Audio upload helper ─────────────────────────────────────

async function uploadAudio(fileInput, statusEl) {
  if (!fileInput.files.length) {
    setStatus(statusEl, "Please select an audio file first.", "err");
    return null;
  }

  const rawFile = fileInput.files[0];
  const ext = rawFile.name.includes(".") ? rawFile.name.slice(rawFile.name.lastIndexOf(".")) : "";
  const safeFile = new File([rawFile], "audio" + ext, { type: rawFile.type });

  const formData = new FormData();
  formData.append("file", safeFile);
  setStatus(statusEl, "Uploading audio…", "loading");

  const res  = await fetch("/upload-audio", { method: "POST", body: formData });
  const data = await res.json();
  if (data.error) {
    setStatus(statusEl, "Audio upload error: " + data.error, "err");
    return null;
  }
  return data.audio_id;
}

// ── Replace Audio ───────────────────────────────────────────

document.getElementById("replaceAudioBtn").addEventListener("click", async () => {
  const fileInput = document.getElementById("replaceAudioFile");
  const status    = document.getElementById("replaceAudioStatus");

  if (!currentFileId) { setStatus(status, "No video uploaded.", "err"); return; }

  document.getElementById("replaceAudioBtn").disabled = true;
  try {
    const audioId = await uploadAudio(fileInput, status);
    if (!audioId) { document.getElementById("replaceAudioBtn").disabled = false; return; }

    setStatus(status, "Replacing audio track…", "loading");
    const data = await apiFetch("/replace-audio", { video_id: currentFileId, audio_id: audioId });

    if (data.error) {
      setStatus(status, "Error: " + data.error, "err");
    } else {
      status.innerHTML = `Done → <a href="/download/outputs/${data.output_id}" download style="color:#60a5fa">${data.output_id}</a>`;
      status.className = "status ok";
    }
  } catch (e) {
    setStatus(status, "Request failed: " + e.message, "err");
  }
  document.getElementById("replaceAudioBtn").disabled = false;
});

// ── Mix Audio ───────────────────────────────────────────────

document.getElementById("mixAudioVol").addEventListener("input", () => {
  document.getElementById("mixAudioVolLabel").textContent =
    parseFloat(document.getElementById("mixAudioVol").value).toFixed(1) + "×";
});

document.getElementById("mixAudioBtn").addEventListener("click", async () => {
  const fileInput = document.getElementById("mixAudioFile");
  const status    = document.getElementById("mixAudioStatus");
  const vol       = parseFloat(document.getElementById("mixAudioVol").value);

  if (!currentFileId) { setStatus(status, "No video uploaded.", "err"); return; }

  document.getElementById("mixAudioBtn").disabled = true;
  try {
    const audioId = await uploadAudio(fileInput, status);
    if (!audioId) { document.getElementById("mixAudioBtn").disabled = false; return; }

    setStatus(status, "Mixing audio tracks…", "loading");
    const data = await apiFetch("/merge-audio", { video_id: currentFileId, audio_id: audioId, vol });

    if (data.error) {
      setStatus(status, "Error: " + data.error, "err");
    } else {
      status.innerHTML = `Done → <a href="/download/outputs/${data.output_id}" download style="color:#60a5fa">${data.output_id}</a>`;
      status.className = "status ok";
    }
  } catch (e) {
    setStatus(status, "Request failed: " + e.message, "err");
  }
  document.getElementById("mixAudioBtn").disabled = false;
});
