"""Buduje archiwum integracji z plików śledzonych przez Git."""

import argparse
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = Path("custom_components/dlms_reader")


def package(output, version=None, root=ROOT):
    manifest = json.loads((root / INTEGRATION / "manifest.json").read_text())
    if version is not None and version.removeprefix("v") != manifest["version"]:
        raise ValueError("Wersja wydania nie odpowiada wersji w manifest.json.")
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z", "--", INTEGRATION.as_posix()], cwd=root
    ).decode().split("\0")
    files = [Path(name) for name in tracked if name]
    required = {"__init__.py", "manifest.json", "LICENSE", "brand/icon.png", "translations/pl.json"}
    included = {file.relative_to(INTEGRATION).as_posix() for file in files}
    if not required <= included:
        raise ValueError("Brakuje wymaganych plików integracji: " + ", ".join(sorted(required - included)))
    for file in files:
        if (root / file).is_symlink() or not (root / file).is_file():
            raise ValueError("Archiwum może zawierać tylko zwykłe pliki integracji.")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(files):
            info = zipfile.ZipInfo(file.relative_to("custom_components").as_posix())
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (root / file).read_bytes())
    return manifest["version"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", help="Wersja lub tag sprawdzany względem manifest.json.")
    args = parser.parse_args()
    print("Przygotowano integrację", package(args.output, args.version), "w", args.output)
