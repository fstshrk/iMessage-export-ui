#!/usr/bin/env python3
"""
iMessage Export Web Viewer & Index Generator

Copyright (c) 2026, Bora Akyol
All rights reserved.
Licensed under the BSD 3-Clause License. See LICENSE for details.

Scans an imessage-exporter export directory, maps phone numbers to real contact
names from the message transcripts, injects the enhanced viewer helper, and creates
a modern Apple Messages-style index.html front-end.
"""

import os
import re
import sys
import json
import html
import shutil
import argparse
import urllib.parse
from datetime import datetime
from collections import Counter
from pathlib import Path

__version__ = "1.0.0"

# Regex patterns optimized for imessage-exporter HTML structure
MSG_DIV_RE = re.compile(r'<div class="(?:message|announcement)"', re.IGNORECASE)
DATE_RE = re.compile(r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4}\s+[\d:]+\s+[AP]M)')
BUBBLE_RE = re.compile(r'<span class="bubble">([\s\S]*?)</span>', re.IGNORECASE)
ANNOUNCEMENT_RE = re.compile(r'<div class="announcement">[\s\S]*?<p>([\s\S]*?)</p>', re.IGNORECASE)
ATTACHMENT_RE = re.compile(r'<div class="attachment"><(?:img|video|audio)[^>]*src="([^"]+)"', re.IGNORECASE)
SENDER_RE = re.compile(r'<span class="sender">([^<]+)</span>', re.IGNORECASE)
SPAN_TITLE_RE = re.compile(r'<span title="([^"]+)"><b>([^<]+)</b></span>')
TAPBACK_RE = re.compile(r'<div class="tapback"><span><b>[^<]+</b>\s+by\s+([^<]+)</span></div>', re.IGNORECASE)

AVATAR_COLORS = [
    "#007AFF", "#34C759", "#5856D6", "#AF52DE", "#FF2D55",
    "#FF9500", "#FFCC00", "#5AC8FA", "#FF3B30", "#30B0C7",
    "#32ADE6", "#00C7BE", "#A2845E"
]

def hash_color(name: str) -> str:
    h = 0
    for char in name:
        h = (h << 5) - h + ord(char)
        h &= 0xFFFFFFFF
    return AVATAR_COLORS[abs(h) % len(AVATAR_COLORS)]

def format_phone_number(raw: str) -> str:
    cleaned = raw.strip()
    digits = re.sub(r'\D', '', cleaned)
    if digits.startswith('1') and len(digits) == 11:
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    elif len(digits) == 10:
        return f"({digits[0:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) in (3, 4, 5, 6):
        return f"Service {digits}"
    return cleaned

def is_real_contact_name(name: str) -> bool:
    if not name or not isinstance(name, str):
        return False
    name = name.strip()
    if name.lower() == "me":
        return False
    if name.startswith("urn:") or "@" in name or name.startswith("+"):
        return False
    if not re.search(r'[a-zA-Z]', name):
        return False
    if len(name) > 40:
        return False
    return True

def get_initials(name: str) -> str:
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', name).strip()
    words = [w for w in clean.split() if w]
    if len(words) >= 2:
        return (words[0][0] + words[-1][0]).upper()
    elif len(words) == 1:
        return words[0][:2].upper()
    return "💬"

def build_contact_directory(all_files):
    """
    Pass 1: Build a comprehensive mapping of phone numbers and emails to real contact names.
    Also injects viewer_helper.js into each transcript file if not already present.
    """
    phone_to_name = {}
    email_to_name = {}

    print(f"Pass 1: Discovering contact names and linking viewer helper across {len(all_files)} files...")
    
    injected_count = 0
    for filepath in all_files:
        filename = os.path.basename(filepath)
        stem = Path(filename).stem.strip()
        
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            continue

        # Inject viewer_helper.js if needed
        if "viewer_helper.js" not in content and "</body>" in content:
            new_content = content.replace("</body>", '<script src="viewer_helper.js"></script></body>', 1)
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                injected_count += 1
            except Exception:
                pass

        # 1. Look for span title attributes, e.g. <span title="+12063514260"><b>Michelle</b></span>
        for phone, name in SPAN_TITLE_RE.findall(content):
            p, n = phone.strip(), name.strip()
            if p.startswith("+") and is_real_contact_name(n):
                if p not in phone_to_name or len(n.split()) > len(phone_to_name[p].split()):
                    phone_to_name[p] = n

        # 2. Look for senders in 1-on-1 chats
        if "," not in stem:
            senders = [s.strip() for s in SENDER_RE.findall(content)]
            real_senders = [s for s in senders if is_real_contact_name(s)]
            if real_senders:
                most_common = Counter(real_senders).most_common(1)[0][0]
                if stem.startswith("+"):
                    curr = phone_to_name.get(stem)
                    if not curr or len(most_common.split()) >= len(curr.split()):
                        phone_to_name[stem] = most_common
                elif "@" in stem:
                    curr = email_to_name.get(stem)
                    if not curr or len(most_common.split()) >= len(curr.split()):
                        email_to_name[stem] = most_common
            else:
                for name in TAPBACK_RE.findall(content):
                    n = name.strip()
                    if is_real_contact_name(n):
                        if stem.startswith("+") and stem not in phone_to_name:
                            phone_to_name[stem] = n

    print(f"  Mapped {len(phone_to_name)} phone numbers and {len(email_to_name)} emails.")
    if injected_count > 0:
        print(f"  Linked viewer_helper.js to {injected_count} conversation transcripts.")
    return phone_to_name, email_to_name

def parse_conversation(filepath: str, phone_to_name: dict, email_to_name: dict):
    filename = os.path.basename(filepath)
    stem = Path(filename).stem.strip()

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        msgs = len(MSG_DIV_RE.findall(content))
        if msgs == 0:
            msgs = 1

        dates = DATE_RE.findall(content)
        first_date_str = dates[0].strip() if dates else ""
        last_date_str = dates[-1].strip() if dates else ""

        last_date_iso = ""
        if last_date_str:
            try:
                clean_d = re.sub(r'\s+', ' ', last_date_str)
                dt = datetime.strptime(clean_d, "%b %d, %Y %I:%M:%S %p")
                last_date_iso = dt.isoformat()
            except Exception:
                last_date_iso = ""

        first_date_iso = ""
        if first_date_str:
            try:
                clean_d = re.sub(r'\s+', ' ', first_date_str)
                dt = datetime.strptime(clean_d, "%b %d, %Y %I:%M:%S %p")
                first_date_iso = dt.isoformat()
            except Exception:
                first_date_iso = ""

        last_preview = ""
        bubbles = BUBBLE_RE.findall(content)
        if bubbles:
            raw_text = bubbles[-1]
            clean_text = html.unescape(re.sub(r'<[^>]+>', ' ', raw_text)).strip()
            clean_text = re.sub(r'\s+', ' ', clean_text)
            last_preview = clean_text[:120]
        else:
            announcements = ANNOUNCEMENT_RE.findall(content)
            if announcements:
                clean_ann = html.unescape(re.sub(r'<[^>]+>', ' ', announcements[-1])).strip()
                last_preview = f"📢 {re.sub(r'\s+', ' ', clean_ann)[:100]}"
            elif ATTACHMENT_RE.search(content):
                last_preview = "📎 [Attachment / Media]"
            else:
                last_preview = "[No preview available]"

        senders = list(dict.fromkeys(SENDER_RE.findall(content)))
        senders_clean = [s for s in senders if s.lower() != "me"]

        title = ""
        category = "direct"
        subtitle = ""
        address = stem

        if stem == "orphaned":
            title = "Orphaned Messages"
            category = "system"
            initials = "⚠️"
            subtitle = "System / Unrouted Messages"
            address = ""
        elif re.match(r'^(.*?)\s*-\s*(\d+)$', stem):
            named_match = re.match(r'^(.*?)\s*-\s*(\d+)$', stem)
            title = named_match.group(1).strip()
            chat_id = named_match.group(2)
            category = "group"
            initials = get_initials(title)
            subtitle = f"Group Chat (ID {chat_id})"
            address = f"Group {chat_id}"
        elif "," in stem:
            category = "group"
            participants = [p.strip() for p in stem.split(",") if p.strip()]
            resolved_participants = []
            for p in participants:
                if p in phone_to_name:
                    resolved_participants.append(phone_to_name[p])
                elif p in email_to_name:
                    resolved_participants.append(email_to_name[p])
                else:
                    resolved_participants.append(format_phone_number(p))
            
            real_named_senders = [s for s in senders_clean if is_real_contact_name(s)]
            if real_named_senders:
                for s in real_named_senders:
                    if s not in resolved_participants and any(p.startswith("+") for p in resolved_participants):
                        for idx, rp in enumerate(resolved_participants):
                            if rp.startswith("+") or rp.startswith("("):
                                resolved_participants[idx] = s
                                break

            title = ", ".join(resolved_participants)
            initials = "👥"
            subtitle = f"Group Chat ({len(participants)} members)"
            address = ", ".join([format_phone_number(p) for p in participants])
        elif "@" in stem:
            category = "email"
            if stem in email_to_name:
                title = email_to_name[stem]
                subtitle = stem
            else:
                real_named_senders = [s for s in senders_clean if is_real_contact_name(s)]
                title = real_named_senders[0] if real_named_senders else stem
                subtitle = stem
            initials = get_initials(title)
            address = stem
        elif stem.startswith("+"):
            category = "direct"
            formatted_phone = format_phone_number(stem)
            if stem in phone_to_name:
                title = phone_to_name[stem]
                subtitle = formatted_phone
            else:
                real_named_senders = [s for s in senders_clean if is_real_contact_name(s)]
                if real_named_senders:
                    title = real_named_senders[0]
                    subtitle = formatted_phone
                else:
                    title = formatted_phone
                    subtitle = "Direct Message"
            initials = get_initials(title) if title != formatted_phone else stem[-2:]
            address = formatted_phone
        else:
            digits = re.sub(r'\D', '', stem)
            if len(digits) in (3, 4, 5, 6):
                category = "shortcode"
                real_named_senders = [s for s in senders_clean if is_real_contact_name(s)]
                if real_named_senders:
                    title = real_named_senders[0]
                    subtitle = f"Service ({stem})"
                else:
                    title = f"Service {stem}"
                    subtitle = "Automated SMS Service"
                initials = "🤖"
                address = stem
            else:
                category = "direct"
                title = stem
                subtitle = "Direct Message"
                initials = get_initials(stem)
                address = stem

        return {
            "filename": filename,
            "url": urllib.parse.quote(filename),
            "title": title,
            "category": category,
            "initials": initials,
            "subtitle": subtitle,
            "address": address,
            "avatar_color": hash_color(title),
            "msg_count": msgs,
            "first_date": first_date_str,
            "last_date": last_date_str,
            "first_date_iso": first_date_iso,
            "last_date_iso": last_date_iso,
            "last_preview": last_preview,
            "senders": senders_clean[:5],
            "file_size": os.path.getsize(filepath)
        }

    except Exception as e:
        return {
            "filename": filename,
            "url": urllib.parse.quote(filename),
            "title": filename,
            "category": "direct",
            "initials": "?",
            "subtitle": f"Error: {e}",
            "address": "",
            "avatar_color": "#8E8E93",
            "msg_count": 0,
            "first_date": "",
            "last_date": "",
            "first_date_iso": "",
            "last_date_iso": "",
            "last_preview": f"Error: {e}",
            "senders": [],
            "file_size": 0
        }

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>iMessage Export Viewer</title>
  <style>
    :root {
      --bg-primary: #ffffff;
      --bg-sidebar: #f6f6f8;
      --bg-hover: #e8e8ed;
      --bg-active: #007aff;
      --text-primary: #1c1c1e;
      --text-secondary: #8e8e93;
      --text-active: #ffffff;
      --border-color: #d1d1d6;
      --bubble-date: #8e8e93;
      --badge-bg: #e5e5ea;
      --badge-text: #3a3a3c;
      --header-bg: rgba(246, 246, 248, 0.92);
      --search-bg: #e3e3e8;
      --font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    }

    @media (prefers-color-scheme: dark) {
      :root {
        --bg-primary: #000000;
        --bg-sidebar: #1c1c1e;
        --bg-hover: #2c2c2e;
        --bg-active: #0a84ff;
        --text-primary: #f2f2f7;
        --text-secondary: #8e8e93;
        --text-active: #ffffff;
        --border-color: #38383a;
        --bubble-date: #8e8e93;
        --badge-bg: #2c2c2e;
        --badge-text: #aeaeb2;
        --header-bg: rgba(28, 28, 30, 0.92);
        --search-bg: #2c2c2e;
      }
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: var(--font-family);
      background-color: var(--bg-primary);
      color: var(--text-primary);
      height: 100vh;
      overflow: hidden;
      display: flex;
    }

    #app {
      display: flex;
      width: 100vw;
      height: 100vh;
      overflow: hidden;
    }

    /* Sidebar */
    .sidebar {
      width: 380px;
      min-width: 320px;
      max-width: 450px;
      background: var(--bg-sidebar);
      border-right: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      height: 100%;
      flex-shrink: 0;
      transition: transform 0.25s ease;
      z-index: 10;
    }

    .sidebar-header {
      padding: 16px 16px 12px 16px;
      background: var(--header-bg);
      backdrop-filter: blur(15px);
      -webkit-backdrop-filter: blur(15px);
      border-bottom: 1px solid var(--border-color);
      position: sticky;
      top: 0;
      z-index: 5;
    }

    .header-title-row {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      margin-bottom: 10px;
    }

    .header-title-row h1 {
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }

    .stats-badge {
      font-size: 13px;
      color: var(--text-secondary);
      font-weight: 500;
    }

    .search-container {
      position: relative;
      margin-bottom: 10px;
    }

    .search-input {
      width: 100%;
      padding: 8px 12px 8px 34px;
      font-size: 14px;
      background: var(--search-bg);
      border: 1px solid transparent;
      border-radius: 10px;
      color: var(--text-primary);
      outline: none;
      transition: all 0.2s;
    }

    .search-input:focus {
      background: var(--bg-primary);
      border-color: #007aff;
      box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.2);
    }

    .search-icon {
      position: absolute;
      left: 10px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-secondary);
      font-size: 14px;
      pointer-events: none;
    }

    .clear-search {
      position: absolute;
      right: 10px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-secondary);
      font-size: 14px;
      cursor: pointer;
      display: none;
    }

    .filter-pills {
      display: flex;
      gap: 6px;
      overflow-x: auto;
      padding-bottom: 4px;
      scrollbar-width: none;
    }
    .filter-pills::-webkit-scrollbar {
      display: none;
    }

    .filter-pill {
      font-size: 12px;
      font-weight: 500;
      padding: 5px 10px;
      border-radius: 14px;
      background: var(--badge-bg);
      color: var(--text-secondary);
      border: none;
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.15s;
    }

    .filter-pill.active {
      background: var(--text-primary);
      color: var(--bg-primary);
    }

    .sort-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 8px;
      font-size: 12px;
      color: var(--text-secondary);
    }

    .sort-select {
      background: transparent;
      border: none;
      font-size: 12px;
      color: #007aff;
      font-weight: 500;
      cursor: pointer;
      outline: none;
    }

    /* Conversation List */
    .chat-list {
      flex: 1;
      overflow-y: auto;
      list-style: none;
    }

    .chat-item {
      display: flex;
      align-items: center;
      padding: 12px 16px;
      border-bottom: 1px solid var(--border-color);
      cursor: pointer;
      transition: background-color 0.1s;
      gap: 12px;
    }

    .chat-item:hover {
      background-color: var(--bg-hover);
    }

    .chat-item.active {
      background-color: var(--bg-active);
      color: var(--text-active);
    }

    .chat-item.active .chat-date,
    .chat-item.active .chat-preview,
    .chat-item.active .chat-subline {
      color: rgba(255, 255, 255, 0.85);
    }

    .chat-item.active .chat-badge {
      background: rgba(255, 255, 255, 0.25);
      color: #ffffff;
    }

    .avatar {
      width: 44px;
      height: 44px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 600;
      font-size: 16px;
      color: #ffffff;
      flex-shrink: 0;
      text-transform: uppercase;
      user-select: none;
      box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }

    .chat-info {
      flex: 1;
      min-width: 0;
    }

    .chat-top-row {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 2px;
    }

    .chat-name {
      font-size: 15px;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      padding-right: 8px;
    }

    .chat-date {
      font-size: 12px;
      color: var(--bubble-date);
      white-space: nowrap;
      font-weight: 400;
    }

    .chat-subline {
      font-size: 11px;
      color: var(--text-secondary);
      margin-bottom: 2px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .chat-bottom-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }

    .chat-preview {
      font-size: 13px;
      color: var(--text-secondary);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      flex: 1;
    }

    .chat-badge {
      font-size: 11px;
      font-weight: 600;
      background: var(--badge-bg);
      color: var(--badge-text);
      padding: 2px 7px;
      border-radius: 10px;
      white-space: nowrap;
    }

    /* Main Reading Pane */
    .main-view {
      flex: 1;
      display: flex;
      flex-direction: column;
      height: 100%;
      background: var(--bg-primary);
      position: relative;
    }

    .main-header {
      height: 60px;
      padding: 0 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--border-color);
      background: var(--header-bg);
      backdrop-filter: blur(15px);
      -webkit-backdrop-filter: blur(15px);
      z-index: 5;
      gap: 12px;
    }

    .main-header-info {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
      flex: 1;
    }

    .back-btn {
      display: none;
      background: none;
      border: none;
      font-size: 16px;
      color: #007aff;
      cursor: pointer;
      font-weight: 500;
      align-items: center;
      gap: 4px;
    }

    .main-title-container {
      min-width: 0;
    }

    .main-title {
      font-size: 16px;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .main-subtitle {
      font-size: 12px;
      color: var(--text-secondary);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .main-actions {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-shrink: 0;
    }

    .action-btn {
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 500;
      border-radius: 8px;
      text-decoration: none;
      border: 1px solid var(--border-color);
      background: var(--bg-sidebar);
      color: var(--text-primary);
      display: inline-flex;
      align-items: center;
      gap: 4px;
      cursor: pointer;
      transition: all 0.15s;
      white-space: nowrap;
    }

    .action-btn:hover {
      background: var(--bg-hover);
      color: var(--bg-active);
      border-color: var(--bg-active);
    }

    .iframe-container {
      flex: 1;
      width: 100%;
      height: calc(100% - 60px);
      position: relative;
      background: var(--bg-primary);
    }

    iframe {
      width: 100%;
      height: 100%;
      border: none;
      display: block;
      background: var(--bg-primary);
    }

    .empty-state {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100%;
      color: var(--text-secondary);
      text-align: center;
      padding: 20px;
    }

    .empty-icon {
      font-size: 64px;
      margin-bottom: 16px;
      opacity: 0.8;
    }

    .empty-state h2 {
      font-size: 20px;
      font-weight: 600;
      margin-bottom: 8px;
      color: var(--text-primary);
    }

    .empty-state p {
      font-size: 14px;
      max-width: 320px;
      line-height: 1.4;
    }

    @media (max-width: 768px) {
      .sidebar {
        width: 100vw;
        max-width: 100vw;
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
      }
      .sidebar.hidden {
        transform: translateX(-100%);
      }
      .back-btn {
        display: inline-flex;
      }
    }
  </style>
</head>
<body>
  <div id="app">
    <!-- Sidebar -->
    <aside class="sidebar" id="sidebar">
      <div class="sidebar-header">
        <div class="header-title-row">
          <h1>Messages</h1>
          <span class="stats-badge" id="statsBadge">...</span>
        </div>
        
        <div class="search-container">
          <span class="search-icon">🔍</span>
          <input type="text" id="searchInput" class="search-input" placeholder="Search contacts, numbers, or messages..." autocomplete="off">
          <span id="clearSearch" class="clear-search">✕</span>
        </div>

        <div class="filter-pills" id="filterPills">
          <button class="filter-pill active" data-filter="all">All</button>
          <button class="filter-pill" data-filter="direct">Direct</button>
          <button class="filter-pill" data-filter="group">Groups</button>
          <button class="filter-pill" data-filter="shortcode">Services</button>
          <button class="filter-pill" data-filter="email">Email</button>
        </div>

        <div class="sort-row">
          <span id="matchCount">0 conversations</span>
          <select id="sortSelect" class="sort-select">
            <option value="recent">Sort: Most Recent</option>
            <option value="messages">Sort: Most Messages</option>
            <option value="alphabetical">Sort: Name (A-Z)</option>
          </select>
        </div>
      </div>

      <ul class="chat-list" id="chatList"></ul>
    </aside>

    <!-- Reading View -->
    <main class="main-view" id="mainView">
      <div class="main-header" id="mainHeader" style="display: none;">
        <div class="main-header-info">
          <button class="back-btn" id="backBtn">❮ Chats</button>
          <div class="avatar" id="mainAvatar" style="width: 36px; height: 36px; font-size: 14px;"></div>
          <div class="main-title-container">
            <div class="main-title" id="mainTitle"></div>
            <div class="main-subtitle" id="mainSubtitle"></div>
          </div>
        </div>

        <!-- Navigation Toolbar: Jump Top/Bottom, Jump to Date, Order -->
        <div class="main-actions">
          <button class="action-btn" id="headerScrollTopBtn" title="Go to top of messages">
            <span>⬆</span> Top
          </button>
          <button class="action-btn" id="headerScrollBottomBtn" title="Go to bottom of messages">
            <span>⬇</span> Bottom
          </button>
          <button class="action-btn" id="headerTimelineBtn" title="Jump to month and year">
            <span>📅</span> Jump to Date
          </button>
          <a href="#" id="openNewTabBtn" target="_blank" class="action-btn" title="Open transcript in a new tab">
            <span>↗</span>
          </a>
        </div>
      </div>

      <div class="iframe-container" id="iframeContainer">
        <div class="empty-state" id="emptyState">
          <div class="empty-icon">💬</div>
          <h2>Select a Conversation</h2>
          <p>Choose any contact or thread from the sidebar to view your exported messages.</p>
        </div>
        <iframe id="chatFrame" style="display: none;"></iframe>
      </div>
    </main>
  </div>

  <script>
    const CONVERSATIONS = __CHAT_DATA_JSON__;

    let currentFilter = 'all';
    let currentSort = 'recent';
    let searchQuery = '';
    let selectedChat = null;

    const chatList = document.getElementById('chatList');
    const searchInput = document.getElementById('searchInput');
    const clearSearch = document.getElementById('clearSearch');
    const filterPills = document.getElementById('filterPills');
    const sortSelect = document.getElementById('sortSelect');
    const statsBadge = document.getElementById('statsBadge');
    const matchCount = document.getElementById('matchCount');
    const sidebar = document.getElementById('sidebar');
    const backBtn = document.getElementById('backBtn');
    const chatFrame = document.getElementById('chatFrame');
    const emptyState = document.getElementById('emptyState');
    const mainHeader = document.getElementById('mainHeader');
    const mainTitle = document.getElementById('mainTitle');
    const mainSubtitle = document.getElementById('mainSubtitle');
    const mainAvatar = document.getElementById('mainAvatar');
    const openNewTabBtn = document.getElementById('openNewTabBtn');
    const headerScrollTopBtn = document.getElementById('headerScrollTopBtn');
    const headerScrollBottomBtn = document.getElementById('headerScrollBottomBtn');
    const headerTimelineBtn = document.getElementById('headerTimelineBtn');

    const totalMsgs = CONVERSATIONS.reduce((sum, c) => sum + (c.msg_count || 0), 0);
    statsBadge.textContent = `${CONVERSATIONS.length.toLocaleString()} chats · ${totalMsgs.toLocaleString()} msgs`;

    function formatDisplayDate(isoOrStr) {
      if (!isoOrStr) return '';
      try {
        const d = new Date(isoOrStr);
        if (isNaN(d.getTime())) return isoOrStr.split(' ')[0] || '';
        const now = new Date();
        const diffDays = Math.floor((now - d) / (1000 * 60 * 60 * 24));
        if (diffDays < 1) {
          return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } else if (diffDays < 7) {
          return d.toLocaleDateString([], { weekday: 'short' });
        } else if (d.getFullYear() === now.getFullYear()) {
          return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
        } else {
          return d.toLocaleDateString([], { month: 'numeric', day: 'numeric', year: '2-digit' });
        }
      } catch (e) {
        return '';
      }
    }

    function renderList() {
      const q = searchQuery.toLowerCase().trim();
      let filtered = CONVERSATIONS.filter(item => {
        if (currentFilter !== 'all' && item.category !== currentFilter) {
          return false;
        }
        if (!q) return true;
        return (
          item.title.toLowerCase().includes(q) ||
          item.filename.toLowerCase().includes(q) ||
          (item.address && item.address.toLowerCase().includes(q)) ||
          (item.subtitle && item.subtitle.toLowerCase().includes(q)) ||
          (item.last_preview && item.last_preview.toLowerCase().includes(q)) ||
          (item.senders && item.senders.some(s => s.toLowerCase().includes(q)))
        );
      });

      filtered.sort((a, b) => {
        if (currentSort === 'recent') {
          const da = a.last_date_iso || '';
          const db = b.last_date_iso || '';
          return db.localeCompare(da);
        } else if (currentSort === 'messages') {
          return (b.msg_count || 0) - (a.msg_count || 0);
        } else if (currentSort === 'alphabetical') {
          return a.title.localeCompare(b.title);
        }
        return 0;
      });

      matchCount.textContent = `${filtered.length.toLocaleString()} of ${CONVERSATIONS.length.toLocaleString()}`;

      chatList.innerHTML = '';
      if (filtered.length === 0) {
        chatList.innerHTML = `
          <li style="padding: 30px 16px; text-align: center; color: var(--text-secondary); font-size: 14px;">
            No conversations found matching "${escapeHtml(q)}"
          </li>`;
        return;
      }

      const fragment = document.createDocumentFragment();
      filtered.forEach(chat => {
        const li = document.createElement('li');
        li.className = 'chat-item' + (selectedChat && selectedChat.filename === chat.filename ? ' active' : '');
        li.dataset.filename = chat.filename;

        const displayDate = formatDisplayDate(chat.last_date_iso || chat.last_date);
        
        const hasSubline = chat.address && chat.address !== chat.title;
        const sublineHtml = hasSubline ? `<div class="chat-subline">${escapeHtml(chat.address)}</div>` : '';

        li.innerHTML = `
          <div class="avatar" style="background-color: ${chat.avatar_color};">${escapeHtml(chat.initials)}</div>
          <div class="chat-info">
            <div class="chat-top-row">
              <span class="chat-name" title="${escapeHtml(chat.title)}">${escapeHtml(chat.title)}</span>
              <span class="chat-date">${escapeHtml(displayDate)}</span>
            </div>
            ${sublineHtml}
            <div class="chat-bottom-row">
              <span class="chat-preview">${escapeHtml(chat.last_preview || 'No messages')}</span>
              <span class="chat-badge">${(chat.msg_count || 0).toLocaleString()}</span>
            </div>
          </div>
        `;

        li.addEventListener('click', () => selectChat(chat));
        fragment.appendChild(li);
      });

      chatList.appendChild(fragment);
    }

    function selectChat(chat) {
      selectedChat = chat;

      document.querySelectorAll('.chat-item').forEach(item => {
        item.classList.toggle('active', item.dataset.filename === chat.filename);
      });

      mainHeader.style.display = 'flex';
      mainTitle.textContent = chat.title;
      mainTitle.title = chat.title;
      mainAvatar.textContent = chat.initials;
      mainAvatar.style.backgroundColor = chat.avatar_color;

      const dateSpan = (chat.first_date && chat.last_date && chat.first_date !== chat.last_date)
        ? `${chat.first_date.split('  ')[0]} – ${chat.last_date.split('  ')[0]}`
        : (chat.last_date || '');

      const subInfo = [chat.subtitle || chat.address, `${(chat.msg_count || 0).toLocaleString()} messages`, dateSpan]
        .filter(Boolean)
        .join(' · ');

      mainSubtitle.textContent = subInfo;
      openNewTabBtn.href = chat.url;

      emptyState.style.display = 'none';
      chatFrame.style.display = 'block';
      if (chatFrame.getAttribute('src') !== chat.url) {
        chatFrame.src = chat.url;
      }

      window.history.replaceState(null, '', '#' + chat.url);

      if (window.innerWidth <= 768) {
        sidebar.classList.add('hidden');
      }
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    headerScrollTopBtn.addEventListener('click', () => {
      if (chatFrame && chatFrame.contentWindow) {
        chatFrame.contentWindow.postMessage({ action: 'scrollToTop' }, '*');
      }
    });

    headerScrollBottomBtn.addEventListener('click', () => {
      if (chatFrame && chatFrame.contentWindow) {
        chatFrame.contentWindow.postMessage({ action: 'scrollToBottom' }, '*');
      }
    });

    headerTimelineBtn.addEventListener('click', () => {
      if (chatFrame && chatFrame.contentWindow) {
        chatFrame.contentWindow.postMessage({ action: 'toggleDrawer' }, '*');
      }
    });

    searchInput.addEventListener('input', (e) => {
      searchQuery = e.target.value;
      clearSearch.style.display = searchQuery ? 'block' : 'none';
      renderList();
    });

    clearSearch.addEventListener('click', () => {
      searchInput.value = '';
      searchQuery = '';
      clearSearch.style.display = 'none';
      renderList();
      searchInput.focus();
    });

    filterPills.addEventListener('click', (e) => {
      if (e.target.classList.contains('filter-pill')) {
        document.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        currentFilter = e.target.dataset.filter;
        renderList();
      }
    });

    sortSelect.addEventListener('change', (e) => {
      currentSort = e.target.value;
      renderList();
    });

    backBtn.addEventListener('click', () => {
      sidebar.classList.remove('hidden');
    });

    window.addEventListener('DOMContentLoaded', () => {
      renderList();

      const hash = window.location.hash.slice(1);
      if (hash) {
        const found = CONVERSATIONS.find(c => c.url === hash || c.filename === decodeURIComponent(hash));
        if (found) {
          selectChat(found);
          return;
        }
      }
      
      if (window.innerWidth > 768 && CONVERSATIONS.length > 0) {
        const sorted = [...CONVERSATIONS].sort((a,b) => (b.last_date_iso || '').localeCompare(a.last_date_iso || ''));
        if (sorted.length > 0) {
          selectChat(sorted[0]);
        }
      }
    });
  </script>
</body>
</html>
"""

def main():
    parser = argparse.ArgumentParser(
        description="Generate a modern, responsive Apple Messages-style index.html for imessage-exporter exports."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Path to the directory containing imessage-exporter HTML files (defaults to current directory)."
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )
    args = parser.parse_args()

    target_dir = os.path.abspath(args.directory)
    if not os.path.isdir(target_dir):
        print(f"Error: Directory '{target_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning iMessage export in: {target_dir}")

    # Ensure style.css and viewer_helper.js exist in target directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for helper_file in ("style.css", "viewer_helper.js"):
        src = os.path.join(script_dir, helper_file)
        dst = os.path.join(target_dir, helper_file)
        if os.path.exists(src) and src != dst:
            shutil.copy2(src, dst)

    all_files = [
        os.path.join(target_dir, f)
        for f in os.listdir(target_dir)
        if f.endswith(".html") and f != "index.html" and not f.startswith(".")
    ]

    if not all_files:
        print(f"No conversation HTML files found in '{target_dir}'.", file=sys.stderr)
        sys.exit(1)

    phone_to_name, email_to_name = build_contact_directory(all_files)

    print(f"Pass 2: Processing {len(all_files)} conversations with resolved contact names...")
    conversations = []
    for f in all_files:
        conv = parse_conversation(f, phone_to_name, email_to_name)
        conversations.append(conv)

    conversations.sort(key=lambda c: c.get("last_date_iso") or "", reverse=True)

    print(f"Generating index.html with {len(conversations)} conversations...")
    json_data = json.dumps(conversations, ensure_ascii=False)
    index_content = HTML_TEMPLATE.replace("__CHAT_DATA_JSON__", json_data)

    output_path = os.path.join(target_dir, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(index_content)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"SUCCESS! Created {output_path} ({size_mb:.2f} MB)")

if __name__ == "__main__":
    main()
