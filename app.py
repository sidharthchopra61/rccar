import os
import time
import json
import threading
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8080"))

HARDWARE_URL = os.getenv("RC_HARDWARE_URL", "").rstrip("/")
CAMERA_URL = os.getenv("RC_CAMERA_URL", "")

COMMAND_TIMEOUT = 1.0
VALID_COMMANDS = {
    "forward", "backward", "left", "right", "stop",
    "forward_left", "forward_right", "backward_left", "backward_right"
}

current_command = "stop"
last_command_time = time.time()
powered_on = False
state_lock = threading.Lock()


# ---------------- HARDWARE ----------------

def send_hardware_command(command, speed=60):
    """Send a command to a compatible hardware bridge."""
    if not HARDWARE_URL:
        return True, "Demo mode"

    payload = json.dumps({
        "command": command,
        "speed": max(0, min(100, int(speed))),
        "powered_on": powered_on,
    }).encode("utf-8")

    req = Request(
        HARDWARE_URL + "/command",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=1.2) as response:
            return response.status < 400, "OK"
    except (URLError, HTTPError, TimeoutError) as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)


def force_stop():
    global current_command, last_command_time

    with state_lock:
        current_command = "stop"
        last_command_time = time.time()

    send_hardware_command("stop")


def watchdog():
    """Stop the current command when the browser stops sending heartbeats."""
    global current_command

    while True:
        time.sleep(0.15)
        should_stop = False

        with state_lock:
            if (
                current_command != "stop"
                and time.time() - last_command_time > COMMAND_TIMEOUT
            ):
                current_command = "stop"
                should_stop = True

        if should_stop:
            send_hardware_command("stop")


threading.Thread(target=watchdog, daemon=True).start()


# ---------------- HTML / UI PAGE ----------------

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
<meta name="theme-color" content="#070a12">
<title>RC Pilot Cockpit</title>

<style>
:root {
    --bg: #070a12;
    --panel: #0f1523;
    --panel2: #162035;
    --border: #23314a;
    --text: #f4f7ff;
    --muted: #8899b3;
    --blue: #0091ff;
    --cyan: #00e5ff;
    --red: #ff334b;
    --green: #00e676;
}

* {
    box-sizing: border-box;
    -webkit-tap-highlight-color: transparent;
}

html, body {
    margin: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    user-select: none;
    -webkit-user-select: none;
}

body {
    overscroll-behavior: none;
}

button, input {
    font: inherit;
}

button {
    touch-action: none;
    cursor: pointer;
}

/* =========================================
   BLANK ROTATE SCREEN (ACTIVE IN PORTRAIT)
   ========================================= */
#orientationGuard {
    position: fixed;
    inset: 0;
    width: 100vw;
    height: 100dvh;
    background: #05070c;
    z-index: 999999;
    display: none;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    padding: 24px;
    text-align: center;
}

#orientationGuard svg {
    width: 64px;
    height: 64px;
    fill: var(--blue);
    margin-bottom: 18px;
    animation: rotatePhone 2.2s ease-in-out infinite;
}

#orientationGuard h2 {
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 0.5px;
    margin: 0 0 8px 0;
    color: var(--text);
}

#orientationGuard p {
    font-size: 12px;
    color: var(--muted);
    margin: 0;
    max-width: 260px;
}

@keyframes rotatePhone {
    0%, 15% { transform: rotate(0deg); }
    50%, 65% { transform: rotate(90deg); }
    100% { transform: rotate(0deg); }
}


.app {
    width: 100vw;
    height: 100dvh;
    display: flex;
    flex-direction: column;
    padding: 6px 10px;
    gap: 6px;
}

/* TOP HEADER */
.header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 28px;
    flex-shrink: 0;
}

.brand {
    display: flex;
    align-items: center;
    gap: 7px;
}

.logo {
    width: 24px;
    height: 24px;
    border-radius: 6px;
    background: linear-gradient(135deg, var(--blue), var(--cyan));
    color: #040810;
    font-weight: 900;
    font-size: 14px;
    display: grid;
    place-items: center;
}

.brand-name {
    font-size: 13px;
    font-weight: 800;
    letter-spacing: .5px;
}

.hud-actions {
    display: flex;
    align-items: center;
    gap: 6px;
}

.status {
    display: flex;
    align-items: center;
    gap: 6px;
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 3px 8px;
    color: var(--muted);
    font-size: 9px;
    font-weight: 700;
}

.dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--green);
}

.small-btn {
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    background: var(--panel2);
    padding: 3px 8px;
    font-size: 10px;
    font-weight: 700;
}

