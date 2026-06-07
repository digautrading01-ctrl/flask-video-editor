import os
import subprocess
import uuid
import json
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_from_directory, abort

app = Flask(__name__)

UPLOAD_FOLDER = Path("uploads")
OUTPUT_FOLDER = Path("outputs")
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm", "flv", "wmv"}
ALLOWED_AUDIO     = {"wav", "mp3", "flac", "ogg", "m4a", "aac"}
MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2 GB
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_audio_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_AUDIO


def safe_filename(filename: str) -> str:
    """Return filename with only safe characters."""
    name, ext = os.path.splitext(filename)
    safe = "".join(c for c in name if c.isalnum() or c in "-_ ")
    return (safe or "video") + ext.lower()


def unique_path(folder: Path, suffix: str) -> Path:
    return folder / f"{uuid.uuid4().hex}{suffix}"


def run_ffmpeg(args: list[str]) -> tuple[bool, str]:
    """Run an ffmpeg command; return (success, stderr_output)."""
    cmd = ["ffmpeg", "-y"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stderr


def get_video_info(path: Path) -> dict:
    """Return basic video metadata via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {}
    try:
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        return {
            "duration": float(fmt.get("duration", 0)),
            "size": int(fmt.get("size", 0)),
            "format": fmt.get("format_name", ""),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "fps": video_stream.get("r_frame_rate", ""),
        }
    except (json.JSONDecodeError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(f.filename):
        return jsonify({"error": "File type not allowed"}), 400

    filename = safe_filename(f.filename)
    save_name = f"{uuid.uuid4().hex}_{filename}"
    save_path = UPLOAD_FOLDER / save_name
    f.save(save_path)

    info = get_video_info(save_path)
    return jsonify({"file_id": save_name, "info": info})


@app.route("/info/<file_id>")
def info(file_id: str):
    path = UPLOAD_FOLDER / file_id
    if not path.exists():
        abort(404)
    return jsonify(get_video_info(path))


@app.route("/split", methods=["POST"])
def split():
    """
    Split a video into segments by timestamp.

    Body (JSON):
    {
        "file_id": "...",
        "segments": [
            {"start": "00:00:00", "end": "00:00:10", "label": "part1"},
            {"start": "00:00:10", "end": "00:00:30", "label": "part2"}
        ]
    }
    """
    data = request.get_json(force=True)
    file_id = data.get("file_id", "")
    segments = data.get("segments", [])

    if not file_id or not segments:
        return jsonify({"error": "file_id and segments are required"}), 400

    src = UPLOAD_FOLDER / file_id
    if not src.exists():
        return jsonify({"error": "Source file not found"}), 404

    results = []
    for seg in segments:
        start = seg.get("start", "0")
        end = seg.get("end")
        label = seg.get("label", "segment")
        out_path = unique_path(OUTPUT_FOLDER, ".mp4")

        args = ["-i", str(src), "-ss", str(start)]
        if end:
            args += ["-to", str(end)]
        args += ["-c", "copy", str(out_path)]

        ok, stderr = run_ffmpeg(args)
        if ok:
            results.append({"label": label, "output_id": out_path.name, "start": start, "end": end})
        else:
            results.append({"label": label, "error": stderr[-300:], "start": start, "end": end})

    return jsonify({"results": results})


@app.route("/merge", methods=["POST"])
def merge():
    """
    Merge multiple video files into one.

    Body (JSON):
    {
        "file_ids": ["id1", "id2", "id3"],
        "source": "uploads"   // "uploads" (default) or "outputs"
    }
    """
    data = request.get_json(force=True)
    file_ids = data.get("file_ids", [])
    source = data.get("source", "uploads")

    if len(file_ids) < 2:
        return jsonify({"error": "At least two files are required for merging"}), 400

    folder = UPLOAD_FOLDER if source == "uploads" else OUTPUT_FOLDER

    # Validate all files exist
    paths = []
    for fid in file_ids:
        p = folder / fid
        if not p.exists():
            return jsonify({"error": f"File not found: {fid}"}), 404
        paths.append(p)

    # Write concat list file
    list_path = unique_path(OUTPUT_FOLDER, ".txt")
    with open(list_path, "w") as lf:
        for p in paths:
            lf.write(f"file '{p.resolve()}'\n")

    out_path = unique_path(OUTPUT_FOLDER, ".mp4")
    args = ["-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_path)]
    ok, stderr = run_ffmpeg(args)
    list_path.unlink(missing_ok=True)

    if not ok:
        return jsonify({"error": stderr[-500:]}), 500

    return jsonify({"output_id": out_path.name})


@app.route("/trim", methods=["POST"])
def trim():
    """
    Trim a video to a specific time range.

    Body (JSON):
    {
        "file_id": "...",
        "start": "00:00:05",
        "end": "00:01:30"
    }
    """
    data = request.get_json(force=True)
    file_id = data.get("file_id", "")
    start = data.get("start", "0")
    end = data.get("end")

    if not file_id:
        return jsonify({"error": "file_id is required"}), 400

    src = UPLOAD_FOLDER / file_id
    if not src.exists():
        return jsonify({"error": "Source file not found"}), 404

    out_path = unique_path(OUTPUT_FOLDER, ".mp4")
    args = ["-i", str(src), "-ss", str(start)]
    if end:
        args += ["-to", str(end)]
    args += ["-c", "copy", str(out_path)]

    ok, stderr = run_ffmpeg(args)
    if not ok:
        return jsonify({"error": stderr[-500:]}), 500

    return jsonify({"output_id": out_path.name})


@app.route("/extract-audio", methods=["POST"])
def extract_audio():
    """
    Extract audio track from a video.

    Body (JSON):
    {
        "file_id": "...",
        "format": "mp3"   // mp3 (default) | aac | wav
    }
    """
    data = request.get_json(force=True)
    file_id = data.get("file_id", "")
    fmt = data.get("format", "mp3").lower()
    if fmt not in ("mp3", "aac", "wav"):
        fmt = "mp3"

    if not file_id:
        return jsonify({"error": "file_id is required"}), 400

    src = UPLOAD_FOLDER / file_id
    if not src.exists():
        return jsonify({"error": "Source file not found"}), 404

    out_path = unique_path(OUTPUT_FOLDER, f".{fmt}")
    args = ["-i", str(src), "-vn", "-acodec"]
    if fmt == "mp3":
        args += ["libmp3lame", "-q:a", "2"]
    elif fmt == "aac":
        args += ["aac", "-b:a", "192k"]
    else:
        args += ["pcm_s16le"]
    args.append(str(out_path))

    ok, stderr = run_ffmpeg(args)
    if not ok:
        return jsonify({"error": stderr[-500:]}), 500

    return jsonify({"output_id": out_path.name})


@app.route("/convert", methods=["POST"])
def convert():
    """
    Convert a video to a different format/resolution.

    Body (JSON):
    {
        "file_id": "...",
        "format": "mp4",       // mp4 | webm | avi | mkv
        "resolution": "1280x720"  // optional, e.g. "1920x1080", "1280x720", "854x480"
    }
    """
    data = request.get_json(force=True)
    file_id = data.get("file_id", "")
    fmt = data.get("format", "mp4").lower()
    resolution = data.get("resolution")

    if fmt not in ("mp4", "webm", "avi", "mkv"):
        fmt = "mp4"

    if not file_id:
        return jsonify({"error": "file_id is required"}), 400

    src = UPLOAD_FOLDER / file_id
    if not src.exists():
        return jsonify({"error": "Source file not found"}), 404

    out_path = unique_path(OUTPUT_FOLDER, f".{fmt}")
    args = ["-i", str(src)]
    if resolution:
        args += ["-vf", f"scale={resolution}"]
    args.append(str(out_path))

    ok, stderr = run_ffmpeg(args)
    if not ok:
        return jsonify({"error": stderr[-500:]}), 500

    return jsonify({"output_id": out_path.name})


@app.route("/upload-audio", methods=["POST"])
def upload_audio():
    """Upload an audio file to be used in replace-audio or merge-audio operations."""
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_audio_file(f.filename):
        return jsonify({"error": "File type not allowed. Supported: wav, mp3, flac, ogg, m4a, aac"}), 400

    ext = f.filename.rsplit(".", 1)[1].lower()
    save_path = UPLOAD_FOLDER / f"{uuid.uuid4().hex}.{ext}"
    f.save(save_path)
    return jsonify({"audio_id": save_path.name})


@app.route("/replace-audio", methods=["POST"])
def replace_audio():
    """
    Replace the audio track of a video with a new audio file.

    Body (JSON):
    {
        "video_id": "uploaded_video_filename",
        "audio_id": "uploaded_audio_filename"
    }
    """
    data     = request.get_json(force=True)
    video_id = (data.get("video_id") or "").strip()
    audio_id = (data.get("audio_id") or "").strip()

    if not video_id or not audio_id:
        return jsonify({"error": "video_id and audio_id are required"}), 400

    video_path = UPLOAD_FOLDER / video_id
    audio_path = UPLOAD_FOLDER / audio_id
    if not video_path.exists():
        return jsonify({"error": "Video file not found"}), 404
    if not audio_path.exists():
        return jsonify({"error": "Audio file not found"}), 404

    out_path = unique_path(OUTPUT_FOLDER, ".mp4")
    args = [
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-shortest",
        str(out_path),
    ]
    ok, stderr = run_ffmpeg(args)
    if not ok:
        return jsonify({"error": stderr[-500:]}), 500

    return jsonify({"output_id": out_path.name})


@app.route("/merge-audio", methods=["POST"])
def merge_audio():
    """
    Mix a new audio file into the existing audio track of a video.

    Body (JSON):
    {
        "video_id": "uploaded_video_filename",
        "audio_id": "uploaded_audio_filename",
        "vol":      1.0   // volume multiplier for the new audio (default 1.0, range 0.1–5.0)
    }
    """
    data     = request.get_json(force=True)
    video_id = (data.get("video_id") or "").strip()
    audio_id = (data.get("audio_id") or "").strip()
    try:
        vol = float(data.get("vol", 1.0))
        vol = max(0.1, min(5.0, vol))
    except (TypeError, ValueError):
        vol = 1.0

    if not video_id or not audio_id:
        return jsonify({"error": "video_id and audio_id are required"}), 400

    video_path = UPLOAD_FOLDER / video_id
    audio_path = UPLOAD_FOLDER / audio_id
    if not video_path.exists():
        return jsonify({"error": "Video file not found"}), 404
    if not audio_path.exists():
        return jsonify({"error": "Audio file not found"}), 404

    out_path = unique_path(OUTPUT_FOLDER, ".mp4")

    if vol != 1.0:
        filter_complex = (
            f"[1:a]volume={vol:.2f}[a1];"
            "[0:a][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )
    else:
        filter_complex = "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0[aout]"

    args = [
        "-i", str(video_path),
        "-i", str(audio_path),
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        str(out_path),
    ]
    ok, stderr = run_ffmpeg(args)
    if not ok:
        return jsonify({"error": stderr[-500:]}), 500

    return jsonify({"output_id": out_path.name})


@app.route("/download/<folder>/<file_id>")
def download(folder: str, file_id: str):
    if folder == "uploads":
        directory = UPLOAD_FOLDER.resolve()
    elif folder == "outputs":
        directory = OUTPUT_FOLDER.resolve()
    else:
        abort(404)
    return send_from_directory(directory, file_id, as_attachment=True)


@app.route("/list-outputs")
def list_outputs():
    files = [
        {"name": f.name, "size": f.stat().st_size}
        for f in OUTPUT_FOLDER.iterdir()
        if f.is_file() and not f.name.endswith(".txt")
    ]
    return jsonify(files)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
