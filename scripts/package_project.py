"""Create a source-only ZIP without databases, environments, or local reports."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parent.parent
    destination = root / "dist" / "ecommerce-flashsale-testing.zip"
    destination.parent.mkdir(exist_ok=True)
    folders = ("app", "tests", "performance", "scripts", "docs", ".github")
    files = [root / name for name in ("README.md", "LICENSE", ".gitignore", "pytest.ini",
             "requirements.txt", "requirements-ui.txt", "requirements-performance.txt")]
    for folder in folders:
        files.extend(path for path in (root / folder).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    files.append(root / "reports" / ".gitkeep")
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, "ecommerce-flashsale-testing/" + path.relative_to(root).as_posix())
    print(f"Created {destination} ({len(files)} files)")


if __name__ == "__main__":
    main()
