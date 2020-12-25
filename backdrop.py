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
from PIL import Image, ImageTk
import math
import hashlib

# Set meta info
appVersion = '1.2.0-alpha2'
threadsForProgressBar = 5

# TODO: @Shares are copied to root of drives, so other directories with data are most likely left intact
#     We may need to account for this, by checking for free space, and then adding the size of the existing share directories
#     This would prevent counting for existing data, though it's probably safe to wipe the drive of things that aren't getting copied anyway
#     When we copy, check directory size of source and dest, and if the dest is larger than source, copy those first to free up space for ones that increased
# TODO: Add a button in @interface for deleting the @config from @selected_drives
# IDEA: Add interactive CLI option if correct parameters are passed in @interface

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

def copyFileObj(sourceFilename, destFilename, callback, guiOptions={}, length=0):
    """Copy a source binary file to a destination.

    Args:
        sourceFilename (String): The source to copy.
        destFilename (String): The destination to copy to.
        callback (def): The function to call on progress change.
        guiOptions (obj): Options to handle GUI interaction (optional).
        length (int): The buffer length to use (default 0).

    Returns:
        bool: True if file was copied and verified successfully, False otherwise.
    """

    fsrc = open(sourceFilename, 'rb')
    fdst = open(destFilename, 'wb')

    try:
        # check for optimisation opportunity
        if "b" in fsrc.mode and "b" in fdst.mode and fsrc.readinto:
            return copyFile(fsrc, fdst, callback, length)
    except AttributeError:
        # one or both file objects do not support a .mode or .readinto attribute
        pass

    if not length:
        length = shutil.COPY_BUFSIZE

    fsrc_read = fsrc.read
    fdst_write = fdst.write

    file_size = os.path.getsize(sourceFilename)

    guiOptions['fileName'] = destFilename

    copied = 0
    while True:
        buf = fsrc_read(length)
        if not buf:
            break
        fdst_write(buf)
        copied += len(buf)
        callback(copied, file_size, guiOptions)

    fsrc.close()
    fdst.close()

    # If file copied in full, copy meta, and verify
    if copied == file_size:
        shutil.copymode(sourceFilename, destFilename)
        shutil.copystat(sourceFilename, destFilename)

        with open(sourceFilename, 'rb') as f:
            source_hash = hashlib.blake2b()
            while chunk := f.read(8192):
                source_hash.update(chunk)

        with open(destFilename, 'rb') as f:
            dest_hash = hashlib.blake2b()
            while chunk := f.read(8192):
                dest_hash.update(chunk)

        print(source_hash.hexdigest())
        print(dest_hash.hexdigest())
        if source_hash.hexdigest() == dest_hash.hexdigest():
            print('Files are identical')

        return source_hash.hexdigest() == dest_hash.hexdigest()
    else:
        return False

# differs from shutil.COPY_BUFSIZE on platforms != Windows
READINTO_BUFSIZE = 1024 * 1024

def copyFile(sourceFilename, destFilename, callback, guiOptions={}, length=0):
    """Copy a source binary file to a destination.

    Args:
        sourceFilename (String): The source to copy.
        destFilename (String): The destination to copy to.
        callback (def): The function to call on progress change.
        guiOptions (obj): Options to handle GUI interaction (optional).
        length (int): The buffer length to use (default 0).

    Returns:
        bool: True if file was copied and verified successfully, False otherwise.
    """

    """readinto()/memoryview() based variant of copyfileobj().
    *fsrc* must support readinto() method and both files must be
    open in binary mode.
    """

    fsrc = open(sourceFilename, 'rb')
    fdst = open(destFilename, 'wb')

    fsrc_readinto = fsrc.readinto
    fdst_write = fdst.write

    if not length:
        try:
            file_size = os.stat(fsrc.fileno()).st_size
        except OSError:
            file_size = READINTO_BUFSIZE
        length = min(file_size, READINTO_BUFSIZE)

    guiOptions['fileName'] = destFilename

    copied = 0
    with memoryview(bytearray(length)) as mv:
        while True:
            if threadManager.threadList['Backup']['killFlag']:
                break

            n = fsrc_readinto(mv)
            if not n:
                break
            elif n < length:
                with mv[:n] as smv:
                    fdst.write(smv)
            else:
                fdst_write(mv)
            copied += n
            callback(copied, file_size, guiOptions)

    fsrc.close()
    fdst.close()

    # If file copied in full, copy meta, and verify
    if copied == file_size:
        shutil.copymode(sourceFilename, destFilename)
        shutil.copystat(sourceFilename, destFilename)

        with open(sourceFilename, 'rb') as f:
            source_hash = hashlib.blake2b()
            while chunk := f.read(8192):
                source_hash.update(chunk)

        with open(destFilename, 'rb') as f:
            dest_hash = hashlib.blake2b()
            while chunk := f.read(8192):
                dest_hash.update(chunk)

        print(source_hash.hexdigest())
        print(dest_hash.hexdigest())
        if source_hash.hexdigest() == dest_hash.hexdigest():
            print('Files are identical')

        return source_hash.hexdigest() == dest_hash.hexdigest()
    else:
        return False

def printProgress(copied, total, guiOptions):
    """Display the copy progress of a transfer

    Args:
        copied (int): the number of bytes copied.
        total (int): The total file size.
        guiOptions (obj): The options for updating the GUI.
    """
    print('%s copied' % (str(math.floor(copied / total * 10000) / 100)))
    percentCopied = copied / total * 100

    fileName = guiOptions['fileName']

    # If display index has been specified, write progress to GUI
    if 'displayIndex' in guiOptions.keys():
        displayIndex = guiOptions['displayIndex']

        cmdInfoBlocks[displayIndex]['currentFileResult'].configure(text=fileName, fg=color.NORMAL)
        cmdInfoBlocks[displayIndex]['lastOutResult'].configure(text=f'{percentCopied:.2f}% \u2192 {human_filesize(copied)} of {human_filesize(total)}', fg=color.NORMAL)

