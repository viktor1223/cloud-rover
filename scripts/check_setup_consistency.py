#!/usr/bin/env python3
"""
Cloud Rover — Setup Consistency Checker

Validates that all three sources of truth stay in sync:
  1. Python code (imports in pi/*.py, cloud/*.py)
  2. Setup scripts (scripts/pi-setup.sh, pi/requirements.txt)
  3. Documentation (docs/PI_SETUP.md)

Run locally:       python3 scripts/check_setup_consistency.py
Run in CI:         triggered automatically on PRs to main

Exit code 0 = all checks pass, 1 = mismatches found.
"""
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ── Mapping: Python import name → apt package or requirements.txt name ──────
# Only non-stdlib packages. Key = Python import, Value = (apt_pkg, pip_pkg)
IMPORT_TO_PACKAGE = {
    "picamera2":  ("python3-picamera2", "picamera2"),
    "gpiozero":   ("python3-gpiozero",  "gpiozero"),
    "pigpio":     ("python3-pigpio",     "pigpio"),
    "requests":   ("python3-requests",   "requests"),
    "websockets": (None,                 "websockets"),   # pip-only
    "PIL":        ("python3-pil",        "Pillow"),
    "libcamera":  ("python3-libcamera",  None),           # apt-only
}

# Standard library modules to ignore
STDLIB = {
    "http", "json", "time", "os", "sys", "io", "threading",
    "argparse", "pathlib", "datetime", "collections", "functools",
    "subprocess", "shutil", "hashlib", "base64", "struct",
    "logging", "cgi", "math", "re", "signal", "socket",
    "unittest", "typing", "enum", "dataclasses", "abc",
}

# Camera config that must be consistent
CAMERA_CONFIG = {
    "camera_auto_detect": "0",
    "dtoverlay": "imx708",
}

errors = []
warnings = []


def error(check: str, msg: str):
    errors.append(f"  ✗ [{check}] {msg}")


def warn(check: str, msg: str):
    warnings.append(f"  ⚠ [{check}] {msg}")


def ok(msg: str):
    print(f"  ✓ {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 1: Python imports vs requirements.txt & pi-setup.sh
# ─────────────────────────────────────────────────────────────────────────────
def check_imports_vs_packages():
    """Every non-stdlib import must appear in requirements.txt OR pi-setup.sh."""
    print("\n── Check 1: Python imports vs install manifests ──")

    # Collect all imports from .py files
    py_files = list((REPO_ROOT / "pi").glob("*.py")) + \
               list((REPO_ROOT / "cloud").glob("*.py"))

    imports_found = {}  # {module_name: [file_paths]}
    for f in py_files:
        content = f.read_text()
        for line in content.splitlines():
            m = re.match(r"^\s*(?:from|import)\s+([\w\.]+)", line)
            if m:
                top_module = m.group(1).split(".")[0]
                if top_module not in STDLIB:
                    imports_found.setdefault(top_module, []).append(
                        str(f.relative_to(REPO_ROOT))
                    )

    if not imports_found:
        ok("No third-party imports found")
        return

    # Read requirements.txt
    req_file = REPO_ROOT / "pi" / "requirements.txt"
    req_packages = set()
    if req_file.exists():
        for line in req_file.read_text().splitlines():
            pkg = line.strip().split("==")[0].split(">=")[0].split("<=")[0].lower()
            if pkg:
                req_packages.add(pkg)

    # Read pi-setup.sh apt packages
    setup_file = REPO_ROOT / "scripts" / "pi-setup.sh"
    setup_content = setup_file.read_text() if setup_file.exists() else ""
    setup_apt = set(re.findall(r"python3-[\w-]+", setup_content))

    for module, files in sorted(imports_found.items()):
        pkg_info = IMPORT_TO_PACKAGE.get(module)
        if pkg_info is None:
            # Unknown package — warn but don't fail
            warn("imports", f"Unknown package '{module}' imported in {files} — "
                 "add it to IMPORT_TO_PACKAGE in check_setup_consistency.py")
            continue

        apt_pkg, pip_pkg = pkg_info
        in_apt = apt_pkg and apt_pkg in setup_apt
        in_pip = pip_pkg and pip_pkg.lower() in req_packages

        if not in_apt and not in_pip:
            error("imports", f"'{module}' imported in {files} but not in "
                  f"pi-setup.sh (as {apt_pkg}) or requirements.txt (as {pip_pkg})")
        else:
            ok(f"'{module}' → {'apt: ' + apt_pkg if in_apt else 'pip: ' + pip_pkg}")


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 2: pi-setup.sh apt packages vs docs/PI_SETUP.md
# ─────────────────────────────────────────────────────────────────────────────
def check_script_vs_docs():
    """Every apt package in pi-setup.sh must also appear in PI_SETUP.md and vice versa."""
    print("\n── Check 2: pi-setup.sh vs docs/PI_SETUP.md packages ──")

    setup_file = REPO_ROOT / "scripts" / "pi-setup.sh"
    docs_file = REPO_ROOT / "docs" / "PI_SETUP.md"

    if not setup_file.exists():
        error("script-docs", "scripts/pi-setup.sh not found")
        return
    if not docs_file.exists():
        error("script-docs", "docs/PI_SETUP.md not found")
        return

    def extract_apt_packages(text: str) -> set:
        """Extract package names from apt-get install blocks in a file."""
        pkgs = set()
        # Valid apt package name: starts with letter, contains alphanum/dots/hyphens/plus
        pkg_pattern = re.compile(r"^[a-z][a-z0-9\.\-\+]+$")
        skip_flags = {"-y", "-qq", "--yes", "--quiet", "--no-install-recommends"}
        in_install = False
        for line in text.splitlines():
            if "apt-get install" in line:
                in_install = True
                # Parse tokens after 'install'
                after = line.split("install", 1)[-1]
                for token in after.replace("\\", "").split():
                    if token not in skip_flags and not token.startswith("-") \
                       and pkg_pattern.match(token):
                        pkgs.add(token)
                if "\\" not in line:
                    in_install = False
                continue
            if in_install:
                for token in line.strip().rstrip("\\").split():
                    if token not in skip_flags and not token.startswith("#") \
                       and pkg_pattern.match(token):
                        pkgs.add(token)
                if "\\" not in line:
                    in_install = False
        return pkgs

    setup_content = setup_file.read_text()
    docs_content = docs_file.read_text()
    setup_pkgs = extract_apt_packages(setup_content)
    docs_pkgs = extract_apt_packages(docs_content)

    # Compare
    only_in_script = setup_pkgs - docs_pkgs
    only_in_docs = docs_pkgs - setup_pkgs

    if only_in_script:
        error("script-docs", f"In pi-setup.sh but NOT in PI_SETUP.md: {sorted(only_in_script)}")
    if only_in_docs:
        error("script-docs", f"In PI_SETUP.md but NOT in pi-setup.sh: {sorted(only_in_docs)}")
    if not only_in_script and not only_in_docs:
        ok(f"Package lists match ({len(setup_pkgs)} packages)")


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 3: Camera config consistency
# ─────────────────────────────────────────────────────────────────────────────
def check_camera_config():
    """Verify camera config is mentioned consistently in scripts and docs."""
    print("\n── Check 3: Camera configuration consistency ──")

    files_to_check = {
        "scripts/pi-setup.sh": REPO_ROOT / "scripts" / "pi-setup.sh",
        "docs/PI_SETUP.md":    REPO_ROOT / "docs" / "PI_SETUP.md",
    }

    # Also check flash-sd.sh if it exists
    flash_script = REPO_ROOT / "scripts" / "flash-sd.sh"
    if flash_script.exists():
        files_to_check["scripts/flash-sd.sh"] = flash_script

    for key, expected_val in CAMERA_CONFIG.items():
        for label, fpath in files_to_check.items():
            if not fpath.exists():
                continue
            content = fpath.read_text()
            if key == "dtoverlay":
                pattern = f"dtoverlay={expected_val}"
                if pattern not in content:
                    error("camera", f"'{pattern}' not found in {label}")
                else:
                    ok(f"'{pattern}' present in {label}")
            elif key == "camera_auto_detect":
                # Check that the script sets it to 0 (either directly or via sed)
                if f"camera_auto_detect={expected_val}" in content or \
                   f"camera_auto_detect=1/camera_auto_detect={expected_val}" in content:
                    ok(f"camera_auto_detect={expected_val} in {label}")
                else:
                    error("camera", f"camera_auto_detect={expected_val} not set in {label}")


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 4: requirements.txt ↔ pi-setup.sh cross-reference
# ─────────────────────────────────────────────────────────────────────────────
def check_requirements_vs_setup():
    """Packages in requirements.txt should have apt equivalents in pi-setup.sh where possible."""
    print("\n── Check 4: requirements.txt vs pi-setup.sh ──")

    req_file = REPO_ROOT / "pi" / "requirements.txt"
    if not req_file.exists():
        warn("req-setup", "pi/requirements.txt not found")
        return

    setup_file = REPO_ROOT / "scripts" / "pi-setup.sh"
    setup_content = setup_file.read_text() if setup_file.exists() else ""

    for line in req_file.read_text().splitlines():
        pkg = line.strip().split("==")[0].split(">=")[0].strip().lower()
        if not pkg or pkg.startswith("#"):
            continue

        # Find apt equivalent
        apt_pkg = None
        for _, (apt, pip) in IMPORT_TO_PACKAGE.items():
            if pip and pip.lower() == pkg:
                apt_pkg = apt
                break

        if apt_pkg and apt_pkg in setup_content:
            ok(f"requirements.txt '{pkg}' → apt '{apt_pkg}' in pi-setup.sh")
        elif apt_pkg and apt_pkg not in setup_content:
            warn("req-setup", f"'{pkg}' in requirements.txt has apt equivalent "
                 f"'{apt_pkg}' but it's not in pi-setup.sh (apt is faster on Pi)")
        else:
            ok(f"requirements.txt '{pkg}' — pip-only package")


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 5: Essential files exist
# ─────────────────────────────────────────────────────────────────────────────
def check_essential_files():
    """Verify all expected project files exist."""
    print("\n── Check 5: Essential files ──")

    essential = [
        "README.md",
        ".gitignore",
        "pi/requirements.txt",
        "scripts/pi-setup.sh",
        "docs/PI_SETUP.md",
    ]

    for f in essential:
        path = REPO_ROOT / f
        if path.exists():
            ok(f"{f} exists")
        else:
            error("files", f"Missing essential file: {f}")


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 6: Version pinning in docs
# ─────────────────────────────────────────────────────────────────────────────
def check_version_table():
    """Verify PI_SETUP.md has a version table with key packages."""
    print("\n── Check 6: Version documentation ──")

    docs_file = REPO_ROOT / "docs" / "PI_SETUP.md"
    if not docs_file.exists():
        error("versions", "docs/PI_SETUP.md not found")
        return

    content = docs_file.read_text()
    required_entries = ["Python", "picamera2", "gpiozero", "git"]

    for entry in required_entries:
        if entry.lower() in content.lower():
            ok(f"Version documented for '{entry}'")
        else:
            warn("versions", f"No version entry found for '{entry}' in PI_SETUP.md")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Cloud Rover — Setup Consistency Check")
    print("=" * 60)

    check_essential_files()
    check_imports_vs_packages()
    check_script_vs_docs()
    check_camera_config()
    check_requirements_vs_setup()
    check_version_table()

    print("\n" + "=" * 60)
    if errors:
        print(f"  FAILED — {len(errors)} error(s), {len(warnings)} warning(s)")
        print("=" * 60)
        print("\nErrors:")
        for e in errors:
            print(e)
        if warnings:
            print("\nWarnings:")
            for w in warnings:
                print(w)
        sys.exit(1)
    elif warnings:
        print(f"  PASSED with {len(warnings)} warning(s)")
        print("=" * 60)
        for w in warnings:
            print(w)
        sys.exit(0)
    else:
        print("  ALL CHECKS PASSED ✓")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
