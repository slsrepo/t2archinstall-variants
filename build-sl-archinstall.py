#!/usr/bin/env python3
"""Build the standard non-T2 Arch installer variant."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
import re

UPSTREAM_URL = "https://raw.githubusercontent.com/slsrepo/t2archinstall/main/t2archinstall.py"

def replace_t2_package_family(text: str, replacement: str = "linux") -> str:
    packages = "linux-t2 linux-t2-headers apple-t2-audio-config apple-bcm-firmware-fetcher"
    count = text.count(packages)
    if count != 2:
        raise RuntimeError(
            f"Expected two upstream T2 package lists, found {count}"
        )
    return text.replace(packages, replacement)

def transform_generic_arch(source_text: str) -> str:
    """Apply the same non-T2 behavior changes as the packaged sl-archinstall."""
    text = source_text

    def replace_required(old: str, new: str, expected: int | None = None) -> None:
        nonlocal text
        found = text.count(old)
        if expected is not None and found != expected:
            raise RuntimeError(
                f"Expected {expected} occurrence(s) of {old!r}, found {found}"
            )
        if found == 0:
            raise RuntimeError(f"Required source text not found: {old!r}")
        text = text.replace(old, new)

    def remove_pattern(pattern: str, description: str, expected: int = 1) -> None:
        nonlocal text
        text, removed = re.subn(pattern, "", text, flags=re.MULTILINE)
        if removed != expected:
            raise RuntimeError(
                f"Expected to remove {expected} {description}, removed {removed}"
            )

    text = replace_t2_package_family(text)

    remove_pattern(
        r'^\s*"systemctl enable t2fanrd\.service"\s*,?\s*\n',
        "t2fanrd service command",
    )
    replace_required(" t2fanrd", "", expected=2)

    replace_required("T2 Arch Linux Installer", "Sl's Arch Installer")
    replace_required("Arch Linux T2", "Arch Linux")
    replace_required(
        "Install the base system and T2 packages",
        "Install the base system",
        expected=1,
    )

    # Keep the source documentation accurate without changing behavior.
    replace_required(
        '"""Main application for T2 Arch Linux installer."""',
        '"""Main application for Sl\'s standard Arch Linux installer."""',
        expected=1,
    )
    replace_required(
        '"""Install the base system with T2 packages automatically using pacstrap."""',
        '"""Install the base system automatically using pacstrap."""',
        expected=1,
    )
    replace_required(
        '"""Install the base system with T2 packages manually by exiting the app and showing the pacstrap command."""',
        '"""Show the manual base-system installation command and exit the app."""',
        expected=1,
    )
    replace_required(
        '"""Configure T2 modules, locale, and time."""',
        '"""Configure locale, time and basic system settings."""',
        expected=1,
    )

    doc_start = text.find('"""')
    doc_end = text.find('"""', doc_start + 3) if doc_start != -1 else -1
    if doc_start == -1 or doc_end == -1:
        raise RuntimeError("Upstream module docstring is missing")
    text = (
        text[:doc_start]
        + '"""Sl\'s standard Arch Linux installer."""'
        + text[doc_end + 3 :]
    )

    replace_required("vmlinuz-linux-t2", "vmlinuz-linux")
    replace_required("initramfs-linux-t2", "initramfs-linux")
    replace_required("linux-t2.preset", "linux.preset", expected=1)
    replace_required("arch-linux-t2.efi", "arch-linux.efi", expected=1)

    for widget_id in (
        "add_repo_btn",
        "chroot_repo_btn",
        "tiny_dfr_btn",
        "enable_hybrid_graphics_btn",
        "recurring_network_notifications_fix_btn",
        "audio_dsp_btn",
        "suspend_sleep_btn",
        "ignore_lid_btn",
        "suspend_fix_btn",
        "extended_suspend_fix_btn",
    ):
        remove_pattern(
            rf'^\s*yield .*id="{re.escape(widget_id)}".*\n',
            f"{widget_id} widget",
        )

    remove_pattern(
        r'^\s*yield Static\("T2 Suspend solutions:"\)\s*\n',
        "T2 suspend section heading",
    )

    for button_id in (
        "add_repo_btn",
        "chroot_repo_btn",
        "tiny_dfr_btn",
        "suspend_sleep_btn",
        "ignore_lid_btn",
        "suspend_fix_btn",
        "extended_suspend_fix_btn",
    ):
        remove_pattern(
            rf'^\s*elif button_id == "{re.escape(button_id)}":.*\n',
            f"{button_id} dispatch",
        )

    remove_pattern(
        r'^\s*elif button_id == "enable_hybrid_graphics_btn":\s*\n'
        r'^\s*await self\.enable_hybrid_graphics\(\)\s*\n',
        "hybrid graphics dispatch block",
    )
    remove_pattern(
        r'^\s*elif button_id == "recurring_network_notifications_fix_btn":\s*\n'
        r'^\s*await self\.recurring_network_notifications_fix\(\)\s*\n',
        "recurring network notification dispatch block",
    )
    remove_pattern(
        r'^\s*elif button_id == "audio_dsp_btn":\s*\n'
        r'^\s*await self\.install_audio_dsp\(\)\s*\n',
        "audio DSP dispatch block",
    )

    replace_required(
        'self.query_one("#chroot_repo_btn").focus()',
        'self.query_one("#config_basic_btn").focus()',
        expected=1,
    )

    return text

def validate(text: str, filename: str = "<sl-archinstall>") -> None:
    tree = ast.parse(text, filename=filename)
    classes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    installer = classes.get("T2ArchInstaller")
    if installer is None:
        raise RuntimeError("T2ArchInstaller class is missing")

    methods = {
        node.name
        for node in installer.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for required in (
        "compose",
        "on_mount",
        "on_button_pressed",
        "install_base_system_auto",
        "install_grub",
        "install_limine",
        "install_plymouth",
    ):
        if required not in methods:
            raise RuntimeError(f"Installer method is missing: {required}")

    if 'if __name__ == "__main__":' not in text or "app.run()" not in text:
        raise RuntimeError("Installer launcher is missing")

    for forbidden in (
        'id="add_repo_btn"',
        'id="chroot_repo_btn"',
        'id="tiny_dfr_btn"',
        'id="enable_hybrid_graphics_btn"',
        'id="recurring_network_notifications_fix_btn"',
        'id="audio_dsp_btn"',
        'id="suspend_sleep_btn"',
        'id="ignore_lid_btn"',
        'id="suspend_fix_btn"',
        'id="extended_suspend_fix_btn"',
        "linux-t2",
        "initramfs-linux-t2",
        "vmlinuz-linux-t2",
        " t2fanrd",
    ):
        if forbidden in text:
            raise RuntimeError(f"Unexpected T2-only content remains: {forbidden}")

    if "pacstrap -K /mnt base linux linux-firmware" not in text:
        raise RuntimeError("The standard-kernel pacstrap command is missing")

    # The T2-only methods intentionally remain in the new class, matching the
    # packaged variant. Their UI and dispatch paths are removed above.
    for preserved in (
        "configure_t2_repository",
        "add_t2_repository",
        "add_t2_repo_to_chroot",
        "install_tiny_dfr",
        "install_audio_dsp",
    ):
        if preserved not in methods:
            raise RuntimeError(f"Expected inherited source method is missing: {preserved}")

    if len(text.splitlines()) < 2000:
        raise RuntimeError("Installer is unexpectedly short")

def load_upstream_source(root: Path, requested: Path | None) -> str:
    if requested is not None:
        source = requested.expanduser().resolve()
        if not source.is_file():
            raise SystemExit(f"error: t2archinstall source not found: {source}")
        return source.read_text(encoding="utf-8")

    for source in (
        root / "t2archinstall.py",
        root / "t2archinstall" / "t2archinstall.py",
    ):
        if source.is_file():
            return source.read_text(encoding="utf-8")

    try:
        from urllib.request import urlopen

        with urlopen(UPSTREAM_URL, timeout=30) as response:
            return response.read().decode("utf-8")
    except Exception as exc:
        raise SystemExit(
            "error: could not load t2archinstall.py; "
            "place it beside the builder or pass --source PATH"
        ) from exc

def write_executable(output: Path, text: str) -> None:
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        temporary.chmod(0o755)
        temporary.replace(output)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass

def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Build sl-archinstall.")
    parser.add_argument(
        "--source",
        type=Path,
        help="use an existing t2archinstall.py instead of the current upstream source",
    )
    args = parser.parse_args()

    installer = transform_generic_arch(load_upstream_source(root, args.source))
    output = root / "sl-archinstall"
    validate(installer, str(output))
    write_executable(output, installer)
    print(f"Built {output.name}")

if __name__ == "__main__":
    main()
