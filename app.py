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
VALID_COMMANDS = {"forward", "backward", "left", "right", "stop"}

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
<meta name="theme-color" content="#080d18">
<title>RC Pilot Controller</title>

<style>
:root {
    --bg: #080d18;
    --panel: #111b2d;
    --panel2: #1a2941;
    --border: #2c3d59;
    --text: #f4f7ff;
    --muted: #9aaac2;
    --blue: #3478f6;
    --cyan: #39d7e8;
    --red: #f0445b;
    --green: #35d69a;
}

* {
    box-sizing: border-box;
    -webkit-tap-highlight-color: transparent;
}

html, body {
    margin: 0;
    width: 100%;
    min-height: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
}

body {
    overscroll-behavior: none;
}

button, input {
    font: inherit;
}

button {
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
    cursor: pointer;
}

.app {
    min-height: 100dvh;
    display: flex;
    flex-direction: column;
    gap: 9px;
    padding: 10px;
}

.header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    min-height: 38px;
    flex-shrink: 0;
}

.brand {
    display: flex;
    align-items: center;
    gap: 9px;
    min-width: 0;
}

.logo {
    width: 35px;
    height: 35px;
    flex-shrink: 0;
    display: grid;
    place-items: center;
    border-radius: 10px;
    background: linear-gradient(135deg, var(--blue), var(--cyan));
    color: #06101c;
    font-weight: 900;
    font-size: 20px;
}

.brand-name {
    font-size: 17px;
    font-weight: 900;
    letter-spacing: .5px;
}

.sub {
    color: var(--muted);
    font-size: 10px;
    margin-top: 3px;
}

.status {
    display: flex;
    align-items: center;
    gap: 7px;
    border: 1px solid var(--border);
    border-radius: 30px;
    padding: 8px 10px;
    color: var(--muted);
    font-size: 10px;
    white-space: nowrap;
}

.dot {
    width: 8px;
    height: 8px;
    flex-shrink: 0;
    border-radius: 50%;
    background: var(--green);
}

.camera {
    position: relative;
    flex-shrink: 0;
    height: clamp(145px, 25dvh, 270px);
    border: 1px solid var(--border);
    border-radius: 14px;
    overflow: hidden;
    background: #03060c;
}

.camera img {
    width: 100%;
    height: 100%;
    position: absolute;
    inset: 0;
    object-fit: contain;
    background: #03060c;
}