/* CAMERA VIEW (LARGER ALLOCATION) */
.camera-container {
    position: relative;
    flex: 1 1 58%;
    min-height: 0;
    border: 1.5px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    background: #000;
    display: flex;
    align-items: center;
    justify-content: center;
}

.camera-container img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    background: #000;
}

.camera-placeholder {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 6px;
    text-align: center;
    padding: 10px;
    color: var(--muted);
    font-size: 11px;
}

.camera-placeholder strong {
    color: var(--text);
    font-size: 13px;
}

.camera-badge {
    position: absolute;
    top: 6px;
    left: 8px;
    padding: 3px 6px;
    border-radius: 4px;
    background: rgba(0, 0, 0, 0.65);
    font-size: 9px;
    font-weight: 700;
    letter-spacing: .8px;
    color: var(--text);
    z-index: 2;
}

/* COMPACT CONTROLS DECK */
.deck {
    flex: 0 0 38%;
    min-height: 0;
    display: grid;
    grid-template-columns: 1fr 140px 1fr;
    gap: 12px;
    align-items: stretch;
}

/* LEFT: FORWARD & BACKWARD */
.throttle-col {
    display: flex;
    flex-direction: column;
    gap: 6px;
    height: 100%;
}

/* RIGHT: LEFT & RIGHT */
.steering-row {
    display: flex;
    gap: 6px;
    height: 100%;
}

/* CENTER: POWER, STOP, READOUT */
.center-col {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 5px;
    height: 100%;
}

.ctrl-btn {
    flex: 1;
    min-height: 0;
    width: 100%;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 2px;
    padding: 2px;
    color: var(--text);
    border: 1.5px solid var(--border);
    border-radius: 10px;
    background: linear-gradient(145deg, #182236, #0e1422);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
    touch-action: none;
    transition: all 0.06s ease;
}

.ctrl-btn.active {
    background: linear-gradient(145deg, #0080ff, #0050aa);
    border-color: #6bb5ff;
    box-shadow: 0 0 14px rgba(0, 145, 255, 0.5);
    transform: scale(0.97);
}

.arrow {
    font-size: clamp(20px, 4.5vh, 28px);
    line-height: 1;
    font-weight: 900;
}

.btn-lbl {
    font-size: 9px;
    font-weight: 800;
    letter-spacing: .5px;
}

.stop-btn {
    background: linear-gradient(145deg, #c41c32, #7a0c1c);
    border-color: #ff4d64;
    color: #fff;
    font-weight: 900;
    letter-spacing: 1px;
}

.stop-btn:active {
    transform: scale(0.96);
}

.power-btn {
    background: linear-gradient(145deg, #10664e, #0a4233);
    border-color: #1ed49d;
    font-size: 10px;
    font-weight: 800;
}

.power-btn.off {
    background: linear-gradient(145deg, #3d2a13, #241707);
    border-color: #e09228;
    color: #e09228;
}

.center-hud {
    background: #0b101c;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 3px 6px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 9px;
    font-weight: 800;
}

.hud-val {
    color: var(--cyan);
    font-family: monospace;
}

/* SETTINGS MODAL */
.modal-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.75);
    backdrop-filter: blur(4px);
    z-index: 100;
    align-items: center;
    justify-content: center;
}

.modal-box {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px;
    width: 90%;
    max-width: 380px;
}

.modal-box h3 { margin: 0 0 10px 0; font-size: 13px; }
.modal-box input {
    width: 100%;
    padding: 8px;
    background: #060a12;
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    font-size: 12px;
    margin-bottom: 12px;
}

.modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
}
</style>
</head>

<body>

<!-- FULL-SCREEN BLANK GUARD WITH AUTO-DETECT + MANUAL BYPASS -->
<div id="orientationGuard" style="display:none;">
    <svg viewBox="0 0 24 24" style="width:54px;height:54px;fill:#0091ff;margin-bottom:14px;">
        <path d="M16.48 2.52c3.27 1.55 5.61 4.72 5.97 8.48h1.5C23.44 4.84 18.29 0 12 0l-.66.03 3.81 3.81 1.33-1.32zm-12.96 18.96C.25 19.93-2.09 16.76-2.45 13H-3.95C-3.44 19.16 1.71 24 8 24l.66-.03-3.81-3.81-1.33 1.32zM7.5 4A2.5 2.5 0 0 0 5 6.5v11A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5v-11A2.5 2.5 0 0 0 16.5 4h-9z"/>
    </svg>
    <h2 style="font-size:17px;color:#fff;margin:0 0 6px 0;">Rotate to Landscape</h2>
    <p style="font-size:12px;color:#8899b3;margin:0 0 16px 0;">Turn your phone sideways or enable Auto-Rotate.</p>
    <button id="btnBypassRotate" style="background:#162035;border:1px solid #0091ff;color:#fff;padding:8px 16px;border-radius:8px;font-size:11px;font-weight:700;">
        CONTINUE ANYWAY ➔
    </button>
</div>


<div class="app">

    <!-- TOP HEADER -->
    <header class="header">
        <div class="brand">
            <div class="logo">R</div>
            <div class="brand-name">RC PILOT</div>
        </div>

        <div class="hud-actions">
            <div class="status">
                <span class="dot" id="statusDot"></span>
                <span id="connectionStatus">READY</span>
            </div>
            <button class="small-btn" id="btnSettings">CAM SETTINGS</button>
            <button class="small-btn" id="btnFullscreen">FULLSCREEN</button>
        </div>
    </header>

    <!-- LARGE CAMERA VIEW -->
    <section class="camera-container">
        <div class="camera-badge">LIVE FPV</div>
        <img id="cameraImage" alt="RC camera" style="display:none">
        <div class="camera-placeholder" id="cameraPlaceholder">
            <div style="font-size:26px">▣</div>
            <strong>No Active Camera Stream</strong>
            <span>Tap CAM SETTINGS to provide your video stream link.</span>
        </div>
    </section>

    <!-- COMPACT DUAL-THUMB DECK -->
    <main class="deck">

        <!-- LEFT: FORWARD / BACKWARD -->
        <div class="throttle-col">
            <button type="button" class="ctrl-btn" data-key="forward">
                <span class="arrow">▲</span>
                <span class="btn-lbl">FORWARD</span>
            </button>
            <button type="button" class="ctrl-btn" data-key="backward">
                <span class="arrow">▼</span>
                <span class="btn-lbl">BACKWARD</span>
            </button>
        </div>

        <!-- CENTER: POWER, STATUS & STOP -->
        <div class="center-col">
            <button type="button" class="ctrl-btn power-btn off" id="powerToggle">
                <span class="arrow" style="font-size:16px">⏻</span>
                <span class="btn-lbl" id="powerLabel">POWER ON</span>
            </button>

            <div class="center-hud">
                <span style="color:var(--muted)">CMD:</span>
                <span class="hud-val" id="commandName">STOPPED</span>
            </div>

            <button type="button" class="ctrl-btn stop-btn" id="stopButton">
                <span class="arrow" style="font-size:18px">■</span>
                <span class="btn-lbl">STOP</span>
            </button>
        </div>

        <!-- RIGHT: LEFT / RIGHT -->
        <div class="steering-row">
            <button type="button" class="ctrl-btn" data-key="left">
                <span class="arrow">◀</span>
                <span class="btn-lbl">LEFT</span>
            </button>
            <button type="button" class="ctrl-btn" data-key="right">
                <span class="arrow">▶</span>
                <span class="btn-lbl">RIGHT</span>
            </button>
        </div>

    </main>
</div>

<!-- SETTINGS MODAL -->
<div class="modal-overlay" id="modalSettings">
    <div class="modal-box">
        <h3>Camera Stream Setup</h3>
        <input id="cameraUrl" type="url" placeholder="http://192.168.1.50:81/stream">
        <div class="modal-actions">
            <button class="small-btn" id="modalClose">Cancel</button>
            <button class="small-btn" id="modalSave" style="background:var(--blue)">Apply & Stream</button>
        </div>
    </div>
</div>

<script>
const cameraImage = document.getElementById("cameraImage");
const cameraPlaceholder = document.getElementById("cameraPlaceholder");
const cameraUrlInput = document.getElementById("cameraUrl");
const statusText = document.getElementById("connectionStatus");
const statusDot = document.getElementById("statusDot");
const commandName = document.getElementById("commandName");
const powerToggle = document.getElementById("powerToggle");
const powerLabel = document.getElementById("powerLabel");
const stopButton = document.getElementById("stopButton");

let isPoweredOn = false;
let heartbeat = null;

const guard = document.getElementById("orientationGuard");
const bypassBtn = document.getElementById("btnBypassRotate");
let bypassed = false;

function checkOrientation() {
    if (bypassed) {
        guard.style.display = "none";
        return;
    }
    // Check actual rendered width vs height
    const isLandscape = window.innerWidth > window.innerHeight;
    if (isLandscape) {
        guard.style.display = "none";
    } else {
        guard.style.display = "flex";
    }
}

// Check continuously on load, resize, and rotate
window.addEventListener("resize", checkOrientation);
window.addEventListener("orientationchange", checkOrientation);
window.addEventListener("load", checkOrientation);
checkOrientation();

bypassBtn.addEventListener("click", () => {
    bypassed = true;
    guard.style.display = "none";
    if (document.documentElement.requestFullscreen) {
        document.documentElement.requestFullscreen().catch(() => {});
    }
});

// Track active held directions for multi-touch (e.g. forward + right)
const activeKeys = new Set();
const pointerMap = new Map();

function setStatus(msg, ok = true) {
    statusText.textContent = msg;
    statusDot.style.background = ok ? "var(--green)" : "var(--red)";
}

// Compute combined state: forward+right -> "forward_right"
function computeCommand() {
    if (!isPoweredOn || activeKeys.size === 0) {
        return "stop";
    }

    const hasFwd = activeKeys.has("forward");
    const hasBwd = activeKeys.has("backward");
    const hasLeft = activeKeys.has("left");
    const hasRight = activeKeys.has("right");

    if (hasFwd && hasLeft) return "forward_left";
    if (hasFwd && hasRight) return "forward_right";
    if (hasBwd && hasLeft) return "backward_left";
    if (hasBwd && hasRight) return "backward_right";

    if (hasFwd) return "forward";
    if (hasBwd) return "backward";
    if (hasLeft) return "left";
    if (hasRight) return "right";

    return "stop";
}

async function postCommand(command) {
    try {
        const response = await fetch("/api/command", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ command, speed: 75 })
        });
        const res = await response.json();
        if (response.ok) {
            setStatus(res.demo ? "DEMO MODE" : "CONNECTED", true);
        } else {
            setStatus(res.message || "ERROR", false);
        }
    } catch (_) {
        setStatus("OFFLINE", false);
    }
}

function updateState() {
    const nextCmd = computeCommand();
    commandName.textContent = nextCmd.toUpperCase().replace("_", " ");

    document.querySelectorAll("[data-key]").forEach(b => {
        b.classList.toggle("active", activeKeys.has(b.dataset.key));
    });

    postCommand(nextCmd);

    if (nextCmd !== "stop") {
        if (!heartbeat) {
            heartbeat = setInterval(() => {
                postCommand(computeCommand());
            }, 300);
        }
    } else {
        if (heartbeat) {
            clearInterval(heartbeat);
            heartbeat = null;
        }
    }
}

function forceHalt() {
    activeKeys.clear();
    pointerMap.clear();
    updateState();
}

// Multi-touch Pointer Events on Controls
document.querySelectorAll("[data-key]").forEach(btn => {
    const key = btn.dataset.key;

    btn.addEventListener("pointerdown", e => {
        e.preventDefault();
        btn.setPointerCapture(e.pointerId);
        pointerMap.set(e.pointerId, key);
        activeKeys.add(key);
        updateState();
    });

    const release = e => {
        e.preventDefault();
        const mapped = pointerMap.get(e.pointerId);
        if (mapped) {
            activeKeys.delete(mapped);
            pointerMap.delete(e.pointerId);
        }
        updateState();
    };

    btn.addEventListener("pointerup", release);
    btn.addEventListener("pointercancel", release);
    btn.addEventListener("lostpointercapture", release);
    btn.addEventListener("contextmenu", e => e.preventDefault());
});

// Center Emergency Stop
stopButton.addEventListener("click", () => {
    forceHalt();
});

// Power Button
powerToggle.addEventListener("click", async () => {
    forceHalt();
    const desired = !isPoweredOn;

    try {
        const res = await fetch("/api/power", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ powered_on: desired })
        });
        const data = await res.json();
        isPoweredOn = Boolean(data.powered_on);

        if (isPoweredOn) {
            powerToggle.classList.remove("off");
            powerLabel.textContent = "POWER OFF";
            setStatus("POWER ON", true);
            commandName.textContent = "STOPPED";
        } else {
            powerToggle.classList.add("off");
            powerLabel.textContent = "POWER ON";
            setStatus("POWER OFF", true);
            commandName.textContent = "OFF";
        }
    } catch (_) {
        setStatus("SERVER ERROR", false);
    }
});

// Keyboard controls
const keyBindings = {
    KeyW: "forward", ArrowUp: "forward",
    KeyS: "backward", ArrowDown: "backward",
    KeyA: "left", ArrowLeft: "left",
    KeyD: "right", ArrowRight: "right"
};

window.addEventListener("keydown", e => {
    if (e.code === "Space") {
        e.preventDefault();
        forceHalt();
        return;
    }
    if (keyBindings[e.code] && !e.repeat) {
        e.preventDefault();
        activeKeys.add(keyBindings[e.code]);
        updateState();
    }
});

