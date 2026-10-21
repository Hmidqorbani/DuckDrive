#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Duck Drive Standalone - All-in-One Cloud Virtual Drive via Telegram
Developed by Hmidqorbani
Version 2.2 (Standalone) - Smart MTProto Proxy + FakeTLS + Health-Check
"""

import sys

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import os
import json
import time
import sqlite3
import hashlib
import threading
import asyncio
import subprocess
import shutil
import tempfile
import uuid
import mimetypes
import socket
import urllib.request
import re
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any, Callable, Tuple
import queue
import argparse
from urllib.parse import urlparse, parse_qs

# Third-party imports
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import print as rprint

    HAS_RICH = True
except ImportError:
    HAS_RICH = False

try:
    import winreg
except ImportError:
    winreg = None

try:
    from telethon import TelegramClient, events, Button
    from telethon.errors import (
        FloodWaitError,
        AccessTokenInvalidError,
        ApiIdInvalidError,
    )
    from telethon import connection as telethon_connection

    HAS_TELETHON = True
except ImportError:
    HAS_TELETHON = False
    telethon_connection = None
    Button = None

# Optional FakeTLS (ee secret) support for better Iran proxy compatibility
HAS_FAKETLS = False
ConnectionTcpMTProxyFakeTLS = None
try:
    import TelethonFakeTLS as _tftls
    ConnectionTcpMTProxyFakeTLS = getattr(
        _tftls, "ConnectionTcpMTProxyFakeTLS", None
    )
    if ConnectionTcpMTProxyFakeTLS is not None:
        HAS_FAKETLS = True
except ImportError:
    pass

try:
    from wsgidav.wsgidav_app import WsgiDAVApp
    from wsgidav.dav_provider import DAVProvider, DAVCollection, DAVNonCollection
    from wsgidav.dav_error import DAVError, HTTP_NOT_FOUND
    from cheroot import wsgi

    HAS_WSGIDAV = True
except ImportError:
    HAS_WSGIDAV = False

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    from aiohttp import web
    import aiohttp

    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

# ==================== CONSTANTS ====================
CONFIG_FILE = "config.json"
DEFAULT_STORAGE_DIR = os.path.abspath("./Telegram_Drive")
DEFAULT_CACHE_DIR = os.path.abspath("./Telegram_Cache")
DEFAULT_DB_FILE = os.path.abspath("./cydrive_meta.db")
DEFAULT_API_ID = 6
DEFAULT_API_HASH = "eb06d4abfb49dc3eeb1aeb98ae0f581e"
DEFAULT_PROXY_FILE = "proxies.txt"
CHUNK_BUFFER_SIZE = 10 * 1024 * 1024

# ==================== STATIC FILES (Embedded) ====================
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Duck Drive • Infinite Cloud Virtual Drive</title>
    <link rel="icon" type="image/jpeg" href="/static/img/logo.jpg">
    <link rel="stylesheet" href="/static/css/style.css">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body>
    <div class="background-glow"></div>
    <div class="app-container">
        <aside class="sidebar">
            <div class="brand">
                <div class="logo-box">
                    <img src="/static/img/logo.jpg" alt="DUCK Drive Logo" class="brand-logo-img">
                </div>
                <div class="brand-text">
                    <h2>DUCK Drive</h2>
                    <span>v2.2 • DUCK ENGINE</span>
                </div>
            </div>
            <nav class="nav-menu">
                <a href="#" class="nav-item active" onclick="filterType('all')"><i class="fa-solid fa-hard-drive"></i> Cloud Drive</a>
                <a href="#" class="nav-item" onclick="filterType('media')"><i class="fa-solid fa-photo-film"></i> Media Gallery</a>
                <a href="#" class="nav-item" onclick="filterType('documents')"><i class="fa-solid fa-file-lines"></i> Documents</a>
            </nav>
            <div class="storage-card">
                <div class="storage-header">
                    <span>Cloud Storage</span>
                    <span id="storage-percent">0%</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" id="storage-bar" style="width: 15%;"></div>
                </div>
                <p id="storage-detail">0 MB / Unlimited</p>
                <div class="drive-badge">
                    <i class="fa-brands fa-windows"></i> Mounted on <strong id="drive-letter">Y:</strong>
                </div>
                <div class="proxy-badge" id="proxy-status" style="margin-top:0.6rem; background:rgba(0,255,136,0.1); border:1px solid rgba(0,255,136,0.2); padding:0.4rem 0.6rem; border-radius:8px; font-size:0.75rem; color:#00ff88; text-align:center;">
                    <i class="fa-solid fa-shield"></i> Proxy: Checking...
                </div>
            </div>
        </aside>
        <main class="main-content">
            <header class="topbar">
                <div class="search-box">
                    <i class="fa-solid fa-magnifying-glass"></i>
                    <input type="text" id="search-input" placeholder="Search files, documents, videos in DUCK Drive...">
                </div>
                <div class="topbar-actions">
                    <button class="btn btn-primary" onclick="document.getElementById('file-upload').click()">
                        <i class="fa-solid fa-cloud-arrow-up"></i> Upload File
                    </button>
                    <input type="file" id="file-upload" style="display: none;" onchange="handleFileUpload(this)">
                    <button class="btn btn-icon" title="Refresh Drive" onclick="loadDriveData()"><i class="fa-solid fa-rotate"></i></button>
                </div>
            </header>
            <section class="stats-grid">
                <div class="stat-card">
                    <div class="stat-icon icon-blue"><i class="fa-solid fa-cloud"></i></div>
                    <div class="stat-info">
                        <h3 id="stat-total-files">0</h3>
                        <p>Total Files Stored</p>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon icon-purple"><i class="fa-solid fa-database"></i></div>
                    <div class="stat-info">
                        <h3 id="stat-total-size">0 MB</h3>
                        <p>Total Cloud Volume</p>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon icon-green"><i class="fa-solid fa-bolt"></i></div>
                    <div class="stat-info">
                        <h3>Active</h3>
                        <p>MTProto Telethon Sync</p>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon icon-cyan"><i class="fa-solid fa-network-wired"></i></div>
                    <div class="stat-info">
                        <h3>127.0.0.1:8080</h3>
                        <p>WebDAV Service</p>
                    </div>
                </div>
            </section>
            <section class="drop-zone" id="drop-zone">
                <i class="fa-solid fa-cloud-arrow-up drop-icon"></i>
                <h3>Drag & Drop Files Here</h3>
                <p>Instantly syncs to your Windows Drive & Telegram Cloud</p>
            </section>
            <section class="files-container">
                <div class="section-title">
                    <h3><i class="fa-solid fa-folder-open"></i> Cloud Files & Directories</h3>
                    <span id="file-count-label">0 items</span>
                </div>
                <div class="table-responsive">
                    <table class="files-table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Size</th>
                                <th>Status</th>
                                <th>Last Modified</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="files-tbody">
                            <tr>
                                <td colspan="5" class="loading-state">
                                    <i class="fa-solid fa-circle-notch fa-spin"></i> Loading DUCK Drive files...
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </section>
        </main>
    </div>
    <div id="media-modal" class="modal">
        <div class="modal-content">
            <button class="modal-close" onclick="closeModal()">&times;</button>
            <h3 id="modal-title">File Preview</h3>
            <div id="modal-body"></div>
        </div>
    </div>
    <script src="/static/js/app.js"></script>
</body>
</html>
"""

STYLE_CSS = """:root {
    --bg-main: #0b0e1a;
    --bg-card: rgba(18, 24, 38, 0.75);
    --bg-card-hover: rgba(28, 36, 56, 0.9);
    --border-color: rgba(255, 255, 255, 0.08);
    --accent-cyan: #00f3ff;
    --accent-purple: #7928ca;
    --accent-pink: #ff007f;
    --accent-green: #00ff88;
    --text-main: #e5e9f0;
    --text-muted: #8b9bb4;
    --font-main: 'Outfit', sans-serif;
    --font-mono: 'JetBrains Mono', monospace;
}
* { margin: 0; padding: 0; box-sizing: border-box; font-family: var(--font-main); }
body { background-color: var(--bg-main); color: var(--text-main); min-height: 100vh; overflow-x: hidden; position: relative; }
.background-glow { position: fixed; top: -20%; left: -10%; width: 60vw; height: 60vh; background: radial-gradient(circle, rgba(0,243,255,0.12) 0%, rgba(121,40,202,0.06) 60%, transparent 100%); filter: blur(90px); pointer-events: none; z-index: 0; }
.app-container { display: flex; min-height: 100vh; position: relative; z-index: 1; }
.sidebar { width: 280px; background: var(--bg-card); backdrop-filter: blur(20px); border-right: 1px solid var(--border-color); padding: 2rem 1.5rem; display: flex; flex-direction: column; }
.brand { display: flex; align-items: center; gap: 1rem; margin-bottom: 2.5rem; }
.logo-box { width: 48px; height: 48px; border-radius: 50%; overflow: hidden; display: flex; align-items: center; justify-content: center; border: 2px solid var(--accent-cyan); box-shadow: 0 0 20px rgba(0,243,255,0.45); background: #0b0e1a; flex-shrink: 0; transition: all 0.3s ease; }
.logo-box:hover { transform: scale(1.08); box-shadow: 0 0 28px rgba(0,243,255,0.7); }
.brand-logo-img { width: 100%; height: 100%; object-fit: cover; border-radius: 50%; }
.brand-text h2 { font-size: 1.3rem; font-weight: 800; letter-spacing: 0.5px; background: linear-gradient(to right, #00f3ff, #7928ca); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.brand-text span { font-size: 0.65rem; color: var(--accent-cyan); font-weight: 600; letter-spacing: 1.5px; }
.nav-menu { display: flex; flex-direction: column; gap: 0.5rem; flex-grow: 1; }
.nav-item { display: flex; align-items: center; gap: 0.9rem; padding: 0.8rem 1.1rem; color: var(--text-muted); text-decoration: none; font-size: 0.95rem; font-weight: 500; border-radius: 10px; transition: all 0.2s ease; }
.nav-item:hover, .nav-item.active { background: rgba(0,243,255,0.1); color: #00f3ff; border-left: 3px solid var(--accent-cyan); }
.storage-card { background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); padding: 1.2rem; border-radius: 14px; }
.storage-header { display: flex; justify-content: space-between; font-size: 0.85rem; font-weight: 600; margin-bottom: 0.6rem; }
.progress-bar { height: 6px; background: rgba(255,255,255,0.1); border-radius: 10px; overflow: hidden; margin-bottom: 0.6rem; }
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--accent-cyan), var(--accent-purple)); border-radius: 10px; }
.storage-card p { font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.8rem; }
.drive-badge { background: rgba(0,243,255,0.1); border: 1px solid rgba(0,243,255,0.2); padding: 0.4rem 0.6rem; border-radius: 8px; font-size: 0.8rem; color: var(--accent-cyan); text-align: center; }
.main-content { flex-grow: 1; padding: 2rem 2.5rem; display: flex; flex-direction: column; gap: 2rem; }
.topbar { display: flex; justify-content: space-between; align-items: center; gap: 1.5rem; }
.search-box { display: flex; align-items: center; gap: 0.8rem; background: var(--bg-card); border: 1px solid var(--border-color); padding: 0.8rem 1.2rem; border-radius: 12px; flex-grow: 1; max-width: 500px; }
.search-box input { background: transparent; border: none; outline: none; color: #e5e9f0; width: 100%; font-size: 0.95rem; }
.topbar-actions { display: flex; gap: 0.8rem; }
.btn { padding: 0.75rem 1.4rem; border-radius: 10px; font-size: 0.9rem; font-weight: 600; cursor: pointer; border: none; display: inline-flex; align-items: center; gap: 0.6rem; transition: all 0.2s ease; }
.btn-primary { background: linear-gradient(135deg, var(--accent-cyan), var(--accent-purple)); color: #fff; box-shadow: 0 0 15px rgba(0,243,255,0.3); }
.btn-primary:hover { transform: translateY(-2px); box-shadow: 0 0 25px rgba(0,243,255,0.5); }
.btn-icon { background: var(--bg-card); border: 1px solid var(--border-color); color: var(--text-main); padding: 0.75rem 1rem; }
.btn-icon:hover { background: var(--bg-card-hover); color: var(--accent-cyan); }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1.2rem; }
.stat-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 14px; padding: 1.2rem 1.5rem; display: flex; align-items: center; gap: 1.2rem; transition: all 0.2s ease; }
.stat-card:hover { border-color: rgba(0,243,255,0.3); transform: translateY(-3px); }
.stat-icon { width: 50px; height: 50px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.3rem; }
.icon-blue { background: rgba(0,243,255,0.15); color: var(--accent-cyan); }
.icon-purple { background: rgba(121,40,202,0.15); color: #7928ca; }
.icon-green { background: rgba(0,255,136,0.15); color: var(--accent-green); }
.icon-cyan { background: rgba(255,0,127,0.15); color: var(--accent-pink); }
.stat-info h3 { font-size: 1.4rem; font-weight: 700; }
.stat-info p { font-size: 0.8rem; color: var(--text-muted); }
.drop-zone { border: 2px dashed rgba(0,243,255,0.3); background: rgba(0,243,255,0.02); border-radius: 16px; padding: 2rem; text-align: center; cursor: pointer; transition: all 0.2s ease; }
.drop-zone:hover, .drop-zone.dragover { background: rgba(0,243,255,0.08); border-color: var(--accent-cyan); }
.drop-icon { font-size: 2.2rem; color: var(--accent-cyan); margin-bottom: 0.6rem; }
.files-container { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 16px; padding: 1.5rem; }
.section-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.2rem; }
.section-title h3 { font-size: 1.1rem; font-weight: 700; }
.section-title span { font-size: 0.85rem; color: var(--text-muted); }
.table-responsive { overflow-x: auto; }
.files-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
.files-table th { text-align: left; padding: 0.8rem 1rem; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border-color); }
.files-table td { padding: 0.9rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.03); }
.files-table tr:hover td { background: rgba(255,255,255,0.02); }
.file-name-cell { display: flex; align-items: center; gap: 0.8rem; font-weight: 500; }
.badge-status { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.25rem 0.6rem; border-radius: 6px; font-size: 0.75rem; font-weight: 600; }
.badge-synced { background: rgba(0,255,136,0.15); color: var(--accent-green); }
.badge-uploading { background: rgba(0,243,255,0.15); color: var(--accent-cyan); }
.action-btn { background: transparent; border: none; color: var(--text-muted); cursor: pointer; margin-right: 0.5rem; font-size: 1rem; transition: all 0.2s ease; padding: 0.3rem 0.5rem; border-radius: 6px; }
.action-btn:hover { color: var(--accent-cyan); background: rgba(0,243,255,0.1); }
.action-btn.btn-delete:hover { color: #ff3366; background: rgba(255,51,102,0.15); }
.modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); backdrop-filter: blur(10px); z-index: 100; align-items: center; justify-content: center; }
.modal-content { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 16px; padding: 2rem; max-width: 700px; width: 90%; position: relative; }
.modal-close { position: absolute; top: 1rem; right: 1.5rem; background: transparent; border: none; color: var(--text-muted); font-size: 1.5rem; cursor: pointer; }
"""

