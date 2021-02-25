from tkinter import messagebox
import os
import itertools
from datetime import datetime
import shutil

from bin.fileutils import human_filesize, get_directory_size
from bin.color import bcolor
from bin.threadManager import ThreadManager
from bin.config import Config
from bin.status import Status

class Backup:
    def __init__(self, config, backupConfigDir, backupConfigFile, doCopyFn, doDelFn, startBackupTimerFn, updateFileDetailListFn, analysisSummaryDisplayFn, enumerateCommandInfoFn, threadManager, updateUiComponentFn=None, uiColor=None, progress=None):
        """
        Args:
            config (dict): The backup config to be processed.
            backupConfigDir (String): The directory to store backup configs on each drive.
            backupConfigFile (String): The file to store backup configs on each drive.
            doCopyFn (def): The function to be used to handle file copying. TODO: Move doCopyFn outside of Backup class.
            doDelFn (def): The function to be used to handle file copying. TODO: Move doDelFn outside of Backup class.
            startBackupTimerFn (def): The function to be used to start the backup timer.
            updateUiComponentFn (def): The function to be used to update UI components (default None).
            updateFileDetailListFn (def): The function to be used to update file lists.
            analysisSummaryDisplayFn (def): The function to be used to show an analysis
                    summary.
            enumerateCommandInfoFn (def): The function to be used to enumerate command info
                    in the UI.
            threadManager (ThreadManager): The thread manager to check for kill flags.
            uiColor (Color): The UI color instance to reference for styling (default None). TODO: Move uiColor outside of Backup class
            progress (Progress): The progress tracker to bind to.
        """

        self.totals = {
            'master': 0,
            'delete': 0,
            'delta': 0,
            'running': 0,
            'buffer': 0,
            'progressBar': 0
        }

        self.confirmWipeExistingDrives = False
        self.analysisValid = False
        self.analysisStarted = False
        self.analysisRunning = False
        self.backupRunning = False
        self.backupStartTime = 0
        self.commandList = []

        self.config = config
        self.driveVidInfo = {drive['vid']: drive for drive in config['drives']}

        self.backupConfigDir = backupConfigDir
        self.backupConfigFile = backupConfigFile
        self.uiColor = uiColor
        self.doCopyFn = doCopyFn
        self.doDelFn = doDelFn
        self.startBackupTimerFn = startBackupTimerFn
        self.updateUiComponentFn = updateUiComponentFn
        self.updateFileDetailListFn = updateFileDetailListFn
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

        self.updateUiComponentFn(Status.UPDATEUI_STATUS_BAR, Status.BACKUP_ANALYSIS_RUNNING)

        # Sanity check for space requirements
        if not self.sanityCheck():
            return

        if not self.config['cliMode']:
            self.progress.startIndeterminate()
            self.updateUiComponentFn(Status.UPDATEUI_BACKUP_BTN, {'state': 'disable'})
            self.updateUiComponentFn(Status.UPDATEUI_ANALYSIS_BTN, {'state': 'disable'})

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
                # TODO: Replace hardcoded .backdrop with variable dir name from main file
                curDriveInfo['configSize'] = get_directory_size(drive['name'] + '.backdrop')
            else:
                curDriveInfo['name'] = f"[{drive['vid']}]"
                curDriveInfo['configSize'] = 20000  # Assume 20K config size

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

        allDriveFilesBuffer = {drive['name']: [] for drive in masterDriveList}

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
                        driveShareList[nextDrive['vid']].extend([share for share in smallShares.keys()])  # All small shares on next drive
                    else:
                        # Better to leave on current, but overflow to next drive
                        driveShareList[drive['vid']].extend(sharesThatFit)  # Shares that fit on current drive
                        driveShareList[nextDrive['vid']].extend([share for share in smallShares.keys() if share not in sharesThatFit])  # Remaining small shares on next drive
                else:
                    # If overflow for next drive is more than can fit on that drive, ignore it, put overflow
                    # back in pool of shares to sort, and put small drive shares only in current drive
                    driveShareList[drive['vid']].extend(sharesThatFit)  # Shares that fit on current drive
                    allDriveFilesBuffer[drive['name']].extend([f"{drive['name']}{share}" for share in sharesThatFit])

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

                filename = entry.path.split('\\')[-1]
                fileInfo[filename] = newDirSize

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
        driveExclusions = {drive['name']: [] for drive in masterDriveList}
        for share in shareInfo.keys():
            if os.path.exists(self.config['sourceDrive'] + share) and os.path.isdir(self.config['sourceDrive'] + share):
                summary = splitShare(share)

                # Build exclusion list for other drives\
                # This is done by "inverting" the file list for each drive into a list of exclusions for other drives
                for summaryItem in summary:
                    fileList = summaryItem['files']

                    for drive, files in fileList.items():
                        driveLetter = self.driveVidInfo[drive]['name']

                        # Add files to file list
                        allDriveFilesBuffer[driveLetter].extend(files)

                # Each summary contains a split share, and any split subfolders, starting with
                # the share and recursing into the directories
                for directory in summary:
                    shareName = directory['share']
                    shareFiles = directory['files']
                    shareExclusions = directory['exclusions']

                    allFiles = shareFiles.copy()
                    allFiles['exclusions'] = shareExclusions

                    # sourcePathStub = self.config['sourceDrive'] + shareName + '\\'
                    sourcePathStub = shareName + '\\'

                    # For each drive, gather list of files to be written to other drives, and
                    # use that as exclusions
                    for drive, files in shareFiles.items():
                        if len(files) > 0:
                            rawExclusions = allFiles.copy()
                            rawExclusions.pop(drive, None)

                            masterExclusions = [file for fileList in rawExclusions.values() for file in fileList]

                            # Remove share if excluded in parent splitting
                            if shareName in driveExclusions[self.driveVidInfo[drive]['name']]:
                                driveExclusions[self.driveVidInfo[drive]['name']].remove(shareName)

                            # Add new exclusions to list
                            driveExclusions[self.driveVidInfo[drive]['name']].extend([sourcePathStub + file for file in masterExclusions])
                            driveShareList[drive].append(shareName)

        def recurseFileList(directory):
            """Get a complete list of files in a directory.

            Args:
                directory (String): The directory to check.

            Returns:
                String[]: The file list.
            """

            fileList = []
            try:
                if len(os.scandir(directory)) > 0:
                    for entry in os.scandir(directory):
                        # For each entry, either add filesize to the total, or recurse into the directory
                        if entry.is_file():
                            fileList.append(entry.path)
                        elif entry.is_dir():
                            fileList.append(entry.path)
                            fileList.extend(recurseFileList(entry.path))
                else:
                    # No files, so append dir to list
                    fileList.append(entry.path)
            except NotADirectoryError:
                return []
            except PermissionError:
                return []
            except OSError:
                return []
            return fileList

        # For each drive in file list buffer, recurse into each directory and build a complete file list
        allDriveFiles = {drive['name']: [] for drive in masterDriveList}
        for drive, files in allDriveFilesBuffer.items():
            for file in files:
                allDriveFiles[drive].extend(recurseFileList(file))

        def buildDeltaFileList(drive, shares, exclusions):
            """Get lists of files to delete and replace from the destination drive, that no longer
            exist in the source, or have changed.

            Args:
                drive (String): The drive to check.
                shares (String[]): The list of shares to check.
                exclusions (String[]): The list of files and folders to exclude.

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
                sharesBeingProcessed = [share for share in shares if share == drive[3:] or share + '\\' in drive[3:]]
                for entry in os.scandir(drive):
                    # For each entry, either add filesize to the total, or recurse into the directory
                    if entry.is_file():
                        stubPath = entry.path[3:]
                        sourcePath = self.config['sourceDrive'] + stubPath
                        if (stubPath.find('\\') == -1  # Files should not be on root of drive
                                or not os.path.isfile(sourcePath)  # File doesn't exist in source, so delete it
                                or stubPath in exclusions  # File is excluded from drive
                                or len(sharesBeingProcessed) == 0):  # File should only count if dir is share or child, not parent
                            fileList['delete'].append((entry.path, entry.stat().st_size))
                            self.updateFileDetailListFn('delete', entry.path)
                        elif os.path.isfile(sourcePath):
                            if (entry.stat().st_mtime != os.path.getmtime(sourcePath)  # Existing file is older than source
                                    or entry.stat().st_size != os.path.getsize(sourcePath)):  # Existing file is different size than source
                                # If existing dest file is not same time as source, it needs to be replaced
                                fileList['replace'].append((entry.path, os.path.getsize(sourcePath), entry.stat().st_size))
                                self.updateFileDetailListFn('copy', entry.path)
                    elif entry.is_dir():
                        foundShare = False
                        stubPath = entry.path[3:]
                        sourcePath = self.config['sourceDrive'] + stubPath
                        for item in shares:
                            if (stubPath == item  # Dir is share, so it stays
                                    or (stubPath.find(item + '\\') == 0 and os.path.isdir(sourcePath))  # Dir is subdir inside share, and it exists in source
                                    or item.find(stubPath + '\\') == 0):  # Dir is parent directory of a share we're copying, so it stays
                                # Recurse into the share
                                newList = buildDeltaFileList(entry.path, shares, exclusions)
                                fileList['delete'].extend(newList['delete'])
                                fileList['replace'].extend(newList['replace'])
                                foundShare = True
                                break

                        if not foundShare and stubPath not in specialIgnoreList and stubPath not in exclusions:
                            # Directory isn't share, or part of one, and isn't a special folder or
                            # exclusion, so delete it
                            fileList['delete'].append((entry.path, get_directory_size(entry.path)))
                            self.updateFileDetailListFn('delete', entry.path)
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

        def buildNewFileList(drive, shares, exclusions):
            """Get lists of files to copy to the destination drive, that only exist on the
            source.

            Args:
                drive (String): The drive to check.
                shares (String[]): The list of shares the drive should contain.
                exclusions (String[]): The list of files and folders to exclude.

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
                if len(os.listdir(self.config['sourceDrive'] + drive[3:])) > 0:
                    sharesBeingProcessed = [share for share in shares if share == drive[3:] or share + '\\' in drive[3:]]
                    for entry in os.scandir(self.config['sourceDrive'] + drive[3:]):
                        # For each entry, either add filesize to the total, or recurse into the directory
                        if entry.is_file():
                            if (entry.path[3:].find('\\') > -1  # File is not in root of source
                                    and not os.path.isfile(targetDrive + entry.path[3:])  # File doesn't exist in destination drive
                                    and entry.path[3:] not in exclusions  # File isn't part of drive exclusion
                                    and len(sharesBeingProcessed) > 0):  # File should only count if dir is share or child, not parent
                                fileList['new'].append((targetDrive + entry.path[3:], entry.stat().st_size))
                                self.updateFileDetailListFn('copy', targetDrive + entry.path[3:])
                        elif entry.is_dir():
                            for item in shares:
                                if (entry.path[3:] == item  # Dir is share, so it stays
                                        or entry.path[3:].find(item + '\\') == 0  # Dir is subdir inside share
                                        or item.find(entry.path[3:] + '\\') == 0):  # Dir is parent directory of share
                                    if os.path.isdir(targetDrive + entry.path[3:]):
                                        # If exists on dest, recurse into it
                                        newList = buildNewFileList(targetDrive + entry.path[3:], shares, exclusions)
                                        fileList['new'].extend(newList['new'])
                                        break
                                    elif entry.path[3:] not in exclusions:
                                        # Path doesn't exist on dest, so add to list if not excluded
                                        # fileList['new'].append((targetDrive + entry.path[3:], get_directory_size(entry.path)))
                                        # self.updateFileDetailListFn('copy', targetDrive + entry.path[3:])

                                        newList = buildNewFileList(targetDrive + entry.path[3:], shares, exclusions)
                                        fileList['new'].extend(newList['new'])
                                        break
                elif not os.path.isdir(drive):
                    # If no files in folder on source, create empty folder in destination
                    return {
                        'new': [(targetDrive + drive[3:], get_directory_size(self.config['sourceDrive'] + drive[3:]))]
                    }

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
            modifyFileList = buildDeltaFileList(self.driveVidInfo[drive]['name'], shares, driveExclusions[self.driveVidInfo[drive]['name']])

            deleteItems = modifyFileList['delete']
            if len(deleteItems) > 0:
                deleteFileList[self.driveVidInfo[drive]['name']] = deleteItems
                fileDeleteList = [file for file, size in deleteItems]

                displayPurgeCommandList.append({
                    'enabled': True,
                    'type': 'fileList',
                    'drive': self.driveVidInfo[drive]['name'],
                    'size': sum([size for file, size in deleteItems]),
                    'fileList': fileDeleteList,
                    'mode': 'delete'
                })

                purgeCommandList.append({
                    'displayIndex': len(displayPurgeCommandList) + 1,
                    'type': 'fileList',
                    'drive': self.driveVidInfo[drive]['name'],
                    'fileList': fileDeleteList,
                    'payload': deleteItems,
                    'mode': 'delete'
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
            newItems = buildNewFileList(self.driveVidInfo[drive]['name'], shares, driveExclusions[self.driveVidInfo[drive]['name']])['new']
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
            # Double copy total to account for both copy and verify operations
            self.totals['master'] += 2 * driveTotal['copy'] + driveTotal['delete']
            self.totals['delete'] += driveTotal['delete']
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
        self.updateUiComponentFn(Status.UPDATEUI_STATUS_BAR, Status.BACKUP_READY_FOR_BACKUP)

        if not self.config['cliMode']:
            self.updateUiComponentFn(Status.UPDATEUI_BACKUP_BTN, {'state': 'normal'})
            self.updateUiComponentFn(Status.UPDATEUI_ANALYSIS_BTN, {'state': 'normal'})
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
            shareList = ','.join([item['name'] for item in self.config['shares']])
            rawVidList = [drive['vid'] for drive in self.config['drives']]
            rawVidList.extend(self.config['missingDrives'].keys())
            vidList = ','.join(rawVidList)

            # For each drive letter connected, get drive info, and write file
            for drive in self.config['drives']:
                # If config exists on drives, back it up first
                if os.path.isfile(f"{drive['name']}{self.backupConfigDir}\\{self.backupConfigFile}"):
                    shutil.move(f"{drive['name']}{self.backupConfigDir}\\{self.backupConfigFile}", f"{drive['name']}{self.backupConfigDir}\\{self.backupConfigFile}.old")

                backupConfigFile = Config(f"{self.driveVidInfo[drive['vid']]['name']}{self.backupConfigDir}\\{self.backupConfigFile}")

                # Write shares and VIDs to config file
                backupConfigFile.set('selection', 'shares', shareList)
                backupConfigFile.set('selection', 'vids', vidList)

                # Write info for each drive to its own section
                for curDrive in self.config['drives']:
                    backupConfigFile.set(curDrive['vid'], 'vid', curDrive['vid'])
                    backupConfigFile.set(curDrive['vid'], 'serial', curDrive['serial'])
                    backupConfigFile.set(curDrive['vid'], 'capacity', curDrive['capacity'])

                # Write info for missing drives
                for driveVid, capacity in self.config['missingDrives'].items():
                    backupConfigFile.set(driveVid, 'vid', driveVid)
                    backupConfigFile.set(driveVid, 'serial', 'Unknown')
                    backupConfigFile.set(driveVid, 'capacity', capacity)

    def run(self):
        """Once the backup analysis is run, and drives and shares are selected, run the backup.

        This function is run in a new thread, but is only run if the backup config is valid.
        If sanityCheck() returns False, the backup isn't run.
        """

        self.backupRunning = True
        self.updateUiComponentFn(Status.UPDATEUI_STATUS_BAR, Status.BACKUP_BACKUP_RUNNING)

        if not self.analysisValid or not self.sanityCheck():
            return

        # Write config file to drives
        self.writeConfigFile()

        if not self.config['cliMode']:
            self.progress.setMax(self.totals['master'])

            for cmd in commandList:
                self.cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Pending', fg=self.uiColor.PENDING)
                if cmd['type'] == 'fileList':
                    self.cmdInfoBlocks[cmd['displayIndex']]['currentFileResult'].configure(text='Pending', fg=self.uiColor.PENDING)
                self.cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text='Pending', fg=self.uiColor.PENDING)

            self.updateUiComponentFn(Status.UPDATEUI_STOP_BACKUP_BTN)

        timerStarted = False

        for cmd in commandList:
            if cmd['type'] == 'fileList':
                if not self.config['cliMode']:
                    self.cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Running', fg=self.uiColor.RUNNING)

                if not timerStarted:
                    timerStarted = True
                    self.backupStartTime = datetime.now()

                    self.threadManager.start(ThreadManager.KILLABLE, name='backupTimer', target=self.startBackupTimerFn)

                if cmd['mode'] == 'delete':
                    for file, size in cmd['payload']:
                        if self.threadManager.threadList['Backup']['killFlag']:
                            break

                        guiOptions = {
                            'displayIndex': cmd['displayIndex']
                        }

                        self.doDelFn(file, size, guiOptions)
                if cmd['mode'] == 'replace':
                    for file, sourceSize, destSize in cmd['payload']:
                        if self.threadManager.threadList['Backup']['killFlag']:
                            break

                        sourceFile = self.config['sourceDrive'] + file[3:]
                        destFile = file

                        guiOptions = {
                            'displayIndex': cmd['displayIndex']
                        }

                        self.doCopyFn(sourceFile, destFile, guiOptions)
                elif cmd['mode'] == 'copy':
                    for file, size in cmd['payload']:
                        if self.threadManager.threadList['Backup']['killFlag']:
                            break

                        sourceFile = self.config['sourceDrive'] + file[3:]
                        destFile = file

                        guiOptions = {
                            'displayIndex': cmd['displayIndex']
                        }

                        self.doCopyFn(sourceFile, destFile, guiOptions)

            if self.threadManager.threadList['Backup']['killFlag']:
                if not self.config['cliMode']:
                    self.cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Aborted', fg=self.uiColor.STOPPED)
                    self.cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text='Aborted', fg=self.uiColor.STOPPED)
                else:
                    print(f"{bcolor.FAIL}Backup aborted by user{bcolor.ENDC}")
                break
            if not self.threadManager.threadList['Backup']['killFlag']:
                if not self.config['cliMode']:
                    self.cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Done', fg=self.uiColor.FINISHED)
                    self.cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text='Done', fg=self.uiColor.FINISHED)
                else:
                    print(f"{bcolor.OKGREEN}Backup finished{bcolor.ENDC}")

        self.threadManager.kill('backupTimer')

        if not self.config['cliMode']:
            self.updateUiComponentFn(Status.UPDATEUI_START_BACKUP_BTN)

        self.updateUiComponentFn(Status.UPDATEUI_STATUS_BAR, Status.BACKUP_IDLE)
        self.backupRunning = False

    def getTotals(self):
        """
        Returns:
            totals (dict): The backup totals for the current instance.
        """

        return self.totals

    def getBackupStartTime(self):
        """
        Returns:
            datetime: The time the backup started. (default 0)
        """

        if self.backupStartTime:
            return self.backupStartTime
        else:
            return 0

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
