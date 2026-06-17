from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
ZIP_PATH = ROOT.parent / "crm_flask.zip"
SKIP_DIRS = {"venv", "__pycache__", ".git", ".pytest_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".pyd", ".log"}
SKIP_NAMES = {".env", "crm_flask.zip"}
SENSITIVE_PATTERNS = ("service-account", "credentials")
RUNTIME_DIRS = {"uploads", "exports"}
RUNTIME_SUFFIXES = {".sqlite", ".db"}


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP_DIRS:
        return True
    if path.name in SKIP_NAMES:
        return True
    if path.suffix in SKIP_SUFFIXES:
        return True
    if any(pattern in path.name.lower() for pattern in SENSITIVE_PATTERNS):
        return True
    if path.parts and path.parts[0] == "instance" and path.suffix.lower() in RUNTIME_SUFFIXES:
        return True
    if path.parts and path.parts[0] in RUNTIME_DIRS and path.name != ".gitkeep":
        return True
    return False


def main():
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with ZipFile(ZIP_PATH, "w", ZIP_DEFLATED) as zf:
        for path in ROOT.rglob("*"):
            rel = path.relative_to(ROOT)
            if path.is_file() and not should_skip(rel):
                zf.write(path, path.relative_to(ROOT.parent))
    print(f"Created {ZIP_PATH}")


if __name__ == "__main__":
    main()
