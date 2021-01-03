from tkinter import messagebox
import os
import itertools
import subprocess
from bin.fileutils import human_filesize, get_directory_size

class Backup:
    def __init__(self, config, backupConfigDir, backupConfigFile, uiColor, startBackupBtn, startAnalysisBtn, doCopyFn, startBackupFn, killBackupFn, analysisSummaryDisplayFn, enumerateCommandInfoFn, threadManager, progress):
        """
        Args:
            config (dict): The backup config to be processed.
            backupConfigDir (String): The directory to store backup configs on each drive.
            backupConfigFile (String): The file to store backup configs on each drive.
            uiColor (Color): The UI color instance to reference for styling. TODO: Move uiColor outside of Backup class
            startBackupBtn (tk.Button): The backup button to use in the UI. TODO: Move startBackupBtn outside of Backup class
            startAnalysisBtn (tk.Button): The analysis button to use in the UI. TODO: Move startAnalysisBtn outside of Backup class
            doCopy (def): The function to be used to handle file copying. TODO: Move doCopy outside of Backup class.
            startBackupFn (def): The function to be used to start the backup.
            killBackupFn (def): The function to be used to kill the backup.
            analysisSummaryDisplayFn (def): The function to be used to show an analysis
                    summary.
            enumerateCommandInfoFn (def): The function to be used to enumerate command info
                    in the UI.
            threadManager (ThreadManager): The thread manager to check for kill flags.
            progress (Progress): The progress tracker to bind to.
        """

        self.totals = {
            'master': 0,
            'delta': 0,
            'running': 0,
            'progressBar': 0
        }

        self.confirmWipeExistingDrives = False
        self.analysisValid = False
        self.analysisStarted = False
        self.analysisRunning = False
        self.backupRunning = False
        self.commandList = []

        self.config = config
        self.driveVidInfo = {drive['vid']: drive for drive in config['drives']}

        self.backupConfigDir = backupConfigDir
        self.backupConfigFile = backupConfigFile
        self.uiColor = uiColor
        self.startBackupBtn = startBackupBtn
        self.startAnalysisBtn = startAnalysisBtn
        self.doCopyFn = doCopyFn
        self.startBackupFn = startBackupFn
        self.killBackupFn = killBackupFn
        self.analysisSummaryDisplayFn = analysisSummaryDisplayFn
        self.enumerateCommandInfoFn = enumerateCommandInfoFn
        self.threadManager = threadManager
        self.progress = progress

    def sanityCheck(self):
        """Check to make sure everything is correct before a backup.

        Before running a backup, or an analysis, both shares and drives need to be
        selected, and the drive space on selected drives needs to be larger than the
        total size of the selected shares.

        Returns:
            bool: True if conditions are good, False otherwise.
        """

        if not self.config['sourceDrive']:
            return False

        selectionOk = len(self.config['drives']) > 0 and len(self.config['shares']) > 0

        if selectionOk:
            shareTotal = 0
            driveTotal = 0

            sharesKnown = True
            for share in self.config['shares']:
                if share['size'] is None:
                    sharesKnown = False
                    break

                # Add total space of selection
                shareTotal += share['size']

            driveTotal = sum([drive['capacity'] for drive in self.config['drives']])
            configTotal = driveTotal + sum([size for drive, size in self.config['missingDrives'].items()])

            if sharesKnown and ((len(self.config['missingDrives']) == 0 and shareTotal < driveTotal) or (shareTotal < configTotal and self.config['splitMode'])):
                # Sanity check pass if more drive selected than shares, OR, split mode and more config drives selected than shares

                selectedNewDrives = [drive['name'] for drive in self.config['drives'] if drive['hasConfig'] is False]
                if not self.confirmWipeExistingDrives and len(selectedNewDrives) > 0:
                    driveString = ', '.join(selectedNewDrives[:-2] + [' and '.join(selectedNewDrives[-2:])])

                    newDriveConfirmTitle = f"New drive{'s' if len(selectedNewDrives) > 1 else ''} selected"
                    newDriveConfirmMessage = f"Drive{'s' if len(selectedNewDrives) > 1 else ''} {driveString} appear{'' if len(selectedNewDrives) > 1 else 's'} to be new. Existing data will be deleted.\n\nAre you sure you want to continue?"
                    self.confirmWipeExistingDrives = messagebox.askyesno(newDriveConfirmTitle, newDriveConfirmMessage)

                    return self.confirmWipeExistingDrives

                return True

        return False

    # CAVEAT: This @analysis assumes the drives are going to be empty, aside from the config file
    # Other stuff that's not part of the backup will need to be deleted when we actually run it
    # IDEA: When we ignore other stuff on the drives, and delete it, have a dialog popup that summarizes what's being deleted, and ask the user to confirm
    def analyze(self):
        """Analyze the list of selected shares and drives and figure out how to split files.

        Args:
            shares (dict[]): The list of selected shares.
            shares.name (String): The name of the share.
            shares.size (int): The size in bytes of the share.
            drives (tuple(String)): The list of selected drives.

        This function is run in a new thread, but is only run if the backup config is valid.
        If sanityCheck() returns False, the analysis isn't run.
        """
        global backupSummaryTextFrame
        global commandList

        global deleteFileList
        global replaceFileList
        global newFileList

        self.analysisRunning = True
        self.analysisStarted = True

        # Sanity check for space requirements
        if not self.sanityCheck():
            return

        self.progress.startIndeterminate()

        self.startBackupBtn.configure(state='disable')
        self.startAnalysisBtn.configure(state='disable')

        shareInfo = {share['name']: share['size'] for share in self.config['shares']}
        allShareInfo = {share['name']: share['size'] for share in self.config['shares']}

        self.analysisSummaryDisplayFn(
            title='Shares',
            payload=[(share['name'], human_filesize(share['size'])) for share in self.config['shares']],
            reset=True
        )

        driveInfo = []
        driveShareList = {}
        masterDriveList = [drive for drive in self.config['drives']]
        masterDriveList.extend([{'vid': vid, 'capacity': capacity} for vid, capacity in self.config['missingDrives'].items()])
        connectedVidList = [drive['vid'] for drive in self.config['drives']]
        showDriveInfo = []
        for i, drive in enumerate(masterDriveList):
            driveConnected = drive['vid'] in connectedVidList

            curDriveInfo = drive
            curDriveInfo['connected'] = driveConnected

            # If drive is connected, collect info about config size and free space
            if driveConnected:
                curDriveInfo['configSize'] = get_directory_size(drive['name'] + '.backdrop')
            else:
                curDriveInfo['name'] = f"[{drive['vid']}]"
                curDriveInfo['configSize'] = 20000 # Assume 20K config size

            # TODO: Find a way to properly determine free space left of drive here
            curDriveInfo['free'] = drive['capacity'] - drive['configSize']

            driveInfo.append(curDriveInfo)

            # Enumerate list for tracking what shares go where
            driveShareList[drive['vid']] = []

            showDriveInfo.append((curDriveInfo['name'], human_filesize(drive['capacity']), driveConnected))

        self.analysisSummaryDisplayFn(
            title='Drives',
            payload=showDriveInfo
        )

        # For each drive, smallest first, filter list of shares to those that fit
        driveInfo.sort(key=lambda x: x['free'])

        for i, drive in enumerate(driveInfo):
            # Get list of shares small enough to fit on drive
            smallShares = {share: size for share, size in shareInfo.items() if size <= drive['free']}

            # Try every combination of shares that fit to find result that uses most of that drive
            largestSum = 0
            largestSet = []
            for n in range(1, len(smallShares) + 1):
                for subset in itertools.combinations(smallShares.keys(), n):
                    combinationTotal = sum(smallShares[share] for share in subset)

                    if (combinationTotal > largestSum and combinationTotal <= drive['free']):
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
                nextDriveFreeSpace = nextDrive['free'] - notFitTotal

                # If free space on next drive is less than total capacity of current drive, it
                # becomes more efficient to skip current drive, and put all shares on the next
                # drive instead.
                # This applies only if they can all fit on the next drive. If they have to be
                # split across multiple drives after moving them to a larger drive, then it's
                # easier to fit what we can on the small drive, to leave the larger drives
                # available for larger shares
                if notFitTotal <= nextDrive['free']:
                    totalSmallShareSpace = sum(size for size in smallShares.values())
                    if nextDriveFreeSpace < drive['free'] and totalSmallShareSpace <= nextDrive['free']:
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
            driveInfo[i]['free'] -= usedSpace

        def splitShare(share):
            """Recurse into a share or directory, and split the contents.

            Args:
                share (String): The share to split.
            """
            # Enumerate list for tracking what shares go where
            driveFileList = {drive['vid']: [] for drive in driveInfo}

            fileInfo = {}
            for entry in os.scandir(self.config['sourceDrive'] + share):
                if entry.is_file():
                    newDirSize = entry.stat().st_size
                elif entry.is_dir():
                    newDirSize = get_directory_size(entry.path)

                fileName = entry.path.split('\\')[-1]
                fileInfo[fileName] = newDirSize

            # For splitting shares, sort by largest free space first
            driveInfo.sort(reverse=True, key=lambda x: x['free'])

            for i, drive in enumerate(driveInfo):
                # Get list of files small enough to fit on drive
                totalSmallFiles = {file: size for file, size in fileInfo.items() if size <= drive['free']}

                # Since the list of files is truncated to prevent an unreasonably large
                # number of combinations to check, we need to keep processing the file list
                # in chunks to make sure we check if all files can be fit on one drive
                # TODO: This @analysis loop logic may need to be copied to the main @share portion, though this is only necessary if the user selects a large number of shares
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
                        if os.path.isfile(self.config['sourceDrive'] + '\\' + share + '\\' + file):
                            listFiles[file] = size
                        elif os.path.isdir(self.config['sourceDrive'] + '\\' + share + '\\' + file):
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

                            if (combinationTotal > largestSum and combinationTotal <= drive['free'] - processedFileSize):
                                largestSum = combinationTotal
                                largestSet = subset

                    filesThatFit.extend([file for file in largestSet])
                    processedSmallFiles.extend([file for file in trimmedSmallFiles.keys()])
                    fileInfo = {file: size for (file, size) in fileInfo.items() if file not in largestSet}

                    # Subtract file size of each batch of files from the free space on the drive so the next batch sorts properly
                    processedFileSize += sum([size for (file, size) in smallFiles.items() if file in largestSet])

                # Assign files to drive, and subtract filesize from free space
                # Since we're sorting by largest free space first, there's no cases to move
                # to a larger drive. This means all files that can fit should be put on the
                # drive they fit on.
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

        # For shares larger than all drives, recurse into each share
        driveExclusions = []
        for share in shareInfo.keys():
            if os.path.exists(self.config['sourceDrive'] + share) and os.path.isdir(self.config['sourceDrive'] + share):
                summary = splitShare(share)

                # Each summary contains a split share, and any split subfolders, starting with
                # the share and recursing into the directories
                for directory in summary:
                    shareName = directory['share']
                    shareFiles = directory['files']
                    shareExclusions = directory['exclusions']

                    allFiles = shareFiles.copy()
                    allFiles['exclusions'] = shareExclusions

                    sourcePathStub = self.config['sourceDrive'] + shareName + '\\'

                    # For each drive, gather list of files to be written to other drives, and
                    # use that as exclusions
                    for drive, files in shareFiles.items():
                        if len(files) > 0:
                            rawExclusions = allFiles.copy()
                            rawExclusions.pop(drive, None)

                            masterExclusions = [file for fileList in rawExclusions.values() for file in fileList]
                            driveExclusions.extend([sourcePathStub + file for file in masterExclusions])
                            driveShareList[drive].append(shareName)

        def buildDeltaFileList(drive, shares):
            """Get lists of files to delete and replace from the destination drive, that no longer
            exist in the source, or have changed.

            Args:
                drive (String): The drive to check.
                shares (String[]): The list of shares to check

            Returns:
                {
                    'delete' (tuple(String, int)[]): The list of files and filesizes for deleting.
                    'replace' (tuple(String, int, int)[]): The list of files and source/dest filesizes for replacement.
                }
            """
            specialIgnoreList = [self.backupConfigDir, '$RECYCLE.BIN', 'System Volume Information']
            fileList = {
                'delete': [],
                'replace': []
            }
            try:
                for entry in os.scandir(drive):
                    # For each entry, either add filesize to the total, or recurse into the directory
                    if entry.is_file():
                        stubPath = entry.path[3:]
                        sourcePath = self.config['sourceDrive'] + stubPath
                        if (stubPath.find('\\') == -1 # Files should not be on root of drive
                                or not os.path.isfile(sourcePath) # File doesn't exist in source, so delete it
                                or sourcePath in driveExclusions): # File is excluded from drive
                            fileList['delete'].append((entry.path, entry.stat().st_size))
                        elif os.path.isfile(sourcePath):
                            if (entry.stat().st_mtime != os.path.getmtime(sourcePath) # Existing file is older than source
                                    or entry.stat().st_size != os.path.getsize(sourcePath)): # Existing file is different size than source
                                # If existing dest file is not same time as source, it needs to be replaced
                                fileList['replace'].append((entry.path, os.path.getsize(sourcePath), entry.stat().st_size))
                    elif entry.is_dir():
                        foundShare = False
                        stubPath = entry.path[3:]
                        sourcePath = self.config['sourceDrive'] + stubPath
                        for item in shares:
                            if (stubPath == item # Dir is share, so it stays
                                    or (stubPath.find(item + '\\') == 0 and os.path.isdir(sourcePath)) # Dir is subdir inside share, and it exists in source
                                    or item.find(stubPath + '\\') == 0): # Dir is parent directory of a share we're copying, so it stays
                                # Recurse into the share
                                newList = buildDeltaFileList(entry.path, shares)
                                fileList['delete'].extend(newList['delete'])
                                fileList['replace'].extend(newList['replace'])
                                foundShare = True
                                break

                        if not foundShare and stubPath not in specialIgnoreList and entry.path not in driveExclusions:
                            # Directory isn't share, or part of one, and isn't a special folder or
                            # exclusion, so delete it
                            fileList['delete'].append((entry.path, get_directory_size(entry.path)))
            except NotADirectoryError:
                return {
                    'delete': [],
                    'replace': []
                }
            except PermissionError:
                return {
                    'delete': [],
                    'replace': []
                }
            except OSError:
                return {
                    'delete': [],
                    'replace': []
                }
            return fileList

        def buildNewFileList(drive, shares):
            """Get lists of files to copy to the destination drive, that only exist on the
            source.

            Args:
                drive (String): The drive to check.
                shares (String[]): The list of shares the drive should contain.

            Returns:
                {
                    'new' (tuple(String, int)[]): The list of file destinations and filesizes to copy.
                }
            """
            fileList = {
                'new': []
            }

            targetDrive = drive[0:3]

            try:
                for entry in os.scandir(self.config['sourceDrive'] + drive[3:]):
                    # For each entry, either add filesize to the total, or recurse into the directory
                    if entry.is_file():
                        if (entry.path[3:].find('\\') > -1 # File is not in root of source
                                and not os.path.isfile(targetDrive + entry.path[3:]) # File doesn't exist in destination drive
                                and targetDrive + entry.path[3:] not in driveExclusions): # File isn't part of drive exclusion
                            fileList['new'].append((targetDrive + entry.path[3:], entry.stat().st_size))
                    elif entry.is_dir():
                        for item in shares:
                            if (entry.path[3:] == item # Dir is share, so it stays
                                    or entry.path[3:].find(item + '\\') == 0 # Dir is subdir inside share
                                    or item.find(entry.path[3:] + '\\') == 0): # Dir is parent directory of share
                                if os.path.isdir(targetDrive + entry.path[3:]):
                                    # If exists on dest, recurse into it
                                    newList = buildNewFileList(targetDrive + entry.path[3:], shares)
                                    fileList['new'].extend(newList['new'])
                                    break
                                elif targetDrive + entry.path[3:] not in driveExclusions:
                                    # Path doesn't exist on dest, so add to list if not excluded
                                    fileList['new'].append((targetDrive + entry.path[3:], get_directory_size(entry.path)))
            except NotADirectoryError:
                return {
                    'new': []
                }
            except PermissionError:
                return {
                    'new': []
                }
            except OSError:
                return {
                    'new': []
                }
            return fileList

        # Build list of files/dirs to delete and replace
        deleteFileList = {}
        replaceFileList = {}
        newFileList = {}
        purgeCommandList = []
        copyCommandList = []
        displayPurgeCommandList = []
        displayCopyCommandList = []
        for drive, shares in driveShareList.items():
            modifyFileList = buildDeltaFileList(self.driveVidInfo[drive]['name'], shares)

            deleteItems = modifyFileList['delete']
            if len(deleteItems) > 0:
                deleteFileList[self.driveVidInfo[drive]['name']] = deleteItems
                fileDeleteList = [file for file, size in deleteItems]

                # Format list of files into commands
                fileDeleteCmdList = [('del /f "%s"' % (file) if os.path.isfile(file) else 'rmdir /s /q "%s"' % (file)) for file in fileDeleteList]

                displayPurgeCommandList.append({
                    'enabled': True,
                    'type': 'list',
                    'drive': self.driveVidInfo[drive]['name'],
                    'size': sum([size for file, size in deleteItems]),
                    'fileList': fileDeleteList,
                    'cmdList': fileDeleteCmdList
                })

                purgeCommandList.append({
                    'displayIndex': len(displayPurgeCommandList) + 1,
                    'type': 'list',
                    'drive': self.driveVidInfo[drive]['name'],
                    'fileList': fileDeleteList,
                    'cmdList': fileDeleteCmdList
                })

            # Build list of files to replace
            replaceItems = modifyFileList['replace']
            replaceItems.sort(key=lambda x: x[1])
            if len(replaceItems) > 0:
                replaceFileList[self.driveVidInfo[drive]['name']] = replaceItems
                fileReplaceList = [file for file, sourceSize, destSize in replaceItems]

                displayCopyCommandList.append({
                    'enabled': True,
                    'type': 'fileList',
                    'drive': self.driveVidInfo[drive]['name'],
                    'size': sum([sourceSize for file, sourceSize, destSize in replaceItems]),
                    'fileList': fileReplaceList,
                    'mode': 'replace'
                })

                copyCommandList.append({
                    'displayIndex': len(displayPurgeCommandList) + 1,
                    'type': 'fileList',
                    'drive': self.driveVidInfo[drive]['name'],
                    'fileList': fileReplaceList,
                    'payload': replaceItems,
                    'mode': 'replace'
                })

            # Build list of new files to copy
            newItems = buildNewFileList(self.driveVidInfo[drive]['name'], shares)['new']
            if len(newItems) > 0:
                newFileList[self.driveVidInfo[drive]['name']] = newItems
                fileCopyList = [file for file, size in newItems]

                displayCopyCommandList.append({
                    'enabled': True,
                    'type': 'fileList',
                    'drive': self.driveVidInfo[drive]['name'],
                    'size': sum([size for file, size in newItems]),
                    'fileList': fileCopyList,
                    'mode': 'copy'
                })

                copyCommandList.append({
                    'displayIndex': len(displayPurgeCommandList) + 1,
                    'type': 'fileList',
                    'drive': self.driveVidInfo[drive]['name'],
                    'fileList': fileCopyList,
                    'payload': newItems,
                    'mode': 'copy'
                })

        # Gather and summarize totals for analysis summary
        showFileInfo = []
        for i, drive in enumerate(driveShareList.keys()):
            fileSummary = []
            driveTotal = {
                'running': 0,
                'delta': 0,
                'delete': 0,
                'replace': 0,
                'copy': 0,
                'new': 0
            }

            if self.driveVidInfo[drive]['name'] in deleteFileList.keys():
                driveTotal['delete'] = sum([size for file, size in deleteFileList[self.driveVidInfo[drive]['name']]])

                driveTotal['running'] -= driveTotal['delete']
                self.totals['delta'] -= driveTotal['delete']

                fileSummary.append(f"Deleting {len(deleteFileList[self.driveVidInfo[drive]['name']])} files ({human_filesize(driveTotal['delete'])})")

            if self.driveVidInfo[drive]['name'] in replaceFileList.keys():
                driveTotal['replace'] = sum([sourceSize for file, sourceSize, destSize in replaceFileList[self.driveVidInfo[drive]['name']]])

                driveTotal['running'] += driveTotal['replace']
                driveTotal['copy'] += driveTotal['replace']
                driveTotal['delta'] += sum([sourceSize - destSize for file, sourceSize, destSize in replaceFileList[self.driveVidInfo[drive]['name']]])

                fileSummary.append(f"Updating {len(replaceFileList[self.driveVidInfo[drive]['name']])} files ({human_filesize(driveTotal['replace'])})")

            if self.driveVidInfo[drive]['name'] in newFileList.keys():
                driveTotal['new'] = sum([size for file, size in newFileList[self.driveVidInfo[drive]['name']]])

                driveTotal['running'] += driveTotal['new']
                driveTotal['copy'] += driveTotal['new']
                driveTotal['delta'] += driveTotal['new']

                fileSummary.append(f"{len(newFileList[self.driveVidInfo[drive]['name']])} new files ({human_filesize(driveTotal['new'])})")

            # Increment master totals
            self.totals['master'] += driveTotal['running']
            self.totals['delta'] += driveTotal['delta']

            if len(fileSummary) > 0:
                showFileInfo.append((self.driveVidInfo[drive]['name'], '\n'.join(fileSummary)))

        self.analysisSummaryDisplayFn(
            title='Files',
            payload=showFileInfo
        )

        # Concat both lists into command list
        commandList = [cmd for cmd in purgeCommandList]
        commandList.extend([cmd for cmd in copyCommandList])

        # Concat lists into display command list
        displayCommandList = [cmd for cmd in displayPurgeCommandList]
        displayCommandList.extend([cmd for cmd in displayCopyCommandList])

        # Fix display index on command list
        for i, cmd in enumerate(commandList):
            commandList[i]['displayIndex'] = i

        self.analysisSummaryDisplayFn(
            title='Summary',
            payload=[(self.driveVidInfo[drive]['name'], '\n'.join(shares), drive in connectedVidList) for drive, shares in driveShareList.items()]
        )

        self.enumerateCommandInfoFn(self, displayCommandList)

        self.analysisValid = True

        self.startBackupBtn.configure(state='normal')
        self.startAnalysisBtn.configure(state='normal')

        self.progress.stopIndeterminate()

        self.analysisRunning = False

    # TODO: Make changes to existing @config check the existing for missing @drives, and delete the config file from drives we unselected if there's multiple drives in a config
    # TODO: If a @drive @config is overwritten with a new config file, due to the drive
    # being configured for a different backup, then we don't want to delete that file
    # In that case, the config file should be ignored. Thus, we need to delete configs
    # on unselected drives only if the config file on the drive we want to delete matches
    # the config on selected drives
    # TODO: When @drive @selection happens, drives in the @config should only be selected if the config on the other drive matches. If it doesn't don't select it by default, and warn about a conflict.
    def writeConfigFile(self):
        """Write the current running backup config to config files on the drives."""
        if len(self.config['shares']) > 0 and len(self.config['drives']) > 0:
            driveConfigList = ''.join(['\n%s,%s,%d' % (drive['vid'], drive['serial'], drive['capacity']) for drive in self.config['drives']])

            # For each drive letter, get drive info, and write file
            for drive in self.config['drives']:
                if drive['vid'] in self.driveVidInfo.keys():
                    if not os.path.exists(f"{self.driveVidInfo[drive['vid']]['name']}{self.backupConfigDir}"):
                        # If dir doesn't exist, make it
                        os.mkdir(f"{self.driveVidInfo[drive['vid']]['name']}{self.backupConfigDir}")
                    elif os.path.isdir(f"{self.driveVidInfo[drive['vid']]['name']}{self.backupConfigDir}\\{self.backupConfigFile}"):
                        # If dir exists but backup config filename is dir, delete the dir
                        os.rmdir(f"{self.driveVidInfo[drive['vid']]['name']}{self.backupConfigDir}\\{self.backupConfigFile}")

                    f = open(f"{self.driveVidInfo[drive['vid']]['name']}{self.backupConfigDir}\\{self.backupConfigFile}", 'w')
                    # f.write('[id]\n%s,%s\n\n' % (driveInfo['vid'], driveInfo['serial']))
                    f.write('[shares]\n%s\n\n' % (','.join([item['name'] for item in self.config['shares']])))

                    f.write('[drives]')
                    f.write(driveConfigList)

                    f.close()
        else:
            pass
            # print('You must select at least one share, and at least one drive')

    def run(self):
        """Once the backup analysis is run, and drives and shares are selected, run the backup.

        This function is run in a new thread, but is only run if the backup config is valid.
        If sanityCheck() returns False, the backup isn't run.
        """
        global backupHalted

        self.backupRunning = True

        if not self.analysisValid or not self.sanityCheck():
            return

        self.progress.setMax(self.totals['master'])

        # Reset halt flag if it's been tripped
        backupHalted = False

        # Write config file to drives
        self.writeConfigFile()

        for cmd in commandList:
            self.cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Pending', fg=self.uiColor.PENDING)
            if cmd['type'] == 'fileList':
                self.cmdInfoBlocks[cmd['displayIndex']]['currentFileResult'].configure(text='Pending', fg=self.uiColor.PENDING)
            self.cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text='Pending', fg=self.uiColor.PENDING)

        self.startBackupBtn.configure(text='Halt Backup', command=self.killBackupFn, style='danger.TButton')

        for cmd in commandList:
            if cmd['type'] == 'list':
                for item in cmd['cmdList']:
                    process = subprocess.Popen(item, shell=True, stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text=item, fg=self.uiColor.NORMAL)

                    while not self.threadManager.threadList['Backup']['killFlag'] and process.poll() is None:
                        try:
                            self.cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Running', fg=self.uiColor.RUNNING)
                        except Exception as e:
                            print(e)
                    process.terminate()

                    if self.threadManager.threadList['Backup']['killFlag']:
                        break
            elif cmd['type'] == 'fileList':
                self.cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Running', fg=self.uiColor.RUNNING)
                if cmd['mode'] == 'replace':
                    for file, sourceSize, destSize in cmd['payload']:
                        sourceFile = self.config['sourceDrive'] + file[3:]
                        destFile = file

                        guiOptions = {
                            'displayIndex': cmd['displayIndex']
                        }

                        self.doCopyFn(sourceFile, destFile, guiOptions)
                elif cmd['mode'] == 'copy':
                    for file, size in cmd['payload']:
                        sourceFile = self.config['sourceDrive'] + file[3:]
                        destFile = file

                        guiOptions = {
                            'displayIndex': cmd['displayIndex']
                        }

                        self.doCopyFn(sourceFile, destFile, guiOptions)

            if not self.threadManager.threadList['Backup']['killFlag']:
                self.cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Done', fg=self.uiColor.FINISHED)
                self.cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text='Done', fg=self.uiColor.FINISHED)
            else:
                self.cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Aborted', fg=self.uiColor.STOPPED)
                self.cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text='Aborted', fg=self.uiColor.STOPPED)
                break

        self.startBackupBtn.configure(text='Run Backup', command=self.startBackupFn, style='win.TButton')

        self.backupRunning = False

    def getTotals(self):
        """
        Returns:
            totals (dict): The backup totals for the current instance.
        """
        return self.totals

    def getCmdInfoBlocks(self):
        """
        Returns:
            dict: The command info blocks for the current backup.
        """
        return self.cmdInfoBlocks

    def isAnalysisStarted(self):
        """
        Returns:
            bool: Whether or not the analysis has been started.
        """
        return self.analysisStarted

    def isRunning(self):
        """
        Returns:
            bool: Whether or not the backup is actively running something.
        """
        return self.analysisRunning or self.backupRunning