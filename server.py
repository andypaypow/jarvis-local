#!/usr/bin/env python3
"""JARVIS Local: realtime voice assistant that drives Claude Code sessions.

One small FastAPI server:
  GET  /              the futuristic UI (orb + live task panels)
  POST /api/session   mints an ephemeral OpenAI Realtime token (your API key
                      never reaches the browser)
  POST /api/task      spawns a Claude Code session (claude -p) in background
  GET  /api/task/{id} polls a task's status and output

The browser talks to OpenAI Realtime over WebRTC for voice, and the model
calls the delegate_to_claude tool for any real work. Results are read back
aloud when the Claude session finishes.
"""
import json
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT = Path(__file__).parent
app = FastAPI(title="JARVIS Local")

# ------------------------------------------------------------------ logs
LOG_FILE = os.environ.get("JARVIS_LOG_FILE", str(ROOT / "jarvis.log"))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger("jarvis")

# ---------------------------------------------------------------- config

def load_env():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
REALTIME_MODEL = os.environ.get("REALTIME_MODEL", "gpt-realtime")
VOICE = os.environ.get("JARVIS_VOICE", "ballad")
LANGUAGE = os.environ.get("JARVIS_LANGUAGE", "français")
# Where Claude Code sessions run (their filesystem playground).
WORKDIR = os.path.expanduser(os.environ.get("JARVIS_WORKDIR", "~"))

# Headless sessions have nobody to answer permission prompts: a task that asks
# would just hang until the timeout. Run them in a non-interactive mode instead.
# bypassPermissions = no prompt at all; acceptEdits = files yes, commands still ask.
PERMISSION_MODE = os.environ.get("JARVIS_PERMISSION_MODE", "bypassPermissions")

INSTRUCTIONS = f"""Tu es JARVIS, l'assistant vocal personnel de monsieur, dans
l'esprit du majordome d'Iron Man. Tu parles en {LANGUAGE} avec un LÉGER ACCENT
BRITANNIQUE distingué et un flegme impeccable: voix posée, articulation
soignée, débit calme, jamais d'exubérance. Tu t'adresses à l'utilisateur par
"monsieur", avec une courtoisie raffinée et une pointe d'esprit pince-sans-rire
("Très bien, monsieur.", "Si monsieur veut bien patienter un instant.").
Réponses COURTES (une ou deux phrases), naturelles et directes.

Pour toute tâche réelle (lire ou créer des fichiers, chercher sur internet,
coder, analyser, automatiser), tu appelles l'outil delegate_to_claude avec un
prompt clair et complet. Tu annonces brièvement que tu lances la tâche, puis
tu continues la conversation. Quand un résultat de tâche arrive, tu le
résumes à voix haute en une ou deux phrases.

Pour ouvrir un logiciel sur ce PC ("lance Discord", "ouvre Spotify"), tu
appelles open_app avec le nom de l'application. Pour un site web ou service
en ligne ("ouvre mes emails" -> https://mail.google.com, "ouvre YouTube"),
appelle open_url avec l'URL complète. Si l'utilisateur précise un écran
("sur l'écran de gauche", "à droite", "sur l'écran 2"), passe monitor
(left/right/top/bottom/primary ou un numéro). Tu peux enchaîner plusieurs
appels pour installer un setup multi-écrans. Confirme brièvement.

Si l'utilisateur demande d'annuler ou d'arrêter une tâche en cours, appelle
cancel_task (sans task_id pour la plus récente).

Quand tu veux MONTRER quelque chose à l'écran (résultat de calcul, liste,
tableau, extrait de code, définition), appelle display_card: le contenu
s'affiche sur l'interface. Utilise-la spontanément dès qu'un visuel aide
(chiffres, comparaisons, étapes), et garde ta réponse vocale courte.

Pour une ANALYSE DE DONNÉES ou un rapport (fichier Excel/CSV analysé, stats,
comparatifs chiffrés), appelle display_report: un tableau de bord s'affiche
avec indicateurs clés (kpis), graphique (chart) et tableau (table). Quand tu
délègues une analyse à delegate_to_claude, demande-lui explicitement de
terminer sa réponse par les données chiffrées structurées (listes de valeurs,
totaux, moyennes) pour que tu puisses remplir le rapport ensuite.

PROTOCOLE DE RECHERCHE WEB (quand tu délègues une recherche à delegate_to_claude):
- Demande-lui de formuler 3-5 requêtes pertinentes, croiser les sources,
  et te rendre une synthèse de 2-3 paragraphes AVEC les URLs des sources
  et la date/fraîcheur des informations. Tu cites ensuite les sources à
  l'écran (display_card) et tu réserves la voix à la synthèse.

METEO: pour toute question météo, appelle get_weather (jamais de mémoire).

Ne réponds jamais de mémoire à une question qui demande des données réelles:
délègue. Ne lis jamais de longues listes: résume.

RÈGLES ABSOLUES contre l'improvisation:
- N'invente JAMAIS le résultat d'une tâche: tu ne sais qu'elle a été LANCÉE.
  Le résultat réel t'arrivera plus tard dans un message [SYSTEM]; d'ici là,
  si on t'interroge, dis que la tâche est en cours.
- Si tu l'as dit, tu ne peux pas le répéter: pas de résultat imaginé, pas de
  statistiques, pas de contenu de fichier, pas de citation que tu n'as pas
  reçue d'un outil ou de l'utilisateur.
- En cas de doute, dis "Je vérifie, monsieur" et délègue avec
  delegate_to_claude plutôt que de deviner.
- Pour une question d'opinion ou de conversation générale, réponds
  normalement (pas besoin de déléguer)."""

WEATHER_CODES = {0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux",
                 3: "couvert", 45: "brouillard", 48: "brouillard givrant",
                 51: "bruine légère", 53: "bruine", 55: "bruine dense",
                 61: "pluie faible", 63: "pluie", 65: "pluie forte",
                 71: "neige faible", 73: "neige", 75: "neige forte",
                 80: "averses", 81: "averses fortes", 82: "averses violentes",
                 95: "orage", 96: "orage avec grêle", 99: "orage violent avec grêle"}


def get_weather(city: str, days: int = 2) -> dict:
    """Meteo reelle via Open-Meteo (gratuit, sans cle)."""
    g = httpx.get("https://geocoding-api.open-meteo.com/v1/search",
                  params={"name": city, "count": 1, "language": "fr"}, timeout=15).json()
    if not g.get("results"):
        return {"error": f"ville '{city}' introuvable"}
    r = g["results"][0]
    f = httpx.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": r["latitude"], "longitude": r["longitude"],
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code",
        "timezone": "auto", "forecast_days": min(days, 5)}, timeout=15).json()
    cur = f["current"]
    daily = f["daily"]
    return {
        "ville": f"{r['name']}, {r.get('country', '')}",
        "actuel": {"temperature": f"{cur['temperature_2m']}°C",
                   "ressenti": f"{cur['apparent_temperature']}°C",
                   "conditions": WEATHER_CODES.get(cur["weather_code"], "?"),
                   "vent_kmh": cur["wind_speed_10m"]},
        "previsions": [{"jour": d, "min": f"{mn}°C", "max": f"{mx}°C",
                        "conditions": WEATHER_CODES.get(c, "?")}
                       for d, mn, mx, c in zip(daily["time"], daily["temperature_2m_min"],
                                               daily["temperature_2m_max"], daily["weather_code"])],
    }


