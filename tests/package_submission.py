"""Create the required ZIP from an explicit allowlist and verify its contents."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package():
    names = ["README.md", "spec.md", "test_report.md", "docker-compose.yml",
             "nginx.conf", "init-replica.js", "requirements-test.txt"]
    files = [ROOT / name for name in names]
    for folder in ("app", "tests", "logs/lab5", "screenshots/lab5"):
        files += [p for p in (ROOT / folder).rglob("*") if p.is_file()
                  and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    for p in files:
        if not p.is_file():
            raise FileNotFoundError(p)
    destination = ROOT / "dist" / "kurlykov_yevgenii_Lab5.zip"
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(files):
            z.write(p, p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(destination) as z:
        assert z.testzip() is None
        assert all(name in z.namelist() for name in names)
        assert not any(any(part in {".git", ".venv", "__pycache__", ".env"} for part in Path(name).parts) for name in z.namelist())
        print(f"{destination}\n{len(z.namelist())} files, {destination.stat().st_size} bytes; CRC verified")


if __name__ == "__main__":
    package()
