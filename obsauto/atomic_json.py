"""Write a JSON state file so a crash mid-write cannot truncate it.

``config.json`` and ``clip_index.json`` already did write-then-rename;
``offload_queue.json``, ``offload_state.json`` and ``games.json`` still did
``open(path, "w")`` + ``json.dump``. A power cut or a killed process in the
middle of that leaves an empty or half-written file, and every one of those
loaders swallowed the resulting ``ValueError`` - so the queue that gates
manual deletes came back empty, or every classification was forgotten,
with nothing in the log to say why.

Two rules, one place:

* **Never write the live file directly.** Serialise to ``<path>.tmp``, fsync,
  then ``os.replace`` - the reader sees the old file or the new one, never a
  fragment.
* **Never silently treat a corrupt or unreadable file as empty.** ``read_json``
  moves an unparseable file aside to ``<path>.corrupt`` and reports it, so the
  next save starts clean and a human can still recover what was there. A file
  that is present but cannot be read (locked, permissions) is not empty: that
  raises, so a caller cannot persist the default over the real queue.
"""

from __future__ import annotations

import json
import os


def write_json_atomic(path, payload, **dump_kwargs):
    """Serialise ``payload`` to ``path`` via a temp file and ``os.replace``.

    Raises ``OSError`` like a plain open/write would; callers decide whether
    that is fatal. The temp file is removed on failure so it cannot be
    mistaken for state later.
    """
    dump_kwargs.setdefault("indent", 2)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, **dump_kwargs)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_json(path, default, log=None, label=None):
    """Load ``path``; on corrupt JSON quarantine it and return ``default``.

    A missing file is the normal first-run case and returns ``default``
    quietly. An unparseable file is logged (via ``log``) and moved to
    ``<path>.corrupt`` so the next ``write_json_atomic`` does not keep
    re-failing on top of it. Any other ``OSError`` (locked, permissions)
    is logged and re-raised: the file is still there, and returning
    ``default`` is what let a locked offload queue get saved back as empty.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except ValueError as exc:
        name = label or os.path.basename(path)
        if log:
            log("[State] %s unreadable (%s) - moved aside as %s.corrupt"
                % (name, exc, os.path.basename(path)))
        try:
            os.replace(path, path + ".corrupt")
        except OSError:
            pass
        return default
    except OSError as exc:
        name = label or os.path.basename(path)
        if log:
            log("[State] %s could not be read (%s) - left in place, not "
                "treated as empty" % (name, exc))
        raise
