#!/usr/bin/env python3
"""Build the Arch and Asahi post-install variants."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
import re

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

METHODS_TO_EXTRACT = (
    "cleanup_pacman_lock",
    "run_command",
    "parse_locales",
    "add_locales",
    "configure_sudoers",
    "check_repo_in_pacman_conf",
    "update_repo_in_pacman_conf",
    "build_repo_config",
    "add_slsrepo_to_chroot",
    "create_user_and_services",
    "wm_shared_packages",
    "wm_write_user_file",
    "wm_install_greetd_dms_greeter",
    "wm_install_sl_desktop_utils",
    "install_niri",
    "install_niri_with_dms",
    "install_desktop_environment",
    "install_extras",
)

def _method_source_span(source: str, node: ast.AST) -> str:
    lines = source.splitlines(keepends=True)
    start_line = node.lineno
    decorators = getattr(node, "decorator_list", ())
    if decorators:
        start_line = min(item.lineno for item in decorators)
    return "".join(lines[start_line - 1 : node.end_lineno]).rstrip()

def extract_methods(source: str) -> str:
    """Copy the reusable post-install methods from the upstream installer."""
    tree = ast.parse(source)
    installer = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "T2ArchInstaller"
        ),
        None,
    )
    if installer is None:
        raise RuntimeError("T2ArchInstaller class was not found in upstream source")

    methods = {
        node.name: node
        for node in installer.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = [name for name in METHODS_TO_EXTRACT if name not in methods]
    if missing:
        raise RuntimeError("Required upstream method(s) not found: " + ", ".join(missing))

    extracted: list[str] = []
    for method_name in METHODS_TO_EXTRACT:
        code = _method_source_span(source, methods[method_name])
        code = code.replace("self.run_in_chroot", "self.run_command")
        code = code.replace("self._get_target_root()", "'/'")
        code = code.replace("self.update_available_locales_label()", "pass")

        for pattern in (
            r"^([ \t]*)self\.query_one\(TabbedContent\).*",
            r"^([ \t]*)self\.query_one\([\"']#left_panel[\"']\).*",
            r"^([ \t]*)self\.maybe_redirect_completion_from_extras\(.*",
            r"^([ \t]*)self\.query_one\([\"']#.*_btn[\"']\)\.focus\(.*",
            r"^([ \t]*)self\.query_one\([\"']#.*_input[\"']\)\.focus\(.*",
        ):
            code = re.sub(pattern, r"\1pass", code, flags=re.MULTILINE)

        code = code.replace("self.exit()", "pass")
        code = re.sub(
            r"[\"']systemctl enable t2fanrd\.service[\"']\s*,?\s*",
            "",
            code,
        )

        if method_name == "check_repo_in_pacman_conf":
            code = code.replace(
                'repo_name: str = "arch-mact2"',
                'repo_name: str = "slsrepo"',
            )

        if method_name == "install_extras":
            code = re.sub(
                r"^[ \t]*if await self\.target_root_uses_btrfs\(\):.*?(?=^[ \t]*console\.write)",
                "",
                code,
                flags=re.MULTILINE | re.DOTALL,
            )

        extracted.append(code)

    return "\n\n".join(extracted)

def _build_mixin(source_text: str) -> str:
    methods = extract_methods(source_text)
    return "class UpstreamPostInstallMixin:\n" + methods + "\n"

def _validate(text: str, variant: str, output: Path) -> None:
    compile(text, str(output), "exec")
    tree = ast.parse(text, filename=str(output))
    classes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }

    if "UpstreamPostInstallMixin" not in classes or "PostInstallerBase" not in classes:
        raise RuntimeError("Post-install base classes are missing")

    expected_class = (
        "AsahiPostInstaller" if variant == "sl-asahi-postinstall" else "ArchPostInstaller"
    )
    if expected_class not in classes:
        raise RuntimeError(f"Missing post-install class: {expected_class}")

    if "t2fanrd.service" in text:
        raise RuntimeError("T2 fan service remains in post-install variant")

    if variant == "sl-asahi-postinstall":
        for required in ("asahi-desktop-meta", "vulkan-asahi"):
            if required not in text:
                raise RuntimeError(f"Asahi post-install script is missing: {required}")
    elif "asahi-desktop-meta" in text or "vulkan-asahi" in text:
        raise RuntimeError("Asahi packages leaked into the standard Arch post-install variant")

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

def _entrypoint_text(variant: str) -> str:
    if variant == "sl-arch-postinstall":
        return '''
import os
import sys

class ArchPostInstaller(PostInstallerBase):
    APP_TITLE = "Sl's Arch Installer - Postinstall Edition"

if __name__ == "__main__":
    if os.geteuid() != 0:
        try:
            os.execvp(
                "sudo",
                ["sudo", sys.executable, os.path.realpath(__file__), *sys.argv[1:]],
            )
        except FileNotFoundError:
            print(
                "sl-arch-postinstall must be run as root, and sudo was not found.",
                file=sys.stderr,
            )
            raise SystemExit(1)
    ArchPostInstaller().run()
'''.lstrip()

    return '''
import os
import sys

from textual.widgets import RichLog

class AsahiPostInstaller(PostInstallerBase):
    APP_TITLE = "Sl's Arch Installer - Asahi Postinstall Edition"

    async def install_variant_desktop(self, de_type: str) -> None:
        console = self.query_one("#console", RichLog)
        console.write("Installing Asahi GPU drivers & desktop meta packages...")
        if await self.run_command(
            "pacman -S --noconfirm --needed asahi-desktop-meta vulkan-asahi"
        ):
            await super().install_variant_desktop(de_type)
        else:
            console.write("[ERROR] Failed to install Asahi base packages.")

if __name__ == "__main__":
    if os.geteuid() != 0:
        try:
            os.execvp(
                "sudo",
                ["sudo", sys.executable, os.path.realpath(__file__), *sys.argv[1:]],
            )
        except FileNotFoundError:
            print(
                "sl-asahi-postinstall must be run as root, and sudo was not found.",
                file=sys.stderr,
            )
            raise SystemExit(1)
    AsahiPostInstaller().run()
'''.lstrip()

def build_variant(root: Path, source_text: str, variant: str) -> Path:
    mixin_text = _build_mixin(source_text)
    common_text = clean_module(
        (root / "postinstall-common.py").read_text(encoding="utf-8"),
    )
    entry_text = _entrypoint_text(variant)

    installer = (
        "#!/usr/bin/env python3\n"
        "from __future__ import annotations\n\n"
        + mixin_text
        + "\n"
        + common_text
        + "\n"
        + entry_text
    )

    output = root / variant
    _validate(installer, variant, output)
    write_executable(output, installer)
    return output

def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Build an Arch post-install variant.")
    parser.add_argument(
        "variant",
        choices=("sl-arch-postinstall", "sl-asahi-postinstall"),
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