TOOLS = [{
    "type": "function",
    "name": "delegate_to_claude",
    "description": ("Delegate a real task to a Claude Code session running on "
                    "this machine (files, code, web research, automation). "
                    "Returns immediately; the result arrives later as a "
                    "system message."),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Very short task label (3-5 words)"},
            "prompt": {"type": "string", "description": "Complete, self-contained task instruction for Claude Code"},
        },
        "required": ["title", "prompt"],
    },
}, {
    "type": "function",
    "name": "open_app",
    "description": ("Launch an application installed on this PC by name "
                    "(e.g. 'discord', 'spotify', 'chrome', 'notepad'). "
                    "Returns whether it was found and started."),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Application name as the user said it"},
            "monitor": {"type": "string",
                        "description": ("Target screen: 'left', 'right', 'top', "
                                        "'bottom', 'primary', or a number like '2'. "
                                        "Omit to leave window placement alone.")},
        },
        "required": ["name"],
    },
}, {
    "type": "function",
    "name": "open_url",
    "description": ("Open a website in the browser on this PC. Use for online "
                    "services: 'mes emails' -> https://mail.google.com, "
                    "'YouTube' -> https://youtube.com, etc."),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full URL to open (https://...)"},
            "monitor": {"type": "string",
                        "description": "Target screen: 'left', 'right', 'top', 'bottom', 'primary' or a number. Optional."},
        },
        "required": ["url"],
    },
}, {
    "type": "function",
    "name": "get_weather",
    "description": ("Real-time weather for any city (current + forecast). Use for "
                    "'quel temps', 'météo à ...'. Always answer from this tool, never from memory."),
    "parameters": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name, e.g. 'Libreville'"},
            "days": {"type": "number", "description": "Forecast days 1-5 (optional, default 2)"},
        },
        "required": ["city"],
    },
}, {
    "type": "function",
    "name": "cancel_task",
    "description": ("Cancel a running Claude Code task. Omit task_id to cancel "
                    "the most recently started running task."),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "Task id to cancel (optional)"},
        },
    },
}, {
    "type": "function",
    "name": "display_card",
    "description": ("Show a visual card on the JARVIS screen: results, "
                    "numbers, lists, code, comparisons. Use markdown-lite: "
                    "**bold**, `code`, lines starting with '- ' for bullets. "
                    "Use whenever a visual helps; keep the spoken reply short."),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short card title"},
            "content": {"type": "string", "description": "Card body (markdown-lite)"},
            "kind": {"type": "string", "enum": ["info", "result", "code", "warning"],
                      "description": "Visual style of the card"},
        },
        "required": ["title", "content"],
    },
}, {
    "type": "function",
    "name": "display_report",
    "description": ("Show a full data report dashboard on screen: KPI tiles, "
                    "an interactive chart, a sortable table, and markdown notes. "
                    "Use for data analysis results (spreadsheets, stats, "
                    "comparisons). All sections are optional except title."),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Report title"},
            "kpis": {"type": "array", "description": "Headline numbers (max 4)",
                     "items": {"type": "object", "properties": {
                         "label": {"type": "string"},
                         "value": {"type": "string", "description": "e.g. '12 480 €'"},
                         "delta": {"type": "string", "description": "e.g. '+12%' (optional)"},
                     }, "required": ["label", "value"]}},
            "chart": {"type": "object", "description": "One chart", "properties": {
                "type": {"type": "string", "enum": ["line", "bar", "area", "donut"]},
                "categories": {"type": "array", "items": {"type": "string"},
                               "description": "X axis labels (or slice labels for donut)"},
                "series": {"type": "array", "description": "1-3 series",
                           "items": {"type": "object", "properties": {
                               "name": {"type": "string"},
                               "data": {"type": "array", "items": {"type": "number"}},
                           }, "required": ["name", "data"]}},
            }},
            "table": {"type": "object", "properties": {
                "columns": {"type": "array", "items": {"type": "string"}},
                "rows": {"type": "array", "items": {"type": "array",
                         "items": {"type": ["string", "number"]}}},
            }},
            "markdown": {"type": "string", "description": "Notes / conclusions in markdown"},
        },
        "required": ["title"],
    },
}]

# ---------------------------------------------------------------- tasks

TASKS: dict = {}
PROCS: dict = {}  # task_id -> Popen, kept out of TASKS so get_task stays JSON-safe


def _kill_tree(pid: int):
    """Kill a process and its children (claude spawns node)."""
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        try:
            os.killpg(os.getpgid(pid), 15)
        except OSError:
            try:
                os.kill(pid, 15)
            except OSError:
                pass


