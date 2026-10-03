# Football Life 2026 — Rules & Schedule Mod

A Football Life 2026 (FL26) modding project focused on modifying **competition rules, season schedules, tournament structures, and other game systems** to create a more flexible and realistic football season experience.

The project experiments with the internal competition and scheduling behavior of Football Life 2026, with a focus on changing how competitions are structured and how matches are placed throughout a season.

## Overview

Football Life 2026 uses predefined competition structures and scheduling rules to generate football seasons.

This project explores and modifies those rules to allow changes such as:

* Competition rule modifications
* Season calendar modifications
* Fixture scheduling changes
* European competition structure changes
* League and tournament configuration
* Competition registration and scheduling behavior
* Testing alternative season configurations
* Backup and restoration of original game data

The goal is to make the game's competition system more configurable instead of being limited to its original setup.

## Main Areas

### Competition Rules

Modify the rules and structures used by competitions in the game.

This can include:

* League structure
* Competition format
* Number of teams
* Match structure
* Qualification-related configuration
* Competition registration
* Regulation/rulebook configuration

### Schedule & Fixtures

Modify how matches are distributed throughout a season.

The project investigates:

```text
Competition
     ↓
Competition Rules
     ↓
Season Registration
     ↓
Fixture Generation
     ↓
Match Calendar
```

This makes it possible to experiment with alternative season calendars and competition schedules.

### European Competitions

The `euro` area contains work related to modifying European competition behavior.

The purpose is to experiment with alternative European competition structures and scheduling rather than relying entirely on the game's original configuration.

Examples of possible modifications include:

* European competition formats
* League-phase structures
* Knockout stages
* Qualification/play-off structures
* European match dates
* Competition registration

### Testing

The project also contains separate areas for testing modifications before applying them to the main game setup.

```text
Original
   ↓
Build / Modify
   ↓
Test
   ↓
Verify Competition
   ↓
Verify Schedule
   ↓
Install
```

This separation helps keep experimental changes away from the original game files.

## Project Structure

```text
Football-Life-2026-Rules-and-Schedule-Mod/
│
├── backups/
│   └── Original / previous configurations
│
├── build/
│   └── Generated and modified files
│
├── euro/
│   └── European competition modifications
│
├── original/
│   └── Original game data / reference files
│
├── test/
│   └── Testing configurations and experiments
│
├── install.json
├── sider.installed.ini
└── README.md
```

## Modding Workflow

The general workflow is:

```text
Football Life 2026
        │
        ▼
   Original Data
        │
        ▼
  Modify Competition
        │
        ├── Rules
        ├── Format
        ├── Schedule
        └── Registration
        │
        ▼
      Build
        │
        ▼
      Test
        │
        ▼
   Verify Season
        │
        ▼
     Install
        │
        ▼
Football Life 2026
```

## Why This Project?

Football games often provide limited control over how competitions and seasons are generated.

This project investigates the underlying competition and scheduling configuration of Football Life 2026 and provides a way to experiment with:

* Different competition formats
* Different season calendars
* Modified European competitions
* Alternative fixture structures
* Custom competition configurations
* More flexible Master League setups

The project is therefore both a **game modification project** and an exploration of how competition scheduling systems work inside a football game.

## Safety & Backups

Game modification can affect existing configurations and saved careers.

Before applying experimental changes:

1. Back up the original files.
2. Keep modified files separate from originals.
3. Test changes in an isolated setup.
4. Verify the competition calendar after installation.
5. Keep a known-working backup for restoration.

The repository includes a dedicated `backups` area for this purpose.

## Status

This is an experimental Football Life 2026 modding project.

The project is continuously tested and refined as different competition rules, schedules, and game behaviors are investigated.

## Future Work

Possible future improvements include:

* More customizable competition formats
* More flexible season calendars
* Automatic schedule generation
* Additional European competition configurations
* Better competition validation tools
* Automated backup and restore
* Configuration presets
* Improved installation workflow
* More comprehensive testing across multiple seasons
* Better documentation of internal game rules

## Disclaimer

This project is an unofficial modification for Football Life 2026.

It is not affiliated with or endorsed by the game's developers or publishers.

Always keep a backup of your original game configuration and saves before testing modifications.

## Author

**ThachDuc123**

GitHub: [ThachDuc123](https://github.com/ThachDuc123)
