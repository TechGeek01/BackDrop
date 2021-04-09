# Changelog
All notable changes to this project will be documented in this file.

## 3.1.3 - TBD
### Added
- Added status bar backup halt indicator if verification doesn't allow an immediate halt
- Made main window resizable

### Fixed
- Fixed button styling
- Fixed typo in update notification
- Fixed drive selection not emptying missing drive list when selecting extra drives after a config load
- CLI mode updater works on Linux
- Fixed selected source total not updating when auto selecting from config if source paths are already of known size
- Fixed PermissionError when saving config file if it can't be written to

### Changed
- Backup and analysis both disabled the other button when running
- Sped up loading of GUI

## 3.1.2 - 2021-03-31
### Added
- Failed file operations now increment the status bar file counter
- Data verification is now killable
- Data verification now lists files in file details pane

### Fixed
- File verification is prevented from running when backup is active
- Fixed menubar taking background of main window in dark mode

### Changed
- Styled buttons to match the rest of the UI

## 3.1.1 - 2021-03-31
### Fixed
- Fixed incorrect accelerator in tools menu

## 3.1.0 - 2021-03-30
### Fixed
- Fixed typo in CLI mode
- Fixed broken CLI mode in Linux
- Fixed split mode toggle before analysis causing crash
- Fixed file detail lists not emptying during a UI reset
- Fixed file detail lists not scrolling back to top when emptying lists during UI reset

## 3.1.0-rc.3 - 2021-03-30
### Added
- Custom source selection
- Custom destination selection
- Portable mode

### Fixed
- Fixed division by zero when not copying any new files
- Fixed update check timeout causing crash in thread
- Fixed crash on CLI mode when loading destination drives
- Fixed aborted message showing when aborting backup on last file verification

## 3.0.2 - 2021-03-22
### Fixed
- Fixed broken file copy action when running backups

## 3.0.1 - 2021-03-12
### Added
- Linux now has a packaged version, and appropriate icons on the update screen

### Fixed
- Fixed race condition when opening update window on Linux

## 3.0.0 - 2021-03-12
*Previously compiled Windows binaries had CLI mode broken due to lacking console. This has been fixed, but now means there's a console window in the background that will open when launched. As far as I know, this is unavoidable due to the nature of Python.*

### Added
- Added update checking
- Linux support!
- Source can now be a set of mount points for a set of shares, rather than one root share containing all of the shares as folders
- Local/network type can be changed for both source and destination
- Files are now deleted from destination if they're not copied successfully
- Deleting is now handled in code, rather than with subprocess
- Added menu bar and consolidated some options and controls
- Added open and save config options to menubar
- Added option to delete config file from selected drives
- Added config builder if not all drives can be connected at once
- Added status bar to bottom of window
- File details pane now auto scrolls as files are copied

### Fixed
- Removed system drive from destination drive list
- Progress bar now increments correctly
- Drive selection now changes config selection back to "none" when selecting drive that doesn't have a config file
- Fixed crash on drive select click when selection length is 0
- Analysis no longer hangs when trying to truncate long file lists in the backup details pane
- File details pane now left aligns files in lists

### Changed
- Preferences and backup configs are now stored in INI format
	- *Any existing preferences will be lost due to the file change*
- Backup run function now breaks immediately when aborted
- UI improvements

## 2.1.3 - 2021-02-16
### Added
- Added file details pane

### Fixed
- Fixed regression where split shares would cause the analysis to either miss files, or double count them, and cause drives to run out of space and the backup to soft crash

### Changed
- Optimized file transfer buffer size to increase speed

## 2.1.2 - 2021-01-22
### Fixed
- Fixed progress bar and ETA not reporting correct progress

## 2.1.1 - 2021-01-10
### Fixed
- Fixed "Done" text not showing on list items when completed

### Changed
- Progress bar now counts verification to avoid "pauses" during verification passes

## 2.1.0 - 2020-01-08
### Added
- Added settings menu
- Added ETA to backups
- Added command line mode
- Experimental WIP dark mode

### Fixed
- Fixed expanding command arrows causing issues while analysis is still running
- Analysis button now checks if an existing backup is running, to prevent it from being replaced before finishing
- Fixed missing sliders on scrollbars for source and destination trees

### Changed
- Significantly improved copy speed
	- *CLI mode is significantly slower than the GUI. A fix is in the works.*
- Windows can now be centered on top of other windows, rather than just the screen
- Separated classes into their own files
- Restructured code

## 2.0.1 - 2020-12-25
### Fixed
- Functions for gathering file lists during analysis no longer break when trying to query missing drives

## 2.0.0 - 2020-12-25
### Added
- Progress bar now shows overall copy progress based on how much data needs to be copied
- Files are now verified when copying
- Analysis summary now shows how much data will be copied to each drive
- Added confirmation message warning about data deletion on new drives with no config
- Added warning message noting missing drives that need to be connected

### Fixed
- File detection now properly detects all files that should be deleted

### Changed
- Moved from robocopy for file copying to a custom function that allows reporting of progress

## 1.1.3 - 2020-11-02
### Fixed
- BackDrop no longer crashes when no network drives are present to use as source

## 1.1.2 - 2020-11-02
### Fixed
- Summary no longer shows split folders on all drives
- Improved detection of leftover files to delete

### Changed
- Aligned text in summary frame to columns
- Adjusted window size
- Replaced text label branding with Logo

## 1.1.1 - 2020-10-21
### Fixed
- Deleting files that are no longer allocated to a drive now happens before the robocopy in order to prevent running out of space while copying new files

### Changed
- Holding `Alt` while clicking on a drive now ignores config files and just selects the drive

## 1.1.0 - 2020-09-17
### Fixed
- Fixed refresh threads running when a refresh is already active
- Fixed shares being calculated in multiple threads when Ctrl + clicking
- Fixed drive selection breaking after loading a config from a selected drive
- File size of the drive config directory is now subtracted from drive space during analysis

### Changed
- Added ThreadManager class
- Added split mode backup option for backing up a subset of the drives in a config

## 1.0.1 - 2020-09-11
### Changed
- Added proper branding
- Performance improvements

## 1.0.0 - 2020-09-11
Initial release