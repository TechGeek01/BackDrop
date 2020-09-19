import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont
import win32api
import win32file
import shutil
import os
import wmi
import re
import threading
import pythoncom
import itertools
import subprocess
import clipboard
import time
import keyboard

# Set meta info
appVersion = '1.1.1-alpha.1'

# TODO: Shares are copied to root of drives, so other directories with data are most likely left intact
#     We may need to account for this, by checking for free space, and then adding the size of the existing share directories
#     This would prevent counting for existing data, though it's probably safe to wipe the drive of things that aren't getting copied anyway
#     When we copy, check directory size of source and dest, and if the dest is larger than source, copy those first to free up space for ones that increased
# TODO: Add a button for deleting the config from selected drives
# IDEA: Add interactive CLI option if correct parameters are passed in

def center(win):
    """Center a tkinter window on screen.

    Args:
        win (tkinter.Tk()): The tkinter Tk() object to center.
    """
    win.update_idletasks()
    width = win.winfo_width()
    frm_width = win.winfo_rootx() - win.winfo_x()
    win_width = width + 2 * frm_width
    height = win.winfo_height()
    titlebar_height = win.winfo_rooty() - win.winfo_y()
    win_height = height + titlebar_height + frm_width
    x = win.winfo_screenwidth() // 2 - win_width // 2
    y = win.winfo_screenheight() // 2 - win_height // 2
    win.geometry('{}x{}+{}+{}'.format(width, height, x, y))
    win.deiconify()

def human_filesize(num, suffix='B'):
    """Convert a number of bytes to a human readable format.

    Args:
        num (int): The number of bytes.
        suffix (String, optional): The suffix to use. Defaults to 'B'.

    Returns:
        String: A string representation of the filesize passed in.
    """
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.2f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)

def get_directory_size(directory):
    """Get the filesize of a directory and its contents.

    Args:
        directory (String): The directory to check.

    Returns:
        int: The filesize of the directory.
    """
    total = 0
    try:
        for entry in os.scandir(directory):
            # For each entry, either add filesize to the total, or recurse into the directory
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_directory_size(entry.path)
    except NotADirectoryError:
        return os.path.getsize(directory)
    except PermissionError:
        return 0
    except OSError:
        return 0
    return total

def enumerateCommandInfo(displayCommandList):
    """Enumerate the display widget with command info after a backup analysis."""
    global cmdInfoBlocks
    rightArrow = '\U0001f86a'
    downArrow = '\U0001f86e'

    cmdHeaderFont = (None, 9, 'bold')
    cmdStatusFont = (None, 9)

    def toggleCmdInfo(index):
        """Toggle the command info for a given indexed command.

        Args:
            index (int): The index of the command to expand or hide.
        """
        # Check if arrow needs to be expanded
        expandArrow = cmdInfoBlocks[index]['arrow']['text']
        if expandArrow == rightArrow:
            # Collapsed turns into expanded
            cmdInfoBlocks[index]['arrow'].configure(text=downArrow)
            cmdInfoBlocks[index]['infoFrame'].pack(anchor='w')
        else:
            # Expanded turns into collapsed
            cmdInfoBlocks[index]['arrow'].configure(text=rightArrow)
            cmdInfoBlocks[index]['infoFrame'].pack_forget()

        # For some reason, .configure() loses the function bind, so we need to re-set this
        cmdInfoBlocks[index]['arrow'].bind('<Button-1>', lambda event, index=index: toggleCmdInfo(index))

    def copyCmd(index):
        """Copy a given indexed command to the clipboard.

        Args:
            index (int): The index of the command to copy.
        """
        clipboard.copy(cmdInfoBlocks[index]['fullCmd'])

    for widget in backupActivityScrollableFrame.winfo_children():
        widget.destroy()

    cmdInfoBlocks = []
    for i, item in enumerate(displayCommandList):
        cmd = item['cmd']
        cmdParts = cmd.split('/mir')
        # cmdSnip = ' '.join(cmdParts[0:3])
        cmdSnip = cmdParts[0].strip()

        config = {}

        config['mainFrame'] = tk.Frame(backupActivityScrollableFrame)
        config['mainFrame'].pack(anchor='w', expand=1)

        # Set up header arrow, trimmed command, and status
        config['headLine'] = tk.Frame(config['mainFrame'])
        config['headLine'].pack(fill='x')
        config['arrow'] = tk.Label(config['headLine'], text=rightArrow)
        config['arrow'].pack(side='left')
        config['header'] = tk.Label(config['headLine'], text=cmdSnip, font=cmdHeaderFont, fg=color.NORMAL if item['enabled'] else color.FADED)
        config['header'].pack(side='left')
        config['state'] = tk.Label(config['headLine'], text='Pending' if item['enabled'] else 'Skipped', font=cmdStatusFont, fg=color.PENDING if item['enabled'] else color.FADED)
        config['state'].pack(side='left')
        config['arrow'].update_idletasks()
        arrowWidth = config['arrow'].winfo_width()

        # Header toggle action click
        config['arrow'].bind('<Button-1>', lambda event, index=i: toggleCmdInfo(index))
        config['header'].bind('<Button-1>', lambda event, index=i: toggleCmdInfo(index))

        # Set up info frame
        config['infoFrame'] = tk.Frame(config['mainFrame'])
        config['cmdLine'] = tk.Frame(config['infoFrame'])
        config['cmdLine'].pack(anchor='w')
        tk.Frame(config['cmdLine'], width=arrowWidth).pack(side='left')
        config['cmdLineHeader'] = tk.Label(config['cmdLine'], text='Full command:', font=cmdHeaderFont)
        config['cmdLineHeader'].pack(side='left')
        config['cmdLineTooltip'] = tk.Label(config['cmdLine'], text='(Click to copy)', font=cmdStatusFont, fg=color.FADED)
        config['cmdLineTooltip'].pack(side='left')
        config['fullCmd'] = cmd

        config['lastOutLine'] = tk.Frame(config['infoFrame'])
        config['lastOutLine'].pack(anchor='w')
        tk.Frame(config['lastOutLine'], width=arrowWidth).pack(side='left')
        config['lastOutHeader'] = tk.Label(config['lastOutLine'], text='Out:', font=cmdHeaderFont)
        config['lastOutHeader'].pack(side='left')
        config['lastOutResult'] = tk.Label(config['lastOutLine'], text='Pending' if item['enabled'] else 'Skipped', font=cmdStatusFont, fg=color.PENDING if item['enabled'] else color.FADED)
        config['lastOutResult'].pack(side='left')

        # Handle command trimming
        cmdFont = tkfont.Font(family=None, size=10, weight='normal')
        trimmedCmd = cmd
        maxWidth = backupActivityInfoCanvas.winfo_width() * 0.8
        actualWidth = cmdFont.measure(cmd)

        if actualWidth > maxWidth:
            while actualWidth > maxWidth and len(trimmedCmd) > 1:
                trimmedCmd = trimmedCmd[:-1]
                actualWidth = cmdFont.measure(trimmedCmd + '...')
            trimmedCmd = trimmedCmd + '...'

        config['cmdLineCmd'] = tk.Label(config['cmdLine'], text=trimmedCmd, font=cmdStatusFont)
        config['cmdLineCmd'].pack(side='left')

        # Command copy action click
        config['cmdLineHeader'].bind('<Button-1>', lambda event, index=i: copyCmd(index))
        config['cmdLineTooltip'].bind('<Button-1>', lambda event, index=i: copyCmd(index))
        config['cmdLineCmd'].bind('<Button-1>', lambda event, index=i: copyCmd(index))

        # Stats frame
        config['statusStatsLine'] = tk.Frame(config['infoFrame'])
        config['statusStatsLine'].pack(anchor='w')
        tk.Frame(config['statusStatsLine'], width=2 * arrowWidth).pack(side='left')
        config['statusStatsFrame'] = tk.Frame(config['statusStatsLine'])
        config['statusStatsFrame'].pack(side='left')

        cmdInfoBlocks.append(config)

# CAVEAT: This analysis assumes the drives are going to be empty, aside from the config file
# Other stuff that's not part of the backup will need to be deleted when we actually run it
def analyzeBackup(shares, drives):
    """Analyze the list of selected shares and drives and figure out how to split files.

    Args:
        shares (tuple(String)): The list of selected shares.
        drives (tuple(String)): The list of selected drives.

    This function is run in a new thread, but is only run if the backup config is valid.
    If sanityCheck() returns False, the analysis isn't run.
    """
    global backupSummaryTextFrame
    global commandList
    global analysisValid
    global analysisStarted
    global destModeSplitEnabled

    # Sanity check for space requirements
    if not sanityCheck():
        return

    if len(threading.enumerate()) <= 3:
        progressBar.configure(mode='indeterminate')
        progressBar.start()

    startBackupBtn.configure(state='disable')
    startAnalysisBtn.configure(state='disable')

    # Apply split mode status from checkbox before starting analysis
    analysisStarted = True
    destModeSplitEnabled = destModeSplitCheckVar.get()
    splitModeStatus.configure(text='Split mode\n%s' % ('Enabled' if destModeSplitEnabled else 'Disabled'), fg=color.ENABLED if destModeSplitEnabled else color.DISABLED)

    # Set UI variables
    summaryHeaderFont = (None, 14)

    for widget in backupSummaryTextFrame.winfo_children():
        widget.destroy()

    tk.Label(backupSummaryTextFrame, text='Shares', font=summaryHeaderFont,
             wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')

    shareInfo = {}
    allShareInfo = {}
    for item in shares:
        shareName = sourceTree.item(item, 'text')
        shareSize = int(sourceTree.item(item, 'values')[1])

        shareInfo[shareName] = shareSize
        allShareInfo[shareName] = shareSize

        tk.Label(backupSummaryTextFrame, text='%s \u27f6 %s' % (shareName, human_filesize(shareSize)),
                 wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')

    tk.Label(backupSummaryTextFrame, text='Drives', font=summaryHeaderFont,
             wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')

    driveVidToLetterMap = {destTree.item(item, 'values')[3]: destTree.item(item, 'text') for item in destTree.get_children()}

    driveInfo = []
    driveShareList = {}
    for item in drives:
        curDriveInfo = {
            'vid': item['vid'],
            'size': item['capacity'],
            'free': item['capacity'],
            'configSize': 0
        }

        if item['vid'] in driveVidToLetterMap.keys():
            curDriveInfo['name'] = driveVidToLetterMap[item['vid']]
            curDriveInfo['configSize'] = get_directory_size(driveVidToLetterMap[item['vid']] + '.backdrop')

        driveInfo.append(curDriveInfo)

        # Enumerate list for tracking what shares go where
        driveShareList[item['vid']] = []

        humanDriveName = curDriveInfo['name'] if 'name' in curDriveInfo.keys() else item['vid']

        tk.Label(backupSummaryTextFrame, text='%s \u27f6 %s' % (humanDriveName, human_filesize(item['capacity'])),
                 fg=color.NORMAL if 'name' in curDriveInfo.keys() else color.FADED,
                 wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')

    # For each drive, smallest first, filter list of shares to those that fit
    driveInfo.sort(key=lambda x: x['size'] - x['configSize'])

    for i, drive in enumerate(driveInfo):
        # Get list of shares small enough to fit on drive
        smallShares = {share: size for share, size in shareInfo.items() if size <= drive['size'] - drive['configSize']}

        # Try every combination of shares that fit to find result that uses most of that drive
        largestSum = 0
        largestSet = []
        for n in range(1, len(smallShares) + 1):
            for subset in itertools.combinations(smallShares.keys(), n):
                combinationTotal = sum(smallShares[share] for share in subset)

                if (combinationTotal > largestSum and combinationTotal <= drive['size'] - drive['configSize']):
                    largestSum = combinationTotal
                    largestSet = subset

        sharesThatFit = [share for share in largestSet]
        remainingSmallShares = {share: size for (share, size) in smallShares.items() if share not in sharesThatFit}
        shareInfo = {share: size for (share, size) in shareInfo.items() if share not in sharesThatFit}

        # If not all shares fit on smallest drive at once (at least one share has to be put
        # on the next largest drive), check free space on next largest drive
        if len(remainingSmallShares) > 0 and i < (len(driveInfo) - 1):
            notFitTotal = sum(size for size in remainingSmallShares.values())
            nextDrive = driveInfo[i + 1]
            nextDriveFreeSpace = nextDrive['size'] - nextDrive['configSize'] - notFitTotal

            # If free space on next drive is less than total capacity of current drive, it becomes
            # more efficient to skip current drive, and put all shares on the next drive instead
            # NOTE: This applies only if they can all fit on the next drive. If they have to be split
            # across multiple drives after moving them to a larger drive, then it's easier to fit
            # what we can on the small drive, to leave the larger drives available for larger shares
            if notFitTotal <= nextDrive['size'] - nextDrive['configSize']:
                totalSmallShareSpace = sum(size for size in smallShares.values())
                if nextDriveFreeSpace < drive['size'] - drive['configSize'] and totalSmallShareSpace <= nextDrive['size'] - nextDrive['configSize']:
                    # Next drive free space less than total on current, so it's optimal to store on next drive instead
                    driveShareList[nextDrive['vid']].extend([share for share in smallShares.keys()]) # All small shares on next drive
                else:
                    # Better to leave on current, but overflow to next drive
                    driveShareList[drive['vid']].extend(sharesThatFit) # Shares that fit on current drive
                    driveShareList[nextDrive['vid']].extend([share for share in smallShares.keys() if share not in sharesThatFit]) # Remaining small shares on next drive
            else:
                # If overflow for next drive is more than can fit on that drive, ignore it, put overflow
                # back in pool of shares to sort, and put small drive shares only in current drive
                driveShareList[drive['vid']].extend(sharesThatFit) # Shares that fit on current drive

                # Put remaining small shares back into pool to work with for next drive
                shareInfo.update({share: size for share, size in remainingSmallShares.items()})
        else:
            # Fit all small shares onto drive
            driveShareList[drive['vid']].extend(sharesThatFit)

        # Calculate space used by shares, and subtract it from capacity to get free space
        usedSpace = sum(allShareInfo[share] for share in driveShareList[drive['vid']])
        drive.update({'free': drive['size'] - drive['configSize'] - usedSpace})

    def splitShare(share):
        """Recurse into a share or directory, and split the contents.

        Args:
            share (String): The share to split.
        """
        # Enumerate list for tracking what shares go where
        driveFileList = {drive['vid']: [] for drive in driveInfo}

        fileInfo = {}
        for entry in os.scandir(sourceDrive + share):
            if entry.is_file():
                newDirSize = entry.stat().st_size
            elif entry.is_dir():
                newDirSize = get_directory_size(entry.path)

            fileName = entry.path.split('\\')[-1]
            fileInfo[fileName] = newDirSize

        # For splitting shares, sort by largest free space first
        driveInfo.sort(reverse=True, key=lambda x: x['free'] - x['configSize'])

        for i, drive in enumerate(driveInfo):
            # Get list of files small enough to fit on drive
            totalSmallFiles = {file: size for file, size in fileInfo.items() if size <= drive['free'] - drive['configSize']}

            # Since the list of files is truncated to prevent an unreasonably large
            # number of combinations to check, we need to keep processing the file list
            # in chunks to make sure we check if all files can be fit on one drive
            # TODO: This loop logic may need to be copied to the main share portion, though this is only necessary if the user selects a large number of shares
            filesThatFit = []
            processedSmallFiles = []
            processedFileSize = 0
            while len(processedSmallFiles) < len(totalSmallFiles):
                # Trim the list of small files to those that aren't already processed
                smallFiles = {file: size for (file, size) in totalSmallFiles.items() if file not in processedSmallFiles}

                # Make sure we don't end with an unreasonable number of combinations to go through
                # by sorting by largest first, and truncating
                # Sorting files first, since files can't be split, so it's preferred to have directories last
                listFiles = {}
                listDirs = {}
                for file, size in smallFiles.items():
                    if os.path.isfile(sourceDrive + '\\' + share + '\\' + file):
                        listFiles[file] = size
                    elif os.path.isdir(sourceDrive + '\\' + share + '\\' + file):
                        listDirs[file] = size

                # Sort file list by largest first, and truncate to prevent unreasonably large number of combinations
                smallFiles = sorted(listFiles.items(), key=lambda x: x[1], reverse=True)
                smallFiles.extend(sorted(listDirs.items(), key=lambda x: x[1], reverse=True))
                trimmedSmallFiles = {file[0]: file[1] for file in smallFiles[:15]}
                smallFiles = {file[0]: file[1] for file in smallFiles}

                # Try every combination of shares that fit to find result that uses most of that drive
                largestSum = 0
                largestSet = []
                for n in range(1, len(trimmedSmallFiles) + 1):
                    for subset in itertools.combinations(trimmedSmallFiles.keys(), n):
                        combinationTotal = sum(trimmedSmallFiles[file] for file in subset)

                        if (combinationTotal > largestSum and combinationTotal <= drive['free'] - drive['configSize'] - processedFileSize):
                            largestSum = combinationTotal
                            largestSet = subset

                filesThatFit.extend([file for file in largestSet])
                processedSmallFiles.extend([file for file in trimmedSmallFiles.keys()])
                fileInfo = {file: size for (file, size) in fileInfo.items() if file not in largestSet}

                # Subtract file size of each batch of files from the free space on the drive so the next batch sorts properly
                processedFileSize += sum([size for (file, size) in smallFiles.items() if file in largestSet])

            # Assign files to drive, and subtract filesize from free space
            # NOTE: Since we're sorting by largest free space first, there's no cases to
            # move to a larger drive. This means all files that can fit should be put on the
            # drive they fit on
            driveFileList[drive['vid']].extend(filesThatFit)
            driveInfo[i]['free'] -= processedFileSize

        shareSplitSummary = [{
            'share': share,
            'files': driveFileList,
            'exclusions': [file for file in fileInfo.keys()]
        }]

        for file in fileInfo.keys():
            filePath = share + '\\' + file
            shareSplitSummary.extend(splitShare(filePath))

        return shareSplitSummary

    # driveShareList contains info about whole shares mapped to drives
    # Use this to build the list of non-exclusion robocopy commands
    commandList = []
    displayCommandList = []
    for drive, shares in driveShareList.items():
        if len(shares) > 0:
            humanDrive = driveVidToLetterMap[drive] if drive in driveVidToLetterMap.keys() else '[%s]\\' % (drive)

            displayCommandList.extend([{
                'enabled': drive in driveVidToLetterMap.keys(),
                'cmd': 'robocopy "%s" "%s" /mir' % (sourceDrive + share, humanDrive + share)
            } for share in shares])

            if drive in driveVidToLetterMap.keys():
                commandList.extend([{
                    'displayIndex': len(displayCommandList) - len(shares) + i,
                    'cmd': 'robocopy "%s" "%s" /mir' % (sourceDrive + share, humanDrive + share)
                } for i, share in enumerate(shares)])

    # For each share that needs splitting, split each one
    # For each resulting folder in the summary, get list of files
    # For each drive, exclusions are files on other drives, plus explicit exclusions

    # For shares larger than all drives, recurse into each share
    for share in shareInfo.keys():
        if os.path.exists(sourceDrive + share) and os.path.isdir(sourceDrive + share):
            summary = splitShare(share)

            # Each summary contains a split share, and any split subfolders, starting with
            # the share and recursing into the directories
            for directory in summary:
                shareName = directory['share']
                shareFiles = directory['files']
                shareExclusions = directory['exclusions']

                allFiles = shareFiles.copy()
                allFiles['exclusions'] = shareExclusions

                sourcePathStub = sourceDrive + shareName + '\\'

                # For each drive, gather list of files to be written to other drives, and
                # use that as exclusions
                for drive, files in shareFiles.items():
                    if len(files) > 0:
                        rawExclusions = allFiles.copy()
                        rawExclusions.pop(drive, None)

                        humanDrive = driveVidToLetterMap[drive] if drive in driveVidToLetterMap.keys() else '[%s]\\' % (drive)

                        masterExclusions = [file for fileList in rawExclusions.values() for file in fileList]

                        fileExclusions = [sourcePathStub + file for file in masterExclusions if os.path.isfile(sourcePathStub + file)]
                        dirExclusions = [sourcePathStub + file for file in masterExclusions if os.path.isdir(sourcePathStub + file)]
                        xs = (' /xf "' + '" "'.join(fileExclusions) + '"') if len(fileExclusions) > 0 else ''
                        xd = (' /xd "' + '" "'.join(dirExclusions) + '"') if len(dirExclusions) > 0 else ''

                        displayCommandList.append({
                            'enabled': drive in driveVidToLetterMap.keys(),
                            'cmd': 'robocopy "%s" "%s" /mir%s%s' % (sourceDrive + shareName, humanDrive + shareName, xd, xs)
                        })

                        if drive in driveVidToLetterMap.keys():
                            commandList.append({
                                'displayIndex': len(displayCommandList) - 1,
                                'cmd': 'robocopy "%s" "%s" /mir%s%s' % (sourceDrive + shareName, humanDrive + shareName, xd, xs)
                            })
                    driveShareList[drive].append(shareName)

    enumerateCommandInfo(displayCommandList)

    tk.Label(backupSummaryTextFrame, text='Summary', font=summaryHeaderFont,
             wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')
    for drive, shares in driveShareList.items():
        humanDrive = driveVidToLetterMap[drive] if drive in driveVidToLetterMap.keys() else '[%s]' % (drive)
        tk.Label(backupSummaryTextFrame, text='%s \u27f6 %s' % (humanDrive, ', '.join(shares)),
                 fg=color.NORMAL if drive in driveVidToLetterMap.keys() else color.FADED,
                 wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')

    analysisValid = True

    startBackupBtn.configure(state='normal')
    startAnalysisBtn.configure(state='normal')

    if len(threading.enumerate()) <= 3:
        progressBar.configure(mode='determinate')
        progressBar.stop()

def sanityCheck():
    """Check to make sure everything is correct before a backup.

    Before running a backup, or an analysis, both shares and drives need to be
    selected, and the drive space on selected drives needs to be larger than the
    total size of the selected shares.

    Returns:
        bool: True if conditions are good, False otherwise.
    """
    sourceSelection = sourceTree.selection()
    destSelection = destTree.selection()
    selectionOk = len(sourceSelection) > 0 and len(destSelection) > 0

    if selectionOk:
        shareTotal = 0
        driveTotal = 0

        sharesKnown = True
        for item in sourceSelection:
            if sourceTree.item(item, 'values')[0] == 'Unknown':
                sharesKnown = False
                break

            # Add total space of selection
            shareSize = sourceTree.item(item, 'values')[1]
            shareTotal = shareTotal + int(shareSize)

        for item in destSelection:
            # Add total space of selection
            driveSize = destTree.item(item, 'values')[1]
            driveTotal = driveTotal + int(driveSize)

        configTotal = sum(int(drive['capacity']) for drive in config['drives'])

        if sharesKnown and ((len(destSelection) == len(config['drives']) and shareTotal < driveTotal) or (shareTotal < configTotal and destModeSplitEnabled)):
            # Sanity check pass if more drive selected than shares, OR, split mode and more config drives selected than shares
            return True

    return False

def startBackupAnalysis():
    """Start the backup analysis in a separate thread."""
    # FIXME: If backup analysis thread is already running, it needs to be killed before it's rerun
    # CAVEAT: This requires some way to have the thread itself check for the kill flag and break if it's set.
    threadManager.start(threadManager.SINGLE, target=analyzeBackup, args=[sourceTree.selection(), config['drives']], name='Backup Analysis', daemon=True)

def writeSettingToFile(setting, file):
    """Write a setting to a given file.

    Args:
        setting (String): The setting to be written.
        file (String): The filename to write to.
    """
    dirParts = file.split('\\')
    pathDir = '\\'.join(dirParts[:-1])

    if not os.path.exists(pathDir):
        os.mkdir(pathDir)

    f = open(file, 'w')
    f.write(setting)
    f.close()

def readSettingFromFile(file, default, verifyData=None):
    """Read a setting from a file.

    Args:
        file (String): The file to read from.
        default (String): The default value to set if setting can't be read.
        verifyData (String[], optional): A list of data to verify the read setting against. Defaults to None.
            If the setting is able to be read from the given file, and this list is
            defined, the default value will be used if the read setting isn't contained
            in the verifyData list.

    Returns:
        String: The setting read from the file if the file exists, and result is
        contained in optional verifyData list. Default otherwise.
    """
    if os.path.exists(file) and os.path.isfile(file):
        f = open(file, 'r')
        rawConfig = f.read().split('\n')
        f.close()

        setting = rawConfig[0]

        if verifyData is not None and setting not in verifyData:
            setting = default
            writeSettingToFile(default, file)

        return setting
    else:
        return default

def loadSource():
    """Load the source share list, and display it in the tree."""
    global analysisValid
    if len(threading.enumerate()) <= 3:
        progressBar.configure(mode='indeterminate')
        progressBar.start()

    analysisValid = False

    # Empty tree in case this is being refreshed
    sourceTree.delete(*sourceTree.get_children())

    shareSelectedSpace.configure(text='Selected: ' + human_filesize(0))
    shareTotalSpace.configure(text='Total: ~' + human_filesize(0))

    # Enumerate list of shares in source
    for directory in next(os.walk(sourceDrive))[1]:
        sourceTree.insert(parent='', index='end', text=directory, values=('Unknown', 0))

    if len(threading.enumerate()) <= 3:
        progressBar.configure(mode='determinate')
        progressBar.stop()

def startRefreshSource():
    """Start a source refresh in a new thread."""
    threadManager.start(threadManager.SINGLE, target=loadSource, name='Load Source', daemon=True)

def changeSourceDrive(selection):
    """Change the source drive to pull shares from to a new selection.

    Args:
        selection (String): The selection to set as the default.
    """
    global sourceDrive
    sourceDrive = selection
    startRefreshSource()
    writeSettingToFile(sourceDrive, appDataFolder + '\\sourceDrive.default')

# IDEA: Calculate total space of all shares in background
prevShareSelection = []
def shareSelectCalc():
    """Calculate and display the filesize of a selected share, if it hasn't been calculated.

    This gets the selection in the source tree, and then calculates the filesize for
    all shares selected that haven't yet been calculated. The summary of total
    selection, and total share space is also shown below the tree.
    """
    global prevShareSelection
    global analysisValid
    if len(threading.enumerate()) <= 3:
        progressBar.configure(mode='indeterminate')
        progressBar.start()

    def updateShareSize(item):
        """Update share info for a given share.

        Args:
            item (String): The identifier for a share in the source tree to be calculated.
        """
        shareName = sourceTree.item(item, 'text')
        newShareSize = get_directory_size(sourceDrive + shareName)
        sourceTree.set(item, 'size', human_filesize(newShareSize))
        sourceTree.set(item, 'rawsize', newShareSize)

        # After calculating share info, update the meta info
        selectedTotal = 0
        selectedShareList = []
        for item in sourceTree.selection():
            # Write selected shares to config
            selectedShareList.append(sourceTree.item(item, 'text'))

            # Add total space of selection
            if sourceTree.item(item, 'values')[0] != 'Unknown':
                # Add total space of selection
                shareSize = sourceTree.item(item, 'values')[1]
                selectedTotal = selectedTotal + int(shareSize)

        shareSelectedSpace.configure(text='Selected: ' + human_filesize(selectedTotal))
        config['shares'] = selectedShareList

        shareTotal = 0
        totalIsApprox = False
        totalPrefix = 'Total: '
        for item in sourceTree.get_children():
            shareTotal += int(sourceTree.item(item, 'values')[1])

            # If total is not yet approximate, check if the item hasn't been calculated
            if not totalIsApprox and sourceTree.item(item, 'values')[0] == 'Unknown':
                totalIsApprox = True
                totalPrefix += '~'

        shareTotalSpace.configure(text=totalPrefix + human_filesize(shareTotal))

        # If everything's calculated, enable analysis button to be clicked
        sharesAllKnown = True
        for item in sourceTree.selection():
            if sourceTree.item(item, 'values')[0] == 'Unknown':
                sharesAllKnown = False
        if sharesAllKnown:
            startAnalysisBtn.configure(state='normal')

        if len(threading.enumerate()) <= 3:
            progressBar.configure(mode='determinate')
            progressBar.stop()

    selected = sourceTree.selection()

    # If selection is different than last time, invalidate the analysis
    selectMatch = [share for share in selected if share in prevShareSelection]
    if len(selected) != len(prevShareSelection) or len(selectMatch) != len(prevShareSelection):
        analysisValid = False
        startBackupBtn.configure(state='disable')

    prevShareSelection = [share for share in selected]

    # Check if items in selection need to be calculated
    for item in selected:
        # If new selected item hasn't been calculated, calculate it on the fly
        if sourceTree.item(item, 'values')[0] == 'Unknown':
            startAnalysisBtn.configure(state='disable')
            shareName = sourceTree.item(item, 'text')
            threadManager.start(threadManager.SINGLE, target=lambda: updateShareSize(item), name='shareCalc_%s' % (shareName), daemon=True)

def loadSourceInBackground(event):
    """Start a calculation of source filesize in a new thread."""
    threadManager.start(threadManager.MULTIPLE, target=shareSelectCalc, name='Load Source Selection', daemon=True)

def loadDest():
    """Load the destination drive info, and display it in the tree."""
    global destDriveMap
    if len(threading.enumerate()) <= 3:
        progressBar.configure(mode='indeterminate')
        progressBar.start()

    driveList = win32api.GetLogicalDriveStrings()
    driveList = driveList.split('\000')[:-1]

    # Associate logical drives with physical drives, and map them to physical serial numbers
    logicalPhysicalMap = {}
    pythoncom.CoInitialize()
    try:
        for physicalDisk in wmi.WMI().Win32_DiskDrive():
            for partition in physicalDisk.associators("Win32_DiskDriveToDiskPartition"):
                logicalPhysicalMap.update({logicalDisk.DeviceID[0]: physicalDisk.SerialNumber.strip() for logicalDisk in partition.associators("Win32_LogicalDiskToPartition")})
    finally:
        pythoncom.CoUninitialize()

    # Empty tree in case this is being refreshed
    destTree.delete(*destTree.get_children())

    # Enumerate drive list to find info about all non-source drives
    totalUsage = 0
    destDriveMap = {}
    destDriveLetterToInfo = {}
    for drive in driveList:
        if drive != sourceDrive:
            driveType = win32file.GetDriveType(drive)
            if driveType not in (4, 6): # Make sure drive isn't REMOTE or RAMDISK
                driveSize = shutil.disk_usage(drive).total
                vsn = os.stat(drive).st_dev
                vsn = '{:04X}-{:04X}'.format(vsn >> 16, vsn & 0xffff)
                try:
                    serial = logicalPhysicalMap[drive[0]]
                except KeyError:
                    serial = 'Not Found'

                # Add drive to drive list
                destDriveMap[vsn] = drive[0]
                destDriveLetterToInfo[drive[0]] = {
                    'vid': vsn,
                    'serial': serial
                }

                driveHasConfigFile = os.path.exists('%s%s/%s' % (drive, backupConfigDir, backupConfigFile)) and os.path.isfile('%s%s/%s' % (drive, backupConfigDir, backupConfigFile))

                totalUsage = totalUsage + driveSize
                destTree.insert(parent='', index='end', text=drive, values=(human_filesize(driveSize), driveSize, 'Yes' if driveHasConfigFile else '', vsn, serial))

    driveTotalSpace.configure(text='Available: ' + human_filesize(totalUsage))

    if len(threading.enumerate()) <= 3:
        progressBar.configure(mode='determinate')
        progressBar.stop()

def startRefreshDest():
    """Start the loading of the destination drive info in a new thread."""
    if not threadManager.is_alive('Refresh destination'):
        threadManager.start(threadManager.SINGLE, target=loadDest, name='Refresh destination', daemon=True)

def selectFromConfig():
    """From the current config, select the appropriate shares and drives in the GUI."""
    global driveSelectBind

    # Get list of shares in config
    sourceTreeIdList = [item for item in sourceTree.get_children() if sourceTree.item(item, 'text') in config['shares']]

    sourceTree.focus(sourceTreeIdList[-1])
    sourceTree.selection_set(tuple(sourceTreeIdList))

    # Get list of drives where volume ID is in config
    driveTreeIdList = [item for item in destTree.get_children() if destTree.item(item, 'values')[3] in config['vidList']]

    # If drives aren't mounted that should be, display the warning
    if len(driveTreeIdList) < len(config['drives']):
        missingDriveCount = len(config['drives']) - len(driveTreeIdList)
        splitWarningPrefix.configure(text='There %s' % ('is' if missingDriveCount == 1 else 'are'))
        splitWarningSuffix.configure(text='%s in the config that %s connected. Please connect %s, or enable split mode.' % ('drive' if missingDriveCount == 1 else 'drives', 'isn\'t' if missingDriveCount == 1 else 'aren\'t', 'it' if missingDriveCount == 1 else 'them'))
        splitWarningMissingDriveCount.configure(text='%d' % (missingDriveCount))
        destSplitWarningFrame.grid(row=3, column=0, columnspan=2, sticky='nsew', pady=(0, elemPadding), ipady=elemPadding / 4)

    # Only redo the selection if the config data is different from the current
    # selection (that is, the drive we selected to load a config is not the only
    # drive listed in the config)
    # Because of the <<TreeviewSelect>> handler, re-selecting the same single item
    # would get stuck into an endless loop of trying to load the config
    # QUESTION: Is there a better way to handle this config loading selection handler conflict?
    if destTree.selection() != tuple(driveTreeIdList):
        destTree.unbind('<<TreeviewSelect>>', driveSelectBind)

        destTree.focus(driveTreeIdList[-1])
        destTree.selection_set(tuple(driveTreeIdList))

        driveSelectBind = destTree.bind("<<TreeviewSelect>>", selectDriveInBackground)

def readConfigFile(file):
    """Read a config file, and set the current config based off of it.

    Args:
        file (String): The file to read from.
    """
    global config
    if os.path.exists(file) and os.path.isfile(file):
        f = open(file, 'r')
        rawConfig = f.read().split('\n\n')
        f.close()

        newConfig = {}

        # Each chunk after splitting on \n\n is a header followed by config stuff
        configTotal = 0
        for chunk in rawConfig:
            splitChunk = chunk.split('\n')
            header = re.search(r'\[(.*)\]', splitChunk.pop(0)).group(1)

            if header == 'shares':
                # Shares is a single line, comma separated list of shares
                newConfig['shares'] = splitChunk[0].split(',')
            elif header == 'drives':
                # Drives is a list, where each line is one drive, and each drive lists
                # comma separated volume ID and physical serial
                newConfig['drives'] = []
                newConfig['vidList'] = []
                for drive in splitChunk:
                    drive = drive.split(',')
                    newConfig['vidList'].append(drive[0])
                    newConfig['drives'].append({
                        'vid': drive[0],
                        'serial': drive[1],
                        'capacity': int(drive[2])
                    })

                    configTotal += int(drive[2])

        config = newConfig
        configSelectedSpace.configure(text='Config: ' + human_filesize(configTotal))
        selectFromConfig()

prevSelection = 0
prevDriveSelection = []

# BUG: keyboard module seems to be returning false for keypress on first try. No idea how to fix this
keyboard.is_pressed('alt')
def handleDriveSelectionClick():
    """Parse the current drive selection, read config data, and select other drives and shares if needed.

    If the selection involves a single drive that the user specifically clicked on,
    this function reads the config file on it if one exists, and will select any
    other drives and shares in the config.
    """
    global prevSelection
    global prevDriveSelection
    global analysisValid

    if len(threading.enumerate()) <= 3:
        progressBar.configure(mode='indeterminate')
        progressBar.start()

    selected = destTree.selection()

    # If selection is different than last time, invalidate the analysis
    selectMatch = [drive for drive in selected if drive in prevDriveSelection]
    if len(selected) != len(prevDriveSelection) or len(selectMatch) != len(prevDriveSelection):
        analysisValid = False
        startBackupBtn.configure(state='disable')

    prevDriveSelection = [share for share in selected]

    # Check if newly selected drive has a config file
    # NOTE: We only want to do this if the click is the first selection (that is,
    # there are no other drives selected except the one we clicked)
    selectedDriveLetter = destTree.item(selected[0], 'text')[0]
    configFilePath = '%s:/%s/%s' % (selectedDriveLetter, backupConfigDir, backupConfigFile)
    readDrivesFromConfigFile = False
    if not keyboard.is_pressed('alt') and prevSelection <= len(selected) and len(selected) == 1 and os.path.exists(configFilePath) and os.path.isfile(configFilePath):
        # Found config file, so read it
        readConfigFile(configFilePath)
        selected = destTree.selection()
        readDrivesFromConfigFile = True
    else:
        destSplitWarningFrame.grid_remove()
        prevSelection = len(selected)

    selectedTotal = 0
    selectedDriveList = []
    for item in selected:
        # Write drive IDs to config
        driveVals = destTree.item(item, 'values')
        selectedDriveList.append({
            'vid': driveVals[3],
            'serial': driveVals[4],
            'capacity': int(driveVals[1])
        })

        driveSize = driveVals[1]
        selectedTotal = selectedTotal + int(driveSize)

    driveSelectedSpace.configure(text='Selected: ' + human_filesize(selectedTotal))
    if not readDrivesFromConfigFile:
        config['drives'] = selectedDriveList

    if len(threading.enumerate()) <= 3:
        progressBar.configure(mode='determinate')
        progressBar.stop()

def selectDriveInBackground(event):
    """Start the drive selection handling in a new thread."""
    threadManager.start(threadManager.MULTIPLE, target=handleDriveSelectionClick, name='Drive Select', daemon=True)

# TODO: Make changes to existing config check the existing for missing drives, and delete the config file from drives we unselected if there's multiple drives in a config
# TODO: If a drive config is overwritten with a new config file, due to the drive
# being configured for a different backup, then we don't want to delete that file
# In that case, the config file should be ignored. Thus, we need to delete configs
# on unselected drives only if the config file on the drive we want to delete matches
# the config on selected drives
# TODO: When drive selection happens, drives in the config should only be selected if the config on the other drive matches. If it doesn't don't select it by default, and warn about a conflict.
def writeConfigFile():
    """Write the current running backup config to config files on the drives."""
    if len(config['shares']) > 0 and len(config['drives']) > 0:
        driveConfigList = ''.join(['\n%s,%s,%d' % (drive['vid'], drive['serial'], drive['capacity']) for drive in config['drives']])
        driveVidToLetterMap = {destTree.item(item, 'values')[3]: destTree.item(item, 'text') for item in destTree.get_children()}

        # For each drive letter, get drive info, and write file
        for drive in config['drives']:
            if drive['vid'] in driveVidToLetterMap.keys():
                if not os.path.exists('%s:/%s' % (destDriveMap[drive['vid']], backupConfigDir)):
                    # If dir doesn't exist, make it
                    os.mkdir('%s:/%s' % (destDriveMap[drive['vid']], backupConfigDir))
                elif os.path.exists('%s:/%s/%s' % (destDriveMap[drive['vid']], backupConfigDir, backupConfigFile)) and os.path.isdir('%s:/%s/%s' % (destDriveMap[drive['vid']], backupConfigDir, backupConfigFile)):
                    # If dir exists but backup config filename is dir, delete the dir
                    os.rmdir('%s:/%s/%s' % (destDriveMap[drive['vid']], backupConfigDir, backupConfigFile))

                f = open('%s:/%s/%s' % (destDriveMap[drive['vid']], backupConfigDir, backupConfigFile), 'w')
                # f.write('[id]\n%s,%s\n\n' % (driveInfo['vid'], driveInfo['serial']))
                f.write('[shares]\n%s\n\n' % (','.join(config['shares'])))

                f.write('[drives]')
                f.write(driveConfigList)

                f.close()
    else:
        pass
        # print('You must select at least one share, and at least one drive')

backupHalted = False
def runBackup():
    """Once the backup analysis is run, and drives and shares are selected, run the backup.

    This function is run in a new thread, but is only run if the backup config is valid.
    If sanityCheck() returns False, the backup isn't run.
    """
    global backupHalted

    if not analysisValid:
        return

    if len(threading.enumerate()) <= 3:
        progressBar.configure(mode='indeterminate')
        progressBar.start()

    # Reset halt flag if it's been tripped
    backupHalted = False

    # Write config file to drives
    writeConfigFile()

    for cmd in commandList:
        cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Pending', fg=color.PENDING)
        cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text='Pending', fg=color.PENDING)

    startBackupBtn.configure(text='Halt Backup', command=lambda: threadManager.kill('Backup'), style='danger.TButton')

    for cmd in commandList:
        process = subprocess.Popen(cmd['cmd'], shell=True, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # process = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        while not threadManager.threadList['Backup']['killFlag'] and process.poll() is None:
            try:
                out = process.stdout.readline().decode().strip()
                cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Running', fg=color.RUNNING)
                cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text=out.strip(), fg=color.NORMAL)
            except Exception as e:
                print(e)
        process.terminate()

        if not threadManager.threadList['Backup']['killFlag']:
            cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Done', fg=color.FINISHED)
            cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text='Done', fg=color.FINISHED)
        else:
            cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Aborted', fg=color.STOPPED)
            cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text='Aborted', fg=color.STOPPED)
            break

    if len(threading.enumerate()) <= 3:
        progressBar.configure(mode='determinate')
        progressBar.stop()

    startBackupBtn.configure(text='Run Backup', command=startBackup, style='win.TButton')

def startBackup():
    """Start the backup in a new thread."""
    if sanityCheck():
        def killBackupThread():
            try:
                subprocess.run('taskkill /im robocopy.exe /f', shell=True, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            except Exception as e:
                print(e)

        threadManager.start(threadManager.KILLABLE, killBackupThread, target=runBackup, name='Backup', daemon=True)

class ThreadManager:
    # Define thread types for starting threads
    SINGLE = 0      # One thread at once, block if already running
    MULTIPLE = 1    # Multiple threads, name with counter, and run
    KILLABLE = 2    # Thread can be killed with a flag
    REPLACEABLE = 3 # Like SINGLE, but instead of blocking, kill and restart

    threadList = {}
    counter = 0

    def is_alive(self, threadName):
        """Check if a thread by a given name is active.

        Args:
            threadName (String): The name of the thread to check.

        Returns:
            threading.Thread: If thread found by name is active.
            bool: False if thread not found, or thread is not active.
        """
        for thread in threading.enumerate():
            if thread.name == threadName and thread.is_alive():
                return thread
        return False

    def garbage_collect(self):
        """Remove threads from threadList that aren't active anymore."""
        self.threadList = {name: thread for name, thread in self.threadList.items() if thread['thread'].is_alive()}

    def __init__(self):
        def threadGarbageCollect():
            """Periodically run garbage collection."""
            while 1:
                time.sleep(20)
                self.garbage_collect()

        self.gcThread = threading.Thread(target=threadGarbageCollect, name='ThreadManager_GC', daemon=True)
        self.gcThread.start()

    def start(self, threadType, *args, **kwargs):
        """Create and start a thread if one doesn't already exist.

        Args:
            threadType (int): The constant corresponding to the thread type to create.
            callback (def, optional): For KILLABLE and REPLACEABLE threads, the function to
                run to kill the thread.

        Returns:
            String: If a thread is successfully created, the thread name is returned.
            bool: False if an active thread exists with that name.
        """
        if kwargs['name']:
            threadName = kwargs['name']
        else:
            threadName = 'thread%d' % (self.counter)
            self.counter += 1

        def dummy():
            """A dummy function to pass as a default callback to KILLABLE threads."""
            pass

        # SINGLE: block if already running
        # MULTIPLE: run again, and increment counter
        # KILLABLE: Add flag to let it be killed
        # REPLACEABLE: SINGLE thread, but instead of blocking, kill and restart

        if threadType == self.SINGLE or threadType == self.KILLABLE or threadType == self.REPLACEABLE:
            if kwargs['name']:
                threadName = kwargs['name']
            else:
                self.counter += 1
                threadName = 'thread%d' % (self.counter)
        elif threadType == self.MULTIPLE:
            self.counter += 1
            threadName = '%s_%d' % (kwargs['name'] if kwargs['name'] else 'thread', self.counter)

        # If the thread either isn't in the list, or isn't active, create and run the thread
        if threadType == self.SINGLE and not self.is_alive(threadName):
            # if threadName not in self.threadList.keys() or not self.threadList[threadName]['thread'].is_alive():
            self.threadList[threadName] = {
                'type': threadType,
                'thread': threading.Thread(**kwargs)
            }

            self.threadList[threadName]['thread'].start()
            return threadName
        elif threadType == self.MULTIPLE and not self.is_alive(threadName):
            self.threadList[threadName] = {
                'type': threadType,
                'thread': threading.Thread(**kwargs)
            }

            self.threadList[threadName]['thread'].start()
            return threadName
        elif threadType == self.KILLABLE and not self.is_alive(threadName):
            self.threadList[threadName] = {
                'type': threadType,
                'thread': threading.Thread(**kwargs),
                'killFlag': False,
                'callback': args[0] if len(args) >= 1 else dummy
            }

            self.threadList[threadName]['thread'].start()
            return threadName
        elif threadType == self.REPLACEABLE:
            # If thread is active already, kill it before starting a new thread
            replaceableThread = self.is_alive(threadName)
            if replaceableThread:
                self.kill(replaceableThread)

            self.threadList[threadName] = {
                'type': threadType,
                'thread': threading.Thread(**kwargs),
                'killFlag': False,
                'callback': args[0] if len(args) >= 1 else dummy
            }

            self.threadList[threadName]['thread'].start()
            return threadName

        return False

    def kill(self, name):
        """Kill a KILLABLE or REPLACEABLE thread by name.

        Kills a thread by running the callback function defined during creation. This
        only works on KILLABLE and REPLACEABLE threads.

        Args:
            name (String): The name of the thread, as set in threadList.
        """
        if (name in self.threadList.keys()
                and self.threadList[name]['thread'].is_alive()
                and (self.threadList[name]['type'] == self.KILLABLE or self.threadList[name]['type'] == self.REPLACEABLE)
                and self.threadList[name]['killFlag'] is not True):
            # Thread exists, is active, is KILLABLE or REPLACEABLE, and has not been killed
            self.threadList[name]['killFlag'] = True
            self.threadList[name]['callback']()

    def list(self):
        """List all threads in threadList."""
        print('   Threads   \n=============')
        for thread in self.threadList.keys():
            print('%s => %s' % (thread, '-- Alive --' if self.is_alive(thread) else 'Dead'))

class color:
    NORMAL = '#000'
    FADED = '#999'
    BLUE = '#0093c4'
    GREEN = '#6db500'
    GOLD = '#ebb300'
    RED = '#c00'
    GRAY = '#999'

    ENABLED = GREEN
    DISABLED = RED

    INFO = '#bbe6ff'
    WARNING = '#ffe69d'

    FINISHED = GREEN
    RUNNING = BLUE
    STOPPED = RED
    PENDING = GRAY

# Set app defaults
sourceDrive = None
backupConfigDir = '.backdrop'
backupConfigFile = 'backup.config'
appConfigFile = 'defaults.config'
appDataFolder = os.getenv('LocalAppData') + '\\BackDrop'
elemPadding = 16

config = {
    'shares': [],
    'drives': {}
}

commandList = []

threadManager = ThreadManager()

analysisValid = False
analysisStarted = False

root = tk.Tk()
root.attributes('-alpha', 0.0)
root.title('BackDrop - Unraid Drive Backup Tool')
# TODO: Get an icon for the program
# root.iconbitmap('.\\App\\Shim\\assets\\unpack_128.ico')
root.resizable(False, False)
root.geometry('1200x700')

center(root)
root.attributes('-alpha', 1.0)

mainFrame = tk.Frame(root)
mainFrame.pack(fill='both', expand=1, padx=elemPadding, pady=(elemPadding / 2, elemPadding))

# Set some default styling
buttonWinStyle = ttk.Style()
buttonWinStyle.theme_use('vista')
buttonWinStyle.configure('win.TButton', padding=5)

buttonWinStyle = ttk.Style()
buttonWinStyle.theme_use('vista')
buttonWinStyle.configure('danger.TButton', padding=5, background='#b00')

buttonIconStyle = ttk.Style()
buttonIconStyle.theme_use('vista')
buttonIconStyle.configure('icon.TButton', width=2, height=1, padding=1, font=(None, 15), background='#00bfe6')

# Set source drives and start to set up source dropdown
sourceDriveDefault = tk.StringVar()
driveList = win32api.GetLogicalDriveStrings().split('\000')[:-1]
remoteDrives = [drive for drive in driveList if win32file.GetDriveType(drive) == 4]
sourceDrive = readSettingFromFile(appDataFolder + '\\sourceDrive.default', remoteDrives[0], remoteDrives)
sourceDriveDefault.set(sourceDrive)

if not os.path.exists(appDataFolder + '\\sourceDrive.default') or not os.path.isfile(appDataFolder + '\\sourceDrive.default'):
    writeSettingToFile(sourceDrive, appDataFolder + '\\sourceDrive.default')

# Tree frames for tree and scrollbar
sourceTreeFrame = tk.Frame(mainFrame)
sourceTreeFrame.grid(row=1, column=0, sticky='ns')
destTreeFrame = tk.Frame(mainFrame)
destTreeFrame.grid(row=1, column=1, sticky='ns', padx=(elemPadding, 0))

# Progress/status values
progressBar = ttk.Progressbar(mainFrame, maximum=100)
progressBar.grid(row=10, column=0, columnspan=3, sticky='ew', pady=(elemPadding, 0))

sourceTree = ttk.Treeview(sourceTreeFrame, columns=('size', 'rawsize'))
sourceTree.heading('#0', text='Share')
sourceTree.column('#0', width=200)
sourceTree.heading('size', text='Size')
sourceTree.column('size', width=80)
sourceTree['displaycolumns'] = ('size')

sourceTree.pack(side='left')
sourceShareScroll = ttk.Scrollbar(sourceTreeFrame, orient='vertical', command=sourceTree.yview)
sourceShareScroll.pack(side='left', fill='y')
sourceTree.configure(xscrollcommand=sourceShareScroll.set)

# There's an invisible 1px background on buttons. When changing this in icon buttons, it becomes
# visible, so 1px needs to be added back
sourceMetaFrame = tk.Frame(mainFrame)
sourceMetaFrame.grid(row=2, column=0, sticky='nsew', pady=(1, elemPadding))
tk.Grid.columnconfigure(sourceMetaFrame, 0, weight=1)

shareSpaceFrame = tk.Frame(sourceMetaFrame)
shareSpaceFrame.grid(row=0, column=0)
shareSelectedSpace = tk.Label(shareSpaceFrame, text='Selected: ' + human_filesize(0))
shareSelectedSpace.grid(row=0, column=0)
shareTotalSpace = tk.Label(shareSpaceFrame, text='Total: ~' + human_filesize(0))
shareTotalSpace.grid(row=0, column=1, padx=(12, 0))

startRefreshSource()

refreshSourceBtn = ttk.Button(sourceMetaFrame, text='\u2b6e', command=startRefreshSource, style='icon.TButton')
refreshSourceBtn.grid(row=0, column=1)

sourceSelectFrame = tk.Frame(mainFrame)
sourceSelectFrame.grid(row=0, column=0, pady=(0, elemPadding / 2))
tk.Label(sourceSelectFrame, text='Source:').pack(side='left')
sourceSelectMenu = ttk.OptionMenu(sourceSelectFrame, sourceDriveDefault, sourceDrive, *tuple(remoteDrives), command=changeSourceDrive)
sourceSelectMenu.pack(side='left', padx=(12, 0))

sourceTree.bind("<<TreeviewSelect>>", loadSourceInBackground)

destModeFrame = tk.Frame(mainFrame)
destModeFrame.grid(row=0, column=1, pady=(0, elemPadding / 2))

def handleSplitModeCheck():
    """Handle toggling of split mode based on checkbox value."""
    global destModeSplitEnabled
    if not analysisStarted:
        destModeSplitEnabled = destModeSplitCheckVar.get()
        splitModeStatus.configure(text='Split mode\n%s' % ('Enabled' if destModeSplitEnabled else 'Disabled'), fg=color.ENABLED if destModeSplitEnabled else color.DISABLED)

destModeSplitCheckVar = tk.BooleanVar()
destModeSplitEnabled = False

altTooltipFrame = tk.Frame(destModeFrame, bg=color.INFO)
altTooltipFrame.pack(side='left', ipadx=elemPadding / 2, ipady=4)
tk.Label(altTooltipFrame, text = 'Hold ALT while selecting a drive to ignore config files', bg=color.INFO).pack(fill='y', expand=1)

splitModeCheck = tk.Checkbutton(destModeFrame, text='Backup using split mode', variable=destModeSplitCheckVar, command=handleSplitModeCheck)
splitModeCheck.pack(side='left', padx=(12, 0))

destTree = ttk.Treeview(destTreeFrame, columns=('size', 'rawsize', 'configfile', 'vid', 'serial'))
destTree.heading('#0', text='Drive')
destTree.column('#0', width=50)
destTree.heading('size', text='Size')
destTree.column('size', width=80)
destTree.heading('configfile', text='Config file')
destTree.column('configfile', width=100)
destTree.heading('vid', text='Volume ID')
destTree.column('vid', width=100)
destTree.heading('serial', text='Serial')
destTree.column('serial', width=200)
destTree['displaycolumns'] = ('size', 'configfile', 'vid', 'serial')

destTree.pack(side='left')
driveSelectScroll = ttk.Scrollbar(destTreeFrame, orient='vertical', command=destTree.yview)
driveSelectScroll.pack(side='left', fill='y')
destTree.configure(xscrollcommand=driveSelectScroll.set)

# There's an invisible 1px background on buttons. When changing this in icon buttons, it becomes
# visible, so 1px needs to be added back
destMetaFrame = tk.Frame(mainFrame)
destMetaFrame.grid(row=2, column=1, sticky='nsew', pady=(1, elemPadding))
tk.Grid.columnconfigure(destMetaFrame, 0, weight=1)

destSplitWarningFrame = tk.Frame(mainFrame, bg=color.WARNING)
destSplitWarningFrame.rowconfigure(0, weight=1)
destSplitWarningFrame.columnconfigure(0, weight=1)
destSplitWarningFrame.columnconfigure(10, weight=1)

tk.Frame(destSplitWarningFrame).grid(row=0, column=0)
splitWarningPrefix = tk.Label(destSplitWarningFrame, text='There are', bg=color.WARNING)
splitWarningPrefix.grid(row=0, column=1, sticky='ns')
splitWarningMissingDriveCount = tk.Label(destSplitWarningFrame, text='0', bg=color.WARNING, font=(None, 18, 'bold'))
splitWarningMissingDriveCount.grid(row=0, column=2, sticky='ns')
splitWarningSuffix = tk.Label(destSplitWarningFrame, text='drives in the config that aren\'t connected. Please connect them, or enable split mode.', bg=color.WARNING)
splitWarningSuffix.grid(row=0, column=3, sticky='ns')
tk.Frame(destSplitWarningFrame).grid(row=0, column=10)

driveSpaceFrame = tk.Frame(destMetaFrame)
driveSpaceFrame.grid(row=0, column=0)
configSelectedSpace = tk.Label(driveSpaceFrame, text='Config: ' + human_filesize(0))
configSelectedSpace.grid(row=0, column=0)
driveSelectedSpace = tk.Label(driveSpaceFrame, text='Selected: ' + human_filesize(0))
driveSelectedSpace.grid(row=0, column=1, padx=(12, 0))
driveTotalSpace = tk.Label(driveSpaceFrame, text='Available: ' + human_filesize(0))
driveTotalSpace.grid(row=0, column=2, padx=(12, 0))
splitModeStatus = tk.Label(driveSpaceFrame, text='Split mode\n%s' % ('Enabled' if destModeSplitEnabled else 'Disabled'), fg=color.ENABLED if destModeSplitEnabled else color.DISABLED)
splitModeStatus.grid(row=0, column=3, padx=(12, 0))

refreshDestBtn = ttk.Button(destMetaFrame, text='\u2b6e', command=startRefreshDest, style='icon.TButton')
refreshDestBtn.grid(row=0, column=1)
startAnalysisBtn = ttk.Button(destMetaFrame, text='Analyze Backup', command=startBackupAnalysis, style='win.TButton')
startAnalysisBtn.grid(row=0, column=2)

driveSelectBind = destTree.bind("<<TreeviewSelect>>", selectDriveInBackground)

# Add activity frame for backup status output
tk.Grid.rowconfigure(mainFrame, 5, weight=1)
backupActivityFrame = tk.Frame(mainFrame)
backupActivityFrame.grid(row=5, column=0, columnspan=2, sticky='nsew')

backupActivityInfoCanvas = tk.Canvas(backupActivityFrame)
backupActivityInfoCanvas.pack(side='left', fill='both', expand=1)
backupActivityScroll = ttk.Scrollbar(backupActivityFrame, orient='vertical', command=backupActivityInfoCanvas.yview)
backupActivityScroll.pack(side='left', fill='y')
backupActivityScrollableFrame = ttk.Frame(backupActivityInfoCanvas)
backupActivityScrollableFrame.bind('<Configure>', lambda e: backupActivityInfoCanvas.configure(
    scrollregion=backupActivityInfoCanvas.bbox('all')
))

backupActivityInfoCanvas.create_window((0, 0), window=backupActivityScrollableFrame, anchor='nw')
backupActivityInfoCanvas.configure(yscrollcommand=backupActivityScroll.set)

# commandList = ['robocopy "R:\\atmg" "E:\\atmg" /mir', 'robocopy "R:\\documents" "E:\\documents" /mir', 'robocopy "R:\\backups" "F:\\backups" /mir /xd "Macrium Reflect"', 'robocopy "R:\\backups\\Macrium Reflect" "F:\\backups\\Macrium Reflect" /mir /xd "Main Desktop Boot Drive" "Office Desktop Boot Drive" /xf "Main Desktop Win10 Pre-Reinstall-00-00.mrimg" "AsusLaptop-Original-Win10-00-00.mrimg" "Office Desktop Pre10 - 12-24-2019-00-00.mrimg" "AndyLaptop-Win10-PreUbuntu-00-00.mrimg" "Asus Laptop Win10 Pre-Manjaro 2-26-2020-00-00.mrimg" "B0AA9BDCCD59E188-00-00.mrimg" "AndyLaptop-Ubuntu1810-00-00.mrimg" "WinME-HP-Pavillion-00-00.mrimg" "AndyLaptop-ManjaroArchitectKDE-00-00.mrimg" "Dad Full Clone 1-5-2014.7z" "AsusLaptop-Kali-8-10-2020-00-00.mrimg" "Win98-Gateway-00-00.mrimg" "AsusLaptop_Android-x86_9.0_8-11-2020-00-00.mrimg" "Win10 Reflect Rescue 7.2.4808.iso" "Win7 Reflect Rescue 7.2.4228.iso" "macrium_reflect_v7_user_guide.pdf" "Untitled.json"', 'robocopy "R:\\backups\\Macrium Reflect" "G:\\backups\\Macrium Reflect" /mir /xd "Asus Laptop Boot Drive" "Main Desktop User Files" "School Drive"']
# commandList = ['robocopy "R:\\documents" "H:\\documents" /mir']
# enumerateCommandInfo({
#     'enabled': True,
#     'cmd': cmd
# } for cmd in commandList)

tk.Grid.columnconfigure(mainFrame, 2, weight=1)

rightSideFrame = tk.Frame(mainFrame)
rightSideFrame.grid(row=0, column=2, rowspan=6, sticky='nsew', pady=(elemPadding / 2, 0))

backupSummaryFrame = tk.Frame(rightSideFrame)
backupSummaryFrame.pack(fill='both', expand=1, padx=(elemPadding, 0))
backupSummaryFrame.update()

backupTitle = tk.Label(backupSummaryFrame, text='Analysis Summary', font=(None, 20))
backupTitle.pack()

brandingFrame = tk.Frame(rightSideFrame)
brandingFrame.pack()

tk.Label(brandingFrame, text='BackDrop', font=(None, 28), fg=color.GREEN).pack(side='left')
tk.Label(brandingFrame, text='v' + appVersion, font=(None, 10), fg=color.FADED).pack(side='left', anchor='s', pady=(0, 6))

# Add placeholder to backup analysis
backupSummaryTextFrame = tk.Frame(backupSummaryFrame)
backupSummaryTextFrame.pack(fill='x')
tk.Label(backupSummaryTextFrame, text='This area will summarize the backup that\'s been configured.',
         wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')
tk.Label(backupSummaryTextFrame, text='Please start a backup analysis to generate a summary.',
         wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')
startBackupBtn = ttk.Button(backupSummaryFrame, text='Run Backup', command=startBackup, state='disable', style='win.TButton')
startBackupBtn.pack(pady=elemPadding / 2)

# QUESTION: Does init loadDest need to be SINGLE, MULTIPLE, or OVERRIDE?
threadManager.start(threadManager.SINGLE, target=loadDest, name='Init', daemon=True)

def onClose():
    if threadManager.is_alive('Backup'):
        if messagebox.askokcancel('Quit?', 'There\'s still a background process running. Are you sure you want to kill it?'):
            threadManager.kill('Backup')
            root.destroy()
    else:
        root.destroy()

root.protocol('WM_DELETE_WINDOW', onClose)
root.mainloop()
