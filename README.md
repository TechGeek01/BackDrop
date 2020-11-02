<p align="center">
  <br />
  <img alt="Logo" src="https://github.com/TechGeek01/BackDrop/raw/master/media/logo.png">
  <br /><br />
  <a href="https://lgtm.com/projects/g/TechGeek01/BackDrop/context:python"><img alt="undefined" src="https://img.shields.io/lgtm/grade/python/github/TechGeek01/BackDrop"/></a>
  <br />
  <a href="https://github.com/TechGeek01/BackDrop/releases/latest"><img alt="undefined" src="https://img.shields.io/github/v/release/TechGeek01/BackDrop"></a>
  <img alt="undefined" src="https://img.shields.io/github/downloads/TechGeek01/BackDrop/total" />
  <a href="https://github.com/TechGeek01/BackDrop/blob/master/LICENSE"><img alt="undefined" src="https://img.shields.io/github/license/TechGeek01/BackDrop"></a>
  <br />
  <a href="https://github.com/TechGeek01/BackDrop/releases/download/v1.1.1/backdrop-v1.1.1.exe" target="_blank"><img alt="undefined" src="https://badgen.net/badge/Download/Windows/?color=blue&icon=windows&label"></a>
  <br /><br />
</p>

Online storage of data can get expensive. Obviously, the cheap way to back up important data off of a file server is to load copies of it onto spare drives, and cart them to a friend's house. If you're like me, not all of the data you want to back up will always fit on one drive, and I wanted a way to automate the backup without having to manually figure out the best way to split directories.

![BackDrop UI](https://raw.githubusercontent.com/TechGeek01/BackDrop/master/docs/img/showcase.png)

## Usage
BackDrop was intended for use with Unraid, or another NAS solution. My setup involves network shares, since I don't have room to just pop extra drives into the server, they're docked with a USB adapter in Windows, and encrypted so that data is inaccessible without my encryption key. My setup involves a "root share" where all of the shares I have in Unraid are accessible as subfolders on one network drive.

When you open BackDrop for the first time, you'll want to select the drive letter of your source. From there, select the drives you want to back up to, select the shares to back up, and let it rip. The backup itself is two parts.

### Analysis
First, the analysis scans the directory structure of the shares, and the drives you have. It will try and pack as efficiently as possible, avoiding splitting shares if they don't have to be split. If a share has to be split, it will try and arrange it so that it most efficiently fills up one drive, and split as least as possible.

Once this analysis is done, it will generate a list of robocopy commands to be run, that includes all of the shares, and has all the excludes in place to arrange everything like it planned.

### Backup
Once the analysis is done, and BackDrop knows what files go where, you can actually run the backup. This will iterate through the list of commands, and give you live output of what's happening. Should you need to kill it, you can abort the backup, and even restart it without rerunning the analysis again.

The fun part about robocopy is that it's incremental, and shares can be copied with the `/mir` option to mirror changes. This means that while the initial backup may take some time due to having to copy everything, subsequent backups will take much less time to complete.

## Features
* **Automatic source drive selection:** Once you set the drive letter for the source, BackDrop will remember it, and will automatically use that drive letter each time you run the tool later.
* **Split share mode:** If you can't connect all of the drives at once when updating an existing config, there's an option for split mode. With split mode enabled, the backup will be analyzed and processed as though all drives are connected, but commands to drives that are disconnected will be skipped.
* **Drive split mode warnings:** If a config is loaded from a drive, and not all drives are connected, it will automatically warn you, and only let you continue with analysis if you connect the missing drives, or enable split mode.
* **Backup config memory:** Config files about your backups are stored on each drive. This means that when you select a drive you've previously used for backup, BackDrop will automatically select the other drives in the config, and the shares you had selected, so that you can update the backup that's already on the drive.
* **Manual commands:** Even though BackDrop can run the backup for you with the click of a button, you might wish to run it manually. For these cases, there's an easy way to copy each command to the clipboard.
* **Portability:** The best part about it is that there is no installation, and it's all a single executable! This means you can take it with you if you want, or run it on multiple computers. And because there's no installation, when you're not using it, BackDrop is completely out of the way.