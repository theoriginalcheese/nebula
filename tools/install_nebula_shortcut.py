"""Create / refresh the Start Menu shortcut so Windows Search opens Nebula (spike)."""
from __future__ import annotations

import os
import sys


def shortcut_args(script, show=True, dev=False):
    """Start Menu argv. Everyday launches must not pass ``--dev``.

    ``--dev`` skips the single-instance mutex, so a Search/Start Menu
    shortcut that included it stacked leftover ``pythonw spike/app.py --dev
    --show`` processes and left the UI on HTML placeholders.
    """
    extra = []
    if dev:
        extra.append("--dev")
    if show:
        extra.append("--show")
    quoted = '"%s"' % script
    if not extra:
        return quoted
    return "%s %s" % (quoted, " ".join(extra))


def install_start_menu_shortcut(
    repo_root=None,
    pythonw=None,
    show=True,
):
    """Write ``%APPDATA%\\…\\Start Menu\\Programs\\Nebula.lnk`` → spike app.

    Returns the shortcut path. Uses pywin32 if present, else PowerShell.
    """
    repo_root = os.path.abspath(
        repo_root or os.path.dirname(os.path.dirname(__file__)))
    script = os.path.join(repo_root, "spike", "app.py")
    pythonw = pythonw or os.path.join(
        os.path.dirname(sys.executable),
        "pythonw.exe" if os.name == "nt" else sys.executable)
    if not os.path.isfile(pythonw):
        pythonw = sys.executable
    icon = os.path.join(repo_root, "nebula_icon.ico")
    programs = os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft", "Windows", "Start Menu", "Programs")
    os.makedirs(programs, exist_ok=True)
    lnk = os.path.join(programs, "Nebula.lnk")
    args = shortcut_args(script, show=show, dev=False)

    try:
        import win32com.client  # type: ignore
        shell = win32com.client.Dispatch("WScript.Shell")
        sc = shell.CreateShortCut(lnk)
        sc.Targetpath = pythonw
        sc.Arguments = args
        sc.WorkingDirectory = repo_root
        sc.Description = "Nebula — OBS auto-folder"
        if os.path.isfile(icon):
            sc.IconLocation = icon
        sc.save()
        return lnk
    except Exception:
        pass

    # PowerShell fallback — no pywin32 required.
    ps = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%s'); "
        "$s.TargetPath = '%s'; $s.Arguments = '%s'; "
        "$s.WorkingDirectory = '%s'; $s.Description = 'Nebula — OBS auto-folder'; "
        "%s"
        "$s.Save()"
    ) % (
        lnk.replace("'", "''"),
        pythonw.replace("'", "''"),
        args.replace("'", "''"),
        repo_root.replace("'", "''"),
        ("$s.IconLocation = '%s'; " % icon.replace("'", "''"))
        if os.path.isfile(icon) else "",
    )
    import subprocess
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        check=False, capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return lnk


if __name__ == "__main__":
    path = install_start_menu_shortcut()
    print(path)
    print("exists", os.path.isfile(path))
