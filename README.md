# Sl's Arch and Artix Linux Installer Variants

A collection of user-friendly, terminal-based installer variants based on [t2archinstall](https://github.com/slsrepo/t2archinstall), covering standard Arch Linux, Artix Linux, T2 Macs, post-install setup and Asahi ALARM systems.

## Introduction

`t2archinstall` started as a Terminal User Interface (TUI) for installing [Arch Linux](https://wiki.archlinux.org/index.php/Arch_Linux) on Intel Macs equipped with the T2 Security Chip. It provides a guided installation process from partitioning through desktop setup, while handling the additional packages and configuration required by T2 hardware.

As the installer developed, the same interface and installation workflow also proved useful outside its original T2 Arch use case. That led me to develop variants for standard non-T2 Arch systems, Artix Linux with its different init systems, post-install configuration, and Asahi ALARM on Apple Silicon.

Rather than maintaining several large copies of the same installer, this repository keeps `t2archinstall` as the source of truth. The variant builders start from the current `t2archinstall.py` source and apply only the changes required for their target. Improvements and fixes made to the main installer can therefore flow into the variants without having to maintain several independent forks.

The first versions of these variants used `sed` replacements in the package build process. That worked for simple changes, but became increasingly fragile as the installer grew. The current versions use dedicated Python build scripts instead. The builders validate the upstream sections they change and stop if those sections no longer match.

Like `t2archinstall`, these installers are built with transparency in mind. They feature a dedicated console on the right side of the screen that displays the real-time output of every command the script executes. Located at the bottom of this console is a built-in command input bar. If you need to make manual modifications, check a log file, or troubleshoot a step at any point during the installation, you can type and execute your own terminal commands directly inside the interface without having to exit the installer.

The Artix variants support OpenRC, dinit, runit and s6. The selected init system controls the packages, service scripts, service enablement, display manager setup and other init-specific configuration performed by the installer.

Please note: It is assumed that since you want to install Arch or Artix, you know what it is and how it functions. These scripts are intended to simplify and automate the installation process, not replace the Arch, Artix or Asahi documentation.

## Installation & Usage

### Prerequisites

* **Crucial** for **t2artixinstall**, Before starting, make sure you have gone through the pre-installation steps detailed [here](https://wiki.t2linux.org/guides/preinstall/). These steps include disabling Secure Boot and partitioning macOS to make room for Artix, by creating an empty ExFAT placeholder partition that will be deleted and reused as detailed below.
* An existing installed system for the `-postinstall` variants.
* A bootable Arch Linux or Artix Linux live environment ISO for the non-`-postinstall` variants, and a USB-C to USB-A adapter (or hub) to run that ISO, if required.
* An active internet connection (Ethernet preferred, but WiFi is also configurable).
* An hour of your time (depending on your internet speed and hardware, it might take as little as 5-20 minutes though).

### Usage Instructions
To begin the installation, follow these steps:

1. **Launch the script**: Run the installer that matches the system you want to install. Follow either the *"Download & Run"*, *"Building from Source"* or *"Building Packages"* sections below for detailed commands for every variant.
    * If you are using a `-postinstall` variant, you can skip Step 2 and continue straight to Step 3 :)
2. **Format the filesystem**: Run the partitioning step within the script to convert your placeholder partition or available space into your chosen Linux filesystem, or use **Mount Existing** if you already prepared the partitions yourself.
3. **Follow the prompts**: Continue with the installation process by carefully reading and following the on-screen instructions.

### Download & Run
Choose the variant for your system and run its launch command. The full installers guide you through the installation; the post-install tools provide user, locale, desktop, BTRFS and package configuration for an existing system.

* **sl-archinstall**: Standard Arch Linux installer without the T2-specific hardware changes.

  ```sh
  curl -fsSL https://a.sls.re/sl-arch.sh | sh
  ```

* **sl-artixinstall**: Standard Artix Linux installer without the T2-specific hardware changes.

  ```sh
  curl -fsSL https://a.sls.re/sl-artix.sh | sh
  ```

* **t2artixinstall**: Artix Linux installer for Intel Macs with the T2 Security Chip.

  ```sh
  curl -fsSL https://a.sls.re/t2artix.sh | sh
  ```

* **sl-arch-postinstall**: Post-install configuration for Arch Linux.

  ```sh
  curl -fsSL https://a.sls.re/sl-arch-postinstall.sh | sh
  ```

* **sl-artix-postinstall**: Post-install configuration for Artix Linux.

  ```sh
  curl -fsSL https://a.sls.re/sl-artix-postinstall.sh | sh
  ```

* **sl-asahi-postinstall**: Post-install configuration for [Asahi ALARM](https://asahi-alarm.org) on Apple Silicon.

  ```sh
  curl -fsSL https://a.sls.re/sl-asahi-postinstall.sh | sh
  ```

For Arch Linux on a T2 Mac, use the original **t2archinstall**, maintained in [its own repository](https://github.com/slsrepo/t2archinstall):

```sh
curl -fsSL https://a.sls.re/t2arch.sh | sh
```

These installers and other utilities are also available through [Sl's Arch Repository](https://arch.slsrepo.com).

### Building from Source

To build a variant yourself, clone this repository and run the corresponding command:

```sh
# Standard Arch installer
python3 build-sl-archinstall.py

# Artix installers and post-install variant
python3 build-artix-installer.py sl-artixinstall
python3 build-artix-installer.py t2artixinstall
python3 build-artix-installer.py sl-artix-postinstall

# Arch and Asahi post-install variants
python3 build-arch-postinstall.py sl-arch-postinstall
python3 build-arch-postinstall.py sl-asahi-postinstall
```

The builders use a local `t2archinstall.py`, either beside the builders or in `t2archinstall/`, if present. Otherwise, they download the current upstream source. You can also select a source file explicitly:

```sh
python3 build-artix-installer.py sl-artixinstall --source /path/to/t2archinstall.py
```

Each command writes a standalone executable into the repository directory, named after the selected variant. For example, the command above produces `sl-artixinstall`.

The Artix builder incorporates `artix-common.py` and, for its post-install variant, `sl-artix-postinstall.py`. The Arch and Asahi post-install builder uses `postinstall-common.py`. These shared files are needed only during the building process.

### Building Packages

The six PKGBUILDs are in the `packaging` folder. To build and install a package, select its recipe with `makepkg`, for example:

```sh
makepkg -si -p packaging/PKGBUILD-sl-artixinstall-git
```

Each recipe fetches this repository and the current t2archinstall version, builds and syntax-checks the selected variant, and installs its executable in `/usr/bin`.

### Live ISOs

Need a bootable ISO to get started? You can grab one of the compatible images here:
 * **Sl's Arch ISO:** https://arch.slsrepo.com/arch-iso
 * **Sl's Artix ISO:** https://arch.slsrepo.com/artix-iso

## Support

If you need help with your installation or have any questions regarding these installers, feel free to get in touch by opening an issue, or via [Mastodon](https://social.slsrepo.com/@devsl), [Bluesky](https://bsky.app/profile/devsl.slsrepo.com) or [Matrix](https://matrix.to/#/@devsl:slsrepo.com). For T2-specific issues, the T2 Linux [Discord](https://discord.com/invite/68MRhQu) and [Matrix](https://matrix.to/#/#space:t2linux.org) are available as well :)

## Credits

* Based on [t2archinstall](https://github.com/slsrepo/t2archinstall), which was inspired by [archinstall](https://github.com/archlinux/archinstall).
* [Textual](https://textual.textualize.io) made it easy to write the UI.
* Thanks to the [T2Linux community](https://wiki.t2linux.org/) and especially to [AdityaGarg8](https://github.com/AdityaGarg8) and [NoaHimesaka1873](https://github.com/NoaHimesaka1873) for the guidance and support.
* Thanks to the Arch Linux, Artix Linux and Asahi Linux communities and their documentation too.

## References

* [Arch Linux Installation Guide](https://wiki.archlinux.org/title/Installation_guide)
* [Arch Installation – T2 Linux wiki](https://wiki.t2linux.org/distributions/arch/installation/)
* [Artix Linux Wiki](https://wiki.artixlinux.org/)
* [Asahi Linux](https://asahilinux.org/)

Copyright © 2026 [Sl's Repository Ltd](https://slsrepo.com/).
