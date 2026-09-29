from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import yt_dlp, os, uuid, subprocess, re, sys
from werkzeug.utils import secure_filename

APP_DIR=os.path.dirname(os.path.abspath(__file__))
ROOT_DIR=os.path.dirname(APP_DIR)
OUT_DIR=os.path.join(APP_DIR,"downloads")
FRONTEND_DIR=os.path.join(ROOT_DIR,"frontend")
os.makedirs(OUT_DIR,exist_ok=True)
app=Flask(__name__); CORS(app)

def log(msg):
    print(msg, flush=True)

def safe_mp3_name(title, used_names=None, playback=None):
    name=os.path.splitext(os.path.basename(str(title or "Audio")))[0]
    name=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    name=re.sub(r'\s+', ' ', name).strip().rstrip('.')
    if not name: name="Audio"
    if name.upper() in {"CON","PRN","AUX","NUL"} or re.match(r'^(COM|LPT)[0-9]$', name.upper()):
        name="_"+name
    prefix=f"[{playback}] " if playback else ""
    name=(prefix+name)[:180].rstrip()
    used_names=used_names if used_names is not None else set()
    candidate=name+".mp3"; i=2
    while candidate.lower() in {x.lower() for x in used_names} or os.path.exists(os.path.join(OUT_DIR,candidate)):
        candidate=f"{name} ({i}).mp3"; i+=1
    used_names.add(candidate)
    return candidate

def process_to_mp3(source, output, speed=1.0, gain=0.0, quality="320"):
    base_rate=44100
    shifted_rate=max(1000,int(round(base_rate*speed)))
    filters=f"aresample={base_rate},asetrate={shifted_rate},aresample={base_rate},volume={gain:.2f}dB"
    cmd=["ffmpeg","-y","-i",source,"-vn","-af",filters,"-c:a","libmp3lame","-b:a",quality+"k","-ar",str(base_rate),"-ac","2",output]
    log("CMD: "+" ".join(cmd))
    try: proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    except FileNotFoundError: raise RuntimeError("FFmpeg tidak ditemukan.")
    _,err=proc.communicate()
    if proc.returncode!=0:
        lines=[x.strip() for x in (err or "").splitlines() if x.strip()]
        useful=[x for x in lines if "Error" in x or "error" in x or "Invalid" in x or "failed" in x or "No such" in x]
        raise RuntimeError((useful[-1] if useful else (lines[-1] if lines else "FFmpeg gagal."))[:500])

def download_source(url, template, label):
    log(f"[DOWNLOAD] {label} -> {url}")
    last=[None]
    def hook(d):
        status=d.get("status")
        if status=="downloading":
            p=d.get("_percent_str") or d.get("percent") or "?"
            sp=d.get("_speed_str") or ""
            eta=d.get("_eta_str") or ""
            line=f"[{label}] ======= {p} {sp} ETA {eta}"
            if line!=last[0]: log(line); last[0]=line
        elif status=="finished":
            log(f"[{label}] ======= 100% | sumber selesai")
    opts={
        "format":"bestaudio/best","outtmpl":template,"noplaylist":True,
        "quiet":True,"no_warnings":True,"progress_hooks":[hook],
        "retries":3
    }
    with yt_dlp.YoutubeDL(opts) as y:
        info=y.extract_info(url,download=True)
        return info.get("title","Audio")

@app.get("/")
def home(): return send_from_directory(FRONTEND_DIR,"index.html")

@app.get("/health")
def health(): return jsonify({"status":"ok","service":"MUNKS Audio Processor"})

@app.post("/convert")
def convert():
    urls=[u.strip() for u in request.form.getlist("urls") if u.strip()][:10]
    uploads=request.files.getlist("files")
    if len(urls)+len(uploads)>10: return jsonify({"error":"Maksimal 10 item total."}),400
    mode=request.form.get("mode","speed")
    quality=request.form.get("quality","320")
    if quality not in {"128","192","256","320"}: quality="320"
    try: speed=float(request.form.get("speed","2.30"))
    except: speed=2.30
    try: gain=float(request.form.get("gain","-8"))
    except: gain=-8
    speed=max(.5,min(3,speed)); gain=max(-14,min(12,gain))
    playback=float(request.form.get("playback",f"{1/speed:.2f}")) if mode=="speed" else 1.0
    playback=f"{playback:.2f}"
    items=[]; used_names=set()

    # AUDIO SPEED: uploaded MP3 files
    for f in uploads:
        if not f or not f.filename: continue
        original=secure_filename(f.filename)
        if not original.lower().endswith(".mp3"):
            items.append({"title":original or "File","type":"Upload MP3","quality":quality,"speed":f"{speed:.2f}","gain":f"{gain:.2f}","playback":playback,"status":"Gagal: hanya file MP3 yang diterima."}); continue
        uid=uuid.uuid4().hex; source=os.path.join(OUT_DIR,uid+".upload.mp3")
        output_name=safe_mp3_name(original,used_names,playback if mode=="speed" else None); output=os.path.join(OUT_DIR,output_name)
        try:
            log(f"[PROCESS] {original}")
            f.save(source); process_to_mp3(source,output,speed if mode=="speed" else 1,gain if mode=="speed" else 0,quality)
            os.remove(source)
            log(f"[DONE] {output_name}")
            items.append({"title":original,"type":"Upload MP3","quality":quality,"speed":f"{speed:.2f}","gain":f"{gain:.2f}","playback":playback,"status":"Selesai.","download":"/download/"+output_name})
        except Exception as e:
            try: os.remove(source)
            except OSError: pass
            log(f"[ERROR] {original}: {e}")
            items.append({"title":original,"type":"Upload MP3","quality":quality,"speed":f"{speed:.2f}","gain":f"{gain:.2f}","playback":playback,"status":"Gagal: "+str(e)[:220]})

    # Both tabs use yt-dlp, supporting YouTube / YouTube Music / SoundCloud.
    for idx,url in enumerate(urls,1):
        uid=uuid.uuid4().hex; template=os.path.join(OUT_DIR,uid+".source.%(ext)s")
        source=None
        try:
            title=download_source(url,template,f"LINK {idx}")
            matches=[x for x in os.listdir(OUT_DIR) if x.startswith(uid+".source.")]
            if not matches: raise RuntimeError("File sumber tidak ditemukan.")
            source=os.path.join(OUT_DIR,matches[0])
            out_playback=playback if mode=="speed" else None
            output_name=safe_mp3_name(title,used_names,out_playback); output=os.path.join(OUT_DIR,output_name)
            log(f"[PROCESS] {title}")
            process_to_mp3(source,output,speed if mode=="speed" else 1,gain if mode=="speed" else 0,quality)
            try: os.remove(source)
            except OSError: pass
            log(f"[DONE] {output_name}")
            items.append({"title":title,"type":"Audio Speed" if mode=="speed" else "Link Downloader","quality":quality,"speed":f"{speed:.2f}" if mode=="speed" else "1.00","gain":f"{gain:.2f}" if mode=="speed" else "0.00","playback":playback,"status":"Selesai.","download":"/download/"+output_name})
        except Exception as e:
            if source and os.path.exists(source):
                try: os.remove(source)
                except OSError: pass
            log(f"[ERROR] {url}: {e}")
            items.append({"title":url,"type":"Audio Speed" if mode=="speed" else "Link Downloader","quality":quality,"speed":f"{speed:.2f}" if mode=="speed" else "1.00","gain":f"{gain:.2f}" if mode=="speed" else "0.00","playback":playback,"status":"Gagal: "+str(e)[:300]})

    return jsonify({"items":items})

@app.get("/download/<name>")
def download(name): return send_from_directory(OUT_DIR,name,as_attachment=True)

if __name__=="__main__":
    log("MUNKS Audio Processor: http://127.0.0.1:8765")
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT","8765")))
