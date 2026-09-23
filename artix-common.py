"""Shared Artix compatibility layer for the Artix installer variants."""

from __future__ import annotations

import os
import re
import shlex
import stat
import sys
import tempfile
from typing import Optional

from textual import on
from textual.widgets import Header, Input, RadioButton, RadioSet, RichLog, Static, TabbedContent

class ArtixInstaller(T2ArchInstaller):
    APP_TITLE = "T2 Artix Linux Installer"
    INCLUDE_T2 = True
    INIT_STATE_FILE = "/run/t2archinstall/t2artixinstall-init"

    INIT_LABELS = {
        "openrc": "OpenRC",
        "dinit": "dinit",
        "runit": "runit",
        "s6": "s6",
    }

    INIT_CORE_PACKAGES = {
        "openrc": ["openrc", "elogind-openrc"],
        "dinit": ["dinit", "elogind-dinit"],
        "runit": ["runit", "elogind-runit"],
        "s6": ["s6-base", "s6-frontend", "elogind-s6"],
    }

    INIT_SCRIPT_AVAILABILITY = {
        "acpid": {"openrc", "dinit", "runit", "s6"},
        "alsa-utils": {"openrc", "dinit", "runit", "s6"},
        "avahi": {"openrc", "dinit", "runit", "s6"},
        "backlight": {"openrc", "dinit", "runit", "s6"},
        "bluez": {"openrc", "dinit", "runit", "s6"},
        "colord": {"openrc", "dinit", "runit", "s6"},
        "connman": {"openrc", "dinit", "runit", "s6"},
        "cpupower": {"openrc", "dinit", "runit", "s6"},
        "cronie": {"openrc", "dinit", "runit", "s6"},
        "cups": {"openrc", "dinit", "runit", "s6"},
        "dbus": {"openrc", "dinit", "runit", "s6"},
        "device-mapper": {"openrc", "dinit", "runit", "s6"},
        "dhcp": {"openrc", "dinit", "runit", "s6"},
        "dhcpcd": {"openrc", "dinit", "runit", "s6"},
        "dnsmasq": {"openrc", "dinit", "runit", "s6"},
        "gdm": {"openrc", "dinit", "runit", "s6"},
        "git": {"openrc", "dinit", "runit", "s6"},
        "greetd": {"openrc", "dinit", "runit"},
        "grub-btrfs": {"openrc", "dinit", "runit", "s6"},
        "iwd": {"openrc", "dinit", "runit", "s6"},
        "libvirt": {"openrc", "dinit", "runit", "s6"},
        "lvm2": {"openrc", "dinit", "runit", "s6"},
        "mpd": {"openrc", "dinit", "runit", "s6"},
        "networkmanager": {"openrc", "dinit", "runit", "s6"},
        "pipewire": {"openrc", "dinit"},
        "pipewire-pulse": {"openrc", "dinit"},
        "power-profiles-daemon": {"openrc", "dinit", "runit", "s6"},
        "sddm": {"openrc", "dinit", "runit", "s6"},
        "thermald": {"openrc", "dinit", "runit", "s6"},
        "wireplumber": {"openrc", "dinit"},
    }

    S6_SERVICE_NAME_MAP = {
        "NetworkManager": "NetworkManager-srv",
        "iwd": "iwd-srv",
        "bluetoothd": "bluetoothd-srv",
        "cupsd": "cupsd-srv",
        "cronie": "cronie-srv",
        "gdm": "gdm-srv",
        "greetd": "greetd-srv",
        "grub-btrfsd": "grub-btrfsd-srv",
        "libvirtd": "libvirtd-srv",
        "mpd": "mpd-srv",
        "power-profiles-daemon": "power-profiles-daemon-srv",
        "sddm": "sddm-srv",
        "t2fanrd": "t2fanrd-srv",
        "tiny-dfr": "tiny-dfr-srv",
        "upower": "upower-srv",
    }

    SERVICE_NAME_MAP = {
        "bluetooth": "bluetoothd",
        "cups": "cupsd",
        "gdm": "gdm",
        "greetd": "greetd",
        "iwd": "iwd",
        "libvirtd": "libvirtd",
        "NetworkManager": "NetworkManager",
        "networkmanager": "NetworkManager",
        "plasmalogin": "sddm",
        "sddm": "sddm",
        "cosmic-greeter": "greetd",
        "power-profiles-daemon": "power-profiles-daemon",
        "systemd-resolved": None,
        "snapper-timeline.timer": None,
        "snapper-cleanup.timer": None,
        "snapper-boot.timer": None,
    }

    def __init__(self) -> None:
        super().__init__()
        requested = os.environ.get("ARTIX_INIT", "").strip().lower()
        if requested not in self.INIT_CORE_PACKAGES:
            requested = self._read_saved_init_system()
        self.init_system = requested if requested in self.INIT_CORE_PACKAGES else "openrc"
        self._save_init_system()

    def _init_state_directory(self) -> str:
        directory = os.path.dirname(self.INIT_STATE_FILE)
        os.makedirs(directory, mode=0o700, exist_ok=True)
        info = os.lstat(directory)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise PermissionError(f"Unsafe init state directory: {directory}")
        return directory

    def _read_saved_init_system(self) -> str:
        try:
            self._init_state_directory()
            fd = os.open(self.INIT_STATE_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, encoding="utf-8") as state_file:
                info = os.fstat(state_file.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                    return ""
                return state_file.read(64).strip().lower()
        except (OSError, UnicodeError):
            return ""

    def _save_init_system(self) -> None:
        tmp_path = None
        try:
            directory = self._init_state_directory()
            fd, tmp_path = tempfile.mkstemp(prefix=".init-", dir=directory)
            with os.fdopen(fd, "w", encoding="utf-8") as state_file:
                state_file.write(f"{self.init_system}\n")
            os.replace(tmp_path, self.INIT_STATE_FILE)
        except OSError as exc:
            print(f"[WARN] Could not save the selected init system: {exc}", file=sys.stderr)
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except FileNotFoundError:
                    pass

    async def on_mount(self) -> None:
        if self.post_install_mode:
            self.title = self.APP_TITLE
            return
        await super().on_mount()
        self.title = self.APP_TITLE

        try:
            header = self.query_one(Header)
            header.tooltip = self.APP_TITLE
        except Exception:
            pass

        self._configure_variant_ui()
        self._update_manual_install_command()
        self.query_one("#console", RichLog).write(
            f"[INFO] Target init system: {self.INIT_LABELS[self.init_system]}"
        )

    def _configure_variant_ui(self) -> None:
        for widget_id in ("systemd_bootloader", "gnome_auto_btn"):
            try:
                self.query_one(f"#{widget_id}").display = False
            except Exception:
                pass

        if self.INCLUDE_T2:
            return

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
            try:
                self.query_one(f"#{widget_id}").display = False
            except Exception:
                pass

    @on(RadioSet.Changed, "#artix_init_choice")
    def on_artix_init_changed(self, event: RadioSet.Changed) -> None:
        if event.pressed is None or not event.pressed.id:
            return
        selected = event.pressed.id.removeprefix("artix_init_")
        if selected not in self.INIT_CORE_PACKAGES:
            return
        self.init_system = selected
        self._save_init_system()
        self._update_manual_install_command()
        try:
            self.query_one("#console", RichLog).write(
                f"[INFO] Target init changed to {self.INIT_LABELS[selected]}."
            )
        except Exception:
            pass

    async def run_command(self, command: str, timeout: int = 300) -> bool:
        command = re.sub(r"\bgenfstab\b", "fstabgen", command)
        command = re.sub(r"\barch-chroot\b", "artix-chroot", command)
        return await super().run_command(command, timeout=timeout)

    async def run_in_chroot(self, inner_cmd: str, timeout: int = 300) -> bool:
        translated = self._translate_chroot_command(inner_cmd)
        if not translated or translated.strip() == "true":
            return True
        if self.post_install_mode:
            return await self.run_command(translated, timeout=timeout)
        if not self._is_chroot_ready():
            self.query_one("#console", RichLog).write(
                "[ERROR] Chroot is not ready. Install the Artix base system first."
            )
            return False

        # stdbuf does not work with if/heredocs.
        chroot_cmd = f"artix-chroot /mnt bash -lc {shlex.quote(translated)}"
        return await self.run_command(chroot_cmd, timeout=timeout)

    def _translate_chroot_command(self, command: str) -> str:
        translated = command.replace("/etc/systemd/logind.conf", "/etc/elogind/logind.conf")
        translated = translated.replace("/etc/systemd/sleep.conf", "/etc/elogind/sleep.conf")

        if "/etc/systemd/system/greetd.service.d" in translated:
            return "true"

        # Start DMS from Niri instead of systemd.
        if ".config/systemd/user/niri.service.wants" in translated or "/usr/lib/systemd/user/dms.service" in translated:
            if not self.username:
                return "true"
            config = f"/home/{self.username}/.config/niri/config.kdl"
            return (
                f"mkdir -p /home/{self.username}/.config/niri && "
                f"touch {shlex.quote(config)} && "
                f"grep -Fqx 'spawn-at-startup \"dms\" \"run\"' {shlex.quote(config)} || "
                f"echo 'spawn-at-startup \"dms\" \"run\"' >> {shlex.quote(config)}; "
                f"chown -R {shlex.quote(self.username)}:{shlex.quote(self.username)} "
                f"/home/{shlex.quote(self.username)}/.config"
            )

        translated = self._augment_pacman_command(translated)

        translated = re.sub(
            r"systemctl\s+disable(?:\s+--now)?\s+([A-Za-z0-9_.@-]+)",
            lambda match: self._disable_service_command(match.group(1)),
            translated,
        )
        translated = re.sub(
            r"systemctl\s+enable\s+([A-Za-z0-9_.@-]+)",
            lambda match: self._enable_service_command(match.group(1)),
            translated,
        )
        translated = re.sub(
            r"systemctl\s+restart\s+([A-Za-z0-9_.@-]+)",
            lambda match: self._restart_service_command(match.group(1)),
            translated,
        )
        return translated

    def _augment_pacman_command(self, command: str) -> str:
        stripped = command.strip()
        if not re.match(r"^pacman\s+-S", stripped):
            return command
        if any(token in command for token in ("\n", "&&", "||", ";", "<<")):
            return command

        try:
            words = shlex.split(command)
        except ValueError:
            return command
        if len(words) < 3:
            return command

        packages = [word for word in words[2:] if not word.startswith("-")]
        additions: list[str] = []

        def add(package: Optional[str]) -> None:
            if package and package not in words and package not in additions:
                additions.append(package)

        unqualified_packages = {item.split("/", 1)[-1] for item in packages}
        if "sl-desktop-utils" in unqualified_packages:
            add("greetd")
            add(self._service_package("greetd"))

        for package in packages:
            add(self._service_package(package.split("/", 1)[-1]))

        if not additions:
            return command
        return f"{command} {' '.join(shlex.quote(item) for item in additions)}"

    def _service_package(self, package: str) -> Optional[str]:
        supported = self.INIT_SCRIPT_AVAILABILITY.get(package)
        if supported and self.init_system in supported:
            return f"{package}-{self.init_system}"
        return None

    def _s6_service_name(self, service: str) -> str:
        if service.startswith("agetty-"):
            return service
        return self.S6_SERVICE_NAME_MAP.get(service, service if service.endswith("-srv") else f"{service}-srv")

    def _s6_repository_prepare_command(self) -> str:
        return (
            "if s6 repository list >/dev/null 2>&1; then "
            "s6 repository sync; else s6 repository init; fi"
        )

    def _s6_apply_command(self, change: str = "true") -> str:
        install = "s6 live install" if self.post_install_mode else "s6 live install --init"
        verify = " && test -e /etc/s6/rc/compiled" if not self.post_install_mode else ""
        return (
            f"{self._s6_repository_prepare_command()} && "
            f"( {change} ) && "
            "s6 set check -F -u && "
            "s6 set commit && "
            f"{install}{verify}"
        )

    @staticmethod
    def _getty_tty(service: str) -> Optional[str]:
        name = service.removesuffix(".service")
        match = re.fullmatch(r"(?:getty@|agetty[.-])(tty[0-9]+)", name)
        return match.group(1) if match else None

    def _normalise_service_name(self, service: str) -> Optional[str]:
        name = service.removesuffix(".service")
        if self._getty_tty(service):
            return None
        return self.SERVICE_NAME_MAP.get(name, name)

    def _enable_getty_command(self, tty: str, runlevel: str = "default") -> str:
        openrc_name = shlex.quote(f"agetty.{tty}")
        common_name = f"agetty-{tty}"
        quoted_common = shlex.quote(common_name)
        if self.init_system == "openrc":
            return f"rc-update add {openrc_name} {shlex.quote(runlevel)}"
        if self.init_system == "runit":
            return (
                "install -d /etc/runit/runsvdir/default && "
                f"ln -sfn /etc/runit/sv/{quoted_common} "
                f"/etc/runit/runsvdir/default/{quoted_common}"
            )
        if self.init_system == "dinit":
            return f"dinitctl --offline enable {quoted_common}"
        return self._s6_apply_command(f"s6 set enable {quoted_common}")

    def _disable_getty_command(self, tty: str) -> str:
        openrc_name = shlex.quote(f"agetty.{tty}")
        common_name = f"agetty-{tty}"
        quoted_common = shlex.quote(common_name)
        if self.init_system == "openrc":
            return (
                f"rc-update del {openrc_name} boot 2>/dev/null || true; "
                f"rc-update del {openrc_name} default 2>/dev/null || true"
            )
        if self.init_system == "runit":
            return (
                f"rm -f /etc/runit/runsvdir/default/{quoted_common} "
                f"/run/runit/service/{quoted_common}"
            )
        if self.init_system == "dinit":
            return (
                f"dinitctl --offline disable {quoted_common} 2>/dev/null || true; "
                f"rm -f /etc/dinit.d/boot.d/{quoted_common}"
            )
        return self._s6_apply_command(f"s6 set disable {quoted_common} 2>/dev/null || true")

    def _enable_service_command(self, service: str, runlevel: str = "default") -> str:
        tty = self._getty_tty(service)
        if tty:
            return self._enable_getty_command(tty, runlevel)
        name = self._normalise_service_name(service)
        if not name:
            return "true"
        if self.init_system == "openrc":
            return f"rc-update add {shlex.quote(name)} {shlex.quote(runlevel)}"
        if self.init_system == "runit":
            quoted = shlex.quote(name)
            return (
                "install -d /etc/runit/runsvdir/default && "
                f"ln -sfn /etc/runit/sv/{quoted} /etc/runit/runsvdir/default/{quoted}"
            )
        if self.init_system == "dinit":
            return f"dinitctl --offline enable {shlex.quote(name)}"
        s6_name = shlex.quote(self._s6_service_name(name))
        return self._s6_apply_command(f"s6 set enable {s6_name}")

    def _disable_service_command(self, service: str, runlevel: str = "default") -> str:
        tty = self._getty_tty(service)
        if tty:
            return self._disable_getty_command(tty)
        name = self._normalise_service_name(service)
        if not name:
            return "true"
        if self.init_system == "openrc":
            return f"rc-update del {shlex.quote(name)} {shlex.quote(runlevel)} 2>/dev/null || true"
        if self.init_system == "runit":
            quoted = shlex.quote(name)
            return f"rm -f /etc/runit/runsvdir/default/{quoted} /run/runit/service/{quoted}"
        if self.init_system == "dinit":
            return f"dinitctl --offline disable {shlex.quote(name)} 2>/dev/null || true"
        s6_name = shlex.quote(self._s6_service_name(name))
        return self._s6_apply_command(f"s6 set disable {s6_name} 2>/dev/null || true")

    def _restart_service_command(self, service: str) -> str:
        name = self._normalise_service_name(service)
        if not name:
            return "true"

        if self.init_system == "openrc":
            return f"rc-service {shlex.quote(name)} restart"

        if self.init_system == "runit":
            return f"sv restart {shlex.quote(name)}"

        if self.init_system == "dinit":
            return f"dinitctl restart {shlex.quote(name)}"

        s6_name = self._s6_service_name(name)
        return f"s6-svc -r {shlex.quote(f'/run/service/{s6_name}')}"

    def _append_base_service_package(self, packages: list[str], package: str) -> None:
        if self.init_system == "s6":
            return
        service_package = self._service_package(package)
        if service_package:
            packages.append(service_package)

    def _base_packages(self) -> list[str]:
        # Preserve the original package order.
        packages = [
            "base",
            *self.INIT_CORE_PACKAGES[self.init_system],
            "artix-archlinux-support",
        ]

        if self.INCLUDE_T2:
            packages.extend(
                [
                    "linux-t2",
                    "linux-t2-headers",
                    "apple-t2-audio-config",
                    "apple-bcm-firmware-fetcher",
                ]
            )
        else:
            packages.extend(["linux", "linux-headers"])

        packages.extend(["linux-firmware", "wpa_supplicant"])
        packages.append("networkmanager")
        self._append_base_service_package(packages, "networkmanager")
        self._append_base_service_package(packages, "connman")
        packages.extend(["connman-gtk", "dhcp"])
        self._append_base_service_package(packages, "dhcp")
        packages.append("dhcpcd")
        self._append_base_service_package(packages, "dhcpcd")
        packages.extend(["bluez"])
        self._append_base_service_package(packages, "bluez")
        packages.extend(["bluez-utils", "dbus"])
        self._append_base_service_package(packages, "dbus")

        if self.INCLUDE_T2:
            packages.append("t2fanrd")

        packages.extend(["grub", "efibootmgr", "nano", "sudo", "git"])
        self._append_base_service_package(packages, "git")
        packages.extend(["base-devel", "alsa-utils"])
        self._append_base_service_package(packages, "alsa-utils")
        packages.append("avahi")
        self._append_base_service_package(packages, "avahi")
        packages.append("colord")
        self._append_base_service_package(packages, "colord")
        packages.append("cups")
        self._append_base_service_package(packages, "cups")
        packages.append("acpid")
        self._append_base_service_package(packages, "acpid")
        packages.append("cronie")
        self._append_base_service_package(packages, "cronie")
        packages.append("cpupower")
        self._append_base_service_package(packages, "cpupower")
        packages.append("thermald")
        self._append_base_service_package(packages, "thermald")
        self._append_base_service_package(packages, "backlight")
        packages.append("pipewire")
        self._append_base_service_package(packages, "pipewire")
        packages.append("pipewire-alsa")
        packages.append("wireplumber")
        self._append_base_service_package(packages, "wireplumber")
        packages.append("pipewire-pulse")
        self._append_base_service_package(packages, "pipewire-pulse")
        packages.append("libvirt")
        self._append_base_service_package(packages, "libvirt")
        packages.append("dnsmasq")
        self._append_base_service_package(packages, "dnsmasq")
        if not self.INCLUDE_T2:
            packages.append("qemu-desktop")
        packages.extend(["virt-manager", "lvm2"])
        self._append_base_service_package(packages, "lvm2")
        self._append_base_service_package(packages, "device-mapper")
        packages.append("btrfs-progs")
        return list(dict.fromkeys(packages))

    def _base_service_packages(self) -> list[str]:
        if self.init_system != "s6":
            return []

        service_names = [
            "networkmanager",
            "connman",
            "dhcp",
            "dhcpcd",
            "bluez",
            "dbus",
            "git",
            "alsa-utils",
            "avahi",
            "colord",
            "cups",
            "acpid",
            "cronie",
            "cpupower",
            "thermald",
            "backlight",
            "libvirt",
            "dnsmasq",
            "lvm2",
            "device-mapper",
        ]
        if not self.INCLUDE_T2:
            service_names.insert(0, "iwd")

        packages: list[str] = []
        for package in service_names:
            service_package = self._service_package(package)
            if service_package:
                packages.append(service_package)
        return list(dict.fromkeys(packages))

    def _base_followup_command(self) -> str:
        commands: list[str] = []
        if self.init_system == "s6":
            commands.append(self._s6_repository_prepare_command())
            service_packages = self._base_service_packages()
            if service_packages:
                commands.append(
                    "pacman -S --noconfirm --needed "
                    + " ".join(shlex.quote(package) for package in service_packages)
                )
            commands.append(self._s6_apply_command())

        commands.extend(
            [
                "grep -q '^\\[extra\\]' /etc/pacman.conf || "
                "printf '\n[extra]\nInclude = /etc/pacman.d/mirrorlist-arch\n' >> /etc/pacman.conf",
                "pacman -Sy",
            ]
        )
        return " && ".join(commands)

    def _manual_install_command(self) -> str:
        packages = " ".join(shlex.quote(package) for package in self._base_packages())
        return f"basestrap -K /mnt {packages}"

    def _update_manual_install_command(self) -> None:
        try:
            self.query_one("#pacstrap_cmd", Static).update(self._manual_install_command())
        except Exception:
            pass

    async def add_t2_repo_to_chroot(self) -> bool:
        if self.INCLUDE_T2:
            return await super().add_t2_repo_to_chroot()
        self.query_one("#console", RichLog).write("[INFO] Generic Artix edition: no T2 repository is required.")
        self.query_one("#config_basic_btn").focus()
        return True

    async def set_timezone(self) -> None:
        console = self.query_one("#console", RichLog)
        timezone = self.query_one("#timezone_input", Input).value.strip() or "UTC"
        self.timezone = timezone
        zone_path = f"/usr/share/zoneinfo/{timezone}"
        if not os.path.exists(zone_path):
            console.write(f"[ERROR] Unknown timezone: {timezone}")
            return
        commands = [
            f"ln -sf {shlex.quote(zone_path)} /etc/localtime",
            "hwclock --systohc",
        ]
        for command in commands:
            if not await self.run_command(command):
                console.write("[ERROR] Failed to configure timezone.")
                return
        console.write(f"Timezone configured: {timezone}")
        self.query_one("#locales_input").focus()

    async def install_base_system_auto(self) -> None:
        console = self.query_one("#console", RichLog)
        if self.post_install_mode:
            console.write("[WARN] basestrap is install-only and unavailable in post-install mode.")
            return

        command = self._manual_install_command()
        console.write(
            f"Installing Artix with {self.INIT_LABELS[self.init_system]}. "
            "This can take a while."
        )
        if not await self.run_command(command, timeout=1800):
            console.write("[ERROR] Artix base installation failed. Try the manual command.")
            return

        if self.init_system == "s6":
            if not await self.run_in_chroot(self._s6_repository_prepare_command()):
                console.write("[ERROR] Failed to initialise the s6 service repository.")
                return

            service_packages = self._base_service_packages()
            if service_packages:
                package_command = "pacman -S --noconfirm --needed " + " ".join(
                    shlex.quote(package) for package in service_packages
                )
                if not await self.run_in_chroot(package_command, timeout=900):
                    console.write("[ERROR] Failed to install Artix s6 service packages.")
                    return

            if not await self.run_in_chroot(self._s6_apply_command()):
                console.write("[ERROR] Failed to compile and install the initial s6 boot database.")
                return

        repo_command = (
            "grep -q '^\\[extra\\]' /etc/pacman.conf || "
            "printf '\n[extra]\nInclude = /etc/pacman.d/mirrorlist-arch\n' >> /etc/pacman.conf"
        )
        if not await self.run_in_chroot(repo_command):
            console.write("[ERROR] Failed to configure the Arch extra repository.")
            return
        if not await self.run_in_chroot("pacman -Sy"):
            console.write("[ERROR] Failed to refresh target package databases.")
            return

        console.write("Artix base system installed successfully!")
        self.query_one("#left_panel").focus()
        self.query_one(TabbedContent).active = "system_tab"

    def install_base_system_manual(self) -> None:
        console = self.query_one("#console", RichLog)
        if self.post_install_mode:
            console.write("[WARN] Manual basestrap is unavailable in post-install mode.")
            return
        console.write("Exiting the app for manual installation...")
        console.write("Run this command in the terminal:")
        console.write(self._manual_install_command())
        followup = self._base_followup_command()
        if followup:
            console.write("Then run this command before restarting the installer:")
            console.write(f"artix-chroot /mnt bash -lc {shlex.quote(followup)}")
        console.write("Restart the installer when both commands finish.")
        self.exit()

    async def generate_fstab(self) -> None:
        await super().generate_fstab()
        if self.post_install_mode or not await self.target_root_uses_btrfs(log_warnings=False):
            return

        console = self.query_one("#console", RichLog)
        packages = ["cronie"]
        service_package = self._service_package("cronie")
        if service_package:
            packages.append(service_package)
        commands = [
            "pacman -S --noconfirm --needed " + " ".join(packages),
            "install -Dm755 /dev/stdin /etc/cron.hourly/snapper-timeline <<'EOF'\n#!/bin/sh\nsnapper -c root create --cleanup-algorithm timeline --description 'hourly timeline' >/dev/null 2>&1 || true\nEOF",
            "install -Dm755 /dev/stdin /etc/cron.daily/snapper-cleanup <<'EOF'\n#!/bin/sh\nsnapper -c root cleanup timeline >/dev/null 2>&1 || true\nsnapper -c root cleanup number >/dev/null 2>&1 || true\nEOF",
            self._enable_service_command("cronie"),
        ]
        for command in commands:
            if not await self.run_in_chroot(command):
                console.write(f"[WARN] Artix Snapper scheduling step failed: {command}")

    async def build_initramfs(self) -> None:
        """Build Artix initramfs images without UKI output."""
        console = self.query_one("#console", RichLog)
        preset = (
            "/etc/mkinitcpio.d/linux-t2.preset"
            if self.INCLUDE_T2
            else "/etc/mkinitcpio.d/linux.preset"
        )

        if self.use_lvm:
            if not await self.run_in_chroot(
                r"sed -i '/^HOOKS=/ {/lvm2/! s/\bblock\b/block lvm2/ }' /etc/mkinitcpio.conf"
            ):
                console.write("[ERROR] Failed to add the lvm2 mkinitcpio hook.")
                return

        disable_uki = (
            f"test -f {shlex.quote(preset)} && "
            f"sed -i -E 's|^([[:space:]]*)(default_uki|fallback_uki)=|\\1#\\2=|' {shlex.quote(preset)}"
        )
        if not await self.run_in_chroot(disable_uki):
            console.write("[ERROR] Failed to disable optional UKI generation.")
            return

        console.write("Building initramfs (This might take a while)...")
        if await self.run_in_chroot("mkinitcpio -P", timeout=600):
            console.write("Initramfs built successfully!")
            self.query_one("#left_panel").focus()
            self.query_one(TabbedContent).active = "boot_tab"
        else:
            console.write("[ERROR] Initramfs build failed")

    async def create_boot_icon(self) -> None:
        """Create the macOS Startup Manager icon."""
        console = self.query_one("#console", RichLog)
        if not await self.run_in_chroot(
            "pacman -S --noconfirm --needed wget librsvg python-pillow",
            timeout=600,
        ):
            console.write("[ERROR] Failed to install boot icon packages")
            return

        icon_url = (
            "https://gitea.artixlinux.org/artix/artwork/raw/branch/master/"
            "icons/artixlinux-logo-only.svg"
        )
        python_code = (
            'from PIL import Image; '
            'im=Image.open("/tmp/artix.png").convert("RGBA"); '
            'im.save("/boot/efi/.VolumeIcon.icns", format="ICNS")'
        )
        command = (
            f"wget -q -O /tmp/artix.svg {shlex.quote(icon_url)} && "
            "rsvg-convert -w 1024 -h 1024 -o /tmp/artix.png /tmp/artix.svg && "
            f"python3 -c {shlex.quote(python_code)} && "
            "test -s /boot/efi/.VolumeIcon.icns"
        )
        if await self.run_in_chroot(command, timeout=600):
            console.write("Boot icon created successfully!")
            self.query_one("#boot_label_btn").focus()
        else:
            console.write("[ERROR] Boot icon creation failed")

    async def _validate_dinit_configuration(self) -> bool:
        if self.init_system != "dinit":
            return True
        # dinit check output differs between versions.
        command = (
            "if command -v dinit-check >/dev/null 2>&1; then "
            "dinit-check || echo '[WARN] dinit-check reported a service issue'; "
            "elif command -v dinitcheck >/dev/null 2>&1; then "
            "dinitcheck || echo '[WARN] dinitcheck reported a service issue'; "
            "else echo '[INFO] dinit configuration checker is unavailable'; fi"
        )
        return await self.run_in_chroot(command)

    async def _install_dinit_plymouth_quit_service(self) -> bool:
        if self.init_system != "dinit":
            return True
        quit_script = """#!/bin/sh
if [ -x /usr/bin/plymouth ]; then
    /usr/bin/timeout 10 /usr/bin/plymouth quit >/dev/null 2>&1 || true
fi
exit 0
"""
        service = """type = scripted
command = /usr/local/libexec/sl-plymouth-quit
waits-for = local.target
restart = false
"""
        commands = [
            f"install -Dm755 /dev/stdin /usr/local/libexec/sl-plymouth-quit <<'EOF'\n{quit_script}EOF",
            f"install -Dm644 /dev/stdin /etc/dinit.d/sl-plymouth-quit <<'EOF'\n{service}EOF",
            "dinitctl --offline enable sl-plymouth-quit",
        ]
        for command in commands:
            if not await self.run_in_chroot(command):
                return False
        return await self._validate_dinit_configuration()

    async def install_plymouth(self) -> None:
        await super().install_plymouth()
        if self.init_system != "dinit":
            return
        if not await self.run_in_chroot("test -x /usr/bin/plymouth"):
            return
        console = self.query_one("#console", RichLog)
        if await self._install_dinit_plymouth_quit_service():
            console.write("dinit Plymouth quit service configured successfully!")
        else:
            console.write("[ERROR] Failed to configure Plymouth shutdown for dinit.")

    async def create_user_and_services(self) -> None:
        console = self.query_one("#console", RichLog)
        self.username = self.query_one("#username_input", Input).value.strip()
        password = self.query_one("#user_password_input", Input).value.strip()
        if not self.username:
            console.write("[ERROR] Please enter a username first.")
            return
        if not password:
            console.write("[ERROR] Please enter a user password.")
            return

        service_packages = [
            package
            for package in (
                self._service_package("networkmanager"),
                self._service_package("bluez"),
            )
            if package
        ]
        if service_packages:
            package_command = "pacman -S --noconfirm --needed " + " ".join(service_packages)
            if not await self.run_in_chroot(package_command, timeout=600):
                console.write("[ERROR] Failed to install required service scripts.")
                return

        quoted_user = shlex.quote(self.username)
        commands = [
            f"id -u {quoted_user} >/dev/null 2>&1 || useradd -m -G wheel,storage,power -s /bin/bash {quoted_user}",
            f"printf '%s:%s\\n' {quoted_user} {shlex.quote(password)} | chpasswd",
            self._enable_service_command("NetworkManager"),
            self._enable_service_command("bluetooth"),
        ]
        for command in commands:
            if not await self.run_in_chroot(command):
                console.write("[ERROR] User creation or service setup failed.")
                return

        if self.INCLUDE_T2:
            if not await self._ensure_simple_service(
                "t2fanrd", "/usr/bin/t2fanrd", "T2 Mac fan control daemon"
            ):
                console.write("[WARN] Could not create the t2fanrd init service.")
            elif not await self.run_in_chroot(self._enable_service_command("t2fanrd")):
                console.write("[WARN] Could not enable t2fanrd.")

        if not await self._install_user_audio_autostart(self.username):
            console.write("[WARN] Could not configure the user PipeWire session launcher.")

        await self._validate_dinit_configuration()
        console.write("User and Artix services configured successfully!")
        self.query_one("#user_password_input", Input).value = ""
        try:
            self.query_one("#no_de_btn").focus()
        except Exception:
            pass

    async def _install_user_audio_autostart(self, username: str) -> bool:
        """Configure PipeWire startup for graphical sessions on Artix."""
        home = f"/home/{username}"
        launcher = f"{home}/.local/bin/start-pipewire-session"
        desktop = f"{home}/.config/autostart/pipewire-session.desktop"
        script = """#!/bin/sh
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
[ -d "$XDG_RUNTIME_DIR" ] || exit 0

sleep 1
if ! pgrep -u "$(id -u)" -x pipewire >/dev/null 2>&1; then
    pipewire >/dev/null 2>&1 &
fi
sleep 0.3
if ! pgrep -u "$(id -u)" -x pipewire-pulse >/dev/null 2>&1; then
    pipewire-pulse >/dev/null 2>&1 &
fi
sleep 0.2
if ! pgrep -u "$(id -u)" -x wireplumber >/dev/null 2>&1; then
    wireplumber >/dev/null 2>&1 &
fi
"""
        desktop_text = f"""[Desktop Entry]
Type=Application
Name=PipeWire Session
Exec={launcher}
X-GNOME-Autostart-enabled=true
NoDisplay=true
"""
        command = (
            "set -e\n"
            f"install -Dm755 /dev/stdin {shlex.quote(launcher)} <<'EOF'\n{script}EOF\n"
            f"install -Dm644 /dev/stdin {shlex.quote(desktop)} <<'EOF'\n{desktop_text}EOF\n"
            f"chown -R {shlex.quote(username)}:{shlex.quote(username)} "
            f"{shlex.quote(home + '/.local')} {shlex.quote(home + '/.config/autostart')}"
        )
        if not await self.run_in_chroot(command):
            return False

        if self.init_system == "openrc":
            user_services = (
                "rc-update -U add pipewire default && "
                "rc-update -U add pipewire-pulse default && "
                "rc-update -U add wireplumber default"
            )
            enable_command = f"su - {shlex.quote(username)} -c {shlex.quote(user_services)}"
            if not await self.run_in_chroot(enable_command):
                self.query_one("#console", RichLog).write(
                    "[WARN] Could not enable OpenRC PipeWire user services; "
                    "the graphical-session fallback remains installed."
                )

        return True

    async def _add_niri_audio_autostart(self, username: str) -> bool:
        """Add the PipeWire launcher to an existing Niri configuration."""
        home = f"/home/{username}"
        launcher = f"{home}/.local/bin/start-pipewire-session"
        config = f"{home}/.config/niri/config.kdl"
        spawn = f'spawn-at-startup "{launcher}"'

        if not await self.run_in_chroot(
            f"test -x {shlex.quote(launcher)} -a -f {shlex.quote(config)}"
        ):
            return False

        command = (
            f"grep -Fqx {shlex.quote(spawn)} {shlex.quote(config)} || "
            f"printf '%s\n' {shlex.quote(spawn)} >> {shlex.quote(config)}; "
            f"chown {shlex.quote(username)}:{shlex.quote(username)} {shlex.quote(config)}"
        )
        return await self.run_in_chroot(command)

    async def install_niri(self) -> bool:
        installed = await super().install_niri()
        if installed and self.username:
            if not await self._add_niri_audio_autostart(self.username):
                self.query_one("#console", RichLog).write(
                    "[WARN] Could not add the PipeWire launcher to Niri."
                )
        if installed and not await self.run_in_chroot(
            self._enable_service_command("power-profiles-daemon")
        ):
            self.query_one("#console", RichLog).write(
                "[ERROR] Failed to enable power-profiles-daemon."
            )
            return False
        return installed

    async def install_niri_with_dms(self) -> bool:
        installed = await super().install_niri_with_dms()
        if installed and self.username:
            if not await self._add_niri_audio_autostart(self.username):
                self.query_one("#console", RichLog).write(
                    "[WARN] Could not add the PipeWire launcher to Niri."
                )
         if installed and not await self.run_in_chroot(
            self._enable_service_command("power-profiles-daemon")
        ):
            self.query_one("#console", RichLog).write(
                "[ERROR] Failed to enable power-profiles-daemon."
            )
            return False
        return installed

    async def _ensure_simple_service(self, service: str, command: str, description: str) -> bool:
        name = self._normalise_service_name(service) or service.removesuffix(".service")
        if self.init_system == "openrc":
            path = f"/etc/init.d/{name}"
            body = (
                "#!/sbin/openrc-run\n"
                f"description={shlex.quote(description)}\n"
                f"command={shlex.quote(command)}\n"
                "command_background=false\n"
                "supervisor=supervise-daemon\n"
            )
            install = f"install -Dm755 /dev/stdin {shlex.quote(path)} <<'EOF'\n{body}EOF"
        elif self.init_system == "runit":
            path = f"/etc/runit/sv/{name}/run"
            body = f"#!/bin/sh\nexec {command}\n"
            install = f"install -Dm755 /dev/stdin {shlex.quote(path)} <<'EOF'\n{body}EOF"
        elif self.init_system == "dinit":
            path = f"/etc/dinit.d/{name}"
            body = f"type = process\ncommand = {command}\nrestart = true\n"
            install = f"install -Dm644 /dev/stdin {shlex.quote(path)} <<'EOF'\n{body}EOF"
        else:
            s6_name = self._s6_service_name(name)
            path = f"/etc/s6/sv/{s6_name}/run"
            body = f"#!/bin/sh\nexec {command}\n"
            dependency = ""
            if name == "greetd":
                dependency = (
                    f"\ninstall -d /etc/s6/sv/{shlex.quote(s6_name)}/dependencies.d"
                    f"\ntouch /etc/s6/sv/{shlex.quote(s6_name)}/dependencies.d/logind"
                )
            install = (
                f"install -Dm755 /dev/stdin {shlex.quote(path)} <<'EOF'\n{body}EOF\n"
                f"printf 'longrun\\n' > /etc/s6/sv/{shlex.quote(s6_name)}/type"
                f"{dependency}"
            )
        return await self.run_in_chroot(f"test -e {shlex.quote(path)} || ( {install} )")

    async def wm_install_greetd_dms_greeter(self) -> bool:
        console = self.query_one("#console", RichLog)
        if not self.username:
            console.write("[ERROR] Username not set. Create the user first.")
            return False

        packages = ["greetd"]
        service_package = self._service_package("greetd")
        if service_package:
            packages.append(service_package)
        if not await self.run_in_chroot(
            "pacman -S --noconfirm --needed " + " ".join(packages), timeout=600
        ):
            console.write("[ERROR] Failed to install greetd and its init service.")
            return False

        if self.init_system == "s6" and not await self._ensure_simple_service(
            "greetd", "/usr/bin/greetd", "Greeter daemon"
        ):
            console.write("[ERROR] Failed to create the s6 greetd service.")
            return False

        config = """[terminal]
    vt = 2

    [default_session]
    command = "dms-greeter --command niri"
    user = "greeter"
    """
        commands = [
            f"install -Dm644 /dev/stdin /etc/greetd/config.toml <<'EOF'\n{config}EOF",
            self._disable_getty_command("tty2"),
            self._enable_service_command("greetd"),
        ]
        for command in commands:
            if not await self.run_in_chroot(command):
                console.write("[ERROR] Failed to configure greetd with DMS.")
                return False
        console.write("greetd configured with DMS successfully!")
        return True

    async def wm_install_sl_desktop_utils(self) -> bool:
        console = self.query_one("#console", RichLog)
        if not self.username:
            console.write("[ERROR] Username not set. Create the user first.")
            return False
        if not await self.add_slsrepo_to_chroot():
            console.write("[ERROR] Failed to add Sl's Arch Repository.")
            return False

        packages = [
            "niri", "wayidle-git", "greetd", "sl-desktop-utils"
        ]
        service_package = self._service_package("greetd")
        if service_package:
            packages.append(service_package)
        if not await self.run_in_chroot(
            "pacman -S --noconfirm --needed " + " ".join(packages), timeout=900
        ):
            console.write("[ERROR] Failed to install sl-desktop-utils.")
            return False

        if self.init_system == "s6" and not await self._ensure_simple_service(
            "greetd", "/usr/bin/greetd", "Greeter daemon"
        ):
            console.write("[ERROR] Failed to create the s6 greetd service.")
            return False

        username = self.username
        setup_wallpaper = (
            f"mkdir -p /home/{username}/.local/bin && "
            f"ln -sf /usr/local/share/backgrounds/sl-greeter-current-background "
            f"/home/{username}/.local/bin/current-background && "
            f"chown -R {username}:{username} /home/{username}/.local"
        )
        if not await self.run_in_chroot(setup_wallpaper):
            console.write("[WARN] Could not set up the user wallpaper symlink.")

        for command in (
            self._disable_getty_command("tty2"),
            self._enable_service_command("greetd"),
        ):
            if not await self.run_in_chroot(command):
                console.write("[ERROR] Failed to enable greetd.")
                return False
        console.write("sl-greeter and sl-lock installed and configured successfully!")
        return True

    async def install_desktop_environment(self, de_type: str, is_manual: bool) -> None:
        del is_manual
        console = self.query_one("#console", RichLog)
        if de_type == "niri":
            if await self.install_niri():
                console.write("Niri installed successfully!")
                self._finish_desktop_step()
            return
        if de_type == "niridms":
            if await self.install_niri_with_dms():
                console.write("Niri with DMS installed successfully!")
                self._finish_desktop_step()
            return

        if de_type == "kde":
            packages = [
                "world/plasma-meta", "world/sddm", "world/konsole",
                "world/dolphin", "world/kate", "world/ark", "world/spectacle",
            ]
            service_package = self._service_package("sddm")
            if service_package:
                packages.append(service_package)
            commands = [
                "pacman -S --noconfirm --needed " + " ".join(packages),
                self._enable_service_command("sddm"),
            ]
        elif de_type == "cosmic":
            packages = ["cosmic", "greetd"]
            service_package = self._service_package("greetd")
            if service_package:
                packages.append(service_package)
            if not await self.run_in_chroot(
                "pacman -S --noconfirm --needed " + " ".join(packages), timeout=1800
            ):
                console.write("[ERROR] COSMIC installation failed.")
                return
            if self.init_system == "s6" and not await self._ensure_simple_service(
                "greetd", "/usr/bin/greetd", "Greeter daemon"
            ):
                console.write("[ERROR] Failed to create the s6 greetd service.")
                return
            commands = [
                self._disable_getty_command("tty2"),
                self._enable_service_command("greetd"),
            ]
        elif de_type == "gnome":
            packages = ["world/gnome", "world/gdm", "power-profiles-daemon"]
            service_package = self._service_package("gdm")
            if service_package:
                packages.append(service_package)
            commands = [
                "pacman -S --noconfirm --needed " + " ".join(packages),
                self._enable_service_command("gdm"),
                self._enable_service_command("power-profiles-daemon")
            ]
        else:
            console.write(f"[ERROR] Unsupported desktop: {de_type}")
            return

        for command in commands:
            if not await self.run_in_chroot(command, timeout=1800):
                console.write(f"[ERROR] {de_type.upper()} installation failed.")
                return
        console.write("Desktop environment installed successfully!")
        self._finish_desktop_step()

    def _finish_desktop_step(self) -> None:
        try:
            self.query_one("#left_panel").focus()
            self.query_one(TabbedContent).active = "extras_tab"
        except Exception:
            pass

    async def install_tiny_dfr(self) -> None:
        await super().install_tiny_dfr()
        if not self.INCLUDE_T2:
            return
        console = self.query_one("#console", RichLog)
        if not await self._ensure_simple_service(
            "tiny-dfr",
            "/usr/bin/tiny-dfr",
            "T2 Touch Bar daemon",
        ):
            console.write("[WARN] Could not create the tiny-dfr init service.")
            return
        if not await self.run_in_chroot(self._enable_service_command("tiny-dfr")):
            console.write("[WARN] Could not enable tiny-dfr.")

    async def disable_suspend_sleep(self) -> None:
        console = self.query_one("#console", RichLog)
        command = (
            "install -d /etc/elogind && "
            "grep -q '^\\[Sleep\\]' /etc/elogind/sleep.conf 2>/dev/null || "
            "printf '[Sleep]\\n' >> /etc/elogind/sleep.conf; "
            "printf '\\nAllowSuspend=no\\nAllowHibernation=no\\n"
            "AllowHybridSleep=no\\nAllowSuspendThenHibernate=no\\n' "
            ">> /etc/elogind/sleep.conf"
        )
        if await self.run_in_chroot(command):
            console.write("Suspend and hibernation disabled in /etc/elogind/sleep.conf.")
            self.maybe_redirect_completion_from_extras()
        else:
            console.write("[ERROR] Failed to update elogind sleep.conf.")

    async def ignore_lid_switch(self) -> None:
        console = self.query_one("#console", RichLog)
        commands = [
            "install -d /etc/elogind",
            "touch /etc/elogind/logind.conf",
            "grep -q '^HandleLidSwitch=' /etc/elogind/logind.conf && sed -i 's/^HandleLidSwitch=.*/HandleLidSwitch=ignore/' /etc/elogind/logind.conf || echo 'HandleLidSwitch=ignore' >> /etc/elogind/logind.conf",
            "grep -q '^HandleLidSwitchDocked=' /etc/elogind/logind.conf && sed -i 's/^HandleLidSwitchDocked=.*/HandleLidSwitchDocked=ignore/' /etc/elogind/logind.conf || echo 'HandleLidSwitchDocked=ignore' >> /etc/elogind/logind.conf",
            "grep -q '^HandleLidSwitchExternalPower=' /etc/elogind/logind.conf && sed -i 's/^HandleLidSwitchExternalPower=.*/HandleLidSwitchExternalPower=ignore/' /etc/elogind/logind.conf || echo 'HandleLidSwitchExternalPower=ignore' >> /etc/elogind/logind.conf",
        ]
        for command in commands:
            if not await self.run_in_chroot(command):
                console.write("[ERROR] Failed to update elogind lid handling.")
                return
        console.write("Lid switch handling set to ignore in /etc/elogind/logind.conf.")
        self.maybe_redirect_completion_from_extras()

    async def install_suspend_fix(self) -> None:
        script = """#!/bin/sh
case "$1" in
  pre)
    modprobe -r brcmfmac_wcc 2>/dev/null || true
    modprobe -r brcmfmac 2>/dev/null || true
    rmmod -f apple-bce 2>/dev/null || true
    ;;
  post)
    modprobe apple-bce 2>/dev/null || true
    modprobe brcmfmac 2>/dev/null || true
    modprobe brcmfmac_wcc 2>/dev/null || true
    ;;
esac
"""
        await self._install_elogind_sleep_hook("suspend-fix-t2", script)

    async def install_extended_suspend_fix(self) -> None:
        stop_tiny = self._runtime_service_action("tiny-dfr", "stop")
        start_tiny = self._runtime_service_action("tiny-dfr", "start")
        restart_upower = self._runtime_service_action("upower", "restart")
        script = f"""#!/bin/sh
case "$1" in
  pre)
    printf 0 > /sys/class/leds/:white:kbd_backlight/brightness 2>/dev/null || true
    {stop_tiny}
    rmmod appletbdrm 2>/dev/null || true
    rmmod hid_appletb_kbd 2>/dev/null || true
    rmmod hid_appletb_bl 2>/dev/null || true
    rmmod -f apple-bce 2>/dev/null || true
    ;;
  post)
    modprobe apple-bce 2>/dev/null || true
    sleep 4
    modprobe hid_appletb_bl 2>/dev/null || true
    modprobe hid_appletb_kbd 2>/dev/null || true
    modprobe appletbdrm 2>/dev/null || true
    printf 0 > /sys/bus/usb/devices/3-6/bConfigurationValue 2>/dev/null || true
    sleep 1
    printf 2 > /sys/bus/usb/devices/3-6/bConfigurationValue 2>/dev/null || true
    udevadm settle 2>/dev/null || true
    {start_tiny}
    printf 200 > /sys/class/leds/:white:kbd_backlight/brightness 2>/dev/null || true
    {restart_upower}
    ;;
esac
"""
        await self._install_elogind_sleep_hook("t2-suspend", script)

    def _runtime_service_action(self, service: str, action: str) -> str:
        name = self._normalise_service_name(service) or service.removesuffix(".service")
        if self.init_system == "openrc":
            return f"rc-service {shlex.quote(name)} {action} 2>/dev/null || true"
        if self.init_system == "runit":
            mapped = {"restart": "restart", "start": "up", "stop": "down"}[action]
            return f"sv {mapped} {shlex.quote(name)} 2>/dev/null || true"
        if self.init_system == "dinit":
            return f"dinitctl {action} {shlex.quote(name)} 2>/dev/null || true"
        s6_name = shlex.quote(self._s6_service_name(name))
        return f"s6 live {action} {s6_name} 2>/dev/null || true"

    async def _install_elogind_sleep_hook(self, name: str, script: str) -> None:
        console = self.query_one("#console", RichLog)
        path = f"/etc/elogind/system-sleep/{name}"
        command = f"install -Dm755 /dev/stdin {shlex.quote(path)} <<'EOF'\n{script}EOF"
        if await self.run_in_chroot(command):
            console.write(f"elogind sleep hook installed: {path}")
            self.maybe_redirect_completion_from_extras()
        else:
            console.write(f"[ERROR] Failed to install elogind sleep hook: {path}")
