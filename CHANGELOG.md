# Changelog
All notable changes to this project will be documented in this file.

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

## 1.0.0 - 2020-09-11
Initial release