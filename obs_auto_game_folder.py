import os 
import sys
import json
import time
import ctypes
import threading
import tkinter as tk
import tkinter.messagebox
import customtkinter as ctk
import websocket
import requests
import subprocess
import psutil

# ==== CONFIGURATION ====
OBS_WEBSOCKET_HOST = "localhost"
OBS_WEBSOCKET_PORT = 4455
DEFAULT_RECORDING_DIR = "D:/OBS Recordings"
GAME_LIST_FILE = "game_list.txt"
TO_SORT_LIST_FILE = "TO SORT GAMES.txt"
NON_GAME_LIST_FILE = "SORTED NON-GAMES.txt"
STEAM_COMMON_PATH = r"C:\Program Files (x86)\Steam\steamapps\common"
MISTRAL_API_URL = "http://localhost:11434/api/generate"
IDLE_TIMEOUT_SECONDS = 4
EXTERNAL_IDLE_EXECUTABLE = "obstrigger.exe"

# ==== GLOBALS ====
obs_socket = None
monitoring = False
idle_timer = None
last_game_detected = None
game_detection_lock = threading.Lock()
console_output = None
console_window = None
obs_status_label = None
folder_label = None
status_label = None
start_button = None
stop_button = None
timeout_label = None
idle_timeout_override = IDLE_TIMEOUT_SECONDS


# ==== HELPER FUNCTIONS ====
def log(message):
    print(message)
    if console_output:
        console_output.configure(state="normal")
        console_output.insert("end", message + "\n")
        console_output.see("end")
        console_output.configure(state="disabled")


def get_idle_duration():
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(lii)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return millis / 1000.0
    return 0


def read_game_list():
    if not os.path.exists(GAME_LIST_FILE):
        with open(GAME_LIST_FILE, "w") as f:
            pass
    with open(GAME_LIST_FILE, "r") as f:
        return set(line.strip().lower() for line in f if line.strip())


def classify_with_mistral(exe_path):
    prompt = f"Is '{exe_path}' a game? If it's a game return true, if it isn't a game then return false. Please keep it to true or false."
    try:
        response = requests.post(MISTRAL_API_URL, json={
            "model": "mistral",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "stream": False
        }, timeout=15)
        response.raise_for_status()
        data = response.json()
        output_text = data.get("message", {}).get("content", "").lower()
        return "true" in output_text
    except Exception as e:
        log(f"[Mistral Error] {e}")
        return False


def scan_steam_folder():
    log("[Steam] Scanning Steam common folder...")
    found_new = False
    if not os.path.exists(STEAM_COMMON_PATH):
        log(f"[Steam] Directory not found: {STEAM_COMMON_PATH}")
        return

    existing_games = read_game_list()
    to_sort_set = set()
    if os.path.exists(TO_SORT_LIST_FILE):
        with open(TO_SORT_LIST_FILE, "r") as f:
            to_sort_set.update(line.strip() for line in f)

    for folder in os.listdir(STEAM_COMMON_PATH):
        folder_path = os.path.join(STEAM_COMMON_PATH, folder)
        if not os.path.isdir(folder_path):
            continue
        exe_candidates = [f for f in os.listdir(folder_path) if f.lower().endswith(".exe")]
        for exe in exe_candidates:
            exe_path = os.path.join(folder_path, exe)
            rel_path = os.path.relpath(exe_path, STEAM_COMMON_PATH).replace("\\", "/").lower()
            if rel_path in existing_games or rel_path in to_sort_set:
                continue

            is_game = classify_with_mistral(exe)
            if is_game:
                with open(GAME_LIST_FILE, "a") as f:
                    f.write(rel_path + "\n")
                log(f"[Mistral] Added to game list: {rel_path}")
            else:
                with open(NON_GAME_LIST_FILE, "a") as f:
                    f.write(rel_path + "\n")
                log(f"[Mistral] Marked as non-game: {rel_path}")
            found_new = True

    if not found_new:
        log("[Steam] No new games found.")


def get_current_game():
    game_list = read_game_list()
    for proc in psutil.process_iter(['name', 'exe']):
        try:
            name = proc.info['name']
            exe_path = proc.info['exe']
            if not exe_path:
                continue
            rel_path = os.path.relpath(exe_path, STEAM_COMMON_PATH).replace("\\", "/").lower()
            if rel_path in game_list:
                return name, rel_path
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None, None


