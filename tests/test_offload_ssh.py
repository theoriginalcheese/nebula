"""SSH on-NAS SHA verification - the gate that permits local deletes.

In move mode a clip's local original is removed only after the destination
hash matches. When ``nas_offload_ssh_host`` is set that hash prefers
``sha256sum`` over SSH. These pins matter because every failure path must
fail towards MORE verification, never less:

  - malformed/injected remote paths -> refused (None), never executed
  - garbage ssh output              -> None, falls back to hashing over SMB
  - a WRONG but well-formed digest  -> mismatch, local file kept

    python tests/test_offload_ssh.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import paths as paths_module
from obsauto import offload as offload_module
from obsauto.offload import Offloader

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


GOOD = "a" * 64


def make_off(tmp_root, host="nas", unix="/srv/obs", extra=None):
    app_dir = os.path.join(tmp_root, "app")
    os.makedirs(app_dir, exist_ok=True)
    original = paths_module.APP_DIR
    paths_module.APP_DIR = app_dir
    try:
        cfg = {"nas_offload_root": os.path.join(tmp_root, "nas"),
               "nas_offload_mode": "move",
               "nas_offload_ssh_host": host,
               "nas_offload_unix_root": unix}
        cfg.update(extra or {})
        return Offloader(cfg)
    finally:
        paths_module.APP_DIR = original


def run():
    work = tempfile.mkdtemp(prefix="nebula-offload-ssh-")
    real_run = offload_module.subprocess.run
    nas = os.path.join(work, "nas")

    # ---- path mapping ----
    off = make_off(work)
    inside = os.path.join(nas, "Elden Ring", "clip.mkv")
    mapped = off._unix_path_for(inside)
    check("inside root maps to unix tree",
          mapped == "/srv/obs/Elden Ring/clip.mkv", mapped)
    outside = os.path.join(work, "elsewhere", "x.mkv")
    check("outside root never invents a remote path",
          off._unix_path_for(outside) is None,
          off._unix_path_for(outside))
    check("unconfigured host -> no mapping",
          make_off(work, host="")._unix_path_for(inside) is None)

    # ---- injection guards ----
    for bad in ("/srv/x\nrm -rf /", "/srv/x\rY", "/srv/x\x00"):
        check(f"refuses hostile path {bad[:12]!r}",
              off._ssh_sha256(bad) is None)

    # ---- output parsing via a stubbed ssh ----
    def ssh_stub(returncode=0, stdout=b"", stderr=b""):
        from types import SimpleNamespace

        def _run(*a, **k):
            return SimpleNamespace(returncode=returncode,
                                   stdout=stdout, stderr=stderr)
        return _run

    offload_module.subprocess.run = ssh_stub(stdout=f"{GOOD} */srv/obs/f.mkv\n".encode())
    got = off._ssh_sha256("/srv/obs/f.mkv")
    check("well-formed output parses", got == GOOD, got)

    offload_module.subprocess.run = ssh_stub(returncode=1)
    check("nonzero exit -> None (fallback follows)",
          off._ssh_sha256("/srv/obs/f.mkv") is None)

    offload_module.subprocess.run = ssh_stub(stdout=b"not-a-hash junk\n")
    check("garbage output -> None, not a match",
          off._ssh_sha256("/srv/obs/f.mkv") is None)

    offload_module.subprocess.run = ssh_stub(stdout=(GOOD[:63] + "g").encode())
    check("non-hex digest -> None",
          off._ssh_sha256("/srv/obs/f.mkv") is None)

    offload_module.subprocess.run = ssh_stub(stdout=b"")
    check("empty output -> None", off._ssh_sha256("/srv/obs/f.mkv") is None)

    # BatchMode is part of the safety contract: no interactive prompts.
    captured = {}

    def capture_run(cmd, *a, **k):
        captured["cmd"] = cmd
        class R:
            returncode = 0
            stdout = f"{GOOD} *x".encode()
            stderr = b""
        return R()

    offload_module.subprocess.run = capture_run
    off._ssh_sha256("/srv/obs/My Game v1.0/final clip.mkv")
    cmd = captured.get("cmd") or []
    joined = " ".join(cmd)
    check("BatchMode + ConnectTimeout always set",
          "-o" in joined and "BatchMode=yes" in joined
          and "ConnectTimeout=8" in joined, joined)
    check("remote command is quoted sha256sum",
          any(a.startswith("sha256sum -b -- ") for a in cmd), cmd[-1:])
    check("spaces survive quoting",
          "'/srv/obs/My Game v1.0/final clip.mkv'" in joined, joined)

    # ---- the critical one: SSH failure degrades to LOCAL verify, not skip ----
    logs = []
    off_logs = Offloader(
        {"nas_offload_root": nas, "nas_offload_mode": "move",
         "nas_offload_ssh_host": "nas", "nas_offload_unix_root": "/srv/obs"},
        on_log=logs.append)
    src = os.path.join(work, "src.mkv")
    os.makedirs(os.path.dirname(src), exist_ok=True)
    with open(src, "wb") as f:
        f.write(os.urandom(64_000))
    dest_dir = os.path.join(nas, "Elden Ring")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, "src.mkv")
    with open(dest, "wb") as f:
        f.write(open(src, "rb").read())

    offload_module.subprocess.run = ssh_stub(returncode=255)   # ssh dead
    ok = off_logs._process({"path": src, "game": "Elden Ring"})
    check("dead ssh still verifies over SMB and finalizes",
          ok is True and not os.path.exists(src), f"ok={ok}")
    check("fallback is logged, not silent",
          any("falling back" in m.lower() for m in logs), logs[-3:] if logs else [])

    # A WRONG-but-valid ssh digest must keep the local file (move refused).
    offload_module.subprocess.run = ssh_stub(stdout=("b" * 64).encode())
    src2 = os.path.join(work, "src2.mkv")
    with open(src2, "wb") as f:
        f.write(os.urandom(32_000))
    ok2 = off_logs._process({"path": src2, "game": "Elden Ring"})
    check("wrong digest: move refused, local kept",
          ok2 is False and os.path.exists(src2) and
          not os.path.exists(os.path.join(dest_dir, "src2.mkv")),
          f"ok={ok2}")

    offload_module.subprocess.run = real_run

    passed_all = all(p for _, p, _ in results)
    for name, passed, detail in results:
        print(f"{'PASS' if passed else 'FAIL'}  {name:<46} {detail}")
    print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} "
          f"({len(results)} checks)")
    return 0 if passed_all else 1


if __name__ == "__main__":
    sys.exit(run())
