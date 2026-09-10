#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CyDrive Desktop Control Panel (Windows)
Minimal black & white UI + icon support.
Requires: pip install customtkinter
"""

import os
import sys
import time
import threading
import asyncio
import webbrowser
import queue
from typing import Optional

try:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
except ImportError:
    print("customtkinter is not installed. Run: pip install customtkinter")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from app import (
        CyDriveConfig,
        MetaDatabase,
        CacheManager,
        ProxyManager,
        ProxyInfo,
        TelegramSyncEngine,
        CyWebDAVServer,
        CyWebDashboard,
        WindowsMounter,
        DriveWatcher,
        CONFIG_FILE,
        DEFAULT_PROXY_FILE,
    )
except Exception as e:
    print(f"Failed to import backend from app.py: {e}")
    sys.exit(1)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

C = {
    "bg": "#0a0a0a",
    "card": "#111111",
    "card2": "#161616",
    "border": "#2a2a2a",
    "text": "#f0f0f0",
    "muted": "#888888",
    "accent": "#ffffff",
    "accent_dim": "#cccccc",
    "green": "#3ddc84",
    "red": "#ff4d4d",
}


def resource_path(relative: str) -> str:
    """Resolve resource for dev, cwd, and PyInstaller frozen builds."""
    candidates = []
    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, relative))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), relative))
    candidates.append(os.path.join(os.getcwd(), relative))
    if getattr(sys, "executable", None):
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), relative))
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0] if candidates else relative


class LogHandler:
    def __init__(self):
        self.q = queue.Queue()

    def write(self, msg: str):
        if msg and str(msg).strip():
            self.q.put(str(msg).rstrip())

    def flush(self):
        pass


class ProxyManagerWindow(ctk.CTkToplevel):
    """Manage / test / sort MTProto proxies with latency."""

    def __init__(self, master, proxy_file: str, api_id: int, api_hash: str, on_saved=None):
        super().__init__(master)
        self.title("Manage Proxies")
        self.geometry("720x520")
        self.minsize(640, 420)
        self.configure(fg_color=C["bg"])
        self.proxy_file = proxy_file or DEFAULT_PROXY_FILE
        self.api_id = api_id
        self.api_hash = api_hash
        self.on_saved = on_saved
        self.rows = []  # list of dict: proxy, latency_ms, status, raw
        self._testing = False
        self.pm = ProxyManager(proxy_file=self.proxy_file, timeout=6, enable=True)

        self.transient(master)
        try:
            self.grab_set()
        except Exception:
            pass

        self._build()
        self._reload_from_file()

    def _build(self):
        top = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=0, height=48)
        top.pack(fill="x")
        top.pack_propagate(False)
        ctk.CTkLabel(
            top, text="Manage Proxies",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=C["accent"],
        ).pack(side="left", padx=16, pady=10)
        self.lbl_count = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=12), text_color=C["muted"])
        self.lbl_count.pack(side="right", padx=16)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=10)

        # Add single
        add_row = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=10)
        add_row.pack(fill="x", pady=(0, 8))
        inner = ctk.CTkFrame(add_row, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(
            inner, text="Add proxy", font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).pack(anchor="w")
        line = ctk.CTkFrame(inner, fg_color="transparent")
        line.pack(fill="x", pady=(4, 0))
        self.entry_add = ctk.CTkEntry(
            line, height=36, fg_color=C["card2"], border_color=C["border"],
            text_color=C["text"], border_width=1,
            placeholder_text="host:port:secret  or  tg://proxy?server=...",
        )
        self.entry_add.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            line, text="Add", width=80, height=36, fg_color=C["accent"],
            hover_color=C["accent_dim"], text_color="#000",
            command=self._add_one,
        ).pack(side="left", padx=(8, 0))

        # Toolbar
        bar = ctk.CTkFrame(body, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 6))
        for text, cmd in [
            ("Import File", self._import_file),
            ("Test All", self._test_all),
            ("Sort by Ping", self._sort_by_ping),
            ("Remove Dead", self._remove_dead),
            ("Remove Selected", self._remove_selected),
            ("Save", self._save),
        ]:
            ctk.CTkButton(
                bar, text=text, height=32, width=110,
                fg_color="transparent", hover_color="#1a1a1a",
                border_width=1, border_color=C["border"], text_color=C["text"],
                font=ctk.CTkFont(size=11), command=cmd,
            ).pack(side="left", padx=(0, 6))

        # List header
        hdr = ctk.CTkFrame(body, fg_color=C["card2"], corner_radius=6, height=28)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="  Proxy", width=360, anchor="w",
                     font=ctk.CTkFont(size=11), text_color=C["muted"]).pack(side="left")
        ctk.CTkLabel(hdr, text="Ping", width=80, anchor="w",
                     font=ctk.CTkFont(size=11), text_color=C["muted"]).pack(side="left")
        ctk.CTkLabel(hdr, text="Status", width=100, anchor="w",
                     font=ctk.CTkFont(size=11), text_color=C["muted"]).pack(side="left")

        self.scroll = ctk.CTkScrollableFrame(body, fg_color=C["card"], corner_radius=10)
        self.scroll.pack(fill="both", expand=True, pady=(4, 0))

        self.lbl_status = ctk.CTkLabel(
            body, text="", font=ctk.CTkFont(size=11), text_color=C["muted"], anchor="w"
        )
        self.lbl_status.pack(fill="x", pady=(6, 0))

    def _set_status(self, text: str, color=None):
        self.lbl_status.configure(text=text, text_color=color or C["muted"])

    def _reload_from_file(self):
        self.pm.proxy_file = os.path.abspath(self.proxy_file)
        n = self.pm.load()
        self.rows = []
        for p in self.pm.proxies:
            self.rows.append({
                "proxy": p,
                "raw": p.raw or f"{p.host}:{p.port}:{p.secret or ''}",
                "latency_ms": None,
                "status": "—",
                "selected": False,
                "var": None,
                "frame": None,
            })
        self._render_list()
        self.lbl_count.configure(text=f"{n} proxy(ies)")
        self._set_status(f"Loaded {n} from {self.proxy_file}")

    def _render_list(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        for i, row in enumerate(self.rows):
            fr = ctk.CTkFrame(self.scroll, fg_color=C["card2"] if i % 2 == 0 else "transparent",
                              corner_radius=4, height=32)
            fr.pack(fill="x", pady=1)
            fr.pack_propagate(False)
            var = ctk.BooleanVar(value=bool(row.get("selected")))
            row["var"] = var
            row["frame"] = fr
            cb = ctk.CTkCheckBox(fr, text="", variable=var, width=24, checkbox_width=18,
                                 checkbox_height=18, command=lambda r=row, v=var: r.update({"selected": v.get()}))
            cb.pack(side="left", padx=(6, 0))
            p = row["proxy"]
            label = f"{p.host}:{p.port}"
            if p.secret:
                sec = p.secret
                if len(sec) > 10:
                    sec = sec[:6] + "…" + sec[-4:]
                label += f"  [{sec}]"
            ctk.CTkLabel(
                fr, text=label, width=340, anchor="w",
                font=ctk.CTkFont(family="Consolas", size=11), text_color=C["text"],
            ).pack(side="left")
            lat = row["latency_ms"]
            lat_txt = f"{lat:.0f} ms" if isinstance(lat, (int, float)) else "—"
            lat_color = C["green"] if isinstance(lat, (int, float)) and lat < 800 else (
                C["accent"] if isinstance(lat, (int, float)) else C["muted"]
            )
            ctk.CTkLabel(
                fr, text=lat_txt, width=80, anchor="w",
                font=ctk.CTkFont(size=11), text_color=lat_color,
            ).pack(side="left")
            st = row.get("status") or "—"
            st_color = C["green"] if st == "OK" else (C["red"] if st == "Fail" else C["muted"])
            ctk.CTkLabel(
                fr, text=st, width=80, anchor="w",
                font=ctk.CTkFont(size=11), text_color=st_color,
            ).pack(side="left")
        self.lbl_count.configure(text=f"{len(self.rows)} proxy(ies)")

    def _add_one(self):
        text = self.entry_add.get().strip()
        if not text:
            return
        p = self.pm._parse_line(text)
        if not p:
            self._set_status("Invalid proxy format", C["red"])
            return
        # dedupe
        raw = p.raw or text
        if any(r["raw"] == raw or (r["proxy"].host == p.host and r["proxy"].port == p.port and r["proxy"].secret == p.secret) for r in self.rows):
            self._set_status("Already in list", C["warn"] if "warn" in C else C["muted"])
            return
        self.rows.append({"proxy": p, "raw": raw, "latency_ms": None, "status": "—", "selected": False})
        self.entry_add.delete(0, "end")
        self._render_list()
        self._set_status(f"Added {p.display()}", C["green"])

    def _import_file(self):
        path = filedialog.askopenfilename(
            title="Import proxies",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
        )
        if not path:
            return
        added = 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    p = self.pm._parse_line(line)
                    if not p:
                        continue
                    raw = p.raw or line
                    if any(r["proxy"].host == p.host and r["proxy"].port == p.port and r["proxy"].secret == p.secret for r in self.rows):
                        continue
                    self.rows.append({"proxy": p, "raw": raw, "latency_ms": None, "status": "—", "selected": False})
                    added += 1
            self._render_list()
            self._set_status(f"Imported {added} proxy(ies)", C["green"])
        except Exception as e:
            self._set_status(f"Import failed: {e}", C["red"])

    def _remove_selected(self):
        before = len(self.rows)
        self.rows = [r for r in self.rows if not r.get("selected") and not (r.get("var") and r["var"].get())]
        self._render_list()
        self._set_status(f"Removed {before - len(self.rows)}")

    def _remove_dead(self):
        before = len(self.rows)
        self.rows = [r for r in self.rows if r.get("status") != "Fail"]
        self._render_list()
        self._set_status(f"Removed {before - len(self.rows)} dead")

    def _sort_by_ping(self):
        def key(r):
            lat = r.get("latency_ms")
            if lat is None:
                return 1e12
            return lat
        self.rows.sort(key=key)
        self._render_list()
        self._set_status("Sorted by ping (fastest first)")

    def _save(self):
        try:
            lines = [
                "# CyDrive Proxy List",
                "# Generated by Manage Proxies",
                "",
            ]
            for r in self.rows:
                p = r["proxy"]
                if p.raw and not p.raw.startswith("#"):
                    lines.append(p.raw)
                elif p.secret:
                    lines.append(f"{p.host}:{p.port}:{p.secret}")
                else:
                    lines.append(f"{p.host}:{p.port}")
            path = os.path.abspath(self.proxy_file)
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            self._set_status(f"Saved {len(self.rows)} → {path}", C["green"])
            if self.on_saved:
                try:
                    self.on_saved(path)
                except Exception:
                    pass
        except Exception as e:
            self._set_status(f"Save failed: {e}", C["red"])

    def _test_all(self):
        if self._testing:
            return
        if not self.rows:
            self._set_status("No proxies to test")
            return
        self._testing = True
        self._set_status("Testing…")

        def worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                for i, row in enumerate(list(self.rows)):
                    p = row["proxy"]
                    self.after(0, lambda i=i, p=p: self._set_status(
                        f"Testing {i+1}/{len(self.rows)} — {p.host}:{p.port}"
                    ))
                    t0 = time.perf_counter()
                    try:
                        ok = loop.run_until_complete(
                            self.pm.test_mtproto(p, self.api_id, self.api_hash)
                        )
                    except Exception:
                        ok = False
                    dt = (time.perf_counter() - t0) * 1000.0
                    row["latency_ms"] = dt if ok else None
                    row["status"] = "OK" if ok else "Fail"
                    self.after(0, self._render_list)
            finally:
                loop.close()
                self._testing = False
                ok_n = sum(1 for r in self.rows if r.get("status") == "OK")
                self.after(0, lambda: self._set_status(
                    f"Done — {ok_n}/{len(self.rows)} working", C["green"] if ok_n else C["red"]
                ))

        threading.Thread(target=worker, daemon=True).start()


class CyDriveGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CyDrive")
        self.geometry("880x640")
        self.minsize(780, 560)
        self.configure(fg_color=C["bg"])

        self._icon_path = None
        self._logo_image = None
        self._load_app_icon()

        self.running = False
        self.engine_thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.telegram_engine = None
        self.webdav = None
        self.dashboard = None
        self.watcher = None
        self._stop_event = threading.Event()
        self.log_handler = LogHandler()
        self.config = self._load_config()

        self._build_ui()
        self._load_fields_from_config()
        self.after(250, self._poll_logs)

        # redirect prints into the log panel (must be AFTER log_handler exists)
        sys.stdout = self.log_handler
        sys.stderr = self.log_handler

    def _load_app_icon(self):
        """Load icon.ico for window + header logo (robust for ico multi-size)."""
        names = ("icon.ico", "icon.png", "logo.png", "logo.ico")
        path = None
        for name in names:
            p = resource_path(name)
            if os.path.exists(p):
                path = p
                break
        if not path:
            return
        self._icon_path = path

        # Window taskbar / title-bar icon
        if path.lower().endswith(".ico"):
            try:
                self.iconbitmap(path)
            except Exception:
                pass

        # Header logo via Pillow
        try:
            from PIL import Image

            img = Image.open(path)
            # Multi-resolution .ico: pick the largest frame
            best = None
            best_area = 0
            try:
                n = getattr(img, "n_frames", 1) or 1
            except Exception:
                n = 1
            if n > 1:
                for i in range(n):
                    try:
                        img.seek(i)
                        frame = img.copy()
                        area = frame.size[0] * frame.size[1]
                        if area > best_area:
                            best_area = area
                            best = frame
                    except Exception:
                        continue
                img = best if best is not None else img
            img = img.convert("RGBA")
            try:
                resample = Image.Resampling.LANCZOS
            except Exception:
                resample = Image.LANCZOS
            img = img.resize((32, 32), resample)
            self._logo_image = ctk.CTkImage(light_image=img, dark_image=img, size=(32, 32))
        except Exception:
            self._logo_image = None

    def _load_config(self) -> CyDriveConfig:
        try:
            return CyDriveConfig.load(prompt_if_missing=False)
        except Exception:
            return CyDriveConfig(bot_token="", chat_id=0)

    def _load_fields_from_config(self):
        cfg = self.config
        for entry, val in [
            (self.entry_token, cfg.bot_token or ""),
            (self.entry_chat, str(cfg.chat_id or "")),
            (self.entry_proxy, cfg.proxy_file or DEFAULT_PROXY_FILE),
            (self.entry_drive, cfg.drive_letter or "Y:"),
        ]:
            entry.delete(0, "end")
            entry.insert(0, val)
        if cfg.enable_proxy:
            self.switch_proxy.select()
        else:
            self.switch_proxy.deselect()

    def _collect_config(self) -> Optional[CyDriveConfig]:
        token = self.entry_token.get().strip()
        chat = self.entry_chat.get().strip()
        proxy_file = self.entry_proxy.get().strip() or DEFAULT_PROXY_FILE
        drive = self.entry_drive.get().strip().upper() or "Y:"
        if not drive.endswith(":"):
            drive += ":"
        if not token:
            messagebox.showerror("Error", "Bot Token is required.")
            return None
        if not chat:
            messagebox.showerror("Error", "Chat ID is required.")
            return None
        try:
            chat_id = int(chat)
        except ValueError:
            chat_id = chat
        return CyDriveConfig(
            bot_token=token,
            chat_id=chat_id,
            drive_letter=drive,
            proxy_file=proxy_file,
            enable_proxy=bool(self.switch_proxy.get()),
            webdav_host="127.0.0.1",
            web_ui_host="127.0.0.1",
            auto_mount_drive=True,
        )

    def _save_config(self):
        cfg = self._collect_config()
        if not cfg:
            return
        try:
            cfg.save(CONFIG_FILE)
            self.config = cfg
            self._log("Config saved.")
            messagebox.showinfo("Saved", f"Saved to {CONFIG_FILE}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _build_ui(self):
        self._log_visible = True
        self._log_width = 320

        # Top bar — logo + title + status
        top = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=0, height=54)
        top.pack(fill="x")
        top.pack_propagate(False)

        brand = ctk.CTkFrame(top, fg_color="transparent")
        brand.pack(side="left", padx=14, pady=8)
        if self._logo_image is not None:
            ctk.CTkLabel(brand, text="", image=self._logo_image).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            brand,
            text="CyDrive",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=C["accent"],
        ).pack(side="left")

        self.lbl_status = ctk.CTkLabel(
            top, text="● Stopped", font=ctk.CTkFont(size=12, weight="bold"), text_color=C["muted"]
        )
        self.lbl_status.pack(side="right", padx=18)

        # Notification strip
        self.notif_bar = ctk.CTkLabel(
            self, text="", height=26, font=ctk.CTkFont(size=12),
            text_color=C["muted"], fg_color=C["card2"], corner_radius=0,
        )
        self.notif_bar.pack(fill="x")
        self._notify("Ready", C["muted"])

        # Body
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=14, pady=12)

        # LEFT — settings + controls
        left = ctk.CTkFrame(self.body, fg_color=C["card"], corner_radius=12)
        left.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            left, text="Settings", font=ctk.CTkFont(size=14, weight="bold"), text_color=C["text"]
        ).pack(anchor="w", padx=16, pady=(14, 6))

        form = ctk.CTkFrame(left, fg_color="transparent")
        form.pack(fill="x", padx=16)

        self._field(form, "Bot Token", "entry_token", show="*")
        self._field(form, "Chat / User ID", "entry_chat")
        self._field(form, "Drive Letter", "entry_drive", default="Y:")

        ctk.CTkLabel(
            form, text="Proxy File", font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).pack(anchor="w", pady=(10, 2))
        prow = ctk.CTkFrame(form, fg_color="transparent")
        prow.pack(fill="x")
        self.entry_proxy = ctk.CTkEntry(
            prow, height=34, fg_color=C["card2"], border_color=C["border"],
            text_color=C["text"], border_width=1,
        )
        self.entry_proxy.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            prow, text="...", width=40, height=34, fg_color=C["card2"],
            hover_color="#222", border_width=1, border_color=C["border"],
            text_color=C["text"], command=self._browse_proxy,
        ).pack(side="left", padx=(6, 0))

        self.switch_proxy = ctk.CTkSwitch(
            form, text="Enable Proxy", progress_color=C["accent"],
            button_color=C["accent"], button_hover_color=C["accent_dim"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
        )
        self.switch_proxy.pack(anchor="w", pady=(12, 2))
        self.switch_proxy.select()

        # Row 1: Start | Stop
        row1 = ctk.CTkFrame(left, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(12, 6))
        self.btn_start = ctk.CTkButton(
            row1, text="Start", height=40, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=C["accent"], hover_color=C["accent_dim"], text_color="#000000",
            command=self._on_start,
        )
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.btn_stop = ctk.CTkButton(
            row1, text="Stop", height=40, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", hover_color="#1a1a1a", border_width=1,
            border_color=C["border"], text_color=C["text"], state="disabled",
            command=self._on_stop,
        )
        self.btn_stop.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # Row 2: Web Panel | Save Config
        row2 = ctk.CTkFrame(left, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=4)
        ctk.CTkButton(
            row2, text="Open Web Panel", height=40, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", hover_color="#1a1a1a", border_width=1,
            border_color=C["border"], text_color=C["text"], command=self._open_web,
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(
            row2, text="Save Config", height=40, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", hover_color="#1a1a1a", border_width=1,
            border_color=C["border"], text_color=C["text"], command=self._save_config,
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))

        # Row 3: Test Proxies | Backup
        row3 = ctk.CTkFrame(left, fg_color="transparent")
        row3.pack(fill="x", padx=16, pady=4)
        ctk.CTkButton(
            row3, text="Manage Proxies", height=40, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", hover_color="#1a1a1a", border_width=1,
            border_color=C["border"], text_color=C["text"], command=self._open_proxy_manager,
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(
            row3, text="Backup Now", height=40, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", hover_color="#1a1a1a", border_width=1,
            border_color=C["border"], text_color=C["text"], command=self._backup_now,
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))

        # Row 4: Restore full width
        row4 = ctk.CTkFrame(left, fg_color="transparent")
        row4.pack(fill="x", padx=16, pady=(4, 14))
        ctk.CTkButton(
            row4, text="Restore Backup", height=40, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", hover_color="#1a1a1a", border_width=1,
            border_color=C["border"], text_color=C["text"], command=self._restore_backup,
        ).pack(fill="x")

        # RIGHT — status + collapsible log
        self.right = ctk.CTkFrame(self.body, fg_color=C["card"], corner_radius=12, width=self._log_width)
        self.right.pack(side="right", fill="both", padx=(10, 0))
        self.right.pack_propagate(False)

        # Status header
        ctk.CTkLabel(
            self.right, text="Status", font=ctk.CTkFont(size=14, weight="bold"), text_color=C["text"]
        ).pack(anchor="w", padx=14, pady=(14, 6))

        self.lbl_proxy = self._status_line(self.right, "Proxy")
        self.lbl_webui = self._status_line(self.right, "Web UI")
        self.lbl_webdav = self._status_line(self.right, "WebDAV")

        # Log header
        ctk.CTkLabel(
            self.right, text="Log", font=ctk.CTkFont(size=13, weight="bold"), text_color=C["text"]
        ).pack(anchor="w", padx=14, pady=(12, 4))

        self.log_box = ctk.CTkTextbox(
            self.right, fg_color="#0d0d0d", text_color="#d4d4d4",
            font=ctk.CTkFont(family="Consolas", size=12), corner_radius=8,
            border_width=1, border_color=C["border"],
        )
        self.log_box.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.log_box.configure(state="disabled")

        # Color tags for log lines (PowerShell-like)
        try:
            tb = self.log_box._textbox  # underlying tk Text
            tb.tag_configure("error", foreground="#ff5555")
            tb.tag_configure("success", foreground="#50fa7b")
            tb.tag_configure("warn", foreground="#f1fa8c")
            tb.tag_configure("info", foreground="#8be9fd")
            tb.tag_configure("proxy", foreground="#bd93f9")
            tb.tag_configure("default", foreground="#d4d4d4")
            tb.tag_configure("emoji", foreground="#ffb86c")
        except Exception:
            pass

        # Fixed-position log toggle (same place open or closed)
        self.btn_toggle_log = ctk.CTkButton(
            self, text="Log ›", width=64, height=24,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=C["card"], hover_color="#222",
            border_width=1, border_color=C["border"], text_color=C["text"],
            command=self._toggle_log,
        )
        self.btn_toggle_log.place(relx=1.0, rely=0.0, x=-10, y=62, anchor="ne")

    def _toggle_log(self):
        """Slide the right log/status panel in or out. Button stays in the same place."""
        if self._log_visible:
            self.right.pack_forget()
            self._log_visible = False
            self.btn_toggle_log.configure(text="‹ Log")
        else:
            self.right.pack(side="right", fill="both", padx=(10, 0))
            self.right.configure(width=self._log_width)
            self.right.pack_propagate(False)
            self._log_visible = True
            self.btn_toggle_log.configure(text="Log ›")
        # keep button fixed top-right
        self.btn_toggle_log.place(relx=1.0, rely=0.0, x=-10, y=62, anchor="ne")
        self.btn_toggle_log.lift()

    def _field(self, parent, label, attr, show=None, default=""):
        ctk.CTkLabel(
            parent, text=label, font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).pack(anchor="w", pady=(8, 2))
        e = ctk.CTkEntry(
            parent, height=34, fg_color=C["card2"], border_color=C["border"],
            text_color=C["text"], border_width=1, show=show or "",
        )
        e.pack(fill="x")
        if default:
            e.insert(0, default)
        setattr(self, attr, e)

    def _status_line(self, parent, title):
        lbl = ctk.CTkLabel(
            parent, text=f"{title}:  —", font=ctk.CTkFont(size=12),
            text_color=C["muted"], anchor="w",
        )
        lbl.pack(fill="x", padx=14, pady=1)
        return lbl

    def _browse_proxy(self):
        path = filedialog.askopenfilename(
            title="Select proxies.txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
        )
        if path:
            self.entry_proxy.delete(0, "end")
            self.entry_proxy.insert(0, path)

    def _notify(self, text: str, color: str = None):
        """Show status notification under the header."""
        color = color or C["muted"]
        try:
            self.notif_bar.configure(text=f"  {text}", text_color=color)
        except Exception:
            pass

    def _backup_now(self):
        """Zip config, DB, session, proxies into a backup folder."""
        import zipfile
        from datetime import datetime

        cfg = self._collect_config() or self.config
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(os.getcwd(), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        zip_path = os.path.join(backup_dir, f"cydrive_backup_{stamp}.zip")

        candidates = [
            CONFIG_FILE,
            getattr(cfg, "db_path", "cydrive_meta.db"),
            getattr(cfg, "proxy_file", DEFAULT_PROXY_FILE),
            "cynet_bot_session.session",
            "cynet_bot_session.session-journal",
            "proxies.txt",
        ]
        added = 0
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in candidates:
                    if p and os.path.exists(p) and os.path.isfile(p):
                        zf.write(p, arcname=os.path.basename(p))
                        added += 1
            self._log(f"Backup created: {zip_path} ({added} files)")
            self._notify(f"Backup saved → backups/", C["green"])
            messagebox.showinfo("Backup", f"Backup saved:\n{zip_path}\n\n{added} file(s)")
        except Exception as e:
            self._log(f"Backup failed: {e}")
            messagebox.showerror("Backup", str(e))

    def _restore_backup(self):
        """Restore config/db/proxies/session from a backup zip."""
        if self.running:
            messagebox.showwarning(
                "Restore",
                "Please Stop the engine before restoring a backup.",
            )
            return

        import zipfile

        path = filedialog.askopenfilename(
            title="Select backup zip",
            initialdir=os.path.join(os.getcwd(), "backups"),
            filetypes=[("Backup ZIP", "*.zip"), ("All files", "*.*")],
        )
        if not path:
            return

        if not messagebox.askyesno(
            "Restore",
            "This will overwrite current config / database / proxies / session.\n\nContinue?",
        ):
            return

        try:
            restored = []
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                for name in names:
                    base = os.path.basename(name)
                    if not base:
                        continue
                    # Only restore known safe files
                    allowed = {
                        "config.json",
                        "cydrive_meta.db",
                        "proxies.txt",
                        "cynet_bot_session.session",
                        "cynet_bot_session.session-journal",
                    }
                    # also allow custom db/proxy names from archive
                    if base in allowed or base.endswith(".db") or base.endswith(".txt") or base.endswith(".session") or base.endswith(".session-journal") or base == CONFIG_FILE:
                        target = os.path.join(os.getcwd(), base)
                        with zf.open(name) as src, open(target, "wb") as dst:
                            dst.write(src.read())
                        restored.append(base)

            self.config = self._load_config()
            self._load_fields_from_config()
            self._log(f"Restored from backup: {', '.join(restored) or 'nothing'}")
            self._notify("Backup restored. Review settings, then Start.", C["green"])
            messagebox.showinfo(
                "Restore",
                f"Restored {len(restored)} file(s):\n"
                + "\n".join(restored)
                + "\n\nCheck settings and press Start.",
            )
        except Exception as e:
            self._log(f"Restore failed: {e}")
            messagebox.showerror("Restore", str(e))

    def _log(self, msg: str):
        self.log_handler.write(msg)

    def _log_tag(self, msg: str) -> str:
        """Pick a color tag from message content (PowerShell-like)."""
        m = msg.lower()
        if any(k in m for k in ("error", "failed", "❌", "exception", "traceback", "locked")):
            return "error"
        if any(k in m for k in ("✅", "ok", "working", "connected", "running", "saved", "mounted", "success")):
            return "success"
        if any(k in m for k in ("⚠", "warning", "retry", "waiting", "disconnect")):
            return "warn"
        if any(k in m for k in ("proxy", "mtproto", "🛡️", "faketls")):
            return "proxy"
        if any(k in m for k in ("web ui", "webdav", "starting", "testing", "📡", "🌐", "✨", "🚀", "❤️")):
            return "info"
        return "default"

    def _poll_logs(self):
        try:
            while True:
                msg = self.log_handler.q.get_nowait()
                tag = self._log_tag(msg)
                self.log_box.configure(state="normal")
                try:
                    # Prefer underlying tk Text for reliable tags
                    tb = self.log_box._textbox
                    tb.insert("end", msg + "\n", tag)
                    tb.see("end")
                except Exception:
                    self.log_box.insert("end", msg + "\n")
                    self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(200, self._poll_logs)

    def _set_running_ui(self, running: bool, phase: str = None):
        self.running = running
        if running:
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            if phase == "connecting":
                self.lbl_status.configure(text="● Connecting…", text_color=C["accent"])
                self._notify("Connecting to Telegram…", C["accent"])
            else:
                self.lbl_status.configure(text="● Running", text_color=C["green"])
                self._notify("Connected and running", C["green"])
        else:
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            if phase == "disconnecting":
                self.lbl_status.configure(text="● Disconnecting…", text_color=C["accent"])
                self._notify("Disconnecting services…", C["accent"])
            else:
                self.lbl_status.configure(text="● Stopped", text_color=C["muted"])
                self._notify("Stopped", C["muted"])
                self.lbl_proxy.configure(text="Proxy:  —", text_color=C["muted"])
                self.lbl_webui.configure(text="Web UI:  —", text_color=C["muted"])
                self.lbl_webdav.configure(text="WebDAV:  —", text_color=C["muted"])

    def _on_start(self):
        if self.running:
            return
        # Wait for previous engine thread to fully exit
        if self.engine_thread and self.engine_thread.is_alive():
            self._log("Waiting for previous instance to exit...")
            self._stop_event.set()
            self.engine_thread.join(timeout=8)
            if self.engine_thread.is_alive():
                self._log("Previous instance still running. Try again in a few seconds.")
                return

        cfg = self._collect_config()
        if not cfg:
            return
        try:
            cfg.save(CONFIG_FILE)
            self.config = cfg
        except Exception as e:
            self._log(f"Config save warning: {e}")

        self._stop_event.clear()
        self._set_running_ui(True, phase="connecting")
        self._log("Starting engine...")
        self.engine_thread = threading.Thread(
            target=self._run_engine, args=(cfg,), daemon=True
        )
        self.engine_thread.start()

    def _on_stop(self):
        if not self.running and not (self.engine_thread and self.engine_thread.is_alive()):
            return
        self._log("Stopping...")
        self._set_running_ui(True, phase="disconnecting")
        self._stop_event.set()
        if self.engine_thread and self.engine_thread.is_alive():
            self.engine_thread.join(timeout=8)
        self._set_running_ui(False)
        self._log("Stopped.")

    def _open_web(self):
        port = getattr(self.config, "web_ui_port", 8088)
        url = f"http://127.0.0.1:{port}"
        webbrowser.open(url)
        self._log(f"Opened {url}")

    def _open_proxy_manager(self):
        cfg = self._collect_config() or self.config
        proxy_file = (self.entry_proxy.get().strip() if hasattr(self, "entry_proxy") else None) or getattr(cfg, "proxy_file", DEFAULT_PROXY_FILE)
        api_id = getattr(cfg, "api_id", 6)
        api_hash = getattr(cfg, "api_hash", "eb06d4abfb49dc3eeb1aeb98ae0f581e")

        def on_saved(path):
            self.entry_proxy.delete(0, "end")
            self.entry_proxy.insert(0, path)
            self._log(f"Proxy list updated: {path}")
            self._notify("Proxy list saved", C["green"])

        ProxyManagerWindow(self, proxy_file=proxy_file, api_id=api_id, api_hash=api_hash, on_saved=on_saved)

    def _test_proxies(self):
        cfg = self._collect_config()
        if not cfg:
            return

        def worker():
            self._log(f"Testing proxies: {cfg.proxy_file}")
            pm = ProxyManager(
                proxy_file=cfg.proxy_file,
                timeout=cfg.proxy_timeout,
                enable=True,
            )
            count = pm.load()
            self._log(f"Loaded {count} proxies")
            if count == 0:
                self._log("No proxies found.")
                return
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                working = loop.run_until_complete(
                    pm.find_working(cfg.api_id, cfg.api_hash)
                )
                if working:
                    self._log(f"Working: {working.display()}")
                else:
                    self._log("No working proxy found")
            finally:
                loop.close()

        threading.Thread(target=worker, daemon=True).start()

    def _run_engine(self, cfg: CyDriveConfig):
        try:
            db = MetaDatabase(cfg.db_path)
            cache_mgr = CacheManager(cfg.cache_path, cfg.cache_limit_gb)
            proxy_mgr = ProxyManager(
                proxy_file=cfg.proxy_file,
                timeout=cfg.proxy_timeout,
                enable=cfg.enable_proxy,
            )

            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            self.telegram_engine = TelegramSyncEngine(cfg, db, proxy_mgr)
            self.webdav = CyWebDAVServer(
                cfg.storage_path,
                cfg.webdav_host,
                cfg.webdav_port,
                db,
                cache_mgr,
                self.telegram_engine,
            )
            try:
                self.webdav.start(blocking=False)
            except OSError as e:
                self._log(f"WebDAV port busy: {e}")
                self._log("Close previous CyDrive or wait a few seconds, then retry.")
                return

            async def async_main():
                await self.telegram_engine.start()
                self.dashboard = CyWebDashboard(cfg, db, self.telegram_engine)
                await self.dashboard.start()

                proxy_txt = proxy_mgr.status_text()
                webui = f"http://127.0.0.1:{cfg.web_ui_port}"
                webdav_url = f"http://127.0.0.1:{cfg.webdav_port}"

                self.after(0, lambda: self.lbl_proxy.configure(
                    text=f"Proxy:  {proxy_txt}", text_color=C["green"]
                ))
                self.after(0, lambda: self.lbl_webui.configure(
                    text=f"Web UI:  {webui}", text_color=C["text"]
                ))
                self.after(0, lambda: self.lbl_webdav.configure(
                    text=f"WebDAV:  {webdav_url}", text_color=C["text"]
                ))

                self._log(f"Web UI  -> {webui}")
                self._log(f"WebDAV -> {webdav_url}")
                self._log(f"Proxy  -> {proxy_txt}")
                self._log("CyDrive is running.")
                self.after(0, lambda: self._set_running_ui(True, phase="running"))
                self.after(0, lambda: self._notify(
                    f"Connected via {proxy_txt}", C["green"]
                ))

                # Wait until stop requested
                while not self._stop_event.is_set():
                    await asyncio.sleep(0.3)

                # ---- clean shutdown inside the loop ----
                self._log("Shutting down services...")
                try:
                    if self.telegram_engine:
                        await self.telegram_engine.stop()
                except Exception as e:
                    self._log(f"Telegram stop: {e}")

                try:
                    if self.dashboard:
                        await self.dashboard.stop()
                except Exception as e:
                    self._log(f"Dashboard stop: {e}")

            if cfg.auto_mount_drive and WindowsMounter.is_windows():
                try:
                    WindowsMounter.optimize_webdav_registry()
                    ok, msg = WindowsMounter.mount_drive(
                        cfg.drive_letter,
                        f"http://{cfg.webdav_host}:{cfg.webdav_port}",
                    )
                    self._log(f"Mount: {msg}")
                except Exception as e:
                    self._log(f"Mount warning: {e}")

            self.watcher = DriveWatcher(
                cfg.storage_path,
                lambda path, rel: asyncio.run_coroutine_threadsafe(
                    self.telegram_engine.upload_file(path, rel), self.loop
                ),
            )
            self.watcher.start()

            try:
                self.loop.run_until_complete(async_main())
            except Exception as e:
                if "Event loop stopped" not in str(e):
                    raise

        except Exception as e:
            self._log(f"Engine error: {e}")
            import traceback
            self._log(traceback.format_exc())
        finally:
            # Always release ports / files
            try:
                if self.watcher:
                    self.watcher.stop()
            except Exception:
                pass
            try:
                if self.webdav:
                    self.webdav.stop()
            except Exception:
                pass
            try:
                if WindowsMounter.is_windows() and cfg:
                    WindowsMounter.unmount_drive(cfg.drive_letter)
            except Exception:
                pass
            try:
                if self.loop and not self.loop.is_closed():
                    self.loop.close()
            except Exception:
                pass
            self.loop = None
            self.telegram_engine = None
            self.webdav = None
            self.dashboard = None
            self.watcher = None
            self.after(0, lambda: self._set_running_ui(False))


def main():
    app = CyDriveGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
