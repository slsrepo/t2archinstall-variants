"""Artix post-install UI and behavior for existing systems."""

from __future__ import annotations

import os
import shlex
import sys

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Header, Input, RadioButton, RadioSet, RichLog, Static


class SlArtixPostInstaller(ArtixInstaller):
    APP_TITLE = "Sl's Artix Installer - Postinstall Edition"
    INCLUDE_T2 = False
    INIT_STATE_FILE = "/run/t2archinstall/sl-artix-postinstall-init"

    CSS = """
    Screen { background: $surface; color: $text; }
    #left_panel { width: 50%; padding: 1; }
    #right_panel { width: 50%; }
    #console { height: 90%; border: solid $success; scrollbar-gutter: stable; text-wrap: wrap; text-overflow: fold; }
    #command_input { height: 10%; border: solid $primary; }
    .section_title { background: $primary-background; color: $text; text-style: bold; padding-left: 1; margin-top: 1; margin-bottom: 1; width: 100%; }
    Button { background: $primary-background-darken-2; margin-bottom: 1; }
    Button:hover { background: $primary-background; }
    Input { margin-bottom: 1; }
    RadioSet { height: auto; margin-bottom: 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.post_install_mode = True
        if "ARTIX_INIT" not in os.environ:
            detected = self._detect_running_init()
            if detected:
                self.init_system = detected
                self._save_init_system()

    @staticmethod
    def _detect_running_init() -> str | None:
        candidates: list[str] = []
        try:
            candidates.append(open("/proc/1/comm", encoding="utf-8").read().strip())
        except OSError:
            pass
        try:
            candidates.append(os.path.basename(os.readlink("/proc/1/exe")))
        except OSError:
            pass

        joined = " ".join(candidates).lower()
        if "openrc" in joined:
            return "openrc"
        if "runit" in joined:
            return "runit"
        if "s6-svscan" in joined or joined.strip() == "s6":
            return "s6"
        if "dinit" in joined:
            return "dinit"
        return None

    def compose(self) -> ComposeResult:
        yield Header(icon="^", name=self.APP_TITLE, show_clock=True)
        with Horizontal():
            with VerticalScroll(id="left_panel"):
                yield Static("Artix Init System", classes="section_title")
                with RadioSet(id="artix_init_choice"):
                    for name, label in self.INIT_LABELS.items():
                        yield RadioButton(label, id=f"artix_init_{name}", value=name == self.init_system)

                yield Static("BTRFS Setup", classes="section_title")
                yield Button("Create common BTRFS subvolumes", id="btrfs_subvol_btn")
                yield Button("Install and configure Snapper", id="btrfs_snapper_btn")
                yield Button("Install and enable grub-btrfs", id="btrfs_grub_btn")
                yield Button("Install snap-pac", id="btrfs_snappac_btn")

                yield Static("Locale and Language", classes="section_title")
                yield Static("Available: en_US.UTF-8", id="locales_available")
                yield Static("Additional locales (space/comma separated):")
                yield Input(placeholder="en_GB.UTF-8 en_AU.UTF-8", id="locales_input")
                yield Button("Add Locales", id="add_locales_btn")
                yield Static("System language:")
                yield Input(value="en_US.UTF-8", id="lang_input")
                yield Button("Set Language", id="set_language_btn")

                yield Static("User and Services", classes="section_title")
                yield Input(placeholder="Enter username", id="username_input")
                yield Input(placeholder="Enter user password", password=True, id="user_password_input")
                yield Button("Create User and Enable Services", id="create_user_btn")
                yield Button("Configure Sudoers", id="config_sudo_btn")

                yield Static("Desktop Environment / Window Manager", classes="section_title")
                yield Button("KDE Plasma", id="kde_auto_btn")
                yield Button("COSMIC", id="cosmic_auto_btn")
                yield Button("Niri", id="niri_auto_btn")
                yield Button("Niri + DankMaterialShell", id="niridms_auto_btn")

                yield Static("Extras", classes="section_title")
                yield Button("Install Extra Packages", id="extras_btn")
                yield Button("Add Sl's Arch Repository", id="add_slsrepo_btn")

            with Vertical(id="right_panel"):
                yield RichLog(wrap=True, min_width=1, id="console")
                yield Input(placeholder="Type commands here...", id="command_input")
        yield Footer()

    async def on_mount(self) -> None:
        self.title = self.APP_TITLE
        console = self.query_one("#console", RichLog)
        console.write(self.APP_TITLE)
        console.write("=" * 60)
        console.write("Commands run directly on the current Artix installation.")
        console.write(f"Selected init: {self.INIT_LABELS[self.init_system]}")
        console.write("=" * 60)

    def maybe_redirect_completion_from_extras(self) -> None:
        self.query_one("#console", RichLog).write("Post-install action completed.")

    @on(Input.Submitted, "#command_input")
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        command = event.value.strip()
        if command:
            event.input.value = ""
            await self.run_command(command)

    @on(Button.Pressed)
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btrfs_subvol_btn":
            await self.btrfs_create_subvolumes()
        elif button_id == "btrfs_snapper_btn":
            await self.btrfs_install_snapper()
        elif button_id == "btrfs_grub_btn":
            await self.btrfs_setup_grub()
        elif button_id == "btrfs_snappac_btn":
            await self.btrfs_install_snappac()
        elif button_id == "add_locales_btn":
            self.add_locales()
        elif button_id == "set_language_btn":
            await self.set_language()
        elif button_id == "create_user_btn":
            await self.create_user_and_services()
        elif button_id == "config_sudo_btn":
            await self.configure_sudoers()
        elif button_id in {"kde_auto_btn", "cosmic_auto_btn", "niri_auto_btn", "niridms_auto_btn"}:
            await self.install_desktop_environment(button_id.split("_", 1)[0], False)
        elif button_id == "extras_btn":
            await self.install_extras()
        elif button_id == "add_slsrepo_btn":
            await self.add_slsrepo_to_chroot()

    async def set_language(self) -> None:
        console = self.query_one("#console", RichLog)
        selected = self.query_one("#lang_input", Input).value.strip() or "en_US.UTF-8"
        locales = list(dict.fromkeys(["en_US.UTF-8", *self.locales_added, selected]))
        for locale in locales:
            entry = shlex.quote(f"{locale} UTF-8")
            if not await self.run_command(f"grep -Fxq -- {entry} /usr/share/i18n/SUPPORTED"):
                console.write(f"[ERROR] Unsupported UTF-8 locale: {locale}")
                return
        commands = [
            "touch /etc/locale.gen",
            *[
                f"grep -Fxq -- {shlex.quote(locale + ' UTF-8')} /etc/locale.gen || "
                f"printf '%s\\n' {shlex.quote(locale + ' UTF-8')} >> /etc/locale.gen"
                for locale in locales
            ],
            "locale-gen",
            f"printf 'LANG=%s\\nLANGUAGE=%s\\n' {shlex.quote(selected)} {shlex.quote(selected)} > /etc/locale.conf",
            "test -e /etc/vconsole.conf || printf 'KEYMAP=us\\n' > /etc/vconsole.conf",
        ]
        for command in commands:
            if not await self.run_in_chroot(command):
                console.write("[ERROR] Language configuration failed.")
                return
        self.lang_selected = selected
        console.write("Language configured successfully!")

    async def configure_sudoers(self) -> None:
        console = self.query_one("#console", RichLog)
        command = "sed -i 's/^# \\(%wheel ALL=(ALL:ALL) ALL\\)/\\1/' /etc/sudoers"
        if await self.run_in_chroot(command):
            console.write("Sudoers configured successfully!")
        else:
            console.write("[ERROR] Sudoers configuration failed.")

    async def _require_btrfs(self) -> bool:
        if await self.target_root_uses_btrfs(log_warnings=False):
            return True
        self.query_one("#console", RichLog).write("[ERROR] The current root filesystem is not BTRFS.")
        return False

    async def btrfs_create_subvolumes(self) -> None:
        if not await self._require_btrfs():
            return
        console = self.query_one("#console", RichLog)
        # Snapper creates /.snapshots itself when creating its root configuration.
        console.write("/.snapshots is managed by the Snapper configuration step.")
        complete = True
        for path in ("/home", "/var/log", "/var/cache/pacman/pkg"):
            quoted = shlex.quote(path)
            command = (
                f"if [ -L {quoted} ]; then false; "
                f"elif [ -e {quoted} ]; then btrfs subvolume show {quoted} >/dev/null 2>&1; "
                f"else btrfs subvolume create {quoted}; fi"
            )
            if not await self.run_command(command):
                complete = False
                console.write(f"[WARN] Could not create or verify {path}; existing paths are left unchanged.")
        if complete:
            console.write("BTRFS subvolume setup completed.")
        else:
            console.write("[WARN] BTRFS subvolume setup is incomplete; review the paths above.")

    async def btrfs_install_snapper(self) -> None:
        if not await self._require_btrfs():
            return
        console = self.query_one("#console", RichLog)
        if not await self.run_in_chroot("pacman -S --noconfirm --needed snapper btrfs-assistant"):
            console.write("[ERROR] Failed to install Snapper.")
            return
        if not await self.run_in_chroot("test -f /etc/snapper/configs/root || snapper --no-dbus -c root create-config /"):
            console.write("[ERROR] Failed to create the Snapper root configuration. Check the output above; existing snapshots are left unchanged.")
            return
        for command in (
            "pacman -S --noconfirm --needed cronie " + (self._service_package("cronie") or ""),
            self._enable_service_command("cronie"),
        ):
            if not await self.run_in_chroot(command):
                console.write("[ERROR] Snapper is configured, but setting up its scheduler failed.")
                return
        console.write("Snapper installed and configured.")

    async def btrfs_setup_grub(self) -> None:
        if not await self._require_btrfs():
            return
        console = self.query_one("#console", RichLog)
        service_package = self._service_package("grub-btrfs")
        command = "pacman -S --noconfirm --needed grub-btrfs inotify-tools" + (f" {service_package}" if service_package else "")
        if not await self.run_in_chroot(command):
            console.write("[ERROR] Failed to install grub-btrfs.")
            return
        if not await self.run_in_chroot(self._enable_service_command("grub-btrfsd")):
            console.write("[ERROR] Failed to enable grub-btrfsd.")
            return
        if not await self.run_in_chroot("grub-mkconfig -o /boot/grub/grub.cfg"):
            console.write("[ERROR] Failed to regenerate the GRUB configuration.")
            return
        console.write("grub-btrfs installed and enabled.")

    async def btrfs_install_snappac(self) -> None:
        if not await self._require_btrfs():
            return
        console = self.query_one("#console", RichLog)
        if await self.run_in_chroot("pacman -S --noconfirm --needed snap-pac"):
            console.write("snap-pac installed successfully.")
        else:
            console.write("[ERROR] Failed to install snap-pac.")

if __name__ == "__main__":
    if os.geteuid() != 0:
        try:
            os.execvp("sudo", ["sudo", sys.executable, os.path.realpath(__file__), *sys.argv[1:]])
        except FileNotFoundError:
            print("sl-artix-postinstall must be run as root, and sudo was not found.", file=sys.stderr)
            raise SystemExit(1)
    SlArtixPostInstaller().run()