def doCopy(src, dest, guiOptions={}):
    """Copy a source to a destination.

    Args:
        src (String): The source to copy.
        dest (String): The destination to copy to.
        guiOptions (obj): Options to handle GUI interaction (optional).
    """

    if os.path.isfile(src):
        if not threadManager.threadList['Backup']['killFlag']:
            copyFile(src, dest, printProgress, guiOptions)
    elif os.path.isdir(src):
        # Make dir if it doesn't exist
        if not os.path.isdir(dest):
            os.mkdir(dest)

        try:
            for entry in os.scandir(src):
                if threadManager.threadList['Backup']['killFlag']:
                    break

                if entry.is_file():
                    fileName = entry.path.split('\\')[-1]
                    copyFile(src + '\\' + fileName, dest + '\\' + fileName, printProgress, guiOptions)
                elif entry.is_dir():
                    fileName = entry.path.split('\\')[-1]
                    doCopy(src + '\\' + fileName, dest + '\\' + fileName)

            # Handle changing attributes of folders if we copy a new folder
            shutil.copymode(src, dest)
            shutil.copystat(src, dest)
        except:
            return False
        return True

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

    def copyList(index, item):
        """Copy a given indexed command to the clipboard.

        Args:
            index (int): The index of the command to copy.
            item (String): The name of the list to copy
        """
        clipboard.copy('\n'.join(cmdInfoBlocks[index][item]))

    for widget in backupActivityScrollableFrame.winfo_children():
        widget.destroy()

    cmdInfoBlocks = []
    for i, item in enumerate(displayCommandList):
        config = {}

        config['mainFrame'] = tk.Frame(backupActivityScrollableFrame)
        config['mainFrame'].pack(anchor='w', expand=1)

        # Set up header arrow, trimmed command, and status
        config['headLine'] = tk.Frame(config['mainFrame'])
        config['headLine'].pack(fill='x')
        config['arrow'] = tk.Label(config['headLine'], text=rightArrow)
        config['arrow'].pack(side='left')

        if item['type'] == 'cmd':
            cmd = item['cmd']
            cmdParts = cmd.split('/mir')
            # cmdHeaderText = ' '.join(cmdParts[0:3])
            cmdHeaderText = cmdParts[0].strip()
        elif item['type'] == 'list':
            cmdHeaderText = 'Delete %d files from %s' % (len(item['fileList']), item['drive'])
        elif item['type'] == 'fileList':
            if item['mode'] == 'replace':
                cmdHeaderText = 'Update %d files on %s' % (len(item['fileList']), item['drive'])
            elif item['mode'] == 'copy':
                cmdHeaderText = 'Copy %d new files to %s' % (len(item['fileList']), item['drive'])

        config['header'] = tk.Label(config['headLine'], text=cmdHeaderText, font=cmdHeaderFont, fg=color.NORMAL if item['enabled'] else color.FADED)
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

        if item['type'] == 'cmd':
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

            config['lastOutWorkingDirLine'] = tk.Frame(config['infoFrame'])
            config['lastOutWorkingDirLine'].pack(anchor='w')
            tk.Frame(config['lastOutWorkingDirLine'], width=arrowWidth).pack(side='left')
            config['lastOutWorkingDirHeader'] = tk.Label(config['lastOutWorkingDirLine'], text='Working dir:', font=cmdHeaderFont)
            config['lastOutWorkingDirHeader'].pack(side='left')
            config['lastOutWorkingDirResult'] = tk.Label(config['lastOutWorkingDirLine'], text='Pending' if item['enabled'] else 'Skipped', font=cmdStatusFont, fg=color.PENDING if item['enabled'] else color.FADED)
            config['lastOutWorkingDirResult'].pack(side='left')

            config['lastOutFileStatusLine'] = tk.Frame(config['infoFrame'])
            config['lastOutFileStatusLine'].pack(anchor='w')
            tk.Frame(config['lastOutFileStatusLine'], width=arrowWidth).pack(side='left')
            config['lastOutFileStatusHeader'] = tk.Label(config['lastOutFileStatusLine'], text='File Status:', font=cmdHeaderFont)
            config['lastOutFileStatusHeader'].pack(side='left')
            config['lastOutFileStatusResult'] = tk.Label(config['lastOutFileStatusLine'], text='Pending' if item['enabled'] else 'Skipped', font=cmdStatusFont, fg=color.PENDING if item['enabled'] else color.FADED)
            config['lastOutFileStatusResult'].pack(side='left')

            config['lastOutFileNameLine'] = tk.Frame(config['infoFrame'])
            config['lastOutFileNameLine'].pack(anchor='w')
            tk.Frame(config['lastOutFileNameLine'], width=arrowWidth).pack(side='left')
            config['lastOutFileNameHeader'] = tk.Label(config['lastOutFileNameLine'], text='File:', font=cmdHeaderFont)
            config['lastOutFileNameHeader'].pack(side='left')
            config['lastOutFileNameResult'] = tk.Label(config['lastOutFileNameLine'], text='Pending' if item['enabled'] else 'Skipped', font=cmdStatusFont, fg=color.PENDING if item['enabled'] else color.FADED)
            config['lastOutFileNameResult'].pack(side='left')

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
        elif item['type'] == 'list':
            config['fileSizeLine'] = tk.Frame(config['infoFrame'])
            config['fileSizeLine'].pack(anchor='w')
            tk.Frame(config['fileSizeLine'], width=arrowWidth).pack(side='left')
            config['fileSizeLineHeader'] = tk.Label(config['fileSizeLine'], text='Total size:', font=cmdHeaderFont)
            config['fileSizeLineHeader'].pack(side='left')
            config['fileSizeLineTotal'] = tk.Label(config['fileSizeLine'], text=human_filesize(item['size']), font=cmdStatusFont)
            config['fileSizeLineTotal'].pack(side='left')

            config['fileListLine'] = tk.Frame(config['infoFrame'])
            config['fileListLine'].pack(anchor='w')
            tk.Frame(config['fileListLine'], width=arrowWidth).pack(side='left')
            config['fileListLineHeader'] = tk.Label(config['fileListLine'], text='File list:', font=cmdHeaderFont)
            config['fileListLineHeader'].pack(side='left')
            config['fileListLineTooltip'] = tk.Label(config['fileListLine'], text='(Click to copy)', font=cmdStatusFont, fg=color.FADED)
            config['fileListLineTooltip'].pack(side='left')
            config['fullFileList'] = item['fileList']

            config['cmdListLine'] = tk.Frame(config['infoFrame'])
            config['cmdListLine'].pack(anchor='w')
            tk.Frame(config['cmdListLine'], width=arrowWidth).pack(side='left')
            config['cmdListLineHeader'] = tk.Label(config['cmdListLine'], text='Command list:', font=cmdHeaderFont)
            config['cmdListLineHeader'].pack(side='left')
            config['cmdListLineTooltip'] = tk.Label(config['cmdListLine'], text='(Click to copy)', font=cmdStatusFont, fg=color.FADED)
            config['cmdListLineTooltip'].pack(side='left')
            config['fullCmdList'] = item['cmdList']

            config['lastOutLine'] = tk.Frame(config['infoFrame'])
            config['lastOutLine'].pack(anchor='w')
            tk.Frame(config['lastOutLine'], width=arrowWidth).pack(side='left')
            config['lastOutHeader'] = tk.Label(config['lastOutLine'], text='Out:', font=cmdHeaderFont)
            config['lastOutHeader'].pack(side='left')
            config['lastOutResult'] = tk.Label(config['lastOutLine'], text='Pending' if item['enabled'] else 'Skipped', font=cmdStatusFont, fg=color.PENDING if item['enabled'] else color.FADED)
            config['lastOutResult'].pack(side='left')

            # Handle list trimming
            listFont = tkfont.Font(family=None, size=10, weight='normal')
            trimmedFileList = ', '.join(item['fileList'])
            trimmedCmdList = ', '.join(item['cmdList'])
            maxWidth = backupActivityInfoCanvas.winfo_width() * 0.8
            actualFileWidth = listFont.measure(', '.join(item['fileList']))
            actualCmdWidth = listFont.measure(', '.join(item['cmdList']))

            if actualFileWidth > maxWidth:
                while actualFileWidth > maxWidth and len(trimmedFileList) > 1:
                    trimmedFileList = trimmedFileList[:-1]
                    actualFileWidth = listFont.measure(trimmedFileList + '...')
                trimmedFileList = trimmedFileList + '...'

            if actualCmdWidth > maxWidth:
                while actualCmdWidth > maxWidth and len(trimmedCmdList) > 1:
                    trimmedCmdList = trimmedCmdList[:-1]
                    actualCmdWidth = listFont.measure(trimmedCmdList + '...')
                trimmedCmdList = trimmedCmdList + '...'

            config['fileListLineTrimmed'] = tk.Label(config['fileListLine'], text=trimmedFileList, font=cmdStatusFont)
            config['fileListLineTrimmed'].pack(side='left')
            config['cmdListLineTrimmed'] = tk.Label(config['cmdListLine'], text=trimmedCmdList, font=cmdStatusFont)
            config['cmdListLineTrimmed'].pack(side='left')

            # Command copy action click
            config['fileListLineHeader'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullFileList'))
            config['fileListLineTooltip'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullFileList'))
            config['fileListLineTrimmed'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullFileList'))

            config['cmdListLineHeader'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullCmdList'))
            config['cmdListLineTooltip'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullCmdList'))
            config['cmdListLineTrimmed'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullCmdList'))
        elif item['type'] == 'fileList':
            config['fileSizeLine'] = tk.Frame(config['infoFrame'])
            config['fileSizeLine'].pack(anchor='w')
            tk.Frame(config['fileSizeLine'], width=arrowWidth).pack(side='left')
            config['fileSizeLineHeader'] = tk.Label(config['fileSizeLine'], text='Total size:', font=cmdHeaderFont)
            config['fileSizeLineHeader'].pack(side='left')
            config['fileSizeLineTotal'] = tk.Label(config['fileSizeLine'], text=human_filesize(item['size']), font=cmdStatusFont)
            config['fileSizeLineTotal'].pack(side='left')

            config['fileListLine'] = tk.Frame(config['infoFrame'])
            config['fileListLine'].pack(anchor='w')
            tk.Frame(config['fileListLine'], width=arrowWidth).pack(side='left')
            config['fileListLineHeader'] = tk.Label(config['fileListLine'], text='File list:', font=cmdHeaderFont)
            config['fileListLineHeader'].pack(side='left')
            config['fileListLineTooltip'] = tk.Label(config['fileListLine'], text='(Click to copy)', font=cmdStatusFont, fg=color.FADED)
            config['fileListLineTooltip'].pack(side='left')
            config['fullFileList'] = item['fileList']

            config['currentFileLine'] = tk.Frame(config['infoFrame'])
            config['currentFileLine'].pack(anchor='w')
            tk.Frame(config['currentFileLine'], width=arrowWidth).pack(side='left')
            config['currentFileHeader'] = tk.Label(config['currentFileLine'], text='Current file:', font=cmdHeaderFont)
            config['currentFileHeader'].pack(side='left')
            config['currentFileResult'] = tk.Label(config['currentFileLine'], text='Pending' if item['enabled'] else 'Skipped', font=cmdStatusFont, fg=color.PENDING if item['enabled'] else color.FADED)
            config['currentFileResult'].pack(side='left')

            config['lastOutLine'] = tk.Frame(config['infoFrame'])
            config['lastOutLine'].pack(anchor='w')
            tk.Frame(config['lastOutLine'], width=arrowWidth).pack(side='left')
            config['lastOutHeader'] = tk.Label(config['lastOutLine'], text='Progress:', font=cmdHeaderFont)
            config['lastOutHeader'].pack(side='left')
            config['lastOutResult'] = tk.Label(config['lastOutLine'], text='Pending' if item['enabled'] else 'Skipped', font=cmdStatusFont, fg=color.PENDING if item['enabled'] else color.FADED)
            config['lastOutResult'].pack(side='left')

            # Handle list trimming
            listFont = tkfont.Font(family=None, size=10, weight='normal')
            trimmedFileList = ', '.join(item['fileList'])
            maxWidth = backupActivityInfoCanvas.winfo_width() * 0.8
            actualFileWidth = listFont.measure(', '.join(item['fileList']))

            if actualFileWidth > maxWidth:
                while actualFileWidth > maxWidth and len(trimmedFileList) > 1:
                    trimmedFileList = trimmedFileList[:-1]
                    actualFileWidth = listFont.measure(trimmedFileList + '...')
                trimmedFileList = trimmedFileList + '...'

            config['fileListLineTrimmed'] = tk.Label(config['fileListLine'], text=trimmedFileList, font=cmdStatusFont)
            config['fileListLineTrimmed'].pack(side='left')

            # Command copy action click
            config['fileListLineHeader'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullFileList'))
            config['fileListLineTooltip'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullFileList'))
            config['fileListLineTrimmed'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullFileList'))

        cmdInfoBlocks.append(config)

# CAVEAT: This @analysis assumes the drives are going to be empty, aside from the config file
# Other stuff that's not part of the backup will need to be deleted when we actually run it
# IDEA: When we ignore other stuff on the drives, and delete it, have a dialog popup that summarizes what's being deleted, and ask the user to confirm
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

    global deleteFileList
    global replaceFileList
    global newFileList

    # Sanity check for space requirements
    if not sanityCheck():
        return

    if len(threading.enumerate()) <= threadsForProgressBar:
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
    summaryFrame = tk.Frame(backupSummaryTextFrame)
    summaryFrame.pack(fill='x', expand=True)
    summaryFrame.columnconfigure(2, weight=1)

    shareInfo = {}
    allShareInfo = {}
    for i, item in enumerate(shares):
        shareName = sourceTree.item(item, 'text')
        shareSize = int(sourceTree.item(item, 'values')[1])

        shareInfo[shareName] = shareSize
        allShareInfo[shareName] = shareSize

        tk.Label(summaryFrame, text=shareName).grid(row=i, column=0, sticky='w')
        tk.Label(summaryFrame, text='\u27f6').grid(row=i, column=1, sticky='w')
        wrapFrame = tk.Frame(summaryFrame)
        wrapFrame.grid(row=i, column=2, sticky='ew')
        wrapFrame.update_idletasks()
        tk.Label(summaryFrame, text=human_filesize(shareSize),
                 wraplength=wrapFrame.winfo_width() - 2, justify='left').grid(row=i, column=2, sticky='w')

    tk.Label(backupSummaryTextFrame, text='Drives', font=summaryHeaderFont,
             wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')
    driveFrame = tk.Frame(backupSummaryTextFrame)
    driveFrame.pack(fill='x', expand=True)
    driveFrame.columnconfigure(2, weight=1)

    driveVidToLetterMap = {destTree.item(item, 'values')[3]: destTree.item(item, 'text') for item in destTree.get_children()}

    driveInfo = []
    driveShareList = {}
    for i, item in enumerate(drives):
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

        tk.Label(driveFrame, text=humanDriveName,
                 fg=color.NORMAL if 'name' in curDriveInfo.keys() else color.FADED).grid(row=i, column=0, sticky='w')
        tk.Label(driveFrame, text='\u27f6',
                 fg=color.NORMAL if 'name' in curDriveInfo.keys() else color.FADED).grid(row=i, column=1, sticky='w')
        wrapFrame = tk.Frame(driveFrame)
        wrapFrame.grid(row=i, column=2, sticky='ew')
        wrapFrame.update_idletasks()
        tk.Label(driveFrame, text=human_filesize(item['capacity']),
                 fg=color.NORMAL if 'name' in curDriveInfo.keys() else color.FADED,
                 wraplength=wrapFrame.winfo_width() - 2, justify='left').grid(row=i, column=2, sticky='w')

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

            # If free space on next drive is less than total capacity of current drive, it
            # becomes more efficient to skip current drive, and put all shares on the next
            # drive instead.
            # This applies only if they can all fit on the next drive. If they have to be
            # split across multiple drives after moving them to a larger drive, then it's
            # easier to fit what we can on the small drive, to leave the larger drives
            # available for larger shares
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

    # Recurse through drive
    # Exclude config dir, and shares that are purged
    # Recurse through all other files
    # Delete file if not exists on source
    #     QUESTION: Does this exclude files that are part of the source, but aren't supposed to be on that drive?
    # Delete folder if not exists on source
    # Recurse into folder
    # Delete folder if not exists or exists and not part of path for subfolder that's included
    #     If backups/Macrium is copied, don't delete backups, even if backups isn't a share that's copied
    # Delete exclusions
    # URGENT: Delete files that exist on source, but aren't supposed to be copied, and aren't explicitly excluded

    def crawl_drive_for_deletes(drive, excludeList):
        """Get A list of files to delete from a drive.

        Args:
            drive (String): The drive letter to check.
            excludeList (String[]): A list of folders/files to ignore.

        Returns:
            String list: The list of files to delete.
        """
        deleteList = []
        try:
            for entry in os.scandir(drive):
                # For each entry, either add filesize to the total, or recurse into the directory
                fullPath = entry.path[3:]
                if fullPath not in excludeList:
                    if not os.path.exists(sourceDrive + fullPath):
                        # Delete files that don't exist in source drive
                        deleteList.append(fullPath)
                    elif entry.is_dir():
                        # Path is dir, and exists on source, so recurse into it
                        deleteList.extend(crawl_drive_for_deletes(entry.path, excludeList))
        except NotADirectoryError:
            return []
        except PermissionError:
            return []
        except OSError:
            return []
        return deleteList

    # driveShareList contains info about whole shares mapped to drives
    # Use this to build the list of non-exclusion robocopy commands
    mirCommandList = []
    purgeCommandList = []
    displayMirCommandList = []
    displayPurgeCommandList = []
    for drive, shares in driveShareList.items():
        humanDrive = driveVidToLetterMap[drive] if drive in driveVidToLetterMap.keys() else '[%s]\\' % (drive)

        if len(shares) > 0:
            displayMirCommandList.extend([{
                'enabled': drive in driveVidToLetterMap.keys(),
                'type': 'cmd',
                'cmd': 'robocopy "%s" "%s" /mir' % (sourceDrive + share, humanDrive + share)
            } for share in shares])

            if drive in driveVidToLetterMap.keys():
                mirCommandList.extend([{
                    'displayIndex': len(displayMirCommandList) - len(shares) + i,
                    'type': 'cmd',
                    'cmd': 'robocopy "%s" "%s" /mir' % (sourceDrive + share, humanDrive + share)
                } for i, share in enumerate(shares)])

    # For shares larger than all drives, recurse into each share
    driveExclusions = []
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
                        driveExclusions.extend([sourcePathStub + file for file in masterExclusions])

                        # If drive is connected, calculate exclusions
                        if (drive in driveVidToLetterMap.keys()):
                            # Check exclusion list for source, and remove any exclusions in the source dir
                            # Then, add new exclusions to the list
                            print(shareName)
                            upperDir = '\\'.join(shareName.split('\\')[:-1])

                        fileExclusions = [sourcePathStub + file for file in masterExclusions if os.path.isfile(sourcePathStub + file)]
                        dirExclusions = [sourcePathStub + file for file in masterExclusions if os.path.isdir(sourcePathStub + file)]
                        xs = (' /xf "' + '" "'.join(fileExclusions) + '"') if len(fileExclusions) > 0 else ''
                        xd = (' /xd "' + '" "'.join(dirExclusions) + '"') if len(dirExclusions) > 0 else ''

                        displayMirCommandList.append({
                            'enabled': drive in driveVidToLetterMap.keys(),
                            'type': 'cmd',
                            'cmd': 'robocopy "%s" "%s" /mir%s%s' % (sourceDrive + shareName, humanDrive + shareName, xd, xs)
                        })

                        if drive in driveVidToLetterMap.keys():
                            mirCommandList.append({
                                'displayIndex': len(displayMirCommandList) - 1,
                                'type': 'cmd',
                                'cmd': 'robocopy "%s" "%s" /mir%s%s' % (sourceDrive + shareName, humanDrive + shareName, xd, xs)
                            })
                        driveShareList[drive].append(shareName)

    def buildDeltaFileList(drive):
        """Get lists of files to delete and replace from the destination drive, that no longer
        exist in the source, or have changed.

        Args:
            drive (String): The drive to check.

        Returns:
            {
                'delete' (tuple(String, int)[]): The list of files and filesizes for deleting.
                'replace' (tuple(String, int, int)[]): The list of files and source/dest filesizes for replacement.
            }
        """
        specialIgnoreList = [backupConfigDir, '$RECYCLE.BIN', 'System Volume Information']
        fileList = {
            'delete': [],
            'replace': []
        }
        try:
            for entry in os.scandir(drive):
                # For each entry, either add filesize to the total, or recurse into the directory
                if entry.is_file():
                    if (entry.path[3:].find('\\') == -1 # Files should not be on root of drive
                            or not os.path.isfile(sourceDrive + entry.path[3:]) # File doesn't exist in source, so delete it
                            or entry.path in driveExclusions): # File is excluded from drive
                        fileList['delete'].append((entry.path, entry.stat().st_size))
                    elif os.path.isfile(sourceDrive + entry.path[3:]):
                        if (entry.stat().st_mtime != os.path.getmtime(sourceDrive + entry.path[3:]) # Existing file is older than source
                                or entry.stat().st_size != os.path.getsize(sourceDrive + entry.path[3:])): # Existing file is different size than source
                            # If existing dest file is not same time as source, it needs to be replaced
                            filesizeDelta = os.path.getsize(sourceDrive + entry.path[3:]) - entry.stat().st_size
                            fileList['replace'].append((entry.path, os.path.getsize(sourceDrive + entry.path[3:]), entry.stat().st_size))
                elif entry.is_dir():
                    foundShare = False
                    for item in shares:
                        if (entry.path[3:] == item # Dir is share, so it stays
                                or (entry.path[3:].find(item + '\\') == 0 and os.path.isdir(sourceDrive + entry.path[3:])) # Dir is subdir inside share, and it exists in source
                                or item.find(entry.path[3:] + '\\') == 0): # Dir is parent directory of a share we're copying, so it stays
                            # Recurse into the share
                            newList = buildDeltaFileList(entry.path)
                            fileList['delete'].extend(newList['delete'])
                            fileList['replace'].extend(newList['replace'])
                            foundShare = True
                            break
                    if not foundShare and entry.path[3:] not in specialIgnoreList and entry.path not in driveExclusions:
                        # Directory isn't share, or part of one, and isn't a special folder or
                        # exclusion, so delete it
                        fileList['delete'].append((entry.path, get_directory_size(entry.path)))
        except NotADirectoryError:
            return []
        except PermissionError:
            return []
        except OSError:
            return []
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
            for entry in os.scandir(sourceDrive + drive[3:]):
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
            return []
        except PermissionError:
            return []
        except OSError:
            return []
        return fileList

    # Build list of files/dirs to delete and replace
    deleteFileList = {}
    replaceFileList = {}
    newFileList = {}
    for drive, shares in driveShareList.items():
        humanDrive = driveVidToLetterMap[drive] if drive in driveVidToLetterMap.keys() else '[%s]\\' % (drive)

        print('%s => %s' % (humanDrive, ', '.join(shares)))

        modifyFileList = buildDeltaFileList(humanDrive)

        deleteItems = modifyFileList['delete']
        if len(deleteItems) > 0:
            deleteFileList[humanDrive] = deleteItems
            fileDeleteList = [file for file, size in deleteItems]

            # Format list of files into commands
            fileDeleteCmdList = [('del /f "%s"' % (file) if os.path.isfile(file) else 'rmdir /s /q "%s"' % (file)) for file in fileDeleteList]

            displayPurgeCommandList.append({
                'enabled': True,
                'type': 'list',
                'drive': humanDrive,
                'size': sum([size for file, size in deleteItems]),
                'fileList': fileDeleteList,
                'cmdList': fileDeleteCmdList
            })

            purgeCommandList.append({
                'displayIndex': len(displayPurgeCommandList) + 1,
                'type': 'list',
                'drive': humanDrive,
                'fileList': fileDeleteList,
                'cmdList': fileDeleteCmdList
            })

        print('%d extra files => %s' % (len(deleteItems), human_filesize(sum([size for file, size in deleteItems]))))

        # Build list of files to replace
        replaceItems = modifyFileList['replace']
        replaceItems.sort(key = lambda x: x[1])
        if len(replaceItems) > 0:
            replaceFileList[humanDrive] = replaceItems
            fileReplaceList = [file for file, sourceSize, destSize in replaceItems]

            # TODO: Purge list is appended before copy list, so to get this to happen before robocopy, append the command to purge
            # This will need to be fixed once robocopy is no longer in play
            displayPurgeCommandList.append({
                'enabled': True,
                'type': 'fileList',
                'drive': humanDrive,
                'size': sum([sourceSize for file, sourceSize, destSize in replaceItems]),
                'fileList': fileReplaceList,
                'mode': 'replace'
            })

            purgeCommandList.append({
                'displayIndex': len(displayPurgeCommandList) + 1,
                'type': 'fileList',
                'drive': humanDrive,
                'fileList': fileReplaceList,
                'payload': replaceItems,
                'mode': 'replace'
            })

        print('%d replace files => %s' % (len(replaceItems), human_filesize(sum([sourceSize - destSize for file, sourceSize, destSize in replaceItems]))))

        # Build list of new files to copy
        newItems = buildNewFileList(humanDrive, shares)['new']
        if len(newItems) > 0:
            newFileList[humanDrive] = newItems
            fileCopyList = [file for file, size in newItems]

            # TODO: Purge list is appended before copy list, so to get this to happen before robocopy, append the command to purge
            # This will need to be fixed once robocopy is no longer in play
            displayPurgeCommandList.append({
                'enabled': True,
                'type': 'fileList',
                'drive': humanDrive,
                'size': sum([size for file, size in newItems]),
                'fileList': fileCopyList,
                'mode': 'copy'
            })

            purgeCommandList.append({
                'displayIndex': len(displayPurgeCommandList) + 1,
                'type': 'fileList',
                'drive': humanDrive,
                'fileList': fileCopyList,
                'payload': newItems,
                'mode': 'copy'
            })

        print('%d new files => %s' % (len(newItems), human_filesize(sum([size for file, size in newItems]))))

    # Concat both lists into command list
    commandList = []
    commandList.extend([cmd for cmd in purgeCommandList])
    commandList.extend([cmd for cmd in mirCommandList])

    # Concat lists into display command list
    displayCommandList = []
    displayCommandList.extend([cmd for cmd in displayPurgeCommandList])
    displayCommandList.extend([cmd for cmd in displayMirCommandList])

    # Fix display index on command list
    for i, cmd in enumerate(commandList):
        commandList[i]['displayIndex'] = i

    enumerateCommandInfo(displayCommandList)

    tk.Label(backupSummaryTextFrame, text='Summary', font=summaryHeaderFont,
             wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')
    summaryFrame = tk.Frame(backupSummaryTextFrame)
    summaryFrame.pack(fill='x', expand=True)
    summaryFrame.columnconfigure(2, weight=1)
    i = 0
    for drive, shares in driveShareList.items():
        humanDrive = driveVidToLetterMap[drive] if drive in driveVidToLetterMap.keys() else '[%s]' % (drive)
        tk.Label(summaryFrame, text=humanDrive,
                 fg=color.NORMAL if drive in driveVidToLetterMap.keys() else color.FADED).grid(row=i, column=0, sticky='w')
        tk.Label(summaryFrame, text='\u27f6',
                 fg=color.NORMAL if drive in driveVidToLetterMap.keys() else color.FADED).grid(row=i, column=1, sticky='w')
        wrapFrame = tk.Frame(summaryFrame)
        wrapFrame.grid(row=i, column=2, sticky='ew')
        wrapFrame.update_idletasks()
        tk.Label(summaryFrame, text='\n'.join(shares),
                 fg=color.NORMAL if drive in driveVidToLetterMap.keys() else color.FADED,
                 wraplength=wrapFrame.winfo_width() - 2, justify='left').grid(row=i, column=2, sticky='w')

        i += 1

    analysisValid = True

    startBackupBtn.configure(state='normal')
    startAnalysisBtn.configure(state='normal')

    if len(threading.enumerate()) <= threadsForProgressBar:
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

    if not sourceDriveListValid:
        return False

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
    # FIXME: If backup @analysis @thread is already running, it needs to be killed before it's rerun
    # CAVEAT: This requires some way to have the @analysis @thread itself check for the kill flag and break if it's set.
    if sourceDriveListValid:
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
    if len(threading.enumerate()) <= threadsForProgressBar:
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

    if len(threading.enumerate()) <= threadsForProgressBar:
        progressBar.configure(mode='determinate')
        progressBar.stop()

def startRefreshSource():
    """Start a source refresh in a new thread."""
    if sourceDriveListValid:
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

# IDEA: @Calculate total space of all @shares in background
prevShareSelection = []
def shareSelectCalc():
    """Calculate and display the filesize of a selected share, if it hasn't been calculated.

    This gets the selection in the source tree, and then calculates the filesize for
    all shares selected that haven't yet been calculated. The summary of total
    selection, and total share space is also shown below the tree.
    """
    global prevShareSelection
    global analysisValid
    if len(threading.enumerate()) <= threadsForProgressBar:
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

        if len(threading.enumerate()) <= threadsForProgressBar:
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
    if len(threading.enumerate()) <= threadsForProgressBar:
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

    if len(threading.enumerate()) <= threadsForProgressBar:
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
    # QUESTION: Is there a better way to handle this @config loading @selection handler @conflict?
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

    if len(threading.enumerate()) <= threadsForProgressBar:
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
    # We only want to do this if the click is the first selection (that is, there
    # are no other drives selected except the one we clicked).
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

    if len(threading.enumerate()) <= threadsForProgressBar:
        progressBar.configure(mode='determinate')
        progressBar.stop()

def selectDriveInBackground(event):
    """Start the drive selection handling in a new thread."""
    threadManager.start(threadManager.MULTIPLE, target=handleDriveSelectionClick, name='Drive Select', daemon=True)

# TODO: Make changes to existing @config check the existing for missing @drives, and delete the config file from drives we unselected if there's multiple drives in a config
# TODO: If a @drive @config is overwritten with a new config file, due to the drive
# being configured for a different backup, then we don't want to delete that file
# In that case, the config file should be ignored. Thus, we need to delete configs
# on unselected drives only if the config file on the drive we want to delete matches
# the config on selected drives
# TODO: When @drive @selection happens, drives in the @config should only be selected if the config on the other drive matches. If it doesn't don't select it by default, and warn about a conflict.
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

    if len(threading.enumerate()) <= threadsForProgressBar:
        progressBar.configure(mode='indeterminate')
        progressBar.start()

    # Reset halt flag if it's been tripped
    backupHalted = False

    # Write config file to drives
    writeConfigFile()

    for cmd in commandList:
        cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Pending', fg=color.PENDING)
        if cmd['type'] == 'fileList':
            cmdInfoBlocks[cmd['displayIndex']]['currentFileResult'].configure(text='Pending', fg=color.PENDING)
        cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text='Pending', fg=color.PENDING)

    startBackupBtn.configure(text='Halt Backup', command=lambda: threadManager.kill('Backup'), style='danger.TButton')

    import re

    for cmd in commandList:
        if cmd['type'] == 'cmd':
            process = subprocess.Popen(cmd['cmd'], shell=True, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # process = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

            dirFileCount = False
            workingDir = False
            fileAnalysis = False
            fileSize = False
            fileName = False
            filePercent = False

            while not threadManager.threadList['Backup']['killFlag'] and process.poll() is None:
                try:
                    out = process.stdout.readline().decode().strip()

                    fileData = re.split(r'\s{2,}|[\t\r]', out)

                    if fileData[0] != 'Total':
                        # If first item in file line is total, then the summary has started, and we'e done with file output

                        print('--------------------------------------------')

                        if len(fileData) == 2 and fileData[1][-1] == '\\':
                            # If file line has two items only, it indicates file count, and working directory
                            dirFileCount = fileData[0]
                            workingDir = fileData[1]

                            print(dirFileCount + ' => ' + workingDir)
                        elif len(fileData) == 3 and fileData[0] != 'ROBOCOPY':
                            # If file line has 3 items, it's a skipped or extra file or dir, with no percent output
                            fileAnalysis = fileData[0]
                            fileSize = fileData[1]
                            fileName = fileData[2]
                            filePercent = False

                            print(dirFileCount + ' => ' + workingDir)
                            print(fileAnalysis + ' => ' + fileSize + ' => ' + fileName)
                        elif len(fileData) >= 4 and fileData[-1][-1] == '%':
                            # If file line has more than 2 items, it's either a meta line, or a file line
                            # File lines report the last item in the array as percent copied
                            fileAnalysis = fileData[0]
                            fileSize = fileData[1]
                            fileName = fileData[2]
                            filePercent = fileData[-1]

                            print(dirFileCount + ' => ' + workingDir)
                            print(fileAnalysis + ' => ' + fileSize + ' => ' + fileName)
                            print(filePercent)
                        else:
                            fileAnalysis = False
                            fileSize = False
                            fileName = False
                            filePercent = False

                            print(len(fileData))
                            print(fileData)

                        workingDirText = '%s files in %s' % (dirFileCount, workingDir) if dirFileCount and workingDir else ''
                        fileStatusText = '%s => %s' % (fileAnalysis, fileName) if fileAnalysis and fileName else ''
                        if filePercent and fileSize:
                            filePercentText = '%s of %s' % (filePercent, fileSize)
                        elif fileSize:
                            filePercentText = fileSize
                        else:
                            filePercentText = ''

                        cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Running', fg=color.RUNNING)
                        cmdInfoBlocks[cmd['displayIndex']]['lastOutWorkingDirResult'].configure(text=workingDirText, fg=color.NORMAL)
                        cmdInfoBlocks[cmd['displayIndex']]['lastOutFileStatusResult'].configure(text=fileStatusText, fg=color.NORMAL)
                        cmdInfoBlocks[cmd['displayIndex']]['lastOutFileNameResult'].configure(text=filePercentText, fg=color.NORMAL)
                    else:
                        break

                    # print('----------------------')
                    # print(workingDir)
                    # print(dirFileCount)
                    # print(fileAnalysis)
                    # print(fileSize)
                    # print(fileName)
                    # print(filePercent)
                except Exception as e:
                    print(e)
            process.terminate()
        elif cmd['type'] == 'list':
            for item in cmd['cmdList']:
                process = subprocess.Popen(item, shell=True, stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text=item, fg=color.NORMAL)

                while not threadManager.threadList['Backup']['killFlag'] and process.poll() is None:
                    try:
                        cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Running', fg=color.RUNNING)
                    except Exception as e:
                        print(e)
                process.terminate()

                if threadManager.threadList['Backup']['killFlag']:
                    break
        elif cmd['type'] == 'fileList':
            if cmd['mode'] == 'replace':
                for file, sourceSize, destSize in cmd['payload']:
                    sourceFile = sourceDrive + file[3:]
                    destFile = file

                    guiOptions = {
                        'displayIndex': cmd['displayIndex']
                    }

                    doCopy(sourceFile, destFile, guiOptions)
            elif cmd['mode'] == 'copy':
                for file, size in cmd['payload']:
                    sourceFile = sourceDrive + file[3:]
                    destFile = file

                    guiOptions = {
                        'displayIndex': cmd['displayIndex']
                    }

                    doCopy(sourceFile, destFile, guiOptions)

        # URGENT: Fix this GUI output to not break with list types
        if not threadManager.threadList['Backup']['killFlag']:
            cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Done', fg=color.FINISHED)
            cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text='Done', fg=color.FINISHED)

            if cmd['type'] == 'cmd':
                cmdInfoBlocks[cmd['displayIndex']]['lastOutWorkingDirResult'].configure(text='Done', fg=color.FINISHED)
                cmdInfoBlocks[cmd['displayIndex']]['lastOutFileStatusResult'].configure(text='Done', fg=color.FINISHED)
                cmdInfoBlocks[cmd['displayIndex']]['lastOutFileNameResult'].configure(text='Done', fg=color.FINISHED)
        else:
            cmdInfoBlocks[cmd['displayIndex']]['state'].configure(text='Aborted', fg=color.STOPPED)
            cmdInfoBlocks[cmd['displayIndex']]['lastOutResult'].configure(text='Aborted', fg=color.STOPPED)

            if cmd['type'] == 'cmd':
                cmdInfoBlocks[cmd['displayIndex']]['lastOutWorkingDirResult'].configure(text='Aborted', fg=color.STOPPED)
                cmdInfoBlocks[cmd['displayIndex']]['lastOutFileStatusResult'].configure(text='Aborted', fg=color.STOPPED)
                cmdInfoBlocks[cmd['displayIndex']]['lastOutFileNameResult'].configure(text='Aborted', fg=color.STOPPED)
            break

    if len(threading.enumerate()) <= threadsForProgressBar:
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
    ERROR = '#ffd0d0'

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
robocopyLogFile = 'robocopy.log'
elemPadding = 16

config = {
    'shares': [],
    'drives': {}
}

commandList = []

threadManager = ThreadManager()

analysisValid = False
analysisStarted = False

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

root = tk.Tk()
root.attributes('-alpha', 0.0)
root.title('BackDrop - Network Drive Backup Tool')
root.resizable(False, False)
root.geometry('1300x700')
root.iconbitmap(resource_path('media\\icon.ico'))

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

# Progress/status values
progressBar = ttk.Progressbar(mainFrame, maximum=100)
progressBar.grid(row=10, column=0, columnspan=3, sticky='ew', pady=(elemPadding, 0))

# Set source drives and start to set up source dropdown
sourceDriveDefault = tk.StringVar()
driveList = win32api.GetLogicalDriveStrings().split('\000')[:-1]
remoteDrives = [drive for drive in driveList if win32file.GetDriveType(drive) == 4]

sourceDriveListValid = len(remoteDrives) > 0

if sourceDriveListValid:
    sourceDrive = readSettingFromFile(appDataFolder + '\\sourceDrive.default', remoteDrives[0], remoteDrives)
    sourceDriveDefault.set(sourceDrive)

    if not os.path.exists(appDataFolder + '\\sourceDrive.default') or not os.path.isfile(appDataFolder + '\\sourceDrive.default'):
        writeSettingToFile(sourceDrive, appDataFolder + '\\sourceDrive.default')

    # Tree frames for tree and scrollbar
    sourceTreeFrame = tk.Frame(mainFrame)
    sourceTreeFrame.grid(row=1, column=0, sticky='ns')

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
else:
    sourceDriveDefault.set('No remotes')

    # sourceMissingFrame = tk.Frame(mainFrame, width=200)
    # sourceMissingFrame.grid(row=0, column=0,  rowspan=2, sticky='nsew')
    sourceWarning = tk.Label(mainFrame, text='No network drives are available to use as source', font=(None, 14), wraplength=250, bg=color.ERROR)
    sourceWarning.grid(row=0, column=0, rowspan=3, sticky='nsew', padx=10, pady=10, ipadx=20, ipady=20)

destTreeFrame = tk.Frame(mainFrame)
destTreeFrame.grid(row=1, column=1, sticky='ns', padx=(elemPadding, 0))

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
tk.Label(altTooltipFrame, text='Hold ALT while selecting a drive to ignore config files', bg=color.INFO).pack(fill='y', expand=1)

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
startAnalysisBtn = ttk.Button(destMetaFrame, text='Analyze Backup', command=startBackupAnalysis, state='normal' if sourceDriveListValid else 'disabled', style='win.TButton')
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

brandingFrame = tk.Frame(rightSideFrame)
brandingFrame.pack()

logoImageLoad = Image.open(resource_path('media\\logo_ui.png'))
logoImageRender = ImageTk.PhotoImage(logoImageLoad)
tk.Label(brandingFrame, image=logoImageRender).pack(side='left')
tk.Label(brandingFrame, text='v' + appVersion, font=(None, 10), fg=color.FADED).pack(side='left', anchor='s', pady=(0, 12))

backupTitle = tk.Label(backupSummaryFrame, text='Analysis Summary', font=(None, 20))
backupTitle.pack()

# Add placeholder to backup analysis
backupSummaryTextFrame = tk.Frame(backupSummaryFrame)
backupSummaryTextFrame.pack(fill='x')
tk.Label(backupSummaryTextFrame, text='This area will summarize the backup that\'s been configured.',
         wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')
tk.Label(backupSummaryTextFrame, text='Please start a backup analysis to generate a summary.',
         wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')
startBackupBtn = ttk.Button(backupSummaryFrame, text='Run Backup', command=startBackup, state='disable', style='win.TButton')
startBackupBtn.pack(pady=elemPadding / 2)

# QUESTION: Does init loadDest @thread_type need to be SINGLE, MULTIPLE, or OVERRIDE?
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
