"""Shared post-install UI for the Arch and Asahi variants."""

from __future__ import annotations

import asyncio
import codecs
import os
import re
import shlex
import signal
import sys
from typing import Optional

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Header, Input, RichLog, Static

class PostInstallerBase(UpstreamPostInstallMixin, App):
    APP_TITLE = "Sl's Arch Installer - Postinstall Edition"
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
    """

    def __init__(self):
        super().__init__()
        self.post_install_mode = True
        self.locales_added = []
        self.lang_selected = "en_US.UTF-8"
        self.username = ""

    def compose(self) -> ComposeResult:
        yield Header(icon="^", name=self.APP_TITLE, show_clock=True)
        with Horizontal():
            with VerticalScroll(id="left_panel"):
                yield Static("BTRFS Setup", classes="section_title")
                yield Button("1. Create Subvolumes (/home, /var/log, package cache)", id="btrfs_subvol_btn")
                yield Button("2. Install Snapper & BTRFS Assistant", id="btrfs_snapper_btn")
                yield Button("3. Setup grub-btrfs", id="btrfs_grub_btn")
                yield Button("4. Install snap-pac", id="btrfs_snappac_btn")

                yield Static("Locale & Language", classes="section_title")
                yield Static("Additional locales (space/comma separated):")
                yield Input(placeholder="en_GB.UTF-8 en_AU.UTF-8", id="locales_input")
                yield Button("Add Locales", id="add_locales_btn")
                yield Static("System language:")
                yield Input(value="en_US.UTF-8", id="lang_input")
                yield Button("Set Language", id="set_language_btn")

                yield Static("User Creation & Services", classes="section_title")
                yield Input(placeholder="Enter username", id="username_input")
                yield Input(placeholder="Enter user password", password=True, id="user_password_input")
                yield Button("Create User & Enable Services", id="create_user_btn")
                yield Button("Configure Sudoers", id="config_sudo_btn")

                yield Static("Desktop Environment / Window Manager", classes="section_title")
                yield Button("GNOME", id="gnome_auto_btn")
                yield Button("KDE", id="kde_auto_btn")
                yield Button("COSMIC", id="cosmic_auto_btn")
                yield Button("Niri", id="niri_auto_btn")
                yield Button("Niri + DankMaterialShell", id="niridms_auto_btn")

                yield Static("Extras", classes="section_title")
                yield Button("Install Extra packages (ffmpeg, pipewire, ghostty, etc.)", id="extras_btn")
                yield Button("Add Sl's Arch Repository to Pacman", id="add_slsrepo_btn")

            with Vertical(id="right_panel"):
                yield RichLog(wrap=True, min_width=1, id="console")
                yield Input(placeholder="Type commands here...", id="command_input")
        yield Footer()

    def on_mount(self):
        self.title = self.APP_TITLE
        console = self.query_one("#console", RichLog)
        console.write(self.APP_TITLE + " Started")
        console.write("=" * 60)
        console.write("This tool runs commands directly on the current system.")
        console.write("Use the setup actions in the left panel in the order you need them.")
        console.write("=" * 60)

    @on(Input.Submitted, "#command_input")
    async def on_input_submitted(self, event: Input.Submitted):
        command = event.value.strip()
        if command:
            event.input.value = ""
            await self.run_command(command)

    @on(Button.Pressed)
    async def on_button_pressed(self, event: Button.Pressed):
        button_id = event.button.id
        console = self.query_one("#console", RichLog)
        self.screen.set_focus(None)

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
        elif button_id in {"gnome_auto_btn", "kde_auto_btn", "cosmic_auto_btn", "niri_auto_btn", "niridms_auto_btn"}:
            await self.install_variant_desktop(button_id.split("_", 1)[0])
        elif button_id == "extras_btn":
            await self.install_extras()
        elif button_id == "add_slsrepo_btn":
            await self.add_slsrepo_to_chroot()

    async def install_variant_desktop(self, de_type: str) -> None:
        await self.install_desktop_environment(de_type, False)

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
            if not await self.run_command(command):
                console.write("[ERROR] Language configuration failed.")
                return
        self.lang_selected = selected
        console.write("Language configured successfully!")

    async def _require_btrfs(self) -> bool:
        if await self.run_command('test "$(findmnt -n -o FSTYPE --target /)" = btrfs'):
            return True
        self.query_one("#console", RichLog).write("[ERROR] The current root filesystem could not be verified as BTRFS.")
        return False

    async def btrfs_create_subvolumes(self):
        if not await self._require_btrfs():
            return
        console = self.query_one("#console", RichLog)
        console.write("Creating common BTRFS subvolumes on / ...")
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

    async def btrfs_install_snapper(self):
        if not await self._require_btrfs():
            return
        console = self.query_one("#console", RichLog)
        if not await self.run_command("pacman -S --noconfirm --needed snapper btrfs-assistant"):
            console.write("[ERROR] Failed to install Snapper.")
            return
        if not await self.run_command("test -f /etc/snapper/configs/root || snapper --no-dbus -c root create-config /"):
            console.write("[ERROR] Failed to create the Snapper root configuration. Check the output above; existing snapshots are left unchanged.")
            return
        if not await self.run_command("systemctl enable snapper-timeline.timer snapper-cleanup.timer snapper-boot.timer"):
            console.write("[ERROR] Snapper is configured, but enabling its timers failed.")
            return
        console.write("Snapper and BTRFS Assistant installed and enabled.")

    async def btrfs_setup_grub(self):
        if not await self._require_btrfs():
            return
        console = self.query_one("#console", RichLog)
        if not await self.run_command("pacman -S --noconfirm --needed grub-btrfs inotify-tools"):
            console.write("[ERROR] Failed to install grub-btrfs.")
            return
        if not await self.run_command("systemctl enable grub-btrfsd.service"):
            console.write("[ERROR] Failed to enable grub-btrfsd.")
            return
        if not await self.run_command("grub-mkconfig -o /boot/grub/grub.cfg"):
            console.write("[ERROR] Failed to regenerate the GRUB configuration.")
            return
        console.write("grub-btrfs configured successfully.")

    async def btrfs_install_snappac(self):
        if not await self._require_btrfs():
            return
        console = self.query_one("#console", RichLog)
        if await self.run_command("pacman -S --noconfirm --needed snap-pac"):
            console.write("snap-pac installed successfully.")
        else:
            console.write("[ERROR] Failed to install snap-pac.")
