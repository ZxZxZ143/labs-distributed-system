"""Capture local evidence HTML pages using an isolated headless browser profile."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    candidates = [os.environ.get("CHROME_EXECUTABLE"),
                  r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  shutil.which("chromium"), shutil.which("google-chrome")]
    browser = next((p for p in candidates if p and Path(p).is_file()), None)
    if not browser:
        raise RuntimeError("Set CHROME_EXECUTABLE to a Chromium browser executable")
    for page in sorted((ROOT / "screenshots" / "lab5").glob("*.html")):
        target = page.with_suffix(".png")
        with tempfile.TemporaryDirectory(prefix="lab5-browser-") as profile:
            result = subprocess.run([browser, "--headless", "--disable-gpu", "--no-first-run",
                                     "--no-default-browser-check", "--hide-scrollbars",
                                     "--window-size=1600,1400", "--user-data-dir=" + profile,
                                     "--screenshot=" + str(target), page.as_uri()],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
            if result.returncode or not target.is_file():
                raise RuntimeError(result.stderr.decode(errors="replace"))
        print(target)


if __name__ == "__main__":
    main()