def set_obs_recording_folder(path):
    global obs_socket
    if not obs_socket:
        return

    try:
        request_data = {
            "request-type": "SetRecordDirectory",
            "message-id": "1",
            "recordDirectory": path
        }
        obs_socket.send(json.dumps(request_data))
        log(f"[OBS] Recording folder set to: {path}")
    except Exception as e:
        log(f"[OBS] Failed to set recording folder: {e}")


def connect_to_obs():
    global obs_socket
    try:
        url = f"ws://{OBS_WEBSOCKET_HOST}:{OBS_WEBSOCKET_PORT}"
        obs_socket = websocket.create_connection(url, timeout=5)
        log("[OBS] Connected to OBS WebSocket")
        if obs_status_label:
            obs_status_label.configure(text="OBS: Connected", text_color="green")
        return True
    except Exception as e:
        log(f"[OBS] WebSocket connection failed: {e}")
        if obs_status_label:
            obs_status_label.configure(text="OBS: Disconnected", text_color="red")
        return False


def disconnect_obs():
    global obs_socket
    if obs_socket:
        try:
            obs_socket.close()
        except:
            pass
        obs_socket = None
        if obs_status_label:
            obs_status_label.configure(text="OBS: Disconnected", text_color="red")


def launch_idle_executor():
    try:
        subprocess.Popen(EXTERNAL_IDLE_EXECUTABLE)
        log(f"[Idle] Launched external idle executable: {EXTERNAL_IDLE_EXECUTABLE}")
    except Exception as e:
        log(f"[Idle] Failed to launch external executable: {e}")


# ==== MAIN MONITORING LOOP ====
def monitor_loop():
    global monitoring, last_game_detected, idle_timer
    idle_executed = False
    while monitoring:
        idle_duration = get_idle_duration()
        if idle_duration >= idle_timeout_override:
            if last_game_detected:
                log("[System] Idle timeout reached. No input detected.")
                with game_detection_lock:
                    last_game_detected = None
                if status_label:
                    status_label.configure(text="Game: None")
                set_obs_recording_folder(DEFAULT_RECORDING_DIR)
            if not idle_executed:
                launch_idle_executor()
                idle_executed = True
            time.sleep(1)
            continue
        else:
            idle_executed = False

        name, rel_path = get_current_game()
        if name and rel_path:
            with game_detection_lock:
                if rel_path != last_game_detected:
                    last_game_detected = rel_path
                    game_folder = os.path.join(DEFAULT_RECORDING_DIR, os.path.basename(rel_path))
                    os.makedirs(game_folder, exist_ok=True)
                    set_obs_recording_folder(game_folder)
                    if status_label:
                        status_label.configure(text=f"Game: {name}")
                    if folder_label:
                        folder_label.configure(text=f"Folder: {game_folder}")
                    log(f"[Game] Detected game: {name} ({rel_path})")
        else:
            if last_game_detected:
                with game_detection_lock:
                    last_game_detected = None
                if status_label:
                    status_label.configure(text="Game: None")
                set_obs_recording_folder(DEFAULT_RECORDING_DIR)
        time.sleep(1)


# ==== GUI ACTIONS ====
def start_monitoring():
    global monitoring
    if not connect_to_obs():
        tkinter.messagebox.showerror("OBS Error", "Could not connect to OBS WebSocket.")
        return
    monitoring = True
    start_button.configure(state="disabled")
    stop_button.configure(state="normal")
    threading.Thread(target=monitor_loop, daemon=True).start()
    scan_steam_folder()
    log("[Monitor] Monitoring started.")


def stop_monitoring():
    global monitoring
    monitoring = False
    start_button.configure(state="normal")
    stop_button.configure(state="disabled")
    disconnect_obs()
    log("[Monitor] Monitoring stopped.")


def launch_obs():
    try:
        subprocess.Popen("obs64.exe")
        log("[Launch] OBS launched.")
    except FileNotFoundError:
        tkinter.messagebox.showerror("Launch Error", "Could not find OBS executable.")


