# iMessage Export UI

[![License: BSD 3-Clause](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg)](LICENSE)
[![Python: 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![Platform: macOS | Linux | Windows](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)](https://github.com/fstshrk/iMessage-export-ui)

A modern, responsive, **Apple Messages**-style front-end and index generator for iMessage backups created with [`imessage-exporter`](https://github.com/ReagentX/imessage-exporter).

---

## 💡 Why This Exists

[`imessage-exporter`](https://github.com/ReagentX/imessage-exporter) is an outstanding tool for exporting Apple iMessage SQLite databases (`chat.db`) to portable formats. However, when exporting to HTML, it produces hundreds or thousands of individual, unindexed `.html` files in a flat folder with no top-level index or navigation dashboard. Finding a specific conversation or reading long threads in a folder full of raw phone numbers can be daunting.

**iMessage Export UI** solves this:
1. It scans your export folder and builds a **unified Apple Messages-style web app** (`index.html`).
2. It automatically **resolves phone numbers to real contact names** by cross-referencing message transcripts, mentions, and tapback attributions.
3. It defaults to **showing the most current messages at the top** so you don't have to scroll through years of history to see recent messages.
4. It provides an interactive **Month & Year date scrubber** and a **timeline jump drawer** to instantly jump to any time period.

```text
┌─────────────────────────────────┬────────────────────────────────────────────────────────┐
│ 🔍 Search contacts, messages... │ 👤 Bob Smith   +1 (555) 555-2239                      │
│ [All] [Direct] [Groups] [Email] │ [⬆ Top]  [⬇ Bottom]  [📅 Jump to Date]  [↗ Open Tab] │
├─────────────────────────────────┼────────────────────────────────────────────────────────┤
│ (NA) Alice Crypto       2:15 PM │   ┌──────────────────────────────────────────────────┐ │
│      See you tonight!       142 │   │              📅 October 2026  ▾                  │ │
│                                 │   │                                                  │ │
│ (TM) Bob Smith    Yesterday     │   │ [Me] Hi Bob,  did you get the documents?         │ │
│      Thanks, looks great!    56 │   │ [Bob ] Yes, looks great! Thanks for sending!     │ │
│                                 │   │        ❤️ Loved by Bob Smith.                    │ │
│ (👥) Recep, Sertap       Oct 22 │   │                                                  │ │
│      No problem at all       28 │   │ [Me] Sounds like a plan!                         │ │
└─────────────────────────────────┴────────────────────────────────────────────────────────┘
```

---

## ✨ Features

- **🖥️ Apple Messages Split View**:
  - **Sidebar**: Real-time search across contacts, phone numbers, emails, and message snippets. Filter pills (*All*, *Direct*, *Groups*, *Services*, *Email*) and sort options (*Most Recent*, *Message Count*, *A-Z*).
  - **Reading Pane**: Full-fidelity transcript viewer embedding the original conversation HTML with light/dark appearance support.
- **👤 Automatic Contact Name Resolution**:
  - Automatically correlates handles with real contact names found in transcripts, `<span class="sender">` tags, tapback attributions, and mention tags.
  - Replaces cryptic filenames like `+15033302239.html` with friendly names like **Tony McCormick** (with the underlying phone number shown neatly in a subtitle).
- **⏱️ Most Current Messages on Top**:
  - Automatically orders conversation messages newest-first by default so you see the latest messages immediately.
  - Includes a `⇅ Newest First` / `⇅ Oldest First` toggle button to switch back to chronological order anytime.
- **📅 Dynamic Month & Year Scroll Indicator**:
  - As you scroll through a long thread, a floating frosted-glass pill (`📅 October 2026`) appears, updating in real time with the month and year of the messages currently in view.
- **⚡ Quick-Jump Timeline Drawer**:
  - Click the date pill or the **"Jump to Date"** header button to open an interactive drawer grouped by year. Click any month (e.g. `August (80 msgs)`) to smooth-scroll directly to that time window with a brief highlight pulse.
- **⬆️⬇️ Top & Bottom Navigation**:
  - Dedicated buttons in both the header bar and floating navigation to quickly jump between the top and bottom of the transcript.
- **📎 Full Media Fidelity**:
  - Retains all inline photos (JPEG), videos (MP4), audio voice notes, stickers, and tapbacks rendered by `imessage-exporter`.
- **🌙 Automatic Dark Mode**:
  - Adapts automatically to your macOS / system theme preference.
- **🔒 100% Offline & Private**:
  - All processing and viewing happens entirely on your local machine. No external servers, no CDNs, no tracking.
- **📦 Zero External Dependencies**:
  - Built with pure Python standard library (`os`, `re`, `sys`, `json`, `html`, `pathlib`, `datetime`, `collections`, `shutil`, `argparse`). No `pip install` required!

---

## 🚀 Step-by-Step Usage

### Step 1: Export Your Messages

Export your iMessage database using [`imessage-exporter`](https://github.com/ReagentX/imessage-exporter).

We recommend using the **HTML format** (`-f html`) with **full copy method** (`-c full`), which automatically converts Apple HEIC photos to JPEG and CAF/MOV media to MP4 for universal browser playback:

```bash
imessage-exporter -f html -c full -o ~/imessage_export
```

### Step 2: Generate the Web Viewer

Clone or download this repository, then run `generate_index.py` pointing to your export folder:

```bash
# Clone this repo
git clone https://github.com/fstshrk/iMessage-export-ui.git
cd iMessage-export-ui

# Run the generator pointing to your export folder
python3 generate_index.py ~/imessage_export
```

*Or, if you copied the scripts directly into your export folder, simply run:*

```bash
python3 generate_index.py
```

The script will:
1. Scan all transcripts and build the contact mapping dictionary.
2. Link the enhanced viewer helper (`viewer_helper.js` and `style.css`).
3. Generate a fast, self-contained `index.html` file in the export directory.

### Step 3: Open and Browse

Open `index.html` directly in your default browser:

```bash
open ~/imessage_export/index.html
```

Or serve it locally:

```bash
cd ~/imessage_export
python3 -m http.server 8000
# Open http://localhost:8000 in your browser
```

---

## 🛠️ Command-Line Options

```text
usage: generate_index.py [-h] [-v] [directory]

Generate a modern, responsive Apple Messages-style index.html for imessage-exporter exports.

positional arguments:
  directory      Path to the directory containing imessage-exporter HTML files
                 (defaults to current directory).

options:
  -h, --help     show this help message and exit
  -v, --version  show program's version number and exit
```

---

## 📁 Repository Structure

```text
├── generate_index.py    # Main Python index generator & contact mapper
├── viewer_helper.js     # Client-side helper (reordering, scroll indicator, jump drawer)
├── style.css            # Stylesheet for floating navigation & timeline controls
├── run.sh               # Quick execution runner
├── pyproject.toml       # Python packaging specification
├── LICENSE              # BSD 3-Clause License
├── .gitignore           # Strictly ignores all personal data (*.html, attachments/)
└── README.md            # Documentation
```

---

## 🔒 Privacy & Safety Guarantee

> [!IMPORTANT]
> The included [`.gitignore`](.gitignore) is pre-configured to ignore all `*.html` files (including `index.html`), all attachments (`attachments/`), and virtual environments. Your personal chat transcripts and media files will **never** be staged or committed to git.

---

## 📄 License

This project is licensed under the **BSD 3-Clause License**. See the [LICENSE](LICENSE) file for details.