.camera-placeholder {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 7px;
    text-align: center;
    padding: 12px;
    background: radial-gradient(ellipse, #172743, #080d18);
    color: var(--muted);
    font-size: 12px;
}

.camera-placeholder strong {
    color: var(--text);
    font-size: 14px;
}

.camera-badge {
    position: absolute;
    z-index: 2;
    top: 8px;
    left: 8px;
    padding: 5px 8px;
    border-radius: 5px;
    background: rgba(0, 0, 0, 0.6);
    font-size: 10px;
    letter-spacing: 1px;
}

.camera-settings {
    display: flex;
    gap: 6px;
    flex-shrink: 0;
}

.camera-settings input {
    min-width: 0;
    flex: 1;
    width: 100%;
    padding: 10px;
    color: var(--text);
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
}

.small-button {
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    background: var(--panel2);
    padding: 0 12px;
    min-height: 38px;
    font-weight: 700;
}

.main {
    flex: 1;
    min-height: 250px;
    display: grid;
    grid-template-columns: minmax(0, 1fr) 175px;
    gap: 9px;
}

.controls, .side {
    min-width: 0;
    min-height: 0;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 15px;
    padding: 12px;
}

.controls {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.section-title {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 900;
    letter-spacing: 1px;
    text-transform: uppercase;
}

.muted {
    color: var(--muted);
    font-size: 10px;
    letter-spacing: 0;
}

.control-layout {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr);
    gap: 10px;
    align-items: stretch;
}

.group {
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: stretch;
    gap: 10px;
}

.group-title {
    color: var(--muted);
    text-align: center;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1px;
}

.control-btn {
    flex: 1;
    min-height: 60px;
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 4px;
    padding: 5px 2px;
    color: var(--text);
    border: 1px solid #344866;
    border-radius: 14px;
    background: linear-gradient(145deg, #20304a, #121c2d);
    box-shadow: 0 4px 0 #070b13;
}

.control-btn.active {
    background: linear-gradient(145deg, #3478f6, #2050ac);
    border-color: #8ab1ff;
    box-shadow: 0 1px 0 #070b13;
    transform: translateY(2px);
}

.arrow {
    font-size: clamp(24px, 3.5vw, 36px);
    line-height: 1;
    font-weight: 900;
}

.btn-label {
    font-size: 10px;
    font-weight: 900;
    letter-spacing: .4px;
    text-align: center;
}

.centre .control-btn {
    min-height: 64px;
}

.power-btn {
    background: linear-gradient(145deg, #176e55, #104b3c);
    border-color: #2a9b77;
}

.power-btn.off {
    background: linear-gradient(145deg, #a9273c, #6d1728);
    border-color: #ed6578;
}

.stop-btn {
    background: linear-gradient(145deg, #a92c42, #721b2d);
    border-color: #e85b70;
}

.side {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.speed-number {
    font-size: 29px;
    font-weight: 900;
    margin-top: 7px;
}

.speed-number span {
    font-size: 12px;
    color: var(--muted);
}

input[type=range] {
    width: 100%;
    accent-color: var(--blue);
    margin: 10px 0;
}

.speed-labels {
    display: flex;
    justify-content: space-between;
    color: var(--muted);
    font-size: 10px;
}

.readout {
    padding: 10px;
    background: #0a1120;
    border: 1px solid var(--border);
    border-radius: 10px;
}

.readout-value {
    margin-top: 5px;
    font-size: 14px;
    font-weight: 900;
    overflow-wrap: anywhere;
}

.power-state {
    font-size: 12px;
    color: var(--green);
    font-weight: 800;
}

.power-state.off {
    color: #ff6578;
}

.hint {
    margin-top: auto;
    font-size: 10px;
    color: var(--muted);
    line-height: 1.6;
}

/* Portrait mobile layout */
@media (max-width: 650px) and (orientation: portrait) {
    .app {
        padding: max(7px, env(safe-area-inset-top)) 7px max(9px, env(safe-area-inset-bottom));
        gap: 8px;
    }

    .brand-name { font-size: 15px; }
    .sub { font-size: 9px; }
    .status { padding: 7px 8px; font-size: 9px; }

    .camera {
        height: clamp(145px, 23dvh, 230px);
    }

    .main {
        display: flex;
        flex-direction: column;
        min-height: 0;
        flex: none;
        gap: 8px;
    }

    .controls {
        padding: 10px 8px;
        gap: 10px;
    }

    .control-layout {
        gap: 7px;
        min-height: 225px;
    }

    .group { gap: 8px; }
    .group-title { font-size: 9px; }

    .control-btn {
        min-height: 80px;
        border-radius: 12px;
    }

    .centre .control-btn { min-height: 80px; }

    .arrow { font-size: clamp(26px, 7vw, 38px); }
    .btn-label { font-size: clamp(9px, 2.5vw, 11px); }

    .side {
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
        gap: 10px;
        padding: 10px;
    }

    .readout, .hint { grid-column: 1 / -1; }
    .speed-number { font-size: 25px; }
}

/* Landscape mobile */
@media (orientation: landscape) and (max-height: 520px) {
    html, body {
        width: 100%;
        height: 100%;
        overflow: hidden;
    }

    .app {
        height: 100dvh;
        min-height: 0;
        overflow: hidden;
        padding: 4px 7px;
        gap: 5px;
    }

    .header { min-height: 27px; }
    .logo { width: 26px; height: 26px; font-size: 14px; }
    .brand-name { font-size: 13px; }
    .sub { display: none; }
    .status { padding: 5px 7px; font-size: 9px; }

    .camera {
        height: 18dvh;
        min-height: 60px;
        max-height: 100px;
    }

    .camera-settings { display: none; }

    .main {
        flex: 1;
        min-height: 0;
        grid-template-columns: minmax(0, 1fr) 130px;
        gap: 5px;
    }

    .controls, .side {
        padding: 5px;
        gap: 4px;
        overflow: hidden;
    }

    .control-layout {
        flex: 1;
        min-height: 0;
        gap: 5px;
    }

    .group { gap: 4px; min-height: 0; }
    .control-btn, .centre .control-btn {
        flex: 1;
        min-height: 0;
        height: 100%;
        padding: 1px;
        gap: 2px;
        border-radius: 8px;
    }

    .arrow { font-size: clamp(16px, 4vh, 24px); }
    .btn-label { font-size: clamp(7px, 1.8vh, 9px); }

    .side { gap: 4px; }
    .speed-number { font-size: 18px; margin-top: 1px; }
    input[type=range] { margin: 2px 0; }
    .readout { padding: 5px; }
    .readout-value { font-size: 11px; }
    .hint { display: none; }
}
</style>
</head>

<body>
<div class="app">

    <header class="header">
        <div class="brand">
            <div class="logo">R</div>
            <div>
                <div class="brand-name">RC PILOT</div>
                <div class="sub">WIRELESS VEHICLE CONTROL</div>
            </div>
        </div>

        <div class="status">
            <span class="dot" id="statusDot"></span>
            <span id="connectionStatus">CONTROLLER READY</span>
        </div>
    </header>

    <section class="camera">
        <div class="camera-badge">LIVE CAMERA</div>
        <img id="cameraImage" alt="RC camera" style="display:none">
        <div class="camera-placeholder" id="cameraPlaceholder">
            <div style="font-size:28px">▣</div>
            <strong>Camera feed</strong>
            <span>Configure your camera stream URL below.</span>
        </div>
    </section>

    <section class="camera-settings">
        <input id="cameraUrl" type="url" placeholder="Camera stream URL (e.g. http://192.168.1.50:81/stream)">
        <button class="small-button" id="cameraApply">CONNECT</button>
    </section>

    <main class="main">

        <section class="controls">
            <div class="section-title">
                <span>Driving controls</span>
                <span class="muted">Press and hold</span>
            </div>

            <div class="control-layout">

                <!-- LEFT COLUMN: FORWARD & BACKWARD -->
                <div class="group">
                    <div class="group-title">DRIVE</div>

                    <button type="button" class="control-btn" data-command="forward">
                        <span class="arrow">▲</span>
                        <span class="btn-label">FORWARD</span>
                    </button>

                    <button type="button" class="control-btn" data-command="backward">
                        <span class="arrow">▼</span>
                        <span class="btn-label">BACKWARD</span>
                    </button>
                </div>

                <!-- CENTER COLUMN: POWER & STOP -->
                <div class="group centre">
                    <div class="group-title">POWER</div>

                    <button type="button" class="control-btn power-btn off" id="powerToggle">
                        <span class="arrow">⏻</span>
                        <span class="btn-label" id="powerLabel">POWER ON</span>
                    </button>

                    <button type="button" class="control-btn stop-btn" id="stopButton">
                        <span class="arrow">■</span>
                        <span class="btn-label">STOP</span>
                    </button>
                </div>

                <!-- RIGHT COLUMN: LEFT & RIGHT -->
                <div class="group">
                    <div class="group-title">STEERING</div>

                    <button type="button" class="control-btn" data-command="left">
                        <span class="arrow">◀</span>
                        <span class="btn-label">LEFT</span>
                    </button>

                    <button type="button" class="control-btn" data-command="right">
                        <span class="arrow">▶</span>
                        <span class="btn-label">RIGHT</span>
                    </button>
                </div>

            </div>
        </section>

        <aside class="side">
            <div>
                <div class="section-title">SPEED</div>
                <div class="speed-number">
                    <span id="speedValue">60</span><span>%</span>
                </div>
                <input type="range" id="speedSlider" min="10" max="100" value="60">
                <div class="speed-labels">
                    <span>SLOW</span><span>FAST</span>
                </div>
            </div>

            <div class="readout">
                <div class="muted">POWER STATUS</div>
                <div id="powerState" class="power-state off">POWER OFF</div>
                <div class="muted" style="margin-top:8px">COMMAND</div>
                <div id="commandName" class="readout-value">STOPPED</div>
            </div>

            <div class="hint">
                Hold a direction to move.<br>
                Release to stop.<br>
                Spacebar stops on desktop.
            </div>
        </aside>
    </main>
</div>

<script>
const cameraUrlInput = document.getElementById("cameraUrl");
const cameraImage = document.getElementById("cameraImage");
const cameraPlaceholder = document.getElementById("cameraPlaceholder");
const statusText = document.getElementById("connectionStatus");
const statusDot = document.getElementById("statusDot");
const commandName = document.getElementById("commandName");
const speedSlider = document.getElementById("speedSlider");
const speedValue = document.getElementById("speedValue");
const powerToggle = document.getElementById("powerToggle");
const powerLabel = document.getElementById("powerLabel");
const powerState = document.getElementById("powerState");

let isPoweredOn = false;
let activeCommand = "stop";
let activePointerId = null;
let heartbeat = null;

const allowedCommands = new Set(["forward", "backward", "left", "right"]);

function setStatus(message, ok = true) {
    statusText.textContent = message;
    statusDot.style.background = ok ? "#35d69a" : "#f0445b";
}

async function postCommand(command) {
    try {
        const response = await fetch("/api/command", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                command,
                speed: Number(speedSlider.value)
            })
        });

        const result = await response.json();

        if (!response.ok) {
            setStatus(result.message || "COMMAND ERROR", false);
            return false;
        }

        setStatus(result.demo ? "DEMO MODE" : "CONNECTED", true);
        return true;
    } catch (error) {
        setStatus("SERVER ERROR", false);
        return false;
    }
}

function highlightCommand(command) {
    document.querySelectorAll("[data-command]").forEach(button => {
        button.classList.toggle("active", button.dataset.command === command);
    });
}

function stopMovement() {
    clearInterval(heartbeat);
    heartbeat = null;
    activePointerId = null;
    activeCommand = "stop";

    highlightCommand("stop");
    commandName.textContent = isPoweredOn ? "STOPPED" : "POWER IS OFF";
    postCommand("stop");
}

function startMovement(command, pointerId) {
    if (!isPoweredOn || !allowedCommands.has(command)) {
        return;
    }

    clearInterval(heartbeat);
    activePointerId = pointerId;
    activeCommand = command;

    highlightCommand(command);
    commandName.textContent = command.toUpperCase();
    postCommand(command);

    heartbeat = setInterval(() => {
        if (isPoweredOn && activeCommand === command) {
            postCommand(command);
        } else {
            clearInterval(heartbeat);
            heartbeat = null;
        }
    }, 300);
}

// Direction button listeners
document.querySelectorAll("[data-command]").forEach(button => {
    const command = button.dataset.command;

    button.addEventListener("pointerdown", event => {
        event.preventDefault();

        if (!isPoweredOn) {
            commandName.textContent = "POWER IS OFF";
            return;
        }

        stopMovement();
        startMovement(command, event.pointerId);
    });

    button.addEventListener("pointerup", event => {
        event.preventDefault();
        if (activePointerId === event.pointerId) {
            stopMovement();
        }
    });

    button.addEventListener("pointercancel", stopMovement);
    button.addEventListener("lostpointercapture", () => {
        if (activeCommand !== "stop") stopMovement();
    });
    button.addEventListener("contextmenu", e => e.preventDefault());
});

document.getElementById("stopButton").addEventListener("click", () => {
    stopMovement();
});

// Clean Power Toggle Listener
powerToggle.addEventListener("click", async () => {
    stopMovement();
    const desiredState = !isPoweredOn;

    try {
        const response = await fetch("/api/power", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ powered_on: desiredState })
        });

        const result = await response.json();

        if (!response.ok) {
            setStatus("POWER ERROR", false);
            return;
        }

        isPoweredOn = Boolean(result.powered_on);

        if (isPoweredOn) {
            powerToggle.classList.remove("off");
            powerLabel.textContent = "POWER OFF";
            powerState.textContent = "POWER ON";
            powerState.classList.remove("off");
            commandName.textContent = "STOPPED";
            setStatus("POWER ON", true);
        } else {
            powerToggle.classList.add("off");
            powerLabel.textContent = "POWER ON";
            powerState.textContent = "POWER OFF";
            powerState.classList.add("off");
            commandName.textContent = "POWER IS OFF";
            setStatus("POWER OFF", true);
        }
    } catch (error) {
        setStatus("SERVER ERROR", false);
    }
});

speedSlider.addEventListener("input", () => {
    speedValue.textContent = speedSlider.value;
    if (isPoweredOn && activeCommand !== "stop") {
        postCommand(activeCommand);
    }
});

window.addEventListener("blur", stopMovement);
window.addEventListener("pagehide", stopMovement);
document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopMovement();
});