def open_game_list():
    if os.path.exists(GAME_LIST_FILE):
        os.startfile(GAME_LIST_FILE)
    else:
        tkinter.messagebox.showwarning("File Missing", f"{GAME_LIST_FILE} not found.")


def open_to_sort_list():
    if os.path.exists(TO_SORT_LIST_FILE):
        os.startfile(TO_SORT_LIST_FILE)
    else:
        tkinter.messagebox.showwarning("File Missing", f"{TO_SORT_LIST_FILE} not found.")


def open_sorted_non_games_list():
    if os.path.exists(NON_GAME_LIST_FILE):
        os.startfile(NON_GAME_LIST_FILE)
    else:
        tkinter.messagebox.showwarning("File Missing", f"{NON_GAME_LIST_FILE} not found.")


def on_timeout_change(value):
    global idle_timeout_override
    idle_timeout_override = int(value)
    if timeout_label:
        timeout_label.configure(text=f"Idle Timeout ({idle_timeout_override}s):")


# ==== GUI SETUP ====
def setup_gui():
    global console_output, console_window, obs_status_label, folder_label, status_label, start_button, stop_button, timeout_label

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    console_window = ctk.CTk()
    console_window.title("OBS Auto Recording Controller")
    console_window.geometry("800x600")

    frame_top = ctk.CTkFrame(console_window)
    frame_top.pack(padx=10, pady=10, fill="x")

    obs_status_label = ctk.CTkLabel(frame_top, text="OBS: Disconnected", text_color="red")
    obs_status_label.pack(side="left", padx=5)

    start_button = ctk.CTkButton(frame_top, text="Start Monitoring", command=start_monitoring)
    start_button.pack(side="left", padx=5)

    stop_button = ctk.CTkButton(frame_top, text="Stop Monitoring", command=stop_monitoring, state="disabled")
    stop_button.pack(side="left", padx=5)

    launch_button = ctk.CTkButton(frame_top, text="Launch OBS", command=launch_obs)
    launch_button.pack(side="left", padx=5)

    open_games_btn = ctk.CTkButton(frame_top, text="Open Game List", command=open_game_list)
    open_games_btn.pack(side="left", padx=5)

    open_to_sort_btn = ctk.CTkButton(frame_top, text="Open To Sort List", command=open_to_sort_list)
    open_to_sort_btn.pack(side="left", padx=5)

    open_non_games_btn = ctk.CTkButton(frame_top, text="Open Non-Games List", command=open_sorted_non_games_list)
    open_non_games_btn.pack(side="left", padx=5)

    frame_middle = ctk.CTkFrame(console_window)
    frame_middle.pack(padx=10, pady=10, fill="x")

    status_label = ctk.CTkLabel(frame_middle, text="Game: None")
    status_label.pack(anchor="w")

    folder_label = ctk.CTkLabel(frame_middle, text=f"Folder: {DEFAULT_RECORDING_DIR}")
    folder_label.pack(anchor="w")

    frame_bottom = ctk.CTkFrame(console_window)
    frame_bottom.pack(padx=10, pady=10, fill="both", expand=True)

    text_frame = tk.Frame(master=frame_bottom)
    text_frame.pack(fill="both", expand=True)

    scrollbar = tk.Scrollbar(text_frame)
    scrollbar.pack(side="right", fill="y")

    console_output = ctk.CTkTextbox(text_frame, state="disabled", wrap="word", yscrollcommand=scrollbar.set)
    console_output.pack(fill="both", expand=True)
    scrollbar.config(command=console_output.yview)

    frame_timeout = ctk.CTkFrame(console_window)
    frame_timeout.pack(padx=10, pady=10, fill="x")

    timeout_label = ctk.CTkLabel(frame_timeout, text=f"Idle Timeout ({idle_timeout_override}s):")
    timeout_label.pack(side="left", padx=5)

    timeout_slider = ctk.CTkSlider(frame_timeout, from_=1, to=20, number_of_steps=19, command=on_timeout_change)
    timeout_slider.set(idle_timeout_override)
    timeout_slider.pack(side="left", fill="x", expand=True, padx=5)

    console_window.mainloop()


if __name__ == "__main__":
    setup_gui()
