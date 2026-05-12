# mania-inverse-generator

A tool for converting osu!mania tap notes into Long Note (LN) inverse patterns.
Supports any key count (4K, 7K, etc.) and auto-detects the current map via tosu.

Inspired by and based on the original work of
[indekkusu-era (howtoplayLN)](https://github.com/indekkusu-era/InverseGenerator).
The original project was outdated and no longer maintained, so this is a modernized
version with improved integrations and real-time map detection via tosu.

---

## Features

- ✅ Supports any osu!mania key count (4K, 7K, and more)
- ✅ Auto-detects the current map via [tosu](https://github.com/tosuapp/tosu)
- ✅ Auto-detects song folder from osu! config
- ✅ Bookmark-based sections with manual gap control per section
- ✅ Auto-detects sections when no bookmarks are present
- ✅ Custom LN gap (1/4, 1/6, 1/8, 1/12, 1/16, or any custom value)
- ✅ Automatically avoids overwriting existing files (versioning)
- ✅ Dark UI built with PySide6

---

## Requirements

- Windows 10/11
- [osu!](https://osu.ppy.sh) (stable)
- [tosu](https://github.com/tosuapp/tosu) (optional, for auto-detection)

---

## Download

Go to the [Releases](https://github.com/memo2138/mania-inverse-generator/releases)
page and download the latest `ManiaInverseGenerator.exe`.

> ⚠️ Some antivirus software may flag this file as suspicious.
> This is a known false positive with PyInstaller-packaged apps.
> The source code is fully open — you can audit it or build it yourself.

---

## How to use

1. Open tosu and osu! for auto-detection, or click **"browse manually"** to select a `.osu` file.
2. The app shows the detected sections (from bookmarks, or auto-detected).
3. Set the LN gap for each section (default: 1/4).
4. Click **"Generate inverse"**.
5. The new `.osu` file is saved next to the original map.

---

## Building from source

```bash
git clone https://github.com/memo2138/mania-inverse-generator.git
cd mania-inverse-generator
pip install -r requirements.txt
python app.py
```

---

## Credits

- Original concept and algorithm:
  [indekkusu-era / InverseGenerator](https://github.com/indekkusu-era/InverseGenerator)
- Real-time map detection: [tosu](https://github.com/tosuapp/tosu)
- Built with [PySide6](https://doc.qt.io/qtforpython/)

---

*Made with ♥ for the osu!mania LN community.*