document.addEventListener("keydown", event => {
    const map = {
        ArrowUp: "forward",
        ArrowDown: "backward",
        ArrowLeft: "left",
        ArrowRight: "right"
    };

    if (event.code === "Space") {
        event.preventDefault();
        stopMovement();
    } else if (map[event.key] && !event.repeat && isPoweredOn) {
        event.preventDefault();
        stopMovement();
        startMovement(map[event.key], "keyboard");
    }
});

document.addEventListener("keyup", event => {
    if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) {
        stopMovement();
    }
});

function connectCamera(url) {
    const cleanUrl = url.trim();

    if (!cleanUrl) {
        cameraImage.style.display = "none";
        cameraPlaceholder.style.display = "flex";
        return;
    }

    cameraPlaceholder.style.display = "none";
    cameraImage.style.display = "block";
    cameraImage.src = cleanUrl;

    cameraImage.onerror = () => {
        cameraImage.style.display = "none";
        cameraPlaceholder.style.display = "flex";
    };

    cameraImage.onload = () => {
        cameraPlaceholder.style.display = "none";
    };
}

async function saveConfig() {
    try {
        await fetch("/api/config", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                camera_url: cameraUrlInput.value.trim()
            })
        });
    } catch (_) {}
}

document.getElementById("cameraApply").addEventListener("click", async () => {
    connectCamera(cameraUrlInput.value);
    await saveConfig();
});

async function loadConfig() {
    try {
        const response = await fetch("/api/config");
        const config = await response.json();

        cameraUrlInput.value = config.camera_url || "";
        if (config.camera_url) {
            connectCamera(config.camera_url);
        }

        setStatus(config.demo ? "DEMO MODE" : "CONNECTED", true);
    } catch (_) {
        setStatus("SERVER ERROR", false);
    }
}

loadConfig();
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