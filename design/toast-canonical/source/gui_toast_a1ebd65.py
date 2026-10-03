# Frozen excerpt of obsauto/gui.py toast painter at commit a1ebd65.
# Nothing imports this. Live painter: obsauto/gui.py
# From _toast_pill_photo through _toast_animate_dust.

    def _toast_pill_photo(self, sw, sh, radius, chromakey=True):
        """Nebula crop + two-layer glass, masked to a capsule.

        When `chromakey` is True (Windows), outside the pill is TOAST_KEY so
        `-transparentcolor` can punch true rounded ends. Otherwise the outside
        stays fully transparent in the RGBA buffer and we composite onto the
        canvas ground colour — no green flash on Linux/mac.
        """
        key = tuple(int(dv.TOAST_KEY.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        surface = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))

        crop = (self.nebula.resize((sw, sh))
                if self.nebula.size != (sw, sh)
                else self.nebula.copy())
        if crop.mode != "RGBA":
            crop = crop.convert("RGBA")
        mask = Image.new("L", (sw, sh), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, sw - 1, sh - 1], radius=radius, fill=255)
        surface.paste(crop, (0, 0), mask)

        # No drawn stroke on the shell — chromakey + the pill mask already
        # silhouette the capsule; a border reads as a grey rectangular frame
        # once DWM composites the toplevel.
        shell = make_glass_tile(
            sw, sh, CARD_TINT, tint_alpha=210, radius=radius,
            border_hex=CARD_BORDER, border_alpha=0)
        surface = Image.alpha_composite(surface, shell)

        pad = self._S(dv.TOAST_PAD)
        core_w, core_h = max(1, sw - 2 * pad), max(1, sh - 2 * pad)
        core_r = max(1, radius - pad)
        core = make_glass_tile(
            core_w, core_h, CARD_CORE, tint_alpha=200, radius=core_r,
            border_hex=EDGE, border_alpha=0)
        layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        layer.paste(core, (pad, pad), core)
        surface = Image.alpha_composite(surface, layer)

        if chromakey:
            # Flatten: Tk chromakey needs opaque key pixels, not alpha zeros.
            flat = Image.new("RGB", (sw, sh), key)
            flat.paste(surface.convert("RGB"), mask=surface.split()[3])
            return to_photo(flat)
        return to_photo(surface)

    def _toast_build(self, prompt=False):
        w = self.TOAST_PROMPT_W if prompt else self.TOAST_W
        h = self.TOAST_PROMPT_H if prompt else self.TOAST_H
        sw, sh = self._S(w), self._S(h)
        radius = sh // 2          # capsule: full pill ends
        key = dv.TOAST_KEY

        popup = ctk.CTkToplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.attributes("-alpha", 0.0)
        try:
            popup.configure(fg_color=key)
        except Exception:
            pass

        left, top, right, bottom = self._toast_workarea()
        margin = self._S(dv.TOAST_MARGIN)
        x = right - sw - margin
        y_end = bottom - sh - margin
        popup.geometry(f"{sw}x{sh}+{x}+{y_end + self._S(dv.TOAST_IN_RISE)}")
        # Do NOT apply_rounded_corners here. DWM's rounded HWND draws a grey
        # rectangular silhouette around the chromakey pill — the outline we
        # want gone. The pill mask + transparentcolor is the silhouette.

        canvas = ScaledCanvas(
            tk.Canvas(popup, width=sw, height=sh, highlightthickness=0, bd=0,
                      bg=BASE_BG),
            self.scale)
        canvas.pack(fill="both", expand=True)
        # Chromakey only on Windows - elsewhere `-transparentcolor` is a no-op
        # and the key colour would show as a neon green fringe.
        keyed = sys.platform == "win32"
        if keyed:
            try:
                popup.configure(fg_color=key)
                canvas._c.configure(bg=key)
                popup.wm_attributes("-transparentcolor", key)
            except Exception:
                keyed = False
                try:
                    popup.configure(fg_color=BASE_BG)
                    canvas._c.configure(bg=BASE_BG)
                except Exception:
                    pass
            else:
                # Force sharp HWND corners so DWM doesn't stroke a frame.
                self._toast_donot_round(popup)
        else:
            try:
                popup.configure(fg_color=BASE_BG)
            except Exception:
                pass

        photo = self._toast_pill_photo(sw, sh, radius, chromakey=keyed)
        self._keep_image(photo)
        canvas.create_image(0, 0, anchor="nw", image=photo)

        # Single-row capsule: chip + title · game · detail.
        cy = h / 2 if not prompt else 30
        chip_r = 14
        chip_cx, chip_cy = 24, cy
        chip = canvas.create_oval(
            chip_cx - chip_r, chip_cy - chip_r,
            chip_cx + chip_r, chip_cy + chip_r,
            fill=ACCENT_TINT, outline="")
        icon = canvas.create_text(
            chip_cx, chip_cy, text="", fill=ACCENT, font=(ICON_FONT, -13))
        title = canvas.create_text(
            50, cy, anchor="w", text="", fill=TEXT, font=dv.font(14, 500))
        sep = canvas.create_text(
            50, cy, anchor="w", text="·", fill=FAINT, font=dv.font(14, 500),
            state="hidden")
        sub = canvas.create_text(
            50, cy, anchor="w", text="", fill=MUTED, font=dv.type_font("meta"))
        detail = canvas.create_text(
            50, cy, anchor="w", text="", fill=FAINT,
            font=dv.font(12, mono=True), state="hidden")

        # Soft Nebula dust near the chip - event-tint, motion on the tick.
        dust_items = []
        dust_base = []
        dust_home = []
        for dx, dy, r, alpha in dv.TOAST_DUST:
            d = canvas.create_oval(
                chip_cx + dx - r, chip_cy + dy - r,
                chip_cx + dx + r, chip_cy + dy + r,
                fill=dv.over(ACCENT, alpha, CARD_CORE), outline="",
                tags=("toast_dust",))
            dust_items.append(d)
            dust_base.append(alpha)
            dust_home.append((dx, dy, r))

        # Action chips (prompt toasts only). Hit-testing via tagged rects.
        btn_items = []
        if prompt:
            by = h - 40
            specs = [("Record", 16, 108), ("Not now", 132, 108)]
            for i, (label, bx, bw) in enumerate(specs):
                rect = canvas.create_rectangle(
                    bx, by, bx + bw, by + 26,
                    fill=ACCENT_TINT if i == 0 else EDGE, outline="",
                    tags=(f"toast_btn_{i}",))
                text = canvas.create_text(
                    bx + bw / 2, by + 13, text=label,
                    fill=TEXT if i == 0 else MUTED,
                    font=dv.font(12, 500), tags=(f"toast_btn_{i}",))
                btn_items.append({"rect": rect, "text": text, "tag": f"toast_btn_{i}"})

        # 2px drain, inset, left-anchored (spec: scaleX 1→0, origin left).
        track_x0, track_x1 = 18, w - 18
        bar_y = h - 7
        canvas.create_rectangle(
            track_x0, bar_y, track_x1, bar_y + dv.TOAST_DRAIN_H,
            fill=EDGE, outline="")
        drain = canvas.create_rectangle(
            track_x0, bar_y, track_x1, bar_y + dv.TOAST_DRAIN_H,
            fill=ACCENT, outline="")

        toast = {
            "popup": popup, "canvas": canvas, "chip": chip, "icon": icon,
            "title": title, "sep": sep, "sub": sub, "detail": detail,
            "drain": drain, "dust": dust_items, "dust_base": dust_base,
            "dust_home": dust_home, "dust_origin": (chip_cx, chip_cy),
            "dust_style": "drift", "dust_phase": [], "dust_speed": 1.0,
            "dust_amp": 1.0, "dust_t0": time.time(),
            "track": (track_x0, track_x1, bar_y), "geom": (sw, sh, x, y_end),
            "row_y": cy, "text_x": 50,
            "remaining": dv.TOAST_LIFE_MS, "life": dv.TOAST_LIFE_MS,
            "hovering": False, "ticking": False, "dismissing": False,
            "has_detail": False, "actions": [], "buttons": btn_items,
            "prompt": prompt, "on_timeout": None, "tint": ACCENT,
            "event": "start",
        }

        def on_enter(_e):
            toast["hovering"] = True          # "Hover freezes the drain"

        def on_leave(_e):
            toast["hovering"] = False

        def on_click(e):
            if toast.get("actions"):
                try:
                    items = canvas.find_overlapping(e.x, e.y, e.x, e.y)
                except Exception:
                    items = ()
                for i, btn in enumerate(toast["buttons"]):
                    tags = set()
                    for item in items:
                        tags.update(canvas.gettags(item))
                    if btn["tag"] in tags and i < len(toast["actions"]):
                        _label, callback = toast["actions"][i]
                        try:
                            callback()
                        except Exception as exc:
                            self._log(f"[Toast] Action failed: {exc}")
                        return
                return  # body click does nothing on prompt toasts
            self.show()                        # "Click anywhere focuses the window"

        canvas.bind("<Enter>", on_enter)
        canvas.bind("<Leave>", on_leave)
        canvas.bind("<Button-1>", on_click)

        self._toast_rise_in(toast)
        return toast

    def _toast_layout_row(self, toast):
        """Pack title · sub · detail on one baseline; ellipsize to the pill.

        Duration / size (detail) outranks the game name when space is tight —
        a stop toast that keeps "Helldivers 2" but drops "01:35 · 420 MB" is
        the wrong trade.
        """
        canvas = toast["canvas"]
        x = toast["text_x"]
        y = toast["row_y"]
        gap = 8
        detail_text = toast.get("detail_text") or ""
        # Keep text clear of the capsule's curved ends (radius ≈ H/2).
        w = self.TOAST_PROMPT_W if toast.get("prompt") else self.TOAST_W
        max_x = w - dv.TOAST_TEXT_INSET

        def _right(item):
            try:
                bbox = canvas.bbox(item)
                return (bbox[2] / self.scale) if bbox else x
            except Exception:
                return x

        def _width(item):
            try:
                bbox = canvas.bbox(item)
                if not bbox:
                    return 0.0
                return (bbox[2] - bbox[0]) / self.scale
            except Exception:
                return 0.0

        def _ellipsize(item, text, left, limit):
            """Trim from the end until the item's right edge is ≤ limit."""
            if not text:
                canvas.itemconfigure(item, text="", state="hidden")
                return
            candidate = text
            while True:
                shown = candidate if candidate == text else (candidate.rstrip() + "…")
                canvas.itemconfigure(item, text=shown, state="normal")
                canvas.coords(item, left, y)
                if _right(item) <= limit or len(candidate) <= 1:
                    if _right(item) > limit:
                        canvas.itemconfigure(item, text="", state="hidden")
                    return
                candidate = candidate[:-1]

        title_text = canvas.itemcget(toast["title"], "text") or ""
        sub_text = canvas.itemcget(toast["sub"], "text") or ""
        has_detail = bool(toast.get("has_detail") and detail_text)

        canvas.itemconfigure(toast["sep"], state="hidden")
        canvas.itemconfigure(toast["sub"], text="", state="hidden")
        canvas.itemconfigure(toast["detail"], text="", state="hidden")

        _ellipsize(toast["title"], title_text, x, max_x)
        tx = _right(toast["title"]) + gap
        if tx + 12 > max_x:
            return

        # Reserve room for the full detail string on the right when present.
        # Include the middot prefix we'll add when a sub is also shown.
        detail_w = 0.0
        detail_reserve = ""
        if has_detail:
            detail_reserve = (("·  " if sub_text else "") + detail_text)
            canvas.itemconfigure(toast["detail"], text=detail_reserve, state="normal")
            canvas.coords(toast["detail"], tx, y)
            detail_w = _width(toast["detail"])
            # If detail alone cannot fit after the title, drop the sub and
            # ellipsize detail against the remaining width.
            if tx + detail_w > max_x and not sub_text:
                _ellipsize(toast["detail"], detail_text, tx, max_x)
                return
            if tx + detail_w > max_x and sub_text:
                # Prefer full meta over any game name when they cannot coexist.
                sub_text = ""
                detail_reserve = detail_text
                canvas.itemconfigure(toast["detail"], text=detail_reserve)
                detail_w = _width(toast["detail"])
                if tx + detail_w > max_x:
                    _ellipsize(toast["detail"], detail_text, tx, max_x)
                    return

        if sub_text:
            canvas.itemconfigure(toast["sep"], state="normal")
            canvas.coords(toast["sep"], tx, y)
            tx = _right(toast["sep"]) + gap
            # Sub fills the middle; leave gap + detail_w for the trailing meta.
            sub_limit = max_x - ((detail_w + gap) if has_detail else 0)
            if tx < sub_limit:
                _ellipsize(toast["sub"], sub_text, tx, sub_limit)
                shown = canvas.itemcget(toast["sub"], "text") or ""
                # A 1–3 glyph stub ("He…") reads as broken — hide it instead.
                bare = shown.rstrip("…").strip()
                if canvas.itemcget(toast["sub"], "state") == "hidden" or len(bare) < 4:
                    canvas.itemconfigure(toast["sep"], state="hidden")
                    canvas.itemconfigure(toast["sub"], text="", state="hidden")
                    tx = _right(toast["title"]) + gap
                else:
                    tx = _right(toast["sub"]) + gap
            else:
                canvas.itemconfigure(toast["sep"], state="hidden")
                canvas.itemconfigure(toast["sub"], text="", state="hidden")
                tx = _right(toast["title"]) + gap
        else:
            canvas.itemconfigure(toast["sep"], state="hidden")

        if has_detail:
            shown_sub = canvas.itemcget(toast["sub"], "state") != "hidden" and (
                canvas.itemcget(toast["sub"], "text") or "")
            text = (("·  " if shown_sub else "") + detail_text)
            canvas.itemconfigure(toast["detail"], text=text, state="normal")
            if shown_sub:
                left = max(tx, max_x - _width(toast["detail"]))
                canvas.coords(toast["detail"], left, y)
                if _right(toast["detail"]) > max_x + 0.5:
                    # Sub ate the reservation — drop sub, keep full meta.
                    canvas.itemconfigure(toast["sep"], state="hidden")
                    canvas.itemconfigure(toast["sub"], text="", state="hidden")
                    tx = _right(toast["title"]) + gap
                    _ellipsize(toast["detail"], detail_text, tx, max_x)
            else:
                _ellipsize(toast["detail"], detail_text, tx, max_x)

    def _toast_apply(self, toast, content):
        canvas = toast["canvas"]
        tint = content["tint"]
        toast["tint"] = tint
        toast["event"] = content.get("event") or "start"
        canvas.itemconfigure(toast["chip"], fill=_tint_for(tint))
        canvas.itemconfigure(toast["icon"], text=content["glyph"], fill=tint)
        canvas.itemconfigure(toast["title"], text=content["title"])
        canvas.itemconfigure(toast["sub"], text=content["sub"] or "")
        toast["detail_text"] = content["detail"] or ""
        toast["has_detail"] = bool(toast["detail_text"])
        actions = content.get("actions") or []
        toast["actions"] = actions
        for i, btn in enumerate(toast.get("buttons") or []):
            label = actions[i][0] if i < len(actions) else ""
            state = "normal" if i < len(actions) else "hidden"
            canvas.itemconfigure(btn["text"], text=label, state=state)
            canvas.itemconfigure(btn["rect"], state=state)
        canvas.itemconfigure(toast["drain"], fill=tint)
        self._toast_layout_row(toast)
        self._toast_set_drain(toast, 1.0)
        self._toast_seed_dust(toast)
        self._toast_animate_dust(toast, force=True)
        # Re-assert topmost: another window may have been raised over it while
        # the toast sat idle between events.
        try:
            toast["popup"].attributes("-topmost", True)
        except Exception:
            pass

    def _toast_donot_round(self, window):
        """Tell DWM not to round this HWND — rounded preference paints a grey
        rectangular frame around a chromakey pill."""
        try:
            window.update_idletasks()
            hwnd = (ctypes.windll.user32.GetParent(window.winfo_id())
                    or window.winfo_id())
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWC_DONOTROUND = 1
            value = ctypes.c_int(DWMWC_DONOTROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

    def _toast_seed_dust(self, toast):
        """Fresh motion recipe each show: event flavour + random seed."""
        event = toast.get("event") or "start"
        style = dv.TOAST_DUST_STYLE.get(event, "drift")
        # Rare spice so a string of the same event isn't locked to one dance.
        if random.random() < 0.08:
            style = random.choice(tuple(set(dv.TOAST_DUST_STYLE.values())))
        n = len(toast.get("dust") or [])
        anchor = dv.TOAST_DUST_ANCHOR.get(style, "left")
        toast["dust_style"] = style
        toast["dust_anchor"] = anchor
        toast["dust_t0"] = time.time()
        # Quieter than the first busy pass, but still clearly alive.
        toast["dust_speed"] = random.uniform(0.7, 1.15)
        toast["dust_amp"] = random.uniform(0.65, 1.15)
        toast["dust_phase"] = [random.uniform(0, math.tau) for _ in range(n)]
        toast["dust_spin"] = [random.choice((-1.0, 1.0)) for _ in range(n)]
        # Soften at most one dot so the constellation stays readable.
        toast["dust_gain"] = [
            random.uniform(0.7, 0.9) if random.random() < 0.2 else 1.0
            for _ in range(n)
        ]
        w = self.TOAST_PROMPT_W if toast.get("prompt") else self.TOAST_W
        cy = toast.get("row_y") or (self.TOAST_H / 2)
        if anchor == "right":
            # Fan inward from the trailing end so dots stay inside the pill.
            toast["dust_origin"] = (w - 28, cy)
            toast["dust_mirror"] = -1.0
        else:
            toast["dust_origin"] = (24, cy)
            toast["dust_mirror"] = 1.0

    def _toast_animate_dust(self, toast, force=False):
        """Nebula dust — quieter motion, left or right by style.

        Toast is its own toplevel, so this never composites the dashboard.
        """
        dust = toast.get("dust") or []
        home = toast.get("dust_home") or []
        if not dust or len(home) != len(dust):
            return
        tint = toast.get("tint") or ACCENT
        ox, oy = toast.get("dust_origin") or (22, 28)
        mirror = float(toast.get("dust_mirror") or 1.0)
        style = toast.get("dust_style") or "drift"
        speed = float(toast.get("dust_speed") or 1.0)
        amp = float(toast.get("dust_amp") or 1.0)
        phases = toast.get("dust_phase") or [0.0] * len(dust)
        spins = toast.get("dust_spin") or [1.0] * len(dust)
        gains = toast.get("dust_gain") or [1.0] * len(dust)
        t = (time.time() - float(toast.get("dust_t0") or time.time())) * speed
        canvas = toast["canvas"]

        for i, item in enumerate(dust):
            dx0, dy0, r = home[i]
            dx0 = dx0 * mirror
            base = toast["dust_base"][i] * (gains[i] if i < len(gains) else 1.0)
            phase = phases[i] if i < len(phases) else i * 1.7
            spin = spins[i] if i < len(spins) else 1.0
            dist = math.hypot(dx0, dy0) or 1.0
            ux, uy = dx0 / dist, dy0 / dist

            if force:
                ox_i, oy_i = dx0, dy0
                wave = 0.9
            elif style == "burst":
                pulse = 0.5 + 0.5 * math.sin(t * 2.8 + phase)
                reach = (1.8 + 3.6 * pulse) * amp
                ox_i = dx0 + ux * reach
                oy_i = dy0 + uy * reach
                wave = 0.5 + 0.45 * pulse
            elif style == "sink":
                settle = min(1.0, t * 0.5)
                ox_i = dx0 * (1.0 - 0.28 * settle) + 1.0 * amp * math.sin(t + phase)
                oy_i = dy0 * (1.0 - 0.15 * settle) + settle * (2.8 * amp)
                wave = 0.65 - 0.2 * settle + 0.12 * math.sin(t * 1.2 + phase)
            elif style == "drift":
                ox_i = dx0 + amp * 3.0 * math.sin(t * 1.05 + phase)
                oy_i = dy0 + amp * 1.8 * math.sin(t * 0.7 + phase * 0.6)
                wave = 0.55 + 0.4 * (0.5 + 0.5 * math.sin(t * 1.7 + phase))
            elif style == "rise":
                lift = min(1.0, t * 0.7)
                ox_i = dx0 + amp * 1.2 * math.sin(t * 1.4 + phase)
                oy_i = dy0 - lift * (3.2 + 2.2 * amp) * (0.5 + 0.5 * math.sin(t + phase))
                wave = 0.5 + 0.45 * (0.4 + 0.6 * lift)
            elif style == "scatter":
                ox_i = dx0 + amp * 3.4 * math.sin(t * 4.0 * spin + phase)
                oy_i = dy0 + amp * 2.8 * math.cos(t * 3.2 * spin + phase * 1.3)
                wave = 0.4 + 0.5 * abs(math.sin(t * 4.5 + phase))
            else:  # orbit
                ang = phase + t * 1.15 * spin
                radius = dist * (0.88 + 0.18 * amp)
                ox_i = math.cos(ang) * radius
                oy_i = math.sin(ang) * radius * 0.72
                wave = 0.55 + 0.4 * (0.5 + 0.5 * math.sin(t * 1.5 + phase))

            alpha = max(0.08, min(0.95, base * wave))
            try:
                canvas.coords(
                    item,
                    ox + ox_i - r, oy + oy_i - r,
                    ox + ox_i + r, oy + oy_i + r)
                canvas.itemconfigure(item, fill=dv.over(tint, alpha, CARD_CORE))
            except Exception:
                pass

