# Changelog
All notable changes to this project will be documented in this file.

## [2.1.2] - 2021-01-22
### Fixed
- Fixed progress bar and ETA not reporting correct progress

## [2.1.1] - 2021-01-10
### Fixed
- Fixed "Done" text not showing on list items when completed

### Changed
- Progress bar now counts verification to avoid "pauses" during verification passes

## [2.1.0] - 2020-01-08
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
	- ***Note:** CLI mode is significantly slower than the GUI. A fix is in the works.*
- Windows can now be centered on top of other windows, rather than just the screen
- Separated classes into their own files
- Restructured code

## [2.0.1] - 2020-12-25
### Fixed
- Functions for gathering file lists during analysis no longer break when trying to query missing drives

## [2.0.0] - 2020-12-25
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

## [1.1.3] - 2020-11-02
### Fixed
- BackDrop no longer crashes when no network drives are present to use as source

## [1.1.2] - 2020-11-02
### Fixed
- Summary no longer shows split folders on all drives
- Improved detection of leftover files to delete

### Changed
- Aligned text in summary frame to columns
- Adjusted window size
- Replaced text label branding with Logo

## [1.1.1] - 2020-10-21
### Fixed
- Deleting files that are no longer allocated to a drive now happens before the robocopy in order to prevent running out of space while copying new files

### Changed
- Holding `Alt` while clicking on a drive now ignores config files and just selects the drive

## [1.1.0] - 2020-09-17
### Fixed
- Fixed refresh threads running when a refresh is already active
- Fixed shares being calculated in multiple threads when Ctrl + clicking
- Fixed drive selection breaking after loading a config from a selected drive
- File size of the drive config directory is now subtracted from drive space during analysis

### Changed
- Added ThreadManager class
- Added split mode backup option for backing up a subset of the drives in a config

## [1.0.1] - 2020-09-11
### Changed
- Added proper branding
- Performance improvements

## [1.0.0] - 2020-09-11
Initial release