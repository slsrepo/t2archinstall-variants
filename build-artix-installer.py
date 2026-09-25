#!/usr/bin/env python3
"""Build the Artix installer variants."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
import re

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)

def replace_t2_package_family(text: str, replacement: str = "linux") -> str:
    packages = "linux-t2 linux-t2-headers apple-t2-audio-config apple-bcm-firmware-fetcher"
    count = text.count(packages)
    if count != 2:
        raise RuntimeError(
            f"Expected two upstream T2 package lists, found {count}"
        )
    return text.replace(packages, replacement)

def _source_offsets(text: str) -> list[int]:
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets

def _source_span(node: ast.AST, offsets: list[int]) -> tuple[int, int]:
    if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
        raise ValueError(f"AST node has no source span: {type(node).__name__}")
    start = offsets[node.lineno - 1] + node.col_offset
    end = offsets[node.end_lineno - 1] + node.end_col_offset
    return start, end

def _is_main_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq):
        return False

    left, right = test.left, test.comparators[0]
    for name_node, value_node in ((left, right), (right, left)):
        if (
            isinstance(name_node, ast.Name)
            and name_node.id == "__name__"
            and isinstance(value_node, ast.Constant)
            and value_node.value == "__main__"
        ):
            return True
    return False

def clean_module(
    text: str,
    *,
    drop_main_guard: bool = False,
) -> str:
    """Prepare a normal Python module for inclusion in a standalone script."""
    if text.startswith("#!"):
        text = text.split("\n", 1)[1] if "\n" in text else ""

    tree = ast.parse(text)
    offsets = _source_offsets(text)
    removals: list[tuple[int, int]] = []

    if tree.body and isinstance(tree.body[0], ast.Expr):
        value = tree.body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            removals.append(_source_span(tree.body[0], offsets))

    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                removals.append(_source_span(node, offsets))
        elif drop_main_guard and _is_main_guard(node):
            removals.append(_source_span(node, offsets))

    for start, end in sorted(set(removals), reverse=True):
        if end < len(text) and text[end : end + 1] == "\n":
            end += 1
        text = text[:start] + text[end:]

    return text.strip() + "\n"

def transform_generic_arch(source_text: str) -> str:
    text = source_text

    doc_start = text.find('"""')
    doc_end = text.find('"""', doc_start + 3) if doc_start != -1 else -1
    if doc_start == -1 or doc_end == -1:
        raise RuntimeError("Upstream module docstring is missing")
    text = (
        text[:doc_start]
        + '"""Sl\'s standard Arch Linux installer."""'
        + text[doc_end + 3 :]
    )

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

    replace_required(
        "Welcome to the T2 Arch Linux Installer!",
        "Welcome to Sl's Arch Installer!",
        expected=1,
    )
    replace_required("T2 Arch Linux Installer", "Sl's Arch Installer")
    replace_required("Arch Linux T2", "Arch Linux")
    replace_required(
        '"""Main application for T2 Arch Linux installer."""',
        '"""Main application for Sl\'s Arch Linux installer."""',
        expected=1,
    )
    replace_required(
        "Install the base system and T2 packages",
        "Install the base system",
        expected=1,
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

    text = text.replace(
        '"""Install the base system with T2 packages automatically using pacstrap."""',
        '"""Install the base system automatically using pacstrap."""',
        1,
    )
    text = text.replace(
        '"""Install the base system with T2 packages manually by exiting the app and showing the pacstrap command."""',
        '"""Show the manual base-system installation command and exit the app."""',
        1,
    )
    text = text.replace(
        '"""Configure T2 modules, locale, and time."""',
        '"""Configure locale, time, and basic system settings."""',
        1,
    )

    return text

def transform(source_text: str, mode: str) -> str:
    if mode not in {"generic", "t2"}:
        raise ValueError(f"unsupported Artix variant: {mode}")

    if mode == "generic":
        text = transform_generic_arch(source_text)
    else:
        text = source_text

    text = text.replace("arch-chroot", "artix-chroot")
    text = text.replace("tuned tuned-ppd", "power-profiles-daemon")
    text = text.replace('"tuned-ppd"', '"power-profiles-daemon"')

    startup_marker = '''    async def on_mount(self):
        """Initialize the application and asynchronously refresh any already-mounted target filesystem state."""
'''
    startup_replacement = '''    async def on_mount(self):
        """Initialize the application and asynchronously refresh any already-mounted target filesystem state."""
        if getattr(self, "_artix_startup_initialized", False):
            return
        self._artix_startup_initialized = True
        if self.post_install_mode:
            return
'''
    text = replace_once(
        text,
        startup_marker,
        startup_replacement,
        "upstream on_mount() marker",
    )

    startup_message = "To begin, enter your disk path in the Start tab :)"
    if startup_message in text:
        text = replace_once(
            text,
            startup_message,
            "To begin, enter your target disk and choose the target init system in the Start tab :)",
            "startup console message",
        )

    start_message = (
        "Start by entering the disk you want to use below, follow the steps and read "
        "the log on the right :)"
    )
    if start_message in text:
        text = replace_once(
            text,
            start_message,
            "Start by entering your target disk below, choosing your init system and "
            "reading the log on the right :)",
            "Start-tab introduction",
        )

    disk_input = '                            yield Input(placeholder="Enter disk path", id="disk_input")\n'
    init_selector = disk_input + '''                            yield Static("")
                            yield Static("Target Artix init system:")
                            with RadioSet(id="artix_init_choice"):
                                yield RadioButton("OpenRC", id="artix_init_openrc", value=self.init_system == "openrc")
                                yield RadioButton("dinit", id="artix_init_dinit", value=self.init_system == "dinit")
                                yield RadioButton("runit", id="artix_init_runit", value=self.init_system == "runit")
                                yield RadioButton("s6", id="artix_init_s6", value=self.init_system == "s6")
                            yield Static("The selected init controls packages, services, display managers, and post-install setup.")
'''
    text = replace_once(text, disk_input, init_selector, "Start-tab disk input")

    text = replace_once(
        text,
        "https://archlinux.org/logos/archlinux-icon-crystal-64.svg",
        "https://gitea.artixlinux.org/artix/artwork/raw/branch/master/icons/artixlinux-logo-only.svg",
        "Arch boot icon URL",
    )
    text = replace_once(
        text,
        "disklabel-maker.py 'Arch'",
        "disklabel-maker.py 'Artix'",
        "disk label command",
    )

    if mode == "t2":
        text = text.replace("T2 Arch Linux Installer", "T2 Artix Linux Installer")
        text = text.replace("Arch Linux T2", "Artix Linux T2")
        text = text.replace(
            '"""Main application for T2 Arch Linux installer."""',
            '"""Main application for T2 Artix Linux installer."""',
        )
        text = text.replace("arch-linux-t2.efi", "artix-linux-t2.efi")
    else:
        text = text.replace("Sl's Arch Installer", "Sl's Artix Installer")
        text = text.replace("Arch Linux", "Artix Linux")
        text = text.replace("arch-linux.efi", "artix-linux.efi")

    return text

UPSTREAM_URL = "https://raw.githubusercontent.com/slsrepo/t2archinstall/main/t2archinstall.py"

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

def validate_artix(text: str, variant: str, output: Path, mode: str) -> None:
    compile(text, str(output), "exec")
    tree = ast.parse(text, filename=str(output))
    classes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }

    base_class = classes.get("T2ArchInstaller")
    artix_class = classes.get("ArtixInstaller")
    if base_class is None:
        raise RuntimeError("T2ArchInstaller base class is missing")
    if artix_class is None:
        raise RuntimeError("ArtixInstaller class is missing")

    methods = {
        node.name
        for node in artix_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for required in (
        "_base_packages",
        "build_initramfs",
        "create_boot_icon",
        "create_user_and_services",
        "install_desktop_environment",
    ):
        if required not in methods:
            raise RuntimeError(f"ArtixInstaller method is missing: {required}")

    expected_class = {
        "sl-artixinstall": "SlArtixInstaller",
        "t2artixinstall": "T2ArtixInstaller",
        "sl-artix-postinstall": "SlArtixPostInstaller",
    }[variant]
    if expected_class not in classes:
        raise RuntimeError(f"Missing installer class: {expected_class}")

    base_methods = {
        node.name
        for node in base_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for preserved in (
        "configure_t2_repository",
        "add_t2_repository",
        "add_t2_repo_to_chroot",
        "install_tiny_dfr",
        "install_audio_dsp",
    ):
        if preserved not in base_methods:
            raise RuntimeError(f"Expected upstream method is missing: {preserved}")

    if mode == "t2":
        if re.search(
            r"(?<![A-Za-z0-9_-])apple-bcm-firmware(?![A-Za-z0-9_-])",
            text,
        ):
            raise RuntimeError(
                "T2 Artix installer still contains apple-bcm-firmware"
            )
        if not re.search(
            r"(?<![A-Za-z0-9_-])apple-bcm-firmware-fetcher(?![A-Za-z0-9_-])",
            text,
        ):
            raise RuntimeError(
                "T2 Artix installer is missing apple-bcm-firmware-fetcher"
            )

def _entrypoint_text(root: Path, variant: str) -> str:
    if variant == "sl-artixinstall":
        return '''
class SlArtixInstaller(ArtixInstaller):
    APP_TITLE = "Sl's Artix Installer"
    INCLUDE_T2 = False
    INIT_STATE_FILE = "/run/t2archinstall/sl-artixinstall-init"

if __name__ == "__main__":
    SlArtixInstaller().run()
'''.lstrip()

    if variant == "t2artixinstall":
        return '''
class T2ArtixInstaller(ArtixInstaller):
    APP_TITLE = "T2 Artix Linux Installer"
    INCLUDE_T2 = True
    INIT_STATE_FILE = "/run/t2archinstall/t2artixinstall-init"

if __name__ == "__main__":
    T2ArtixInstaller().run()
'''.lstrip()

    return clean_module(
        (root / "sl-artix-postinstall.py").read_text(encoding="utf-8")
    )

def build_variant(root: Path, source_text: str, variant: str) -> Path:
    mode = "t2" if variant == "t2artixinstall" else "generic"

    base_text = clean_module(transform(source_text, mode), drop_main_guard=True)
    common_text = clean_module(
        (root / "artix-common.py").read_text(encoding="utf-8"),
    )
    entry_text = _entrypoint_text(root, variant)

    installer = (
        "#!/usr/bin/env python3\n"
        "from __future__ import annotations\n\n"
        + base_text
        + "\n"
        + common_text
        + "\n"
        + entry_text
    )

    output = root / variant
    validate_artix(installer, variant, output, mode)
    write_executable(output, installer)
    return output

def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Build an Artix installer variant.")
    parser.add_argument(
        "variant",
        choices=("sl-artixinstall", "t2artixinstall", "sl-artix-postinstall"),
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="use an existing t2archinstall.py instead of the current upstream source",
    )
    args = parser.parse_args()

    output = build_variant(root, load_upstream_source(root, args.source), args.variant)
    print(f"Built {output.name}")

if __name__ == "__main__":
    main()