window.addEventListener("keyup", e => {
    if (keyBindings[e.code]) {
        e.preventDefault();
        activeKeys.delete(keyBindings[e.code]);
        updateState();
    }
});

window.addEventListener("blur", forceHalt);
window.addEventListener("pagehide", forceHalt);

// Auto-stop if user rotates to portrait while driving
window.addEventListener("orientationchange", () => {
    forceHalt();
});

// Camera Setup
function connectCamera(url) {
    const clean = url.trim();
    if (!clean) {
        cameraImage.style.display = "none";
        cameraPlaceholder.style.display = "flex";
        return;
    }
    cameraPlaceholder.style.display = "none";
    cameraImage.style.display = "block";
    cameraImage.src = clean;

    cameraImage.onerror = () => {
        cameraImage.style.display = "none";
        cameraPlaceholder.style.display = "flex";
    };
    cameraImage.onload = () => {
        cameraPlaceholder.style.display = "none";
    };
}

// Settings Modal
const modal = document.getElementById("modalSettings");
document.getElementById("btnSettings").addEventListener("click", () => modal.style.display = "flex");
document.getElementById("modalClose").addEventListener("click", () => modal.style.display = "none");
document.getElementById("modalSave").addEventListener("click", async () => {
    const url = cameraUrlInput.value.trim();
    connectCamera(url);
    modal.style.display = "none";
    await fetch("/api/config", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ camera_url: url })
    });
});

// Fullscreen
document.getElementById("btnFullscreen").addEventListener("click", () => {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
    } else {
        document.exitFullscreen().catch(() => {});
    }
});

// Initial config load
fetch("/api/config").then(r => r.json()).then(cfg => {
    if (cfg.camera_url) {
        cameraUrlInput.value = cfg.camera_url;
        connectCamera(cfg.camera_url);
    }
    setStatus(cfg.demo ? "DEMO MODE" : "CONNECTED", true);
}).catch(() => setStatus("OFFLINE", false));

postCommand("stop");
</script>
</body>
</html>
"""


# ---------------- API ROUTES ----------------

@app.route("/")
def home():
    return render_template_string(PAGE)


@app.route("/api/config", methods=["GET", "POST"])
def config():
    global CAMERA_URL

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        CAMERA_URL = str(data.get("camera_url", ""))[:1000]

    return jsonify({
        "camera_url": CAMERA_URL,
        "demo": not bool(HARDWARE_URL),
    })


@app.route("/api/command", methods=["POST"])
def command():
    global current_command, last_command_time, powered_on

    data = request.get_json(silent=True) or {}
    new_command = str(data.get("command", "stop")).lower()

    if new_command not in VALID_COMMANDS:
        return jsonify({"message": "Invalid command"}), 400

    try:
        speed = int(data.get("speed", 60))
    except (ValueError, TypeError):
        speed = 60

    speed = max(0, min(100, speed))

    with state_lock:
        if new_command != "stop" and not powered_on:
            return jsonify({
                "message": "Power is off. Turn power on first."
            }), 403

        current_command = new_command
        last_command_time = time.time()

    ok, message = send_hardware_command(new_command, speed)

    if not ok:
        return jsonify({"message": message}), 502

    return jsonify({
        "ok": True,
        "command": new_command,
        "speed": speed,
        "demo": not bool(HARDWARE_URL),
    })


@app.route("/api/power", methods=["POST"])
def power():
    global powered_on, current_command, last_command_time

    data = request.get_json(silent=True) or {}
    desired_state = bool(data.get("powered_on", False))

    with state_lock:
        powered_on = desired_state
        current_command = "stop"
        last_command_time = time.time()

    ok, message = send_hardware_command("stop")

    return jsonify({
        "powered_on": powered_on,
        "ok": ok,
        "message": message,
    }), (200 if ok else 502)


@app.route("/api/health")
def health():
    with state_lock:
        return jsonify({
            "status": "running",
            "command": current_command,
            "powered_on": powered_on,
            "hardware_configured": bool(HARDWARE_URL),
        })


if __name__ == "__main__":
    print("\n" + "=" * 42)
    print(" RC PILOT CONTROLLER")
    print("=" * 42)
    print(f"Computer: http://127.0.0.1:{PORT}")
    print(f"Phone:    http://YOUR-PC-IP:{PORT}")
    print(f"Hardware: {HARDWARE_URL or 'Demo mode'}")
    print("=" * 42 + "\n")

    try:
        app.run(
            host=HOST,
            port=PORT,
            debug=False,
            threaded=True,
            use_reloader=False,
        )
    finally:
        force_stop()