APP_JS = """let allFiles = [];
let currentFilter = 'all';
document.addEventListener("DOMContentLoaded", () => {
    loadDriveData();
    setupDropZone();
    setupSearch();
    setInterval(loadDriveData, 4000);
});
async function loadDriveData() {
    try {
        const [statsRes, filesRes] = await Promise.all([
            fetch("/api/stats"),
            fetch("/api/files")
        ]);
        if (statsRes.ok) {
            const stats = await statsRes.json();
            updateStatsUI(stats);
        }
        if (filesRes.ok) {
            allFiles = await filesRes.json();
            applyCurrentFilter();
        }
    } catch (err) {
        console.error("Error loading drive data:", err);
    }
}
function updateStatsUI(stats) {
    const totalFilesEl = document.getElementById("stat-total-files");
    if (totalFilesEl) totalFilesEl.innerText = stats.total_files || 0;
    const bytes = stats.total_bytes || 0;
    const mb = (bytes / (1024 * 1024)).toFixed(1);
    const gb = (bytes / (1024 * 1024 * 1024)).toFixed(2);
    const sizeStr = bytes > (1024 * 1024 * 1024) ? `${gb} GB` : `${mb} MB`;
    const sizeEl = document.getElementById("stat-total-size");
    if (sizeEl) sizeEl.innerText = sizeStr;
    const storageDetailEl = document.getElementById("storage-detail");
    if (storageDetailEl) storageDetailEl.innerText = `${sizeStr} / Unlimited`;
    const storageBar = document.getElementById("storage-bar");
    const storagePercent = document.getElementById("storage-percent");
    if (storageBar && storagePercent) {
        const pct = Math.min(100, Math.max(3, Math.round((bytes / (100 * 1024 * 1024 * 1024)) * 100)));
        storageBar.style.width = `${pct}%`;
        storagePercent.innerText = `${pct}%`;
    }
    if (stats.drive_letter) {
        const letterEl = document.getElementById("drive-letter");
        if (letterEl) letterEl.innerText = stats.drive_letter;
    }
    const proxyEl = document.getElementById("proxy-status");
    if (proxyEl && stats.proxy_info) {
        proxyEl.innerHTML = `<i class="fa-solid fa-shield"></i> Proxy: ${stats.proxy_info}`;
    }
}
function filterType(type) {
    currentFilter = type;
    document.querySelectorAll(".nav-menu .nav-item").forEach(item => item.classList.remove("active"));
    const eventTarget = window.event ? window.event.currentTarget : null;
    if (eventTarget) eventTarget.classList.add("active");
    applyCurrentFilter();
}
function applyCurrentFilter() {
    let filtered = allFiles;
    if (currentFilter === 'media') {
        filtered = allFiles.filter(f => isMedia(f.name));
    } else if (currentFilter === 'documents') {
        filtered = allFiles.filter(f => isDocument(f.name));
    }
    const searchInput = document.getElementById("search-input");
    if (searchInput && searchInput.value.trim()) {
        const q = searchInput.value.toLowerCase().trim();
        filtered = filtered.filter(f => f.name.toLowerCase().includes(q));
    }
    renderFilesTable(filtered);
}
function renderFilesTable(files) {
    const tbody = document.getElementById("files-tbody");
    const countLabel = document.getElementById("file-count-label");
    if (countLabel) countLabel.innerText = `${files.length} items`;
    if (!files || files.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 3rem;">
            <i class="fa-solid fa-folder-open" style="font-size: 2.2rem; margin-bottom: 0.8rem; display: block; color: var(--accent-cyan); opacity: 0.6;"></i>
            No files found. Drag and drop files above to sync to Telegram Cloud!
        </td></tr>`;
        return;
    }
    tbody.innerHTML = files.map(file => {
        const icon = getFileIcon(file.name, file.is_dir);
        const sizeStr = file.is_dir ? "-" : formatBytes(file.size);
        const dateStr = file.mtime ? new Date(file.mtime * 1000).toLocaleDateString() : "-";
        const statusBadge = file.is_uploaded
            ? '<span class="badge-status badge-synced"><i class="fa-solid fa-circle-check"></i> Synced</span>'
            : '<span class="badge-status badge-uploading"><i class="fa-solid fa-rotate fa-spin"></i> Syncing</span>';
        const isDir = Boolean(file.is_dir);
        const encName = encodeURIComponent(file.name);
        return `<tr>
            <td><div class="file-name-cell">${icon}<span title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span></div></td>
            <td>${sizeStr}</td>
            <td>${statusBadge}</td>
            <td>${dateStr}</td>
            <td>
                ${!isDir ? `<a href="/api/download/${encName}" class="action-btn" title="Download"><i class="fa-solid fa-download"></i></a>` : ''}
                ${!isDir && isMedia(file.name) ? `<button class="action-btn" title="Stream Online" onclick="previewMedia('${encName}')"><i class="fa-solid fa-play"></i></button>` : ''}
                <button class="action-btn" title="Share" onclick="shareFile('${encName}')"><i class="fa-solid fa-share-nodes"></i></button>
                <button class="action-btn btn-delete" title="Delete" onclick="deleteFile('${encName}')"><i class="fa-solid fa-trash-can"></i></button>
            </td>
        </tr>`;
    }).join("");
}
function getFileIcon(name, isDir) {
    if (isDir) return '<i class="fa-solid fa-folder" style="color: #ffd166; font-size: 1.2rem;"></i>';
    const ext = name.split('.').pop().toLowerCase();
    if (['jpg','jpeg','png','gif','webp','svg','bmp'].includes(ext)) return '<i class="fa-solid fa-file-image" style="color: #00f3ff; font-size: 1.2rem;"></i>';
    if (['mp4','mkv','avi','mov','webm'].includes(ext)) return '<i class="fa-solid fa-file-video" style="color: #ff007f; font-size: 1.2rem;"></i>';
    if (['mp3','wav','flac','ogg','m4a'].includes(ext)) return '<i class="fa-solid fa-file-audio" style="color: #c084fc; font-size: 1.2rem;"></i>';
    if (['zip','rar','7z','tar','gz','bz2'].includes(ext)) return '<i class="fa-solid fa-file-zipper" style="color: #f77f00; font-size: 1.2rem;"></i>';
    if (['pdf','doc','docx','txt','csv','xlsx','pptx','json','py','js','html','css'].includes(ext)) return '<i class="fa-solid fa-file-lines" style="color: #00ff88; font-size: 1.2rem;"></i>';
    return '<i class="fa-solid fa-file" style="color: #8b9bb4; font-size: 1.2rem;"></i>';
}
function isMedia(name) {
    const ext = name.split('.').pop().toLowerCase();
    return ['mp4','webm','mkv','avi','mp3','wav','flac','ogg','jpg','jpeg','png','gif','webp','svg'].includes(ext);
}
function isDocument(name) {
    const ext = name.split('.').pop().toLowerCase();
    return ['pdf','doc','docx','txt','md','csv','xlsx','pptx','json','xml','py','js','html','css','sql','sh'].includes(ext);
}
function previewMedia(fileName) {
    const decoded = decodeURIComponent(fileName);
    const ext = decoded.split('.').pop().toLowerCase();
    const modal = document.getElementById("media-modal");
    const modalTitle = document.getElementById("modal-title");
    const modalBody = document.getElementById("modal-body");
    modalTitle.innerText = decoded;
    const url = `/api/download/${fileName}`;
    if (['mp4','webm','mkv','avi'].includes(ext)) {
        modalBody.innerHTML = `<video controls autoplay style="width:100%; border-radius:10px;"><source src="${url}"></video>`;
    } else if (['mp3','wav','flac','ogg'].includes(ext)) {
        modalBody.innerHTML = `<audio controls autoplay style="width:100%; margin-top:1.5rem;"><source src="${url}"></audio>`;
    } else {
        modalBody.innerHTML = `<img src="${url}" style="max-width:100%; max-height:520px; border-radius:10px; display:block; margin:0 auto;">`;
    }
    modal.style.display = "flex";
}
function closeModal() {
    const modal = document.getElementById("media-modal");
    if (modal) {
        document.getElementById("modal-body").innerHTML = "";
        modal.style.display = "none";
    }
}
async function shareFile(encodedName) {
    const fileName = decodeURIComponent(encodedName);
    try {
        const res = await fetch("/api/share", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: fileName })
        });
        if (res.ok) {
            const data = await res.json();
            alert(`Share Link:\\n${data.share_url}`);
        } else {
            alert("Failed to generate share link.");
        }
    } catch (err) {
        console.error(err);
    }
}
async function deleteFile(encodedName) {
    const fileName = decodeURIComponent(encodedName);
    if (!confirm(`Are you sure you want to delete "${fileName}" from DUCK Drive?`)) return;
    try {
        const res = await fetch("/api/delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: fileName })
        });
        if (res.ok) loadDriveData();
        else alert("Could not delete file.");
    } catch (err) {
        console.error(err);
    }
}
function setupSearch() {
    const searchInput = document.getElementById("search-input");
    if (searchInput) searchInput.addEventListener("input", applyCurrentFilter);
}
function setupDropZone() {
    const dropZone = document.getElementById("drop-zone");
    if (!dropZone) return;
    ['dragenter','dragover'].forEach(name => {
        dropZone.addEventListener(name, e => { e.preventDefault(); dropZone.classList.add('dragover'); });
    });
    ['dragleave','drop'].forEach(name => {
        dropZone.addEventListener(name, e => { e.preventDefault(); dropZone.classList.remove('dragover'); });
    });
    dropZone.addEventListener('drop', e => {
        const files = e.dataTransfer.files;
        if (files.length > 0) uploadFiles(files);
    });
    dropZone.addEventListener('click', () => document.getElementById('file-upload').click());
}
function handleFileUpload(input) {
    if (input.files.length > 0) uploadFiles(input.files);
}
async function uploadFiles(files) {
    for (const file of files) {
        const formData = new FormData();
        formData.append("file", file);
        try {
            await fetch("/api/upload", { method: "POST", body: formData });
        } catch (err) {
            console.error("Upload error:", err);
        }
    }
    loadDriveData();
}
function formatBytes(bytes, decimals=2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes','KB','MB','GB','TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}
function escapeHtml(text) {
    return text.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
"""

# Logo as Base64 (minimal 1x1 transparent pixel to avoid missing image)
LOGO_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


# ==================== UTILITY FUNCTIONS ====================
def get_display_ip(host: str = "127.0.0.1") -> str:
    if host and host not in ("0.0.0.0", "::"):
        return host
    for service in [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ]:
        try:
            req = urllib.request.Request(service, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                ip = resp.read().decode("utf-8").strip()
                if ip and len(ip.split(".")) == 4:
                    return ip
        except Exception:
            continue
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ==================== PROXY MANAGER ====================
@dataclass
class ProxyInfo:
    host: str
    port: int
    secret: Optional[str] = None
    proxy_type: str = "mtproto"  # mtproto | socks5 | http
    username: Optional[str] = None
    password: Optional[str] = None
    raw: str = ""

    def display(self) -> str:
        if self.proxy_type == "mtproto":
            return f"MTProto {self.host}:{self.port}"
        return f"{self.proxy_type.upper()} {self.host}:{self.port}"


class ProxyManager:
    """
    Smart MTProto / SOCKS5 proxy manager with auto-select and fallback.
    """

    def __init__(
        self,
        proxy_file: str = DEFAULT_PROXY_FILE,
        timeout: float = 5.0,
        enable: bool = True,
    ):
        self.proxy_file = os.path.abspath(proxy_file)
        self.timeout = timeout
        self.enable = enable
        self.proxies: List[ProxyInfo] = []
        self.current: Optional[ProxyInfo] = None
        self.last_good: Optional[ProxyInfo] = None
        self._lock = threading.Lock()

    def load(self) -> int:
        self.proxies = []
        if not self.enable:
            return 0
        if not os.path.exists(self.proxy_file):
            # Create empty sample file
            sample = (
                "# DUCK Drive Proxy List\n"
                "# One proxy per line. Supported formats:\n"
                "# host:port:secret\n"
                "# tg://proxy?server=HOST&port=PORT&secret=SECRET\n"
                "# https://t.me/proxy?server=HOST&port=PORT&secret=SECRET\n"
                "# socks5://user:pass@host:port\n"
                "# socks5://host:port\n"
                "\n"
            )
            try:
                with open(self.proxy_file, "w", encoding="utf-8") as f:
                    f.write(sample)
            except Exception:
                pass
            return 0

        try:
            with open(self.proxy_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    p = self._parse_line(line)
                    if p:
                        self.proxies.append(p)
        except Exception as e:
            print(f"⚠️ Failed to load proxies: {e}")
        return len(self.proxies)

    def _parse_line(self, line: str) -> Optional[ProxyInfo]:
        line = line.strip()
        # tg:// or t.me links
        if "tg://proxy" in line or "t.me/proxy" in line or "telegram.me/proxy" in line:
            try:
                # Normalize
                if line.startswith("tg://"):
                    qs = line.split("?", 1)[1] if "?" in line else ""
                else:
                    parsed = urlparse(line)
                    qs = parsed.query
                params = parse_qs(qs)
                server = (params.get("server") or params.get("host") or [None])[0]
                port = (params.get("port") or [None])[0]
                secret = (params.get("secret") or [None])[0]
                if server and port and secret:
                    return ProxyInfo(
                        host=server.strip(),
                        port=int(port),
                        secret=secret.strip(),
                        proxy_type="mtproto",
                        raw=line,
                    )
            except Exception:
                return None

        # socks5:// or http://
        if line.lower().startswith(("socks5://", "socks4://", "http://", "https://")):
            try:
                parsed = urlparse(line)
                host = parsed.hostname
                port = parsed.port or (1080 if "socks" in parsed.scheme else 8080)
                username = parsed.username
                password = parsed.password
                ptype = "socks5" if "socks" in parsed.scheme else "http"
                if host:
                    return ProxyInfo(
                        host=host,
                        port=int(port),
                        proxy_type=ptype,
                        username=username,
                        password=password,
                        raw=line,
                    )
            except Exception:
                return None

        # host:port:secret  or  host:port
        parts = line.split(":")
        if len(parts) >= 3:
            host, port, secret = parts[0], parts[1], ":".join(parts[2:])
            try:
                return ProxyInfo(
                    host=host.strip(),
                    port=int(port),
                    secret=secret.strip(),
                    proxy_type="mtproto",
                    raw=line,
                )
            except Exception:
                return None
        elif len(parts) == 2:
            host, port = parts
            try:
                return ProxyInfo(
                    host=host.strip(),
                    port=int(port),
                    proxy_type="socks5",
                    raw=line,
                )
            except Exception:
                return None
        return None

    def _pick_connection_class(self, secret: Optional[str]):
        """Choose the best connection class based on secret type."""
        secret = (secret or "").strip().lower()
        if secret.startswith("ee") and HAS_FAKETLS and ConnectionTcpMTProxyFakeTLS:
            return ConnectionTcpMTProxyFakeTLS
        # Default: works best with dd and plain secrets
        return telethon_connection.ConnectionTcpMTProxyRandomizedIntermediate

    def _normalize_secret(self, secret: Optional[str]) -> str:
        """Normalize secret for Telethon / FakeTLS."""
        if not secret:
            return "00000000000000000000000000000000"
        s = secret.strip()
        # TelethonFakeTLS often wants the ee prefix removed for its connection class
        # but stock Telethon expects the full secret. We keep original for stock,
        # and strip only when using FakeTLS class.
        return s

    async def test_mtproto(self, proxy: ProxyInfo, api_id: int, api_hash: str) -> bool:
        """Quick connection test for an MTProto proxy (supports ee FakeTLS when available)."""
        if not HAS_TELETHON:
            return False
        secret = self._normalize_secret(proxy.secret)
        conn_cls = self._pick_connection_class(secret)

        # For FakeTLS library, secret is often passed without leading "ee"
        proxy_secret = secret
        if conn_cls is ConnectionTcpMTProxyFakeTLS and secret.lower().startswith("ee"):
            # TelethonFakeTLS docs: remove "ee" from hex secret
            proxy_secret = secret[2:]

        safe_host = proxy.host.replace(".", "_").replace("-", "_")[:40]
        session_name = f"proxy_test_{safe_host}_{proxy.port}"
        client = None
        try:
            client = TelegramClient(
                session_name,
                api_id,
                api_hash,
                connection=conn_cls,
                proxy=(proxy.host, proxy.port, proxy_secret),
                timeout=self.timeout,
                connection_retries=1,
                retry_delay=0,
                auto_reconnect=False,
            )
            await asyncio.wait_for(client.connect(), timeout=self.timeout + 2)
            if client.is_connected():
                return True
        except Exception:
            return False
        finally:
            try:
                if client:
                    await client.disconnect()
            except Exception:
                pass
            for ext in ("", ".session", ".session-journal"):
                try:
                    p = session_name + ext
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
        return False

    async def find_working(
        self, api_id: int, api_hash: str, prefer_last: bool = True
    ) -> Optional[ProxyInfo]:
        if not self.enable or not self.proxies:
            return None

        candidates = list(self.proxies)
        if prefer_last and self.last_good:
            candidates = [self.last_good] + [
                p for p in candidates if p.raw != self.last_good.raw
            ]

        # Prefer dd / plain secrets first when FakeTLS is not available
        if not HAS_FAKETLS:
            def sort_key(p: ProxyInfo):
                s = (p.secret or "").lower()
                if s.startswith("ee"):
                    return 2
                if s.startswith("dd"):
                    return 0
                return 1
            candidates = sorted(candidates, key=sort_key)

        print(f"🔍 Testing {len(candidates)} proxy(ies)...")
        if any((p.secret or "").lower().startswith("ee") for p in candidates):
            if HAS_FAKETLS:
                print("   ℹ️ FakeTLS (ee) support: enabled")
            else:
                print("   ⚠️ FakeTLS (ee) support: disabled (pip install TelethonFakeTLS)")

        for idx, proxy in enumerate(candidates, 1):
            print(f"   [{idx}/{len(candidates)}] Trying {proxy.display()} ...", end=" ", flush=True)
            ok = False
            if proxy.proxy_type == "mtproto":
                ok = await self.test_mtproto(proxy, api_id, api_hash)
            else:
                try:
                    fut = asyncio.open_connection(proxy.host, proxy.port)
                    reader, writer = await asyncio.wait_for(fut, timeout=self.timeout)
                    writer.close()
                    await writer.wait_closed()
                    ok = True
                except Exception:
                    ok = False

            if ok:
                print("✅ OK")
                with self._lock:
                    self.current = proxy
                    self.last_good = proxy
                return proxy
            else:
                print("❌ Failed")
        print("⚠️ No working proxy found. Will try direct connection.")
        with self._lock:
            self.current = None
        return None

    def get_telethon_kwargs(self) -> Dict[str, Any]:
        """Return kwargs to pass to TelegramClient constructor."""
        if not self.current:
            return {}
        p = self.current
        if p.proxy_type == "mtproto":
            secret = self._normalize_secret(p.secret)
            conn_cls = self._pick_connection_class(secret)
            proxy_secret = secret
            if conn_cls is ConnectionTcpMTProxyFakeTLS and secret.lower().startswith("ee"):
                proxy_secret = secret[2:]
            return {
                "connection": conn_cls,
                "proxy": (p.host, p.port, proxy_secret),
            }
        # SOCKS5 / HTTP (requires python-socks)
        proxy_dict = {
            "proxy_type": p.proxy_type,
            "addr": p.host,
            "port": p.port,
            "rdns": True,
        }
        if p.username:
            proxy_dict["username"] = p.username
        if p.password:
            proxy_dict["password"] = p.password
        return {"proxy": proxy_dict}

    def status_text(self) -> str:
        if not self.enable:
            return "Disabled"
        if self.current:
            secret = (self.current.secret or "")[:4].lower()
            tag = " [ee]" if secret.startswith("ee") else (" [dd]" if secret.startswith("dd") else "")
            return self.current.display() + tag
        return "Direct (no proxy)"


# ==================== CONFIGURATION ====================
@dataclass
class CyDriveConfig:
    bot_token: str
    chat_id: int or str
    api_id: int = DEFAULT_API_ID
    api_hash: str = DEFAULT_API_HASH
    storage_path: str = DEFAULT_STORAGE_DIR
    cache_path: str = DEFAULT_CACHE_DIR
    db_path: str = DEFAULT_DB_FILE
    webdav_host: str = "127.0.0.1"
    webdav_port: int = 8080
    web_ui_host: str = "127.0.0.1"
    web_ui_port: int = 8088
    enable_web_ui: bool = True
    drive_letter: str = "Y:"
    auto_mount_drive: bool = True
    chunk_size_mb: int = 1900
    cache_limit_gb: int = 20
    encryption_password: Optional[str] = None
    enable_encryption: bool = False
    bot_username: str = ""
    # Proxy settings
    enable_proxy: bool = True
    proxy_file: str = DEFAULT_PROXY_FILE
    proxy_timeout: float = 5.0

    @classmethod
    def load(
        cls, file_path: str = CONFIG_FILE, prompt_if_missing: bool = True
    ) -> "CyDriveConfig":
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("bot_token") and data.get("chat_id"):
                        return cls(
                            **{
                                k: v
                                for k, v in data.items()
                                if k in cls.__dataclass_fields__
                            }
                        )
            except Exception:
                pass
        if prompt_if_missing:
            return cls.interactive_setup(file_path)
        return cls(bot_token="", chat_id=0)

    @classmethod
    def interactive_setup(cls, file_path: str = CONFIG_FILE) -> "CyDriveConfig":
        print("=" * 65)
        print("  🚀 CHIZ DRIVE: First-Time Interactive Configuration")
        print("  🌐 HMID QORBANI")
        print("=" * 65)
        bot_token = input("👉 Enter Bot Token (from @BotFather): ").strip()
        while not bot_token:
            bot_token = input("❌ Token cannot be empty: ").strip()
        chat_id_input = input("👉 Enter your User ID / Chat ID: ").strip()
        while not chat_id_input:
            chat_id_input = input("❌ Chat ID cannot be empty: ").strip()
        try:
            chat_id = int(chat_id_input)
        except ValueError:
            chat_id = chat_id_input
        drive_letter = "Y:"
        webdav_host = "127.0.0.1"
        web_ui_host = "127.0.0.1"
        if sys.platform.startswith("win"):
            drive_letter = input("👉 Drive letter [default Y:]: ").strip().upper()
            if not drive_letter:
                drive_letter = "Y:"
            if not drive_letter.endswith(":"):
                drive_letter += ":"
        else:
            if (
                input("👉 Running on VPS/Server? Enable external access (y/N): ")
                .strip()
                .lower()
                == "y"
            ):
                webdav_host = "0.0.0.0"
                web_ui_host = "0.0.0.0"

        enable_proxy = True
        proxy_ans = input("👉 Enable MTProto Proxy support? (Y/n): ").strip().lower()
        if proxy_ans == "n":
            enable_proxy = False

        cfg = cls(
            bot_token=bot_token,
            chat_id=chat_id,
            drive_letter=drive_letter,
            webdav_host=webdav_host,
            web_ui_host=web_ui_host,
            enable_proxy=enable_proxy,
        )
        cfg.save(file_path)
        print(f"✅ Config saved to {file_path}")
        if enable_proxy:
            print(f"📄 Put your proxies in: {cfg.proxy_file}")
            print("   Formats: host:port:secret  or  tg://proxy?server=...&port=...&secret=...")
        return cfg

    def save(self, file_path: str = CONFIG_FILE):
        os.makedirs(os.path.dirname(os.path.abspath(file_path)) or ".", exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=4)
        os.makedirs(self.storage_path, exist_ok=True)
        os.makedirs(self.cache_path, exist_ok=True)


# ==================== DATABASE ====================
class MetaDatabase:
    def __init__(self, db_path: str = DEFAULT_DB_FILE):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rel_path TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                parent_dir TEXT NOT NULL,
                size INTEGER DEFAULT 0,
                mtime REAL DEFAULT 0,
                sha256 TEXT,
                is_dir INTEGER DEFAULT 0,
                telegram_msg_id INTEGER,
                is_uploaded INTEGER DEFAULT 0,
                is_cached INTEGER DEFAULT 1,
                is_encrypted INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 1,
                mime_type TEXT,
                created_at REAL,
                updated_at REAL
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                telegram_msg_id INTEGER,
                size INTEGER NOT NULL,
                sha256 TEXT,
                FOREIGN KEY (file_id) REFERENCES files (id) ON DELETE CASCADE,
                UNIQUE(file_id, chunk_index)
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS share_links (
                token TEXT PRIMARY KEY,
                file_id INTEGER NOT NULL,
                created_at REAL DEFAULT (strftime('%s','now')),
                expires_at REAL,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            )""")
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_files_parent ON files(parent_dir)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_files_msg_id ON files(telegram_msg_id)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_share_links_token ON share_links(token)"
            )
            conn.commit()

    def upsert_file(
        self,
        rel_path: str,
        name: str,
        parent_dir: str,
        size: int = 0,
        mtime: float = 0.0,
        sha256: Optional[str] = None,
        is_dir: bool = False,
        telegram_msg_id: Optional[int] = None,
        is_uploaded: bool = False,
        is_cached: bool = True,
        is_encrypted: bool = False,
        chunk_count: int = 1,
        mime_type: Optional[str] = None,
    ) -> int:
        now = time.time()
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                """INSERT INTO files (rel_path, name, parent_dir, size, mtime, sha256, is_dir,
                        telegram_msg_id, is_uploaded, is_cached, is_encrypted, chunk_count, mime_type,
                        created_at, updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(rel_path) DO UPDATE SET
                        name=excluded.name, parent_dir=excluded.parent_dir, size=excluded.size,
                        mtime=excluded.mtime, sha256=coalesce(excluded.sha256, files.sha256),
                        telegram_msg_id=coalesce(excluded.telegram_msg_id, files.telegram_msg_id),
                        is_uploaded=excluded.is_uploaded, is_cached=excluded.is_cached,
                        is_encrypted=excluded.is_encrypted, chunk_count=excluded.chunk_count,
                        mime_type=coalesce(excluded.mime_type, files.mime_type),
                        updated_at=excluded.updated_at""",
                (
                    rel_path,
                    name,
                    parent_dir,
                    size,
                    mtime,
                    sha256,
                    int(is_dir),
                    telegram_msg_id,
                    int(is_uploaded),
                    int(is_cached),
                    int(is_encrypted),
                    chunk_count,
                    mime_type,
                    now,
                    now,
                ),
            )
            conn.commit()
            return c.lastrowid

    def get_file(self, rel_path: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM files WHERE rel_path = ?", (rel_path,))
            row = c.fetchone()
            return dict(row) if row else None

    def get_file_by_id(self, file_id: int) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM files WHERE id = ?", (file_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def get_file_by_msg_id(self, msg_id: int) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM files WHERE telegram_msg_id = ?", (msg_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def list_dir(self, parent_dir: str = "/") -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT * FROM files WHERE parent_dir = ? ORDER BY is_dir DESC, name ASC",
                (parent_dir,),
            )
            return [dict(row) for row in c.fetchall()]

    def list_all_files(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM files ORDER BY updated_at DESC")
            return [dict(row) for row in c.fetchall()]

    def search_files(self, query: str) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            c = conn.cursor()
            pattern = f"%{query}%"
            c.execute(
                "SELECT * FROM files WHERE name LIKE ? OR rel_path LIKE ? ORDER BY is_dir DESC, name ASC",
                (pattern, pattern),
            )
            return [dict(row) for row in c.fetchall()]

    def upsert_chunk(
        self,
        file_id: int,
        chunk_index: int,
        telegram_msg_id: int,
        size: int,
        sha256: Optional[str] = None,
    ):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                """INSERT INTO chunks (file_id, chunk_index, telegram_msg_id, size, sha256)
                        VALUES (?,?,?,?,?)
                        ON CONFLICT(file_id, chunk_index) DO UPDATE SET
                        telegram_msg_id=excluded.telegram_msg_id, size=excluded.size,
                        sha256=coalesce(excluded.sha256, chunks.sha256)""",
                (file_id, chunk_index, telegram_msg_id, size, sha256),
            )
            conn.commit()

    def get_chunks_by_file_id(self, file_id: int) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT * FROM chunks WHERE file_id = ? ORDER BY chunk_index ASC",
                (file_id,),
            )
            return [dict(row) for row in c.fetchall()]

    def delete_file(self, rel_path: str):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM files WHERE rel_path = ?", (rel_path,))
            row = c.fetchone()
            if row:
                file_id = row["id"]
                c.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
                c.execute("DELETE FROM share_links WHERE file_id = ?", (file_id,))
            c.execute("DELETE FROM files WHERE rel_path = ?", (rel_path,))
            conn.commit()

    def get_stats(self) -> Dict[str, Any]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT COUNT(*) as total_files, SUM(size) as total_bytes FROM files WHERE is_dir = 0"
            )
            row = c.fetchone()
            total_files = row["total_files"] or 0
            total_bytes = row["total_bytes"] or 0
            c.execute("SELECT COUNT(*) as total_dirs FROM files WHERE is_dir = 1")
            total_dirs = c.fetchone()["total_dirs"] or 0
            c.execute(
                "SELECT COUNT(*) as uploaded_files FROM files WHERE is_uploaded = 1 AND is_dir = 0"
            )
            uploaded_files = c.fetchone()["uploaded_files"] or 0
            return {
                "total_files": total_files,
                "total_bytes": total_bytes,
                "total_dirs": total_dirs,
                "uploaded_files": uploaded_files,
                "pending_uploads": total_files - uploaded_files,
            }

    def create_share_link(
        self, file_id: int, max_uses: int = 1, expires_in_days: int = 7
    ) -> str:
        token = uuid.uuid4().hex[:16]
        expires_at = (
            time.time() + expires_in_days * 24 * 3600 if expires_in_days > 0 else None
        )
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO share_links (token, file_id, expires_at, max_uses) VALUES (?,?,?,?)",
                (token, file_id, expires_at, max_uses),
            )
            conn.commit()
        return token

    def get_share_link(self, token: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM share_links WHERE token = ?", (token,))
            row = c.fetchone()
            return dict(row) if row else None

    def increment_share_use(self, token: str):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE share_links SET used_count = used_count + 1 WHERE token = ?",
                (token,),
            )
            conn.commit()


# ==================== CACHE MANAGER ====================
class CacheManager:
    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR, limit_gb: int = 20):
        self.cache_dir = os.path.abspath(cache_dir)
        self.limit_bytes = limit_gb * 1024 * 1024 * 1024
        os.makedirs(self.cache_dir, exist_ok=True)

    def get_local_path(self, rel_path: str) -> str:
        clean = rel_path.lstrip("/\\")
        full = os.path.join(self.cache_dir, clean)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        return full

    def is_cached(self, rel_path: str) -> bool:
        local = self.get_local_path(rel_path)
        return os.path.exists(local) and os.path.getsize(local) > 0

    def touch(self, rel_path: str):
        local = self.get_local_path(rel_path)
        if os.path.exists(local):
            try:
                os.utime(local, None)
            except Exception:
                pass

    def get_current_cache_size(self) -> int:
        total = 0
        for root, _, files in os.walk(self.cache_dir):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
        return total

    def evict_lru(self, bytes_needed: int = 0):
        current = self.get_current_cache_size()
        if (current + bytes_needed) <= self.limit_bytes:
            return
        entries = []
        for root, _, files in os.walk(self.cache_dir):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    st = os.stat(fp)
                    entries.append((st.st_atime, st.st_size, fp))
                except OSError:
                    pass
        entries.sort(key=lambda x: x[0])
        for _, size, fp in entries:
            if (current + bytes_needed) <= self.limit_bytes:
                break
            try:
                os.remove(fp)
                current -= size
            except OSError:
                pass

    def clear_all(self):
        for root, dirs, files in os.walk(self.cache_dir, topdown=False):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                except OSError:
                    pass
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except OSError:
                    pass


# ==================== CHUNKER ====================
class FileChunker:
    @staticmethod
    def calculate_sha256(file_path: str) -> str:
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(CHUNK_BUFFER_SIZE):
                sha.update(chunk)
        return sha.hexdigest()

    @staticmethod
    def needs_chunking(file_path: str, max_chunk_mb: int = 1900) -> bool:
        return os.path.getsize(file_path) > (max_chunk_mb * 1024 * 1024)

    @staticmethod
    def split_file(
        file_path: str, output_dir: str, chunk_size_mb: int = 1900
    ) -> List[str]:
        os.makedirs(output_dir, exist_ok=True)
        chunk_size = chunk_size_mb * 1024 * 1024
        chunks = []
        base = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            idx = 0
            while True:
                chunk_file = os.path.join(output_dir, f"{base}.part{idx:03d}")
                written = 0
                with open(chunk_file, "wb") as cf:
                    while written < chunk_size:
                        data = f.read(min(CHUNK_BUFFER_SIZE, chunk_size - written))
                        if not data:
                            break
                        cf.write(data)
                        written += len(data)
                if written > 0:
                    chunks.append(chunk_file)
                    idx += 1
                else:
                    if os.path.exists(chunk_file):
                        os.remove(chunk_file)
                    break
        return chunks

    @staticmethod
    def merge_chunks(chunk_paths: List[str], output_file_path: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(output_file_path)), exist_ok=True)
        with open(output_file_path, "wb") as out:
            for part in chunk_paths:
                with open(part, "rb") as pf:
                    while data := pf.read(CHUNK_BUFFER_SIZE):
                        out.write(data)
        return output_file_path


# ==================== CRYPTO ====================
class CyCrypto:
    SALT_SIZE = 16
    NONCE_SIZE = 12
    KEY_SIZE = 32

    def __init__(self, password: Optional[str] = None):
        self.password = password

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=100000,
        )
        return kdf.derive(password.encode("utf-8"))

    def encrypt_file(self, input_path: str, output_path: str) -> bool:
        if not self.password:
            raise ValueError("No password")
        salt = os.urandom(self.SALT_SIZE)
        nonce = os.urandom(self.NONCE_SIZE)
        key = self._derive_key(self.password, salt)
        with open(input_path, "rb") as f:
            plain = f.read()
        cipher = AESGCM(key).encrypt(nonce, plain, None)
        with open(output_path, "wb") as f:
            f.write(salt)
            f.write(nonce)
            f.write(cipher)
        return True

    def decrypt_file(self, input_path: str, output_path: str) -> bool:
        if not self.password:
            raise ValueError("No password")
        with open(input_path, "rb") as f:
            salt = f.read(self.SALT_SIZE)
            nonce = f.read(self.NONCE_SIZE)
            cipher = f.read()
        key = self._derive_key(self.password, salt)
        plain = AESGCM(key).decrypt(nonce, cipher, None)
        with open(output_path, "wb") as f:
            f.write(plain)
        return True


# ==================== PLATFORM ====================
class WindowsMounter:
    REG_PATH = r"SYSTEM\CurrentControlSet\Services\WebClient\Parameters"

    @staticmethod
    def is_windows() -> bool:
        return sys.platform.startswith("win")

    @classmethod
    def ensure_webclient_service(cls) -> bool:
        if not cls.is_windows():
            return False
        try:
            check = subprocess.run(
                ["sc", "query", "webclient"], capture_output=True, text=True
            )
            if "RUNNING" not in check.stdout:
                subprocess.run(
                    ["sc", "start", "webclient"], capture_output=True, text=True
                )
            return True
        except Exception:
            return False

    @classmethod
    def get_used_drive_letters(cls) -> List[str]:
        used = []
        if not cls.is_windows():
            return used
        try:
            import ctypes

            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                if bitmask & 1:
                    used.append(f"{letter}:")
                bitmask >>= 1
        except Exception:
            pass
        return used

    @classmethod
    def get_best_drive_letter(cls, preferred: str = "Y:") -> str:
        if not cls.is_windows():
            return "Y:"
        preferred = preferred.strip().upper()
        if not preferred.endswith(":"):
            preferred += ":"
        used = cls.get_used_drive_letters()
        if preferred not in used:
            return preferred
        for letter in ["Z:", "Y:", "X:", "W:", "V:", "U:", "T:", "S:"]:
            if letter not in used:
                return letter
        return preferred

    @classmethod
    def optimize_webdav_registry(cls) -> Tuple[bool, str]:
        if not cls.is_windows() or winreg is None:
            return False, "Not on Windows"
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                cls.REG_PATH,
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_READ,
            )
            winreg.SetValueEx(
                key, "FileSizeLimitInBytes", 0, winreg.REG_DWORD, 4294967295
            )
            winreg.SetValueEx(key, "BasicAuthLevel", 0, winreg.REG_DWORD, 2)
            winreg.CloseKey(key)
            subprocess.run(["net", "stop", "webclient"], capture_output=True, text=True)
            subprocess.run(
                ["net", "start", "webclient"], capture_output=True, text=True
            )
            return True, "Registry optimized for 4GB WebDAV"
        except PermissionError:
            return False, "Administrator privileges required"
        except Exception as e:
            return False, f"Registry error: {e}"

    @classmethod
    def mount_drive(
        cls, drive_letter: str = "Y:", webdav_url: str = "http://127.0.0.1:8080"
    ) -> Tuple[bool, str]:
        if not cls.is_windows():
            return False, "Not on Windows"
        cls.ensure_webclient_service()
        drive_letter = drive_letter.strip().upper()
        if not drive_letter.endswith(":"):
            drive_letter += ":"
        cls.unmount_drive(drive_letter)
        cmd = ["net", "use", drive_letter, webdav_url, "/persistent:no"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            return True, f"Mounted {drive_letter}"
        return False, f"Mount failed: {res.stderr or res.stdout}"

    @classmethod
    def unmount_drive(cls, drive_letter: str = "Y:") -> Tuple[bool, str]:
        if not cls.is_windows():
            return False, "Not on Windows"
        drive_letter = drive_letter.strip().upper()
        if not drive_letter.endswith(":"):
            drive_letter += ":"
        cmd = ["net", "use", drive_letter, "/delete", "/y"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return res.returncode == 0, res.stdout or res.stderr


class UnixMounter:
    @staticmethod
    def is_linux() -> bool:
        return sys.platform.startswith("linux")

    @staticmethod
    def is_macos() -> bool:
        return sys.platform == "darwin"

    @classmethod
    def get_default_mount_point(cls) -> str:
        mount = os.path.join(os.path.expanduser("~"), "CyDrive")
        os.makedirs(mount, exist_ok=True)
        return mount

    @classmethod
    def mount_drive(
        cls, mount_path: str = None, webdav_url: str = "http://127.0.0.1:8080"
    ) -> Tuple[bool, str]:
        if mount_path is None:
            mount_path = cls.get_default_mount_point()
        os.makedirs(mount_path, exist_ok=True)
        if cls.is_macos():
            try:
                res = subprocess.run(
                    ["mount_webdav", webdav_url, mount_path],
                    capture_output=True,
                    text=True,
                )
                if res.returncode == 0:
                    return True, f"Mounted to {mount_path}"
            except Exception:
                pass
        if cls.is_linux():
            if shutil.which("gio"):
                try:
                    subprocess.run(
                        ["gio", "mount", webdav_url], capture_output=True, text=True
                    )
                    return True, f"Mounted via GIO: {webdav_url}"
                except Exception:
                    pass
            if shutil.which("mount.davfs"):
                try:
                    subprocess.run(
                        ["mount", "-t", "davfs", webdav_url, mount_path],
                        capture_output=True,
                        text=True,
                    )
                    return True, f"Mounted via davfs2 to {mount_path}"
                except Exception:
                    pass
            return (
                True,
                f"WebDAV active at {webdav_url} (manual mount with davfs2 or rclone)",
            )
        return False, "Unsupported Unix"

    @classmethod
    def unmount_drive(cls, mount_path: str = None) -> Tuple[bool, str]:
        if mount_path is None:
            mount_path = cls.get_default_mount_point()
        if not os.path.exists(mount_path):
            return True, "Mount path not found"
        try:
            if cls.is_macos():
                subprocess.run(["umount", mount_path], capture_output=True, text=True)
            elif cls.is_linux():
                subprocess.run(
                    ["fusermount", "-u", mount_path], capture_output=True, text=True
                )
                subprocess.run(["umount", mount_path], capture_output=True, text=True)
            return True, f"Unmounted {mount_path}"
        except Exception as e:
            return False, f"Unmount failed: {e}"


# ==================== TELEGRAM ENGINE ====================
class TelegramSyncEngine:
    def __init__(self, config: CyDriveConfig, db: MetaDatabase, proxy_manager: Optional[ProxyManager] = None):
        self.config = config
        self.db = db
        self.proxy_manager = proxy_manager or ProxyManager(
            proxy_file=config.proxy_file,
            timeout=config.proxy_timeout,
            enable=config.enable_proxy,
        )
        self.client: Optional[TelegramClient] = None
        self.is_connected = False
        self.loop = None
        self._reconnect_lock = asyncio.Lock()
        self._health_task: Optional[asyncio.Task] = None
        self._health_interval = 45  # seconds
        self._consecutive_fails = 0
        self._max_fails_before_rotate = 2

    async def start(self):
        try:
            self.loop = asyncio.get_running_loop()

            # Load & test proxies
            count = self.proxy_manager.load()
            if count > 0:
                print(f"📡 Loaded {count} proxy(ies) from {self.proxy_manager.proxy_file}")
                if HAS_FAKETLS:
                    print("   ℹ️ FakeTLS (ee) support is available")
                else:
                    print("   ⚠️ For better ee/FakeTLS proxies: pip install TelethonFakeTLS")
                await self.proxy_manager.find_working(
                    self.config.api_id, self.config.api_hash, prefer_last=True
                )
            else:
                if self.config.enable_proxy:
                    print(f"📄 No proxies found in {self.proxy_manager.proxy_file} — using direct connection")

            await self._create_client_and_connect()

            self.is_connected = True
            self._register_handlers()
            me = await self.client.get_me()
            self.config.bot_username = me.username or ""
            proxy_status = self.proxy_manager.status_text()
            print(f"🤖 Connected as @{me.username}  |  Proxy: {proxy_status}")

            # Start background health checker
            self._health_task = asyncio.create_task(self._health_check_loop())
            print(f"❤️ Health-check started (every {self._health_interval}s)")
        except Exception as e:
            print(f"❌ Telegram error: {e}")
            raise

    def _cleanup_session_files(self, session_name: str = "cynet_bot_session"):
        for suffix in (".session", ".session-journal", ""):
            path = session_name + suffix
            try:
                if os.path.exists(path):
                    os.remove(path)
                    print(f"🗑️ Removed broken session: {path}")
            except Exception:
                pass

    async def stop(self):
        """Clean shutdown: cancel health-check, disconnect client, close session."""
        self.is_connected = False
        # Cancel health task
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except (asyncio.CancelledError, Exception):
                pass
            self._health_task = None

        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            # Force-close SQLite session handle (prevents "database is locked")
            try:
                sess = getattr(self.client, "session", None)
                if sess is not None:
                    close_fn = getattr(sess, "close", None)
                    if callable(close_fn):
                        close_fn()
            except Exception:
                pass
            self.client = None

        # Brief pause so Windows releases the file lock
        await asyncio.sleep(0.4)

    async def _create_client_and_connect(self):
        session_name = "cynet_bot_session"
        kwargs = {
            "session": session_name,
            "api_id": self.config.api_id,
            "api_hash": self.config.api_hash,
            "timeout": 20,
            "connection_retries": 3,
            "retry_delay": 1,
            "auto_reconnect": True,
        }
        proxy_kwargs = self.proxy_manager.get_telethon_kwargs()
        kwargs.update(proxy_kwargs)

        last_err = None
        for attempt in range(3):
            try:
                self.client = TelegramClient(**kwargs)
                await self.client.start(bot_token=self.config.bot_token)
                return
            except ValueError as e:
                if "unpack" in str(e).lower():
                    print("⚠️ Session incompatible. Recreating...")
                    self._cleanup_session_files(session_name)
                    last_err = e
                    continue
                raise
            except Exception as e:
                err = str(e).lower()
                last_err = e
                if "database is locked" in err or "locked" in err:
                    print(f"⚠️ Session locked (attempt {attempt+1}/3). Waiting...")
                    # Close any partial client
                    try:
                        if self.client:
                            await self.client.disconnect()
                    except Exception:
                        pass
                    self.client = None
                    # Remove journal (safe); keep .session if possible
                    for s in (session_name + ".session-journal", session_name + "-journal"):
                        try:
                            if os.path.exists(s):
                                os.remove(s)
                        except Exception:
                            pass
                    await asyncio.sleep(1.2 + attempt)
                    if attempt == 2:
                        # Last resort: full session reset
                        print("⚠️ Force-resetting session files...")
                        self._cleanup_session_files(session_name)
                    continue
                if "session" in err or "sqlite" in err or "unpack" in err:
                    print(f"⚠️ Session error ({e}). Recreating...")
                    self._cleanup_session_files(session_name)
                    continue
                raise
        if last_err:
            raise last_err

    async def reconnect_with_next_proxy(self):
        """Force rotate to next working proxy and reconnect."""
        async with self._reconnect_lock:
            print("🔄 Connection lost / unhealthy. Rotating proxy...")
            self.is_connected = False
            if self.client:
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
            await self.proxy_manager.find_working(
                self.config.api_id, self.config.api_hash, prefer_last=False
            )
            await self._create_client_and_connect()
            self.is_connected = True
            self._consecutive_fails = 0
            self._register_handlers()
            print(f"✅ Reconnected via: {self.proxy_manager.status_text()}")

    async def _try_soft_reconnect(self) -> bool:
        """Try reconnect with the same proxy first."""
        try:
            if self.client and not self.client.is_connected():
                await self.client.connect()
            if self.client and self.client.is_connected():
                # light API call to verify
                await asyncio.wait_for(self.client.get_me(), timeout=10)
                self.is_connected = True
                self._consecutive_fails = 0
                return True
        except Exception as e:
            print(f"   soft-reconnect failed: {e}")
        return False

    async def _health_check_loop(self):
        """Background task: periodically verify Telegram connection is alive."""
        await asyncio.sleep(15)  # initial grace period
        while True:
            try:
                await asyncio.sleep(self._health_interval)
                healthy = False
                if self.client:
                    try:
                        if self.client.is_connected():
                            # Real check – cheap request
                            await asyncio.wait_for(self.client.get_me(), timeout=12)
                            healthy = True
                    except Exception as e:
                        print(f"❤️ Health-check failed: {e}")
                        healthy = False

                if healthy:
                    self._consecutive_fails = 0
                    self.is_connected = True
                else:
                    self._consecutive_fails += 1
                    self.is_connected = False
                    print(f"❤️ Health-check: consecutive fails = {self._consecutive_fails}")

                    if self._consecutive_fails >= self._max_fails_before_rotate:
                        try:
                            await self.reconnect_with_next_proxy()
                        except Exception as e:
                            print(f"❌ Auto-reconnect failed: {e}")
                    else:
                        # First try soft reconnect on same proxy
                        ok = await self._try_soft_reconnect()
                        if not ok and self._consecutive_fails >= self._max_fails_before_rotate:
                            try:
                                await self.reconnect_with_next_proxy()
                            except Exception as e:
                                print(f"❌ Auto-reconnect failed: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❤️ Health loop error: {e}")
                await asyncio.sleep(10)

    def _register_handlers(self):
        if not self.client:
            return

        @self.client.on(events.NewMessage(chats=self.config.chat_id))
        async def handler(event):
            if event.message and event.message.media:
                await self._process_incoming_file(event)
            elif event.message and event.message.text:
                await self._process_bot_command(event)

    async def _process_incoming_file(self, event):
        msg = event.message
        if msg.file and hasattr(msg.file, "name") and msg.file.name:
            file_name = msg.file.name
        else:
            ext = getattr(msg.file, "ext", ".bin") if msg.file else ".bin"
            file_name = f"Telegram_File_{msg.id}{ext}"
        file_size = getattr(msg.file, "size", 0)
        mime_type = getattr(msg.file, "mime_type", None)
        rel_path = f"/{file_name}"
        self.db.upsert_file(
            rel_path=rel_path,
            name=file_name,
            parent_dir="/",
            size=file_size,
            mtime=time.time(),
            telegram_msg_id=msg.id,
            is_uploaded=True,
            is_cached=False,
            mime_type=mime_type,
        )
        try:
            size_str = (
                f"{file_size / (1024*1024):.2f} MB"
                if file_size < 1024**3
                else f"{file_size / (1024**3):.2f} GB"
            )
            await event.respond(
                f"☁️ File '{file_name}' ({size_str}) added to your Virtual Drive ({self.config.drive_letter})"
            )
        except Exception:
            pass

    def _menu_keyboard(self):
        """Persistent reply keyboard (glass-style menu under chat input)."""
        if not Button:
            return None
        return [
            [Button.text("📁 Files"), Button.text("📊 Stats")],
            [Button.text("📡 Status"), Button.text("🛡️ Proxy")],
            [Button.text("🔍 Search"), Button.text("❓ Help")],
        ]

    async def _process_bot_command(self, event):
        text = event.message.text.strip()

        # Map keyboard button labels → internal commands
        key_map = {
            "📁 Files": "/list",
            "📊 Stats": "/stats",
            "📡 Status": "/status",
            "🛡️ Proxy": "/proxy",
            "🔍 Search": "/search",
            "❓ Help": "/help",
            "Files": "/list",
            "Stats": "/stats",
            "Status": "/status",
            "Proxy": "/proxy",
            "Search": "/search",
            "Help": "/help",
        }
        if text in key_map:
            text = key_map[text]

        if text.startswith("/start share_"):
            token = text.split("_", 1)[1]
            await self._handle_share_request(event, token)
            return

        if text in ("/start", "/help", "/menu"):
            kb = self._menu_keyboard()
            msg = (
                "🚀 **Duck Drive Menu**\n\n"
                "Use the buttons below, or commands:\n\n"
                "📁 /list — recent files\n"
                "🔍 /search `<name>` — search\n"
                "⬇️ /get `<filename>` — download\n"
                "📊 /stats — storage\n"
                "📡 /status — connection\n"
                "🛡️ /proxy — proxy info\n\n"
                "💡 Send any file to upload it to your drive."
            )
            if kb:
                await event.respond(msg, buttons=kb)
            else:
                await event.respond(msg)
            return

        if text.startswith("/stats"):
            stats = self.db.get_stats()
            size_gb = stats["total_bytes"] / (1024**3)
            await event.respond(
                f"📊 **Stats**\n"
                f"Files: {stats['total_files']}\n"
                f"Folders: {stats['total_dirs']}\n"
                f"Size: {size_gb:.2f} GB\n"
                f"Uploaded: {stats['uploaded_files']}\n"
                f"Pending: {stats['pending_uploads']}\n"
                f"Drive: {self.config.drive_letter}\n"
                f"Proxy: {self.proxy_manager.status_text()}",
                buttons=self._menu_keyboard(),
            )
            return

        if text.startswith("/status"):
            connected = "✅" if self.is_connected else "❌"
            proxy = self.proxy_manager.status_text()
            await event.respond(
                f"📡 **System Status**\n"
                f"Telegram: {connected} Connected\n"
                f"Proxy: `{proxy}`\n"
                f"WebDAV: `http://127.0.0.1:{self.config.webdav_port}`\n"
                f"Web UI: `http://127.0.0.1:{self.config.web_ui_port}`\n"
                f"Drive letter: `{self.config.drive_letter}`",
                buttons=self._menu_keyboard(),
            )
            return

        if text.startswith("/proxy"):
            await event.respond(
                f"🛡️ **Proxy**\n"
                f"Current: `{self.proxy_manager.status_text()}`\n"
                f"Loaded: {len(self.proxy_manager.proxies)}\n"
                f"File: `{self.proxy_manager.proxy_file}`",
                buttons=self._menu_keyboard(),
            )
            return

        if text.startswith("/list"):
            files = self.db.list_all_files()
            files = [f for f in files if not f.get("is_dir")]
            if not files:
                await event.respond(
                    "No files yet. Send a file to upload.",
                    buttons=self._menu_keyboard(),
                )
                return
            lines = ["📁 **Recent files:**"]
            for r in files[:15]:
                kb = max(1, (r.get("size") or 0) // 1024)
                sync = "✅" if r.get("is_uploaded") else "⏳"
                lines.append(f"{sync} `{r['name']}` — {kb} KB")
            lines.append("\nUse /get `<filename>` to download.")
            await event.respond("\n".join(lines), buttons=self._menu_keyboard())
            return

        if text.startswith("/search"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await event.respond(
                    "Type: `/search filename`\nExample: `/search report.pdf`",
                    buttons=self._menu_keyboard(),
                )
                return
            results = self.db.search_files(parts[1])
            if not results:
                await event.respond("No files found.", buttons=self._menu_keyboard())
            else:
                lines = ["🔍 **Results:**"]
                for r in results[:12]:
                    lines.append(f"• `{r['name']}` ({(r.get('size') or 0)//1024} KB)")
                await event.respond("\n".join(lines), buttons=self._menu_keyboard())
            return

        if text.startswith("/get"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await event.respond(
                    "Usage: /get <filename>",
                    buttons=self._menu_keyboard(),
                )
                return
            file_record = self.db.get_file(f"/{parts[1]}") or self.db.get_file(parts[1])
            if not file_record:
                await event.respond(
                    "File not found. Try /list or /search",
                    buttons=self._menu_keyboard(),
                )
                return
            import tempfile

            fd, path = tempfile.mkstemp(prefix="cydrive_get_")
            os.close(fd)
            try:
                await event.respond("⬇️ Downloading…")
                success = await self.download_file_record(file_record, path)
                if success:
                    await self.client.send_file(
                        event.chat_id, path, caption=f"📁 {file_record['name']}"
                    )
                else:
                    await event.respond("Failed to download.")
            finally:
                if os.path.exists(path):
                    os.remove(path)
            return

    async def _handle_share_request(self, event, token):
        link_data = self.db.get_share_link(token)
        if not link_data:
            await event.respond("❌ Invalid or expired share link.")
            return
        file_id = link_data["file_id"]
        expires = link_data["expires_at"]
        max_uses = link_data["max_uses"]
        used = link_data["used_count"]
        if expires and time.time() > expires:
            await event.respond("❌ This link has expired.")
            return
        if max_uses and used >= max_uses:
            await event.respond("❌ This link has been used up.")
            return
        file_record = self.db.get_file_by_id(file_id)
        if not file_record:
            await event.respond("❌ File not found.")
            return
        import tempfile

        fd, path = tempfile.mkstemp(prefix="cydrive_share_")
        os.close(fd)
        try:
            success = await self.download_file_record(file_record, path)
            if success:
                await self.client.send_file(
                    event.chat_id, path, caption=f"📁 Shared: {file_record['name']}"
                )
                self.db.increment_share_use(token)
            else:
                await event.respond("❌ Failed to retrieve file.")
        finally:
            if os.path.exists(path):
                os.remove(path)

    async def upload_file(
        self,
        local_path: str,
        rel_path: str,
        progress_callback: Optional[Callable] = None,
    ) -> Optional[int]:
        if not os.path.exists(local_path):
            return None
        file_size = os.path.getsize(local_path)
        clean_rel = "/" + rel_path.strip("/").replace("\\", "/")
        file_name = os.path.basename(clean_rel)
        parent = (
            "/" + os.path.dirname(clean_rel).strip("/").replace("\\", "/")
            if os.path.dirname(clean_rel).strip("/").replace("\\", "/")
            else "/"
        )
        sha256 = (
            FileChunker.calculate_sha256(local_path)
            if file_size <= 100 * 1024 * 1024
            else None
        )
        upload_path = local_path
        is_encrypted = False
        temp_enc = None
        if self.config.enable_encryption and self.config.encryption_password:
            try:
                crypto = CyCrypto(self.config.encryption_password)
                fd, temp_enc = tempfile.mkstemp(prefix="cydrive_enc_")
                os.close(fd)
                crypto.encrypt_file(local_path, temp_enc)
                upload_path = temp_enc
                is_encrypted = True
            except Exception as e:
                print(f"Encryption failed: {e}")
        try:
            if FileChunker.needs_chunking(upload_path, self.config.chunk_size_mb):
                chunk_dir = tempfile.mkdtemp(prefix="cydrive_chunks_")
                try:
                    chunks = FileChunker.split_file(
                        upload_path, chunk_dir, self.config.chunk_size_mb
                    )
                    chunk_count = len(chunks)
                    file_id = self.db.upsert_file(
                        rel_path=clean_rel,
                        name=file_name,
                        parent_dir=parent,
                        size=file_size,
                        mtime=time.time(),
                        sha256=sha256,
                        is_uploaded=False,
                        is_cached=False,
                        is_encrypted=is_encrypted,
                        chunk_count=chunk_count,
                    )
                    first_msg_id = None
                    for idx, chunk_part in enumerate(chunks):
                        part_name = f"{file_name}.part{idx:03d}"
                        caption = f"🚀 DUCK Drive chunk {idx+1}/{chunk_count}"
                        msg = await self.client.send_file(
                            self.config.chat_id,
                            chunk_part,
                            caption=caption,
                            file_name=part_name,
                            progress_callback=progress_callback,
                        )
                        if idx == 0:
                            first_msg_id = msg.id
                        self.db.upsert_chunk(
                            file_id=file_id,
                            chunk_index=idx,
                            telegram_msg_id=msg.id,
                            size=os.path.getsize(chunk_part),
                        )
                    self.db.upsert_file(
                        rel_path=clean_rel,
                        name=file_name,
                        parent_dir=parent,
                        size=file_size,
                        mtime=time.time(),
                        sha256=sha256,
                        telegram_msg_id=first_msg_id,
                        is_uploaded=True,
                        is_cached=False,
                        is_encrypted=is_encrypted,
                        chunk_count=chunk_count,
                    )
                    return first_msg_id
                finally:
                    shutil.rmtree(chunk_dir, ignore_errors=True)
            caption = f"🚀 DUCK Drive: {clean_rel} ({file_size//1024} KB)"
            msg = await self.client.send_file(
                self.config.chat_id,
                upload_path,
                caption=caption,
                file_name=file_name,
                progress_callback=progress_callback,
            )
            self.db.upsert_file(
                rel_path=clean_rel,
                name=file_name,
                parent_dir=parent,
                size=file_size,
                mtime=time.time(),
                sha256=sha256,
                telegram_msg_id=msg.id,
                is_uploaded=True,
                is_cached=False,
                is_encrypted=is_encrypted,
                chunk_count=1,
            )
            return msg.id
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            return await self.upload_file(local_path, rel_path, progress_callback)
        except Exception as e:
            print(f"Upload error: {e}")
            # Try reconnect with next proxy on connection errors
            if "connection" in str(e).lower() or "timeout" in str(e).lower():
                try:
                    await self.reconnect_with_next_proxy()
                    return await self.upload_file(local_path, rel_path, progress_callback)
                except Exception:
                    pass
            return None
        finally:
            if temp_enc and os.path.exists(temp_enc):
                os.remove(temp_enc)
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
            except OSError:
                pass

    async def download_file_by_id(
        self, msg_id: int, dest_path: str, progress_callback: Optional[Callable] = None
    ) -> bool:
        try:
            msg = await self.client.get_messages(self.config.chat_id, ids=msg_id)
            if msg and msg.media:
                await msg.download_media(
                    file=dest_path, progress_callback=progress_callback
                )
                return True
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            return await self.download_file_by_id(msg_id, dest_path, progress_callback)
        except Exception as e:
            print(f"Download error: {e}")
        return False

    async def download_file_record(
        self,
        file_record: Dict[str, Any],
        dest_path: str,
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        chunk_count = file_record.get("chunk_count", 1) or 1
        file_id = file_record.get("id")
        is_encrypted = bool(file_record.get("is_encrypted", 0))
        target = dest_path if not is_encrypted else dest_path + ".enc_tmp"
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        success = False
        if chunk_count > 1 and file_id:
            chunks = self.db.get_chunks_by_file_id(file_id)
            if chunks and len(chunks) == chunk_count:
                tmp_dir = tempfile.mkdtemp(prefix="cydrive_dl_")
                try:
                    paths = []
                    ok = True
                    for chunk in chunks:
                        part = os.path.join(
                            tmp_dir, f"part_{chunk['chunk_index']:03d}.tmp"
                        )
                        ok = await self.download_file_by_id(
                            chunk["telegram_msg_id"], part, progress_callback
                        )
                        if not ok:
                            break
                        paths.append(part)
                    if ok:
                        FileChunker.merge_chunks(paths, target)
                        success = True
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            else:
                msg_id = file_record.get("telegram_msg_id")
                if msg_id:
                    success = await self.download_file_by_id(
                        msg_id, target, progress_callback
                    )
        else:
            msg_id = file_record.get("telegram_msg_id")
            if msg_id:
                success = await self.download_file_by_id(
                    msg_id, target, progress_callback
                )
        if success and is_encrypted and self.config.encryption_password:
            try:
                crypto = CyCrypto(self.config.encryption_password)
                crypto.decrypt_file(target, dest_path)
                if os.path.exists(target) and target != dest_path:
                    os.remove(target)
                return True
            except Exception as e:
                print(f"Decryption error: {e}")
                return False
        return success


# ==================== WATCHER ====================
class FileSyncHandler(FileSystemEventHandler):
    def __init__(self, watch_dir: str, change_queue: queue.Queue):
        super().__init__()
        self.watch_dir = os.path.abspath(watch_dir)
        self.change_queue = change_queue
        self._last_events = {}

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle(event.dest_path)

    def _handle(self, file_path: str):
        base = os.path.basename(file_path)
        if (
            base.startswith("~")
            or base.startswith(".")
            or base.endswith(".tmp")
            or base.endswith(".crdownload")
        ):
            return
        now = time.time()
        if now - self._last_events.get(file_path, 0) < 2.0:
            return
        self._last_events[file_path] = now
        self.change_queue.put(file_path)


class DriveWatcher:
    def __init__(self, watch_dir: str, on_file_ready: Callable[[str, str], None]):
        self.watch_dir = os.path.abspath(watch_dir)
        self.on_file_ready = on_file_ready
        self.queue = queue.Queue()
        self.observer = Observer() if HAS_WATCHDOG else None
        self.handler = FileSyncHandler(self.watch_dir, self.queue)
        self._running = False
        self._worker = threading.Thread(target=self._process, daemon=True)

    def is_file_ready(
        self, file_path: str, retries: int = 5, delay: float = 0.5
    ) -> bool:
        if not os.path.exists(file_path):
            return False
        for _ in range(retries):
            try:
                s1 = os.path.getsize(file_path)
                time.sleep(delay)
                s2 = os.path.getsize(file_path)
                if s1 == s2 and s1 > 0:
                    with open(file_path, "r+b"):
                        return True
            except (IOError, PermissionError):
                time.sleep(delay)
        return False

    def _process(self):
        while self._running:
            try:
                path = self.queue.get(timeout=1.0)
                if self.is_file_ready(path):
                    rel = "/" + os.path.relpath(path, self.watch_dir).replace(
                        "\\", "/"
                    ).lstrip("/")
                    self.on_file_ready(path, rel)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Watcher error: {e}")

    def start(self):
        if not HAS_WATCHDOG:
            print("⚠️ watchdog not installed")
            return
        self._running = True
        self.observer.schedule(self.handler, self.watch_dir, recursive=True)
        self.observer.start()
        self._worker.start()
        print(f"👁️ Watching {self.watch_dir}")

    def stop(self):
        self._running = False
        if HAS_WATCHDOG and self.observer:
            self.observer.stop()
            self.observer.join()


# ==================== WEBDAV PROVIDER ====================
class VirtualTelegramFile(DAVNonCollection):
    def __init__(
        self,
        path: str,
        environ: dict,
        file_record: dict,
        db: MetaDatabase,
        cache_mgr: CacheManager,
        telegram_engine: Optional[TelegramSyncEngine] = None,
    ):
        env = dict(environ) if environ else {}
        env.setdefault("wsgidav.provider", None)
        super().__init__(path, env)
        self.file_record = file_record or {}
        self.db = db
        self.cache_mgr = cache_mgr
        self.telegram_engine = telegram_engine
        self._write_handle = None

    def get_content_length(self) -> int:
        return self.file_record.get("size", 0)

    def support_content_length(self) -> bool:
        return True

    def get_content_type(self) -> str:
        return self.file_record.get("mime_type") or "application/octet-stream"

    def get_creation_date(self) -> float:
        return self.file_record.get("created_at", time.time())

    def get_last_modified(self) -> float:
        return self.file_record.get("mtime", time.time())

    def get_etag(self) -> str:
        sha = self.file_record.get("sha256")
        if sha:
            return str(sha).replace('"', "")
        return (
            f"{int(self.file_record.get('mtime',0))}-{self.file_record.get('size',0)}"
        )

    def support_etag(self) -> bool:
        return True

    def support_ranges(self) -> bool:
        return True

    def get_content(self):
        rel_path = self.path
        local = self.cache_mgr.get_local_path(rel_path)
        if os.path.exists(local):
            self.cache_mgr.touch(rel_path)
            return open(local, "rb")
        msg_id = self.file_record.get("telegram_msg_id")
        if msg_id and self.telegram_engine and self.telegram_engine.is_connected:
            self.cache_mgr.evict_lru(self.file_record.get("size", 0))
            import asyncio

            loop = (
                getattr(self.telegram_engine, "loop", None)
                or self.telegram_engine.client.loop
            )
            if loop and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self.telegram_engine.download_file_record(self.file_record, local),
                    loop,
                )
                try:
                    if future.result(timeout=180) and os.path.exists(local):
                        return open(local, "rb")
                except Exception as e:
                    print(f"Hydration error: {e}")
        return None

    def begin_write(self, content_type=None):
        rel_path = self.path
        local = self.cache_mgr.get_local_path(rel_path)
        os.makedirs(os.path.dirname(local), exist_ok=True)
        self._write_handle = open(local, "wb")
        return self._write_handle

    def end_write(self, with_errors: bool):
        if self._write_handle and not self._write_handle.closed:
            try:
                self._write_handle.close()
            except Exception:
                pass
        if not with_errors:
            rel_path = self.path
            local = self.cache_mgr.get_local_path(rel_path)
            if os.path.exists(local) and os.path.getsize(local) > 0:
                size = os.path.getsize(local)
                clean = "/" + rel_path.strip("/").replace("\\", "/")
                parent = (
                    "/" + os.path.dirname(clean).strip("/").replace("\\", "/")
                    if os.path.dirname(clean).strip("/").replace("\\", "/")
                    else "/"
                )
                name = os.path.basename(clean)
                self.db.upsert_file(
                    rel_path=clean,
                    name=name,
                    parent_dir=parent,
                    size=size,
                    mtime=time.time(),
                    is_uploaded=False,
                    is_cached=True,
                )
                if self.telegram_engine and self.telegram_engine.is_connected:
                    import asyncio

                    loop = (
                        getattr(self.telegram_engine, "loop", None)
                        or self.telegram_engine.client.loop
                    )
                    if loop and loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self.telegram_engine.upload_file(local, clean), loop
                        )

    def handle_delete(self):
        rel_path = "/" + self.path.strip("/").replace("\\", "/")
        self.db.delete_file(rel_path)
        local = self.cache_mgr.get_local_path(rel_path)
        if os.path.exists(local):
            try:
                os.remove(local)
            except OSError:
                pass
        return True


class VirtualTelegramFolder(DAVCollection):
    def __init__(
        self,
        path: str,
        environ: dict,
        db: MetaDatabase,
        cache_mgr: CacheManager,
        telegram_engine: Optional[TelegramSyncEngine] = None,
    ):
        env = dict(environ) if environ else {}
        env.setdefault("wsgidav.provider", None)
        super().__init__(path, env)
        self.db = db
        self.cache_mgr = cache_mgr
        self.telegram_engine = telegram_engine

    def get_used_bytes(self) -> str:
        stats = self.db.get_stats()
        return str(stats.get("total_bytes", 0))

    def get_available_bytes(self) -> str:
        return str(10 * 1024 * 1024 * 1024 * 1024)

    def get_member_names(self) -> List[str]:
        rel = (
            "/" + self.path.strip("/").replace("\\", "/")
            if self.path.strip("/")
            else "/"
        )
        items = self.db.list_dir(parent_dir=rel)
        return [item["name"] for item in items]

    def get_member_list(self):
        rel = (
            "/" + self.path.strip("/").replace("\\", "/")
            if self.path.strip("/")
            else "/"
        )
        items = self.db.list_dir(parent_dir=rel)
        members = []
        for item in items:
            p = "/" + item["rel_path"].strip("/").replace("\\", "/")
            if item["is_dir"]:
                members.append(
                    VirtualTelegramFolder(
                        p, self.environ, self.db, self.cache_mgr, self.telegram_engine
                    )
                )
            else:
                members.append(
                    VirtualTelegramFile(
                        p,
                        self.environ,
                        item,
                        self.db,
                        self.cache_mgr,
                        self.telegram_engine,
                    )
                )
        return members

    def get_member(self, name: str):
        parent = (
            "/" + self.path.strip("/").replace("\\", "/")
            if self.path.strip("/")
            else "/"
        )
        clean = "/" + os.path.join(parent.lstrip("/"), name).replace("\\", "/")
        item = self.db.get_file(clean)
        if not item:
            items = self.db.list_dir(parent_dir=parent)
            for it in items:
                if it["name"] == name:
                    item = it
                    clean = "/" + it["rel_path"].strip("/").replace("\\", "/")
                    break
        if not item:
            return None
        if item["is_dir"]:
            return VirtualTelegramFolder(
                clean, self.environ, self.db, self.cache_mgr, self.telegram_engine
            )
        return VirtualTelegramFile(
            clean, self.environ, item, self.db, self.cache_mgr, self.telegram_engine
        )

    def support_etag(self) -> bool:
        return False

    def support_ranges(self) -> bool:
        return False

    def create_empty_resource(self, name: str):
        rel = "/" + os.path.join(self.path.strip("/"), name).replace("\\", "/")
        parent = (
            "/" + self.path.strip("/").replace("\\", "/")
            if self.path.strip("/")
            else "/"
        )
        self.db.upsert_file(
            rel,
            name,
            parent,
            0,
            time.time(),
            is_dir=False,
            is_uploaded=False,
            is_cached=True,
        )
        item = self.db.get_file(rel)
        return VirtualTelegramFile(
            rel, self.environ, item, self.db, self.cache_mgr, self.telegram_engine
        )

    def create_collection(self, name: str):
        rel = "/" + os.path.join(self.path.strip("/"), name).replace("\\", "/")
        parent = (
            "/" + self.path.strip("/").replace("\\", "/")
            if self.path.strip("/")
            else "/"
        )
        self.db.upsert_file(
            rel,
            name,
            parent,
            0,
            time.time(),
            is_dir=True,
            is_uploaded=True,
            is_cached=True,
        )
        return VirtualTelegramFolder(
            rel, self.environ, self.db, self.cache_mgr, self.telegram_engine
        )

    def handle_delete(self):
        rel = "/" + self.path.strip("/").replace("\\", "/")
        self.db.delete_file(rel)
        return True


class PureVirtualTelegramProvider(DAVProvider):
    def __init__(self, db: MetaDatabase, cache_mgr: CacheManager, telegram_engine=None):
        super().__init__()
        self.db = db
        self.cache_mgr = cache_mgr
        self.telegram_engine = telegram_engine

    def get_resource_inst(self, path: str, environ: dict):
        env = dict(environ) if environ else {}
        env.setdefault("wsgidav.provider", self)
        clean = "/" + path.strip("/").replace("\\", "/") if path.strip("/") else "/"
        if clean == "/":
            return VirtualTelegramFolder(
                "/", env, self.db, self.cache_mgr, self.telegram_engine
            )
        item = self.db.get_file(clean)
        if not item:
            return None
        if item["is_dir"]:
            return VirtualTelegramFolder(
                clean, env, self.db, self.cache_mgr, self.telegram_engine
            )
        return VirtualTelegramFile(
            clean, env, item, self.db, self.cache_mgr, self.telegram_engine
        )


class CyWebDAVServer:
    def __init__(
        self,
        root_path: str,
        host: str = "127.0.0.1",
        port: int = 8080,
        db: Optional[MetaDatabase] = None,
        cache_mgr: Optional[CacheManager] = None,
        telegram_engine: Optional[TelegramSyncEngine] = None,
    ):
        self.root_path = os.path.abspath(root_path)
        self.host = host
        self.port = port
        self.db = db
        self.cache_mgr = cache_mgr or CacheManager()
        self.telegram_engine = telegram_engine
        self.server = None
        self._thread = None
        os.makedirs(self.root_path, exist_ok=True)

    def _create_app(self):
        # PyInstaller fix: WsgiDAV DirBrowser always loads template.html from
        # htdocs. Under frozen (_MEI) packages those files are missing → crash.
        # Create a dummy htdocs + template, and use a middleware stack that
        # does NOT include WsgiDavDirBrowser at all.
        htdocs = os.path.join(tempfile.gettempdir(), "cydrive_wsgidav_htdocs")
        try:
            os.makedirs(htdocs, exist_ok=True)
            tpl = os.path.join(htdocs, "template.html")
            if not os.path.exists(tpl):
                with open(tpl, "w", encoding="utf-8") as f:
                    f.write(
                        "<!DOCTYPE html><html><body>"
                        "<h3>Duck Drive WebDAV</h3>"
                        "<p>Use the Web UI instead.</p>"
                        "</body></html>"
                    )
        except Exception:
            htdocs = tempfile.gettempdir()

        # Middleware without DirBrowser (default stack includes it and crashes)
        middleware_stack = [
            "wsgidav.mw.cors.Cors",
            "wsgidav.error_printer.ErrorPrinter",
            "wsgidav.http_authenticator.HTTPAuthenticator",
            "wsgidav.request_resolver.RequestResolver",
        ]

        config = {
            "host": self.host,
            "port": self.port,
            "provider_mapping": {
                "/": PureVirtualTelegramProvider(
                    self.db, self.cache_mgr, self.telegram_engine
                )
            },
            "simple_dc": {"user_mapping": {"*": True}},
            "verbose": 1,
            "enable_cors": True,
            "middleware_stack": middleware_stack,
            "dir_browser": {
                "enable": False,
                "htdocs_path": htdocs,
            },
        }
        return WsgiDAVApp(config)

    def start(self, blocking: bool = False):
        app = self._create_app()
        self.server = wsgi.Server(bind_addr=(self.host, self.port), wsgi_app=app)
        ip = get_display_ip(self.host)
        print(f"🌐 WebDAV: http://{ip}:{self.port}")
        if blocking:
            self.server.start()
        else:
            self._thread = threading.Thread(target=self.server.start, daemon=True)
            self._thread.start()

    def stop(self):
        if self.server:
            self.server.stop()


# ==================== WEB UI ====================
class CyWebDashboard:
    def __init__(self, config: CyDriveConfig, db: MetaDatabase, telegram_engine=None):
        self.config = config
        self.db = db
        self.telegram_engine = telegram_engine
        self.app = web.Application() if HAS_AIOHTTP else None
        self.runner = None
        self.site = None
        if self.app:
            self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get("/", self.index_handler)
        self.app.router.add_get("/api/files", self.get_files_handler)
        self.app.router.add_get("/api/stats", self.get_stats_handler)
        self.app.router.add_post("/api/upload", self.upload_handler)
        self.app.router.add_post("/api/delete", self.delete_handler)
        self.app.router.add_post("/api/share", self.share_handler)
        self.app.router.add_get("/api/download/{filename}", self.download_handler)
        # Static routes
        self.app.router.add_get("/static/css/style.css", self.serve_css)
        self.app.router.add_get("/static/js/app.js", self.serve_js)
        self.app.router.add_get("/static/img/logo.jpg", self.serve_logo)

    async def index_handler(self, request):
        return web.Response(text=INDEX_HTML, content_type="text/html")

    async def serve_css(self, request):
        return web.Response(text=STYLE_CSS, content_type="text/css")

    async def serve_js(self, request):
        return web.Response(text=APP_JS, content_type="application/javascript")

    async def serve_logo(self, request):
        import base64

        data = base64.b64decode(LOGO_BASE64)
        return web.Response(body=data, content_type="image/jpeg")

    async def get_files_handler(self, request):
        files = self.db.list_all_files()
        return web.json_response(files)

    async def get_stats_handler(self, request):
        stats = self.db.get_stats()
        proxy_info = "Direct"
        if self.telegram_engine and self.telegram_engine.proxy_manager:
            proxy_info = self.telegram_engine.proxy_manager.status_text()
        stats.update(
            {
                "drive_letter": self.config.drive_letter,
                "webdav_host": self.config.webdav_host,
                "webdav_port": self.config.webdav_port,
                "proxy_info": proxy_info,
            }
        )
        return web.json_response(stats)

    async def share_handler(self, request):
        data = await request.json()
        filename = data.get("filename")
        if not filename:
            return web.json_response({"error": "filename required"}, status=400)
        file_record = self.db.get_file(f"/{filename}") or self.db.get_file(filename)
        if not file_record:
            return web.json_response({"error": "File not found"}, status=404)
        token = self.db.create_share_link(
            file_record["id"], max_uses=1, expires_in_days=7
        )
        bot_username = self.config.bot_username or "YourBot"
        share_url = f"https://t.me/{bot_username}?start=share_{token}"
        return web.json_response({"share_url": share_url, "token": token})

    async def delete_handler(self, request):
        data = await request.json()
        filename = data.get("filename")
        if not filename:
            return web.json_response({"error": "filename required"}, status=400)
        clean = "/" + filename.strip("/").replace("\\", "/")
        self.db.delete_file(clean)
        local = os.path.join(self.config.cache_path, filename.lstrip("/\\"))
        if os.path.exists(local):
            try:
                os.remove(local)
            except OSError:
                pass
        return web.json_response({"success": True})

    async def upload_handler(self, request):
        reader = await request.multipart()
        field = await reader.next()
        if field.name == "file":
            filename = field.filename
            if not filename:
                return web.json_response({"error": "No filename"}, status=400)
            ext = os.path.splitext(filename)[1]
            fd, temp_path = tempfile.mkstemp(prefix="cydrive_up_", suffix=ext)
            try:
                with open(temp_path, "wb") as f:
                    while chunk := await field.read_chunk():
                        f.write(chunk)
                if self.telegram_engine and self.telegram_engine.is_connected:
                    await self.telegram_engine.upload_file(temp_path, f"/{filename}")
                else:
                    dest = os.path.join(self.config.cache_path, filename)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(temp_path, dest)
                    self.db.upsert_file(
                        f"/{filename}",
                        filename,
                        "/",
                        os.path.getsize(dest),
                        time.time(),
                        is_uploaded=False,
                        is_cached=True,
                    )
            finally:
                os.close(fd)
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            return web.json_response({"success": True, "filename": filename})
        return web.json_response({"error": "Invalid upload"}, status=400)

    async def download_handler(self, request):
        filename = request.match_info.get("filename")
        rel_path = f"/{filename}"
        file_record = self.db.get_file(rel_path) or self.db.get_file(filename)
        local_path = os.path.join(self.config.cache_path, filename.lstrip("/\\"))
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            mime, _ = mimetypes.guess_type(local_path)
            return web.FileResponse(
                local_path,
                headers={
                    "Content-Type": mime or "application/octet-stream",
                    "Content-Disposition": f'inline; filename="{filename}"',
                },
            )
        if file_record and self.telegram_engine and self.telegram_engine.is_connected:
            msg_id = file_record.get("telegram_msg_id")
            if msg_id:
                msg = await self.telegram_engine.client.get_messages(
                    self.config.chat_id, ids=msg_id
                )
                if msg and msg.media:
                    mime = (
                        file_record.get("mime_type")
                        or mimetypes.guess_type(filename)[0]
                        or "application/octet-stream"
                    )
                    response = web.StreamResponse(
                        headers={
                            "Content-Type": mime,
                            "Content-Disposition": f'inline; filename="{filename}"',
                            "Content-Length": str(file_record.get("size", 0)),
                        }
                    )
                    await response.prepare(request)
                    async for chunk in self.telegram_engine.client.iter_download(
                        msg.media
                    ):
                        await response.write(chunk)
                    await response.write_eof()
                    return response
        return web.Response(text="File not found", status=404)

    async def start(self):
        if not HAS_AIOHTTP:
            print("⚠️ aiohttp not installed")
            return
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(
            self.runner, self.config.web_ui_host, self.config.web_ui_port
        )
        await self.site.start()
        ip = get_display_ip(self.config.web_ui_host)
        print(f"✨ Web UI: http://{ip}:{self.config.web_ui_port}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()


# ==================== CLI ====================
class CyDriveCLI:
    def __init__(self):
        self.console = Console() if HAS_RICH else None

    def print_banner(self):
        banner = """

        HMID QORBANI

        """
        if HAS_RICH:
            self.console.print(
                Panel(
                    Text(banner, style="bold cyan")
                    + Text(
                        "\n🚀 Infinite Cloud Drive via Telegram\n🛡️ Smart Proxy + FakeTLS + Health-Check\n🌐 HMID QORBANI",
                        style="bold magenta",
                    ),
                    border_style="cyan",
                )
            )
        else:
            print(banner)

    def print_status(self, config: CyDriveConfig, db: MetaDatabase, proxy_mgr: Optional[ProxyManager] = None):
        stats = db.get_stats()
        size_mb = stats["total_bytes"] / (1024 * 1024)
        print(f"📊 Files: {stats['total_files']}, Size: {size_mb:.2f} MB")
        print(
            f"🌐 WebDAV: http://{get_display_ip(config.webdav_host)}:{config.webdav_port}"
        )
        print(
            f"🌐 Web UI: http://{get_display_ip(config.web_ui_host)}:{config.web_ui_port}"
        )
        print(f"💾 Drive: {config.drive_letter} (0 Bytes local footprint)")
        if proxy_mgr:
            print(f"🛡️ Proxy: {proxy_mgr.status_text()}")

    def run(self):
        parser = argparse.ArgumentParser(description="DuckDrive Standalone v2.2")
        parser.add_argument(
            "command",
            nargs="?",
            default="run",
            choices=["run", "mount", "unmount", "fix-reg", "stats", "setup", "proxy-test"],
        )
        args = parser.parse_args()
        self.print_banner()
        if args.command == "setup":
            CyDriveConfig.interactive_setup()
            return
        config = CyDriveConfig.load(prompt_if_missing=(args.command == "run"))
        db = MetaDatabase(config.db_path)
        proxy_mgr = ProxyManager(
            proxy_file=config.proxy_file,
            timeout=config.proxy_timeout,
            enable=config.enable_proxy,
        )

        if args.command == "fix-reg":
            ok, msg = WindowsMounter.optimize_webdav_registry()
            print(f"{'✅' if ok else '❌'} {msg}")
            return
        if args.command == "mount":
            if WindowsMounter.is_windows():
                ok, msg = WindowsMounter.mount_drive(
                    config.drive_letter,
                    f"http://{config.webdav_host}:{config.webdav_port}",
                )
            else:
                ok, msg = UnixMounter.mount_drive(
                    None, f"http://{config.webdav_host}:{config.webdav_port}"
                )
            print(f"{'✅' if ok else '❌'} {msg}")
            return
        if args.command == "unmount":
            if WindowsMounter.is_windows():
                ok, msg = WindowsMounter.unmount_drive(config.drive_letter)
            else:
                ok, msg = UnixMounter.unmount_drive()
            print(f"{'✅' if ok else '❌'} {msg}")
            return
        if args.command == "stats":
            self.print_status(config, db, proxy_mgr)
            return
        if args.command == "proxy-test":
            count = proxy_mgr.load()
            print(f"Loaded {count} proxies from {proxy_mgr.proxy_file}")
            if count == 0:
                return
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            working = loop.run_until_complete(
                proxy_mgr.find_working(config.api_id, config.api_hash)
            )
            if working:
                print(f"✅ Working proxy: {working.display()}")
            else:
                print("❌ No working proxy found")
            return

        # Run all services
        cache_mgr = CacheManager(config.cache_path, config.cache_limit_gb)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        telegram_engine = TelegramSyncEngine(config, db, proxy_mgr)
        webdav = CyWebDAVServer(
            config.storage_path,
            config.webdav_host,
            config.webdav_port,
            db,
            cache_mgr,
            telegram_engine,
        )
        webdav.start(blocking=False)

        # Start async loop in thread
        def async_thread_func():
            asyncio.set_event_loop(loop)
            loop.run_until_complete(telegram_engine.start())
            dashboard = CyWebDashboard(config, db, telegram_engine)
            loop.run_until_complete(dashboard.start())
            self.print_status(config, db, proxy_mgr)
            print("🚀 DUCK Drive running. Press Ctrl+C to stop.")
            loop.run_forever()

        thread = threading.Thread(target=async_thread_func, daemon=True)
        thread.start()
        # Mount drive if auto
        if config.auto_mount_drive:
            if WindowsMounter.is_windows():
                WindowsMounter.optimize_webdav_registry()
                WindowsMounter.mount_drive(
                    config.drive_letter,
                    f"http://{config.webdav_host}:{config.webdav_port}",
                )
            else:
                UnixMounter.mount_drive(
                    None, f"http://{config.webdav_host}:{config.webdav_port}"
                )
        # Watcher
        watcher = DriveWatcher(
            config.storage_path,
            lambda path, rel: asyncio.run_coroutine_threadsafe(
                telegram_engine.upload_file(path, rel), loop
            ),
        )
        watcher.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Shutting down...")
            watcher.stop()
            webdav.stop()
            if WindowsMounter.is_windows():
                WindowsMounter.unmount_drive(config.drive_letter)
            else:
                UnixMounter.unmount_drive()
            loop.call_soon_threadsafe(loop.stop)
            print("👋 Goodbye!")


def main():
    cli = CyDriveCLI()
    cli.run()


if __name__ == "__main__":
    main()