def _run_task(task_id: str, prompt: str):
    task = TASKS[task_id]
    try:
        # Tacheur: DeepSeek Harness en mode headless (replie: claude -p).
        agent = shutil.which("dsh")
        if agent:
            cmd = [agent, "--profile", "headless", prompt]
        else:
            claude = shutil.which("claude")
            if not claude:
                raise FileNotFoundError("dsh/claude")
            cmd = [claude, "-p", prompt]
            if PERMISSION_MODE and PERMISSION_MODE.lower() != "off":
                cmd += ["--permission-mode", PERMISSION_MODE]
        _CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
        env = dict(os.environ)
        if not IS_WINDOWS and os.geteuid() == 0:
            env["IS_SANDBOX"] = "1"  # allow bypassPermissions as root (local VPS)
        proc = subprocess.Popen(
            cmd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", cwd=WORKDIR,
            creationflags=_CREATE_NO_WINDOW, start_new_session=not IS_WINDOWS,
        )
        PROCS[task_id] = proc
        try:
            stdout, stderr = proc.communicate(
                timeout=int(os.environ.get("JARVIS_TASK_TIMEOUT", "600")))
        except subprocess.TimeoutExpired:
            _kill_tree(proc.pid)
            proc.communicate()
            task["status"] = "error"
            task["output"] = "Timeout: la session Claude a dépassé la limite de temps."
        else:
            if task["status"] == "cancelled":
                pass  # set by the cancel endpoint; don't overwrite
            else:
                out = (stdout or "").strip()
                err = (stderr or "").strip()
                task["status"] = "done" if proc.returncode == 0 else "error"
                task["output"] = out if out else err[:2000]
    except FileNotFoundError:
        task["status"] = "error"
        task["output"] = ("Ni 'dsh' ni 'claude' trouves. Installe DeepSeek Harness "
                          "ou Claude Code.")
    except Exception as exc:  # noqa: BLE001
        task["status"] = "error"
        task["output"] = str(exc)
    finally:
        PROCS.pop(task_id, None)
    task["ended"] = time.time()


class TaskIn(BaseModel):
    title: str
    prompt: str


@app.post("/api/task")
def create_task(body: TaskIn):
    task_id = uuid.uuid4().hex[:8]
    TASKS[task_id] = {
        "id": task_id, "title": body.title, "prompt": body.prompt,
        "status": "running", "output": "", "started": time.time(), "ended": None,
    }
    threading.Thread(target=_run_task, args=(task_id, body.prompt), daemon=True).start()
    return {"id": task_id, "status": "running"}


@app.post("/api/task/{task_id}/cancel")
def cancel_task(task_id: str):
    if task_id in ("latest", "last", "-"):
        running = [t for t in TASKS.values() if t["status"] == "running"]
        if not running:
            return {"ok": False, "error": "Aucune tâche en cours."}
        task = max(running, key=lambda t: t["started"])
    else:
        task = TASKS.get(task_id)
        if not task:
            raise HTTPException(404, "unknown task")
        if task["status"] != "running":
            return {"ok": False, "error": f"La tâche est déjà {task['status']}."}
    # Flag first so _run_task's communicate() return doesn't overwrite it.
    task["status"] = "cancelled"
    task["output"] = "Annulée par l'utilisateur."
    proc = PROCS.get(task["id"])
    if proc and proc.poll() is None:
        _kill_tree(proc.pid)
    return {"ok": True, "cancelled": task["id"], "title": task["title"]}


@app.get("/api/task/{task_id}")
def get_task(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "unknown task")
    return task


# ---------------------------------------------------------------- monitors & window placement (Windows API)

IS_WINDOWS = os.name == "nt"
if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

if IS_WINDOWS:
    user32 = ctypes.windll.user32
    try:  # accurate multi-monitor coordinates under display scaling
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        pass

    _MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    _EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)


def _monitors():
    """List monitor work rects as (left, top, right, bottom)."""
    mons = []
    if not IS_WINDOWS:
        return mons

    def cb(hmon, hdc, lprc, lparam):
        r = lprc.contents
        mons.append((r.left, r.top, r.right, r.bottom))
        return 1

    user32.EnumDisplayMonitors(0, 0, _MonitorEnumProc(cb), 0)
    return mons


def _pick_monitor(target: str):
    mons = _monitors()
    if not mons:
        return None
    t = (target or "").strip().lower()
    if t.isdigit():
        i = int(t) - 1
        return mons[i] if 0 <= i < len(mons) else None
    key = {
        "left": lambda m: m[0], "gauche": lambda m: m[0],
        "top": lambda m: m[1], "haut": lambda m: m[1],
    }
    if t in key:
        return min(mons, key=key[t])
    key = {
        "right": lambda m: m[2], "droite": lambda m: m[2], "droit": lambda m: m[2],
        "bottom": lambda m: m[3], "bas": lambda m: m[3],
    }
    if t in key:
        return max(mons, key=key[t])
    # primary: the monitor containing the origin (0,0)
    for m in mons:
        if m[0] <= 0 < m[2] and m[1] <= 0 < m[3]:
            return m
    return mons[0]


def _visible_windows():
    """Map of visible top-level windows: hwnd -> title (Windows only)."""
    wins = {}
    if not IS_WINDOWS:
        return wins

    def cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                wins[hwnd] = buf.value
        return 1

    user32.EnumWindows(_EnumWindowsProc(cb), 0)
    return wins


def _move_to_monitor(hwnd, mon):
    left, top, right, bottom = mon
    SW_RESTORE, SW_MAXIMIZE = 9, 3
    user32.ShowWindow(hwnd, SW_RESTORE)  # a maximized window can't be moved
    user32.MoveWindow(hwnd, left + 40, top + 40,
                      max(400, (right - left) - 80), max(300, (bottom - top) - 80), True)
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    user32.SetForegroundWindow(hwnd)


def _place_app_window(app_name: str, before: dict, mon, timeout: float = 20.0):
    """Wait for the app's window to appear, then move it to the target monitor.

    Prefers a NEW window whose title mentions the app; falls back to any new
    window, then to an existing title match (single-instance apps like Discord
    just refocus their already-open window).
    """
    q = app_name.lower()
    deadline = time.time() + timeout
    fallback = None
    while time.time() < deadline:
        wins = _visible_windows()
        new = {h: t for h, t in wins.items() if h not in before}
        for h, title in new.items():
            if q in title.lower():
                _move_to_monitor(h, mon)
                return title
        if new and fallback is None:
            fallback = max(new)  # remember, but keep hoping for a title match
        time.sleep(0.5)
        if fallback and time.time() > deadline - timeout / 2:
            break
    if fallback:
        wins = _visible_windows()
        _move_to_monitor(fallback, mon)
        return wins.get(fallback, app_name)
    # No new window: single-instance app already running -> match existing title.
    for h, title in _visible_windows().items():
        if q in title.lower():
            _move_to_monitor(h, mon)
            return title
    return None


# ---------------------------------------------------------------- open app

START_MENU_DIRS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
] if IS_WINDOWS else []


def _find_shortcut(name: str):
    """Fuzzy-match a Start Menu shortcut (where installed apps register)."""
    q = name.lower().strip()
    best, best_score = None, 0.0
    for root in START_MENU_DIRS:
        if not root.is_dir():
            continue
        for lnk in root.rglob("*.lnk"):
            stem = lnk.stem.lower()
            if q == stem:
                return lnk
            score = 0.0
            if q in stem:
                score = 2 + len(q) / len(stem)   # substring: prefer tightest match
            elif all(w in stem for w in q.split()):
                score = 1
            # Penalise uninstallers and docs.
            if any(bad in stem for bad in ("uninstall", "désinstaller", "readme", "website")):
                score -= 2
            if score > best_score:
                best, best_score = lnk, score
    return best


class OpenIn(BaseModel):
    name: str = ""
    url: str | None = None
    monitor: str | None = None


def _placed(name: str, monitor: str | None, before: dict, launched: str):
    """Optionally move the freshly launched app to the requested screen."""
    if not monitor:
        return {"ok": True, "launched": launched}
    mon = _pick_monitor(monitor)
    if not mon:
        return {"ok": True, "launched": launched,
                "warning": f"écran '{monitor}' introuvable, fenêtre laissée en place"}
    title = _place_app_window(name, before, mon)
    if title:
        return {"ok": True, "launched": launched, "monitor": monitor, "window": title}
    return {"ok": True, "launched": launched,
            "warning": "fenêtre non détectée, placement impossible"}


@app.post("/api/open")
def open_app(body: OpenIn):
    name = body.name.strip()
    if body.url:
        url = body.url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        before = _visible_windows() if body.monitor else {}
        import webbrowser
        if not webbrowser.open(url):
            return {"ok": False, "error": "Impossible d'ouvrir le navigateur."}
        # Match the browser window by the site's domain.
        domain = url.split("//", 1)[1].split("/", 1)[0].removeprefix("www.")
        return _placed(domain.split(".")[0], body.monitor, before, url)
    if not name:
        raise HTTPException(400, "missing app name or url")
    before = _visible_windows() if body.monitor else {}
    lnk = _find_shortcut(name)
    if lnk:
        os.startfile(lnk)  # noqa: S606 - deliberate: local launcher
        return _placed(name, body.monitor, before, lnk.stem)
    # Fallback: resolve via PATH (Linux/macOS too), then App Paths registry (Windows).
    exe = shutil.which(name) or shutil.which(name + ".exe")
    if not exe and IS_WINDOWS:
        try:
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    key = winreg.OpenKey(hive, rf"Software\Microsoft\Windows"
                                               rf"\CurrentVersion\App Paths\{name}.exe")
                    exe = winreg.QueryValueEx(key, None)[0].strip('"')
                    break
                except OSError:
                    continue
        except ImportError:
            pass
    if not exe:
        return {"ok": False, "error": f"Application '{name}' introuvable sur ce PC."}
    try:
        subprocess.Popen([exe], cwd=str(Path(exe).parent))
        res = _placed(name, body.monitor, before, Path(exe).stem)
        res.setdefault("via", "exe")
        return res
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------- realtime session

