import sys, os, time
sys.path.insert(0, os.path.abspath("."))
import webview
from spike import windows as W
class H:
    config={}
    def _log(s,m): pass
    def call_soon(s,fn): fn()
    def show(s): pass
    def hide(s): pass
    def _toggle_record(s): pass
    def _toggle_pause(s): pass
    def hero_state(s): return "recording"
    def hero_readouts(s): return {"elapsed":"00:00:05","size":"12 MB","bitrate":""}
    def _on_notify(s,*a): pass
nw = W.NebulaWindows(H(), {})
def worker(w):
    time.sleep(2.5)
    nw.toast_replace("start", "Helldivers 2", None)
    print("TOAST UP", flush=True)
    time.sleep(300)   # sit here until killed hard
main = webview.create_window("probe", html="<body></body>", width=160, height=80, hidden=True)
webview.start(worker, main)
