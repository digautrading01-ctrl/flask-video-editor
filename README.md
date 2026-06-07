# Flask Video Editor

A web-based video editing tool built with Python Flask and FFmpeg.

## Features

| Feature | Endpoint | Description |
|---|---|---|
| Upload | `POST /upload` | Upload a video file |
| Split | `POST /split` | Cut a video into multiple segments by timestamps |
| Merge | `POST /merge` | Concatenate multiple videos into one |
| Trim | `POST /trim` | Trim a video to a specific time range |
| Extract Audio | `POST /extract-audio` | Export the audio track (MP3 / AAC / WAV) |
| Convert | `POST /convert` | Change format and/or resolution |
| Replace Audio | `POST /replace-audio` | Strip existing audio and replace with a new track |
| Mix Audio | `POST /merge-audio` | Blend a new audio file with the existing audio track |
| Download | `GET /download/<folder>/<file_id>` | Download any processed file |
| List Outputs | `GET /list-outputs` | List all generated output files |

## Requirements

- Python 3.11+
- [FFmpeg](https://ffmpeg.org/download.html) installed and available on `PATH`
- pip packages: `flask>=3.0.0`

## Setup

```bash
# 1. Clone / copy the project folder
cd flask-video-editor

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the server
python app.py
```

Open your browser at **http://localhost:5000**.

## Project Structure

```
flask-video-editor/
├── app.py              # Flask application & API routes
├── requirements.txt
├── README.md
├── uploads/            # Uploaded source videos (auto-created)
├── outputs/            # Processed output files (auto-created)
├── templates/
│   └── index.html      # Single-page UI
└── static/
    ├── css/style.css
    └── js/app.js
```

## API Reference

### Upload a video
```
POST /upload
Content-Type: multipart/form-data

file: <video file>
```
Response:
```json
{ "file_id": "abc123_video.mp4", "info": { "duration": 120.5, ... } }
```

### Split into segments
```
POST /split
Content-Type: application/json

{
  "file_id": "abc123_video.mp4",
  "segments": [
    { "start": "00:00:00", "end": "00:00:30", "label": "intro" },
    { "start": "00:00:30", "end": "00:01:00", "label": "main" }
  ]
}
```

### Merge videos
```
POST /merge
Content-Type: application/json

{
  "file_ids": ["id1.mp4", "id2.mp4"],
  "source": "uploads"
}
```
`source` can be `"uploads"` (default) or `"outputs"`.

### Trim a video
```
POST /trim
Content-Type: application/json

{ "file_id": "abc123_video.mp4", "start": "00:00:10", "end": "00:01:00" }
```

### Extract audio
```
POST /extract-audio
Content-Type: application/json

{ "file_id": "abc123_video.mp4", "format": "mp3" }
```
`format`: `mp3` (default), `aac`, or `wav`.

### Convert / resize
```
POST /convert
Content-Type: application/json

{ "file_id": "abc123_video.mp4", "format": "webm", "resolution": "1280x720" }
```

### Upload an audio file
```
POST /upload-audio
Content-Type: multipart/form-data

file: <audio file>
```
Response:
```json
{ "audio_id": "def456.mp3" }
```
Supported formats: WAV, MP3, FLAC, OGG, M4A, AAC.

### Replace audio track
```
POST /replace-audio
Content-Type: application/json

{ "video_id": "abc123_video.mp4", "audio_id": "def456.mp3" }
```
Strips the original audio track and replaces it with the uploaded audio file.
The output is trimmed to whichever input is shorter (`-shortest`).

### Mix audio into video
```
POST /merge-audio
Content-Type: application/json

{ "video_id": "abc123_video.mp4", "audio_id": "def456.mp3", "vol": 1.0 }
```
Blends the new audio file with the existing video audio using FFmpeg's `amix` filter.
`vol` controls the volume multiplier for the new audio (default `1.0`, range `0.1–5.0`).

## Notes

- All processed files are stored in the `outputs/` directory and can be downloaded via `/download/outputs/<file_id>`.
- For large videos (> a few hundred MB) ensure your system has enough disk space in both `uploads/` and `outputs/`.
- FFmpeg must be on the system `PATH`. On Windows, add the FFmpeg `bin/` folder to your environment variables.
