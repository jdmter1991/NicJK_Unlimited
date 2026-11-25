# NicJK Unlimited

[![Build](https://github.com/jdmter1991/NicJK_Unlimited/actions/workflows/build.yml/badge.svg)](https://github.com/jdmter1991/NicJK_Unlimited/actions/workflows/build.yml)
[![License](https://img.shields.io/github/license/jdmter1991/NicJK_Unlimited.svg)](LICENSE.txt)

NicJK Unlimited is a Jedi Academy multiplayer client and dedicated server for very large maps and full servers of bots. It is a fork of [TaystJK](https://github.com/taysta/TaystJK), which is built on EternalJK, OpenJK and jaPRO, and it stays compatible with them: the same game files, the same servers, the same mods.

**[Download the latest build](https://github.com/jdmter1991/NicJK_Unlimited/releases/latest)**

What this fork adds on top of TaystJK:

- **Raised engine limits** for maps far larger than the stock game allows.
- **Faster collision on huge maps**, with built-in server and bot profiling to find what costs time.
- **A reworked bot AI** that fights with every saber move, uses the Force by the game's own rules, finds its way on maps without bot routes, and plays objectives.

See [docs/NICJK.md](docs/NICJK.md) for the details and measurements, and [docs/NICJK_BOTS.md](docs/NICJK_BOTS.md) for the bot settings.

## Getting started

You need a copy of Jedi Academy and its retail `base/assets0.pk3` through `base/assets3.pk3` files.

1. Download the [latest build](https://github.com/jdmter1991/NicJK_Unlimited/releases/latest) for your operating system and extract the whole archive into a writable directory.
2. Copy the game's `base` directory beside the executable or macOS app bundle, or point the game at an existing installation with `fs_cdPath`.
3. Launch the executable or app included in the archive.

The executables keep TaystJK's names (`taystjk`, `taystjkded`) and its `taystjk` mod folder, so an existing TaystJK setup, its configuration and its mods carry over unchanged.

### Builds

| Build | Status |
| --- | --- |
| Windows 64-bit | The main build. All development and testing happens on it. |
| Windows 32-bit, Linux, macOS (Intel and Apple silicon), Windows XP | Built automatically from the same source. They are not play-tested by this fork. |

### Maps

Large showcase maps are published as separate, optional PK3 downloads next to the builds, not inside them. Put a map's PK3 in your `base` or `taystjk` folder to use it.

## Documentation

Everything TaystJK documents applies here too: installation, server hosting, features and the console reference are on the [TaystJK documentation site](https://taysta.github.io/TaystJK/).

| Document | What it covers |
| --- | --- |
| [docs/NICJK.md](docs/NICJK.md) | What this fork changes in the engine and the server, and what was measured. |
| [docs/NICJK_BOTS.md](docs/NICJK_BOTS.md) | The bot AI: what the bots do, the `bot_features` switches, what works and what does not yet. |

## Branches

| Branch | Purpose |
| --- | --- |
| `NicJK_Unlimited` | The main branch. Releases are built from it. |
| `TaystJK_AI` | Archive of the earlier build of this fork ("TaystJK AI, improved bots"). Not developed further. |

## Building

The project uses CMake, exactly as TaystJK does. On Windows with Visual Studio 2022:

```
cmake -S . -B build -A x64 -DBuildPortableVersion=ON
cmake --build build --config Release
```

The TaystJK [compilation guide](https://taysta.github.io/TaystJK/development/compiling/) covers the other platforms and the build options.

## Credits and license

NicJK Unlimited stands on the work of the TaystJK, EternalJK, jaPRO, OpenJK and Raven Software developers. It is licensed under the GNU GPL v2, like the projects it is built on; see [LICENSE.txt](LICENSE.txt).

Jedi Academy is a trademark of its respective owners. This project is not affiliated with or endorsed by them, and it does not include the game's assets.
