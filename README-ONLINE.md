# MUNKS Audio Processor — Render Edition

Mobile-friendly YouTube/YouTube Music/SoundCloud audio processor using Flask, yt-dlp and FFmpeg.

## Deploy to Render

1. Create a GitHub repository.
2. Upload the **contents of this folder** to the repository root.
3. In Render: New + → Web Service → connect the GitHub repository.
4. Runtime: **Docker**.
5. Render will detect `Dockerfile`; no Start Command is needed.
6. Health Check Path: `/health` (also configured in `render.yaml`).
7. Create Web Service.
8. Open the generated `https://....onrender.com` URL on Android/iPhone.

## Important

- The service uses FFmpeg inside the Docker image.
- Render's free instance has limited CPU/RAM, can sleep when idle, and its local filesystem is ephemeral. Download generated files promptly.
- This project is intended for URLs/content you are authorized to download and process. Respect platform terms and copyright.
- For larger workloads, use a paid/server instance and object storage instead of relying on local disk.