@app.post("/api/session")
def create_session():
    if not OPENAI_API_KEY:
        raise HTTPException(500, "OPENAI_API_KEY manquant: copie .env.example vers .env et mets ta clé.")
    payload = {
        "session": {
            "type": "realtime",
            "model": REALTIME_MODEL,
            "instructions": INSTRUCTIONS,
            "tools": TOOLS,  # format plat requis par le Realtime
            "audio": {
                "input": {"transcription": {"model": "whisper-1"}},
                "output": {"voice": VOICE},
            },
        }
    }
    r = httpx.post(
        "https://api.openai.com/v1/realtime/client_secrets",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                 "Content-Type": "application/json"},
        json=payload, timeout=30,
    )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, f"OpenAI: {r.text[:300]}")
    data = r.json()
    return {"client_secret": data["value"], "model": REALTIME_MODEL}


# ---------------------------------------------------------------- free local brain (z.ai GLM + Ollama fallback)

OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:8060")
OLLAMA_MODEL = os.environ.get("JARVIS_OLLAMA_MODEL", "qwen3.5:9b")
ZAI_BASE = os.environ.get("JARVIS_ZAI_BASE", "https://api.z.ai/api/coding/paas/v4")
ZAI_MODEL = os.environ.get("JARVIS_ZAI_MODEL", "glm-5.3-flash")
ZAI_KEY = os.environ.get("ZAI_API_KEY", "")
# TOOLS est au format "plat" du Realtime OpenAI ; les API chat classique
# (z.ai, Ollama) exigent le format imbrique {"type":"function","function":{...}}.
OAI_TOOLS = [{"type": "function", "function": t} for t in TOOLS]


class ChatIn(BaseModel):
    text: str
    history: list[dict] = []


def _brain_call(messages: list) -> dict:
    """One LLM round-trip -> {'content': str, 'calls': [{'name', 'args'}]}.

    Primary: z.ai GLM (OpenAI-compatible). Fallback: local Ollama.
    """
    if ZAI_KEY:
        try:
            r = httpx.post(f"{ZAI_BASE}/chat/completions", headers={
                "Authorization": f"Bearer {ZAI_KEY}"}, json={
                "model": ZAI_MODEL, "messages": messages, "tools": OAI_TOOLS,
                "temperature": 0.3,
            }, timeout=180)
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            calls = [{"name": c["function"]["name"],
                      "args": _jsonish(c["function"].get("arguments"))}
                     for c in (msg.get("tool_calls") or [])]
            return {"content": msg.get("content") or "", "calls": calls}
        except (httpx.HTTPError, KeyError, ValueError):
            pass  # fall through to Ollama
    r = httpx.post(f"{OLLAMA_URL}/api/chat", json={
        "model": OLLAMA_MODEL, "messages": messages, "tools": OAI_TOOLS,
        "stream": False, "options": {"temperature": 0.3},
    }, timeout=180)
    r.raise_for_status()
    msg = r.json().get("message", {})
    calls = [{"name": c["function"]["name"], "args": _jsonish(c["function"].get("arguments"))}
             for c in (msg.get("tool_calls") or [])]
    return {"content": msg.get("content") or "", "calls": calls}


def _jsonish(a):
    if isinstance(a, str):
        try:
            return json.loads(a)
        except ValueError:
            return {}
    return a or {}


CHATS: dict = {}  # chat_id -> etat (async: le navigateur sonde, Cloudflare ne coupe pas)


def _chat_pipeline(text: str, history: list) -> dict:
    """Free voice mode: browser does STT/TTS, GLM decides, tools run here."""
    messages = [{"role": "system", "content": INSTRUCTIONS}, *history[-12:],
                {"role": "user", "content": text}]
    cards, reports = [], []
    open_urls = []  # URL a ouvrir dans le NAVIGATEUR de l'utilisateur (pas sur le VPS)
    for _ in range(5):  # tool loop
        msg = _brain_call(messages)
        messages.append({"role": "assistant", "content": msg["content"]})
        if not msg["calls"]:
            return {"reply": msg["content"].strip(),
                    "cards": cards, "reports": reports, "open_urls": open_urls}
        for call in msg["calls"]:
            result = _run_tool(call["name"], call["args"], cards, reports, open_urls)
            messages.append({"role": "tool", "name": call["name"],
                             "content": json.dumps(result, ensure_ascii=False)})
    return {"reply": "J'ai enchaine trop d'actions d'affilee, monsieur.",
            "cards": cards, "reports": reports, "open_urls": open_urls}


@app.post("/api/chat")
def chat(body: ChatIn):
    """Lance la reflexion en tache de fond; le navigateur sonde /api/chat/{id}."""
    if not body.text.strip():
        raise HTTPException(400, "empty text")
    chat_id = uuid.uuid4().hex[:8]
    CHATS[chat_id] = {"id": chat_id, "status": "thinking", "started": time.time()}
    log.info("chat %s <- %r", chat_id, body.text[:80])

    def _run():
        try:
            CHATS[chat_id].update(_chat_pipeline(body.text, body.history),
                                  status="done")
        except httpx.HTTPError as exc:
            CHATS[chat_id].update(status="error",
                                  reply=f"Cerveau injoignable (z.ai puis Ollama): {exc}")
        except Exception as exc:  # noqa: BLE001
            CHATS[chat_id].update(status="error", reply=str(exc))
        log.info("chat %s -> %s (%.1fs)", chat_id, CHATS[chat_id]["status"],
                 time.time() - CHATS[chat_id]["started"])

    threading.Thread(target=_run, daemon=True).start()
    return {"id": chat_id, "status": "thinking"}


@app.get("/api/chat/{chat_id}")
def get_chat(chat_id: str):
    st = CHATS.get(chat_id)
    if not st:
        raise HTTPException(404, "unknown chat")
    return {k: v for k, v in st.items() if k != "started"}


def _run_tool(name: str, args: dict, cards: list, reports: list, open_urls: list) -> dict:
    """Execute a tool locally and return its JSON result for the model."""
    if name == "delegate_to_claude":
        return create_task(TaskIn(title=args.get("title", "Tâche"),
                                  prompt=args.get("prompt", "")))
    if name == "open_url":
        url = (args.get("url") or "").strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        open_urls.append(url)
        return {"ok": True, "opened_in_user_browser": url}
    if name == "open_app":
        # JARVIS tourne sur un serveur distant sans ecran : les applications
        # natives ne sont pas lançables d'ici. Message clair pour le cerveau.
        return {"ok": False,
                "error": (f"Impossible de lancer '{args.get('name', '')}' : JARVIS "
                          "tourne sur un serveur distant sans ecran. Excuse-toi "
                          "brievement et invite monsieur a ouvrir l'application "
                          "lui-meme, ou propose un site web (open_url).")}
    if name == "cancel_task":
        return cancel_task(args.get("task_id") or "latest")
    if name == "get_weather":
        try:
            return get_weather(args.get("city", ""), int(args.get("days") or 2))
        except Exception as exc:  # noqa: BLE001
            return {"error": f"meteo indisponible: {exc}"}
    if name == "display_card":
        card = {"title": args.get("title", "Info"),
                "content": args.get("content", ""), "kind": args.get("kind", "info")}
        cards.append(card)
        return {"status": "displayed"}
    if name == "display_report":
        reports.append(args)
        return {"status": "displayed"}
    return {"error": f"outil inconnu: {name}"}


# ---------------------------------------------------------------- logs navigateur

class LogIn(BaseModel):
    level: str = "error"
    message: str = ""
    extra: dict = {}


@app.post("/api/log")
def client_log(body: LogIn):
    (log.error if body.level == "error" else log.info)(
        "[NAVIGATEUR] %s %s", body.message,
        json.dumps(body.extra, ensure_ascii=False)[:500])
    return {"ok": True}


# ---------------------------------------------------------------- static

@app.get("/")
def index():
    return FileResponse(ROOT / "index.html",
                        headers={"Cache-Control": "no-store"})  # toujours la derniere version


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("JARVIS_PORT", "8788"))
    print(f"\n  JARVIS Local -> http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
