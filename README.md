<p align="center">
  <img alt="Logo" src="https://github.com/TechGeek01/BackDrop/raw/master/media/logo.png">
  <br />
  <a href="https://lgtm.com/projects/g/TechGeek01/BackDrop/context:python"><img alt="Language grade: Python" src="https://img.shields.io/lgtm/grade/python/g/TechGeek01/BackDrop.svg?logo=lgtm&logoWidth=18"/></a>
  <br />
  <a href="https://github.com/TechGeek01/BackDrop/releases/latest"><img alt="undefined" src="https://img.shields.io/github/v/release/TechGeek01/BackDrop"></a>
  <img alt="undefined" src="https://img.shields.io/github/downloads/TechGeek01/BackDrop/total" />
  <a href="https://github.com/TechGeek01/BackDrop/blob/master/LICENSE"><img alt="undefined" src="https://img.shields.io/github/license/TechGeek01/BackDrop"></a>
  <br />
  <a href="https://github.com/TechGeek01/BackDrop/releases/download/v3.1.1/backdrop.exe" target="_blank"><img alt="undefined" src="https://badgen.net/badge/Download/Windows/?color=blue&icon=windows&label"></a>
  <br /><br />
</p>

BackDrop is a tool to copy files from a NAS onto one, or many, external drives for cold storage.

Online storage of data can get expensive. Obviously, the cheap way to back up important data from a file server is to load copies of it onto spare drives, and cart them to a friend's house. If you're like me, not all of the data you want to back up will always fit on one drive, and I wanted a way to automate the backup without having to manually figure out the best way to split directories.

![BackDrop UI](https://raw.githubusercontent.com/TechGeek01/BackDrop/master/docs/img/showcase.png)

## Installation
If you're not running a pre-compiled version of the source code, you can run the Python directly. All packages can be installed by passing the associated requirements.txt file to `pip`.

*BackDrop uses tkinter for the GUI frontend. If you're on Linux, this isn't included with Python and will need to be installed separately.*

## Usage
BackDrop was intended for use with Unraid, or another NAS solution. My setup involves network shares, since I don't have room to just pop extra drives into the server, they're docked with a USB adapter in Windows, and encrypted so that data is inaccessible without my encryption key. My setup involves a "root share" where all of the shares I have in Unraid are accessible as subfolders on one network drive.

When you open BackDrop for the first time, you'll want to select the drive letter of your source. From there, select the drives you want to back up to, select the shares to back up, and let it rip. The backup itself is two parts.

## Portable Mode
By default, BackDrop stores the config inside of the user's AppData folder. If you want to run in portable mode, you can create a `backdrop.ini` file in the same directory as the executable (or Python) file, and it will use that instead. A sample file can be found in the repo, named `backdrop-example.ini`

### Analysis
First, the analysis scans the directory structure of the shares, and the drives you have. It will try and pack as efficiently as possible, avoiding splitting shares if they don't have to be split. If a share has to be split, it will try and arrange it so that it most efficiently fills up one drive, and split as least as possible.

Once this splitting is done, BackDrop will take a look at the existing file structure to determine a list of exactly what needs to be deleted, updated, or copied, and their file size.

### Backup
Once the analysis is done, and BackDrop knows what files go where, you can actually run the backup. This will iterate through the list of files, and give you live output of what's happening. While copying your files, BackDrop also does a second verification pass to make sure the data copied over successfully.

Should you need to stop in the middle of a copy for any reason, you can abort the backup. Any active copy or delete operations are killed, and the rest of the backup is aborted. If the current operation was verifying a copied file, the verification will complete before killing the rest of the backup.

The fun part is that these file lists are calculated before each backup. This means that while the initial backup may take some time due to having to copy everything, subsequent backups will take much less time to complete.

## Features
* **Automatic source drive selection:** Once you set the drive letter for the source, BackDrop will remember it, and will automatically use that drive letter each time you run the tool later.
* **Multi-source:** With options for both single or multi source, you can back up specific folders on one drive, or name and backup several drives if your sources are in multiple locations.
* **Network and local drives:** Both the source and destination can use either a mounted network share, or a local drive.
* **Split share mode:** If you can't connect all of the drives at once when updating an existing config, there's an option for split mode. With split mode enabled, the backup will be analyzed and processed as though all drives are connected, but commands to drives that are disconnected will be skipped.
* **Drive split mode warnings:** If a config is loaded from a drive, and not all drives are connected, it will automatically warn you, and only let you continue with analysis if you connect the missing drives, or enable split mode.
* **Backup config memory:** Config files about your backups are stored on each drive. This means that when you select a drive you've previously used for backup, BackDrop will automatically select the other drives in the config, and the shares you had selected, so that you can update the backup that's already on the drive.
* **Command line:** There's a built-in command line mode that's able to take parameters to configure and run a backup. This makes it possible to script and automate backups with BackDrop.
* **Portability:** The best part about it is that there is no installation, and it's all a single executable! This means you can take it with you if you want, or run it on multiple computers. And because there's no installation, when you're not using it, BackDrop is completely out of the way.