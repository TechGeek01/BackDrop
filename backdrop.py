import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont
import win32api
import win32file
import shutil
import os
import wmi
import re
import pythoncom
import clipboard
import keyboard
import ctypes
from PIL import Image, ImageTk
import hashlib
import sys
import time
from signal import signal, SIGINT
from datetime import datetime
from bin.fileutils import human_filesize, get_directory_size
from bin.color import Color, bcolor
from bin.threadManager import ThreadManager
from bin.preferences import Preferences
from bin.progress import Progress
from bin.commandLine import CommandLine
from bin.backup import Backup

# Set meta info
appVersion = '2.1.0-beta.1'

# TODO: Add a button in @interface for deleting the @config from @selected_drives

def center(win, centerOnWin=None):
    """Center a tkinter window on screen.

    Args:
        win (tkinter.Tk): The tkinter Tk() object to center.
        centerOnWin (tkinter.Tk): The window to center the child window on.
    """

    win.update_idletasks()
    width = win.winfo_width()
    frm_width = win.winfo_rootx() - win.winfo_x()
    win_width = width + 2 * frm_width
    height = win.winfo_height()
    titlebar_height = win.winfo_rooty() - win.winfo_y()
    win_height = height + titlebar_height + frm_width

    if centerOnWin is not None:
        # Center element provided, so use its position for reference
        root_frm_width = centerOnWin.winfo_rootx() - centerOnWin.winfo_x()
        root_win_width = centerOnWin.winfo_width() + 2 * root_frm_width
        root_titlebar_height = centerOnWin.winfo_rooty() - centerOnWin.winfo_y()
        root_win_height = centerOnWin.winfo_height() + root_titlebar_height + root_frm_width

        x = centerOnWin.winfo_x() + root_win_width // 2 - win_width // 2
        y = centerOnWin.winfo_y() + root_win_height // 2 - win_height // 2
    else:
        # No center element, so center on screen
        x = win.winfo_screenwidth() // 2 - win_width // 2
        y = win.winfo_screenheight() // 2 - win_height // 2

    win.geometry('{}x{}+{}+{}'.format(width, height, x, y))
    win.deiconify()

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

    cmdInfoBlocks = backup.getCmdInfoBlocks()
    cmdInfoBlocks[guiOptions['displayIndex']]['currentFileResult'].configure(text=destFilename, fg=uiColor.NORMAL)
    guiOptions['mode'] = 'copy'

    copied = 0
    while True:
        if threadManager.threadList['Backup']['killFlag']:
            break

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
            guiOptions['mode'] = 'verifysource'
            source_hash = hashlib.blake2b()
            copied = 0
            chunk_size = 2**16
            while chunk := f.read(chunk_size):
                copied += chunk_size
                source_hash.update(chunk)
                callback(copied, file_size, guiOptions)

        with open(destFilename, 'rb') as f:
            guiOptions['mode'] = 'verifydest'
            dest_hash = hashlib.blake2b()
            copied = 0
            chunk_size = 2**16
            while chunk := f.read(chunk_size):
                copied += chunk_size
                dest_hash.update(chunk)
                callback(copied, file_size, guiOptions)

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

    if not config['cliMode']:
        cmdInfoBlocks = backup.getCmdInfoBlocks()
        cmdInfoBlocks[guiOptions['displayIndex']]['currentFileResult'].configure(text=destFilename, fg=uiColor.NORMAL)
    else:
        print(f"Copying {destFilename}")
    guiOptions['mode'] = 'copy'

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
            guiOptions['mode'] = 'verifysource'
            source_hash = hashlib.blake2b()
            copied = 0
            chunk_size = 2**16
            while chunk := f.read(chunk_size):
                copied += chunk_size
                source_hash.update(chunk)
                callback(copied, file_size, guiOptions)

        with open(destFilename, 'rb') as f:
            guiOptions['mode'] = 'verifydest'
            dest_hash = hashlib.blake2b()
            copied = 0
            chunk_size = 2**16
            while chunk := f.read(chunk_size):
                copied += chunk_size
                dest_hash.update(chunk)
                callback(copied, file_size, guiOptions)

        if source_hash.hexdigest() == dest_hash.hexdigest():
            print(f"{bcolor.OKGREEN}Files are identical{bcolor.ENDC}")
        else:
            # TODO: Add in way to gather this data as a list of mis-copied files
            print(f"{bcolor.FAIL}File mismatch{bcolor.ENDC}")
            print(f"    Source: {source_hash.hexdigest()}")
            print(F"    Dest:   {dest_hash.hexdigest()}")

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

    backupTotals = backup.getTotals()

    if copied > total:
        copied = total
    percentCopied = copied / total * 100

    # If display index has been specified, write progress to GUI
    if 'displayIndex' in guiOptions.keys():
        displayIndex = guiOptions['displayIndex']

        cmdInfoBlocks = backup.getCmdInfoBlocks()

        backupTotals['buffer'] = copied

        if guiOptions['mode'] == 'copy':
            # Progress bar position should only be updated on copy, not verify
            backupTotals['progressBar'] = backupTotals['running'] + copied
            if not config['cliMode']:
                progress.set(backupTotals['progressBar'])

                cmdInfoBlocks[displayIndex]['lastOutResult'].configure(text=f"{percentCopied:.2f}% \u27f6 {human_filesize(copied)} of {human_filesize(total)}", fg=uiColor.NORMAL)
            else:
                print(f"{percentCopied:.2f}% => {human_filesize(copied)} of {human_filesize(total)}", end='\r', flush=True)
        elif guiOptions['mode'] == 'verifysource':
            if not config['cliMode']:
                cmdInfoBlocks[displayIndex]['lastOutResult'].configure(text=f"Verifying source \u27f6 {percentCopied:.2f}% \u27f6 {human_filesize(copied)} of {human_filesize(total)}", fg=uiColor.BLUE)
            else:
                print(f"{bcolor.OKCYAN}Verifying source => {percentCopied:.2f}% => {human_filesize(copied)} of {human_filesize(total)}{bcolor.ENDC}", end='\r', flush=True)
        elif guiOptions['mode'] == 'verifydest':
            backupTotals['buffer'] += total
            if not config['cliMode']:
                cmdInfoBlocks[displayIndex]['lastOutResult'].configure(text=f"Verifying destination \u27f6 {percentCopied:.2f}% \u27f6 {human_filesize(copied)} of {human_filesize(total)}", fg=uiColor.BLUE)
            else:
                print(f"{bcolor.OKCYAN}Verifying destination => {percentCopied:.2f}% => {human_filesize(copied)} of {human_filesize(total)}{bcolor.ENDC}", end='\r', flush=True)

    if guiOptions['mode'] == 'copy' and copied >= total:
        backupTotals['running'] += total

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
        except Exception:
            return False
        return True

def displayBackupSummaryChunk(title, payload, reset=False):
    """Display a chunk of a backup analysis summary to the user.

    Args:
        title (String): The heading title of the chunk.
        payload (tuple[]): The chunks of data to display.
        payload tuple[0]: The subject of the data line.
        payload tuple[1]: The data to associate to the subject.
        reset (bool): Whether to clear the summary frame first (default: False).
    """

    if not config['cliMode']:
        if reset:
            for widget in backupSummaryTextFrame.winfo_children():
                widget.destroy()

        tk.Label(backupSummaryTextFrame, text=title, font=(None, 14),
                 wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')
        summaryFrame = tk.Frame(backupSummaryTextFrame)
        summaryFrame.pack(fill='x', expand=True)
        summaryFrame.columnconfigure(2, weight=1)

        for i, item in enumerate(payload):
            if len(item) > 2:
                textColor = uiColor.NORMAL if item[2] else uiColor.FADED
            else:
                textColor = uiColor.NORMAL

            tk.Label(summaryFrame, text=item[0], fg=textColor).grid(row=i, column=0, sticky='w')
            tk.Label(summaryFrame, text='\u27f6', fg=textColor).grid(row=i, column=1, sticky='w')
            wrapFrame = tk.Frame(summaryFrame)
            wrapFrame.grid(row=i, column=2, sticky='ew')
            wrapFrame.update_idletasks()
            tk.Label(summaryFrame, text=item[1], fg=textColor,
                     wraplength=wrapFrame.winfo_width() - 2, justify='left').grid(row=i, column=2, sticky='w')
    else:
        print(f"\n{title}")

        for i, item in enumerate(payload):
            if len(item) > 2 and not item[2]:
                print(f"{bcolor.WARNING}{item[0]} => {item[1]}{bcolor.ENDC}")
            else:
                print(f"{item[0]} => {item[1]}")

# FIXME: Can progress bar and status updating be rolled into the same function?
# QUESTION: Instead of the copy function handling display, can it just set variables, and have the timer handle all the UI stuff?
def updateBackupTimer():
    if not config['cliMode']:
        backupEtaLabel.configure(fg=uiColor.NORMAL)

    # Total is copy, verify source, verify dest, so total data is 3 * total
    totalToBackup = backup.getTotals()['master'] * 3
    backupStartTime = backup.getBackupStartTime()

    while not threadManager.threadList['backupTimer']['killFlag']:
        backupTotals = backup.getTotals()

        runningTime = datetime.now() - backupStartTime
        percentCopied = (backupTotals['running'] + backupTotals['buffer']) / totalToBackup

        if percentCopied > 0:
            remainingTime = runningTime / percentCopied - runningTime
        else:
            remainingTime = '\u221e' if not config['cliMode'] else 'infinite'

        if not config['cliMode']:
            backupEtaLabel.configure(text=f"{str(runningTime).split('.')[0]} elapsed \u27f6 {str(remainingTime).split('.')[0]} remaining")
        else:
            print(f"{str(runningTime).split('.')[0]} elapsed => {str(remainingTime).split('.')[0]} remaining")
        time.sleep(0.25)

    if not threadManager.threadList['Backup']['killFlag']:
        # Backup not killed, so completed successfully
        if not config['cliMode']:
            backupEtaLabel.configure(text=f"Backup completed successfully in {str(datetime.now() - backupStartTime).split('.')[0]}", fg=uiColor.FINISHED)
        else:
            print(f"{bcolor.OKGREEN}Backup completed successfully in {str(datetime.now() - backupStartTime).split('.')[0]}{bcolor.ENDC}")
    else:
        # Backup aborted
        if not config['cliMode']:
            backupEtaLabel.configure(text=f"Backup aborted in {str(datetime.now() - backupStartTime).split('.')[0]}", fg=uiColor.STOPPED)
        else:
            print(f"{bcolor.FAIL}Backup aborted in {str(datetime.now() - backupStartTime).split('.')[0]}{bcolor.ENDC}")

# FIXME: There's definitely a better way to handle working with items in the Backup instance than passing self into this function
def enumerateCommandInfo(self, displayCommandList):
    """Enumerate the display widget with command info after a backup analysis."""
    rightArrow = '\U0001f86a'
    downArrow = '\U0001f86e'

    cmdHeaderFont = (None, 9, 'bold')
    cmdStatusFont = (None, 9)

    def toggleCmdInfo(index):
        """Toggle the command info for a given indexed command.

        Args:
            index (int): The index of the command to expand or hide.
        """

        # Expand only if analysis is not running and the list isn't still being built
        if not self.analysisRunning:
            # Check if arrow needs to be expanded
            expandArrow = self.cmdInfoBlocks[index]['arrow']['text']
            if expandArrow == rightArrow:
                # Collapsed turns into expanded
                self.cmdInfoBlocks[index]['arrow'].configure(text=downArrow)
                self.cmdInfoBlocks[index]['infoFrame'].pack(anchor='w')
            else:
                # Expanded turns into collapsed
                self.cmdInfoBlocks[index]['arrow'].configure(text=rightArrow)
                self.cmdInfoBlocks[index]['infoFrame'].pack_forget()

        # For some reason, .configure() loses the function bind, so we need to re-set this
        self.cmdInfoBlocks[index]['arrow'].bind('<Button-1>', lambda event, index=index: toggleCmdInfo(index))

    def copyList(index, item):
        """Copy a given indexed command to the clipboard.

        Args:
            index (int): The index of the command to copy.
            item (String): The name of the list to copy
        """
        clipboard.copy('\n'.join(self.cmdInfoBlocks[index][item]))

    if not config['cliMode']:
        for widget in backupActivityScrollableFrame.winfo_children():
            widget.destroy()
    else:
        print('')

    self.cmdInfoBlocks = []
    for i, item in enumerate(displayCommandList):
        if item['type'] == 'list':
            cmdHeaderText = 'Delete %d files from %s' % (len(item['fileList']), item['drive'])
        elif item['type'] == 'fileList':
            if item['mode'] == 'replace':
                cmdHeaderText = 'Update %d files on %s' % (len(item['fileList']), item['drive'])
            elif item['mode'] == 'copy':
                cmdHeaderText = 'Copy %d new files to %s' % (len(item['fileList']), item['drive'])

        if not config['cliMode']:
            infoConfig = {}

            infoConfig['mainFrame'] = tk.Frame(backupActivityScrollableFrame)
            infoConfig['mainFrame'].pack(anchor='w', expand=1)

            # Set up header arrow, trimmed command, and status
            infoConfig['headLine'] = tk.Frame(infoConfig['mainFrame'])
            infoConfig['headLine'].pack(fill='x')
            infoConfig['arrow'] = tk.Label(infoConfig['headLine'], text=rightArrow)
            infoConfig['arrow'].pack(side='left')

            if item['type'] == 'list':
                cmdHeaderText = 'Delete %d files from %s' % (len(item['fileList']), item['drive'])
            elif item['type'] == 'fileList':
                if item['mode'] == 'replace':
                    cmdHeaderText = 'Update %d files on %s' % (len(item['fileList']), item['drive'])
                elif item['mode'] == 'copy':
                    cmdHeaderText = 'Copy %d new files to %s' % (len(item['fileList']), item['drive'])

            infoConfig['header'] = tk.Label(infoConfig['headLine'], text=cmdHeaderText, font=cmdHeaderFont, fg=uiColor.NORMAL if item['enabled'] else uiColor.FADED)
            infoConfig['header'].pack(side='left')
            infoConfig['state'] = tk.Label(infoConfig['headLine'], text='Pending' if item['enabled'] else 'Skipped', font=cmdStatusFont, fg=uiColor.PENDING if item['enabled'] else uiColor.FADED)
            infoConfig['state'].pack(side='left')
            infoConfig['arrow'].update_idletasks()
            arrowWidth = infoConfig['arrow'].winfo_width()

            # Set up info frame
            infoConfig['infoFrame'] = tk.Frame(infoConfig['mainFrame'])

            if item['type'] == 'list':
                infoConfig['fileSizeLine'] = tk.Frame(infoConfig['infoFrame'])
                infoConfig['fileSizeLine'].pack(anchor='w')
                tk.Frame(infoConfig['fileSizeLine'], width=arrowWidth).pack(side='left')
                infoConfig['fileSizeLineHeader'] = tk.Label(infoConfig['fileSizeLine'], text='Total size:', font=cmdHeaderFont)
                infoConfig['fileSizeLineHeader'].pack(side='left')
                infoConfig['fileSizeLineTotal'] = tk.Label(infoConfig['fileSizeLine'], text=human_filesize(item['size']), font=cmdStatusFont)
                infoConfig['fileSizeLineTotal'].pack(side='left')

                infoConfig['fileListLine'] = tk.Frame(infoConfig['infoFrame'])
                infoConfig['fileListLine'].pack(anchor='w')
                tk.Frame(infoConfig['fileListLine'], width=arrowWidth).pack(side='left')
                infoConfig['fileListLineHeader'] = tk.Label(infoConfig['fileListLine'], text='File list:', font=cmdHeaderFont)
                infoConfig['fileListLineHeader'].pack(side='left')
                infoConfig['fileListLineTooltip'] = tk.Label(infoConfig['fileListLine'], text='(Click to copy)', font=cmdStatusFont, fg=uiColor.FADED)
                infoConfig['fileListLineTooltip'].pack(side='left')
                infoConfig['fullFileList'] = item['fileList']

                infoConfig['cmdListLine'] = tk.Frame(infoConfig['infoFrame'])
                infoConfig['cmdListLine'].pack(anchor='w')
                tk.Frame(infoConfig['cmdListLine'], width=arrowWidth).pack(side='left')
                infoConfig['cmdListLineHeader'] = tk.Label(infoConfig['cmdListLine'], text='Command list:', font=cmdHeaderFont)
                infoConfig['cmdListLineHeader'].pack(side='left')
                infoConfig['cmdListLineTooltip'] = tk.Label(infoConfig['cmdListLine'], text='(Click to copy)', font=cmdStatusFont, fg=uiColor.FADED)
                infoConfig['cmdListLineTooltip'].pack(side='left')
                infoConfig['fullCmdList'] = item['cmdList']

                infoConfig['lastOutLine'] = tk.Frame(infoConfig['infoFrame'])
                infoConfig['lastOutLine'].pack(anchor='w')
                tk.Frame(infoConfig['lastOutLine'], width=arrowWidth).pack(side='left')
                infoConfig['lastOutHeader'] = tk.Label(infoConfig['lastOutLine'], text='Out:', font=cmdHeaderFont)
                infoConfig['lastOutHeader'].pack(side='left')
                infoConfig['lastOutResult'] = tk.Label(infoConfig['lastOutLine'], text='Pending' if item['enabled'] else 'Skipped', font=cmdStatusFont, fg=uiColor.PENDING if item['enabled'] else uiColor.FADED)
                infoConfig['lastOutResult'].pack(side='left')

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

                infoConfig['fileListLineTrimmed'] = tk.Label(infoConfig['fileListLine'], text=trimmedFileList, font=cmdStatusFont)
                infoConfig['fileListLineTrimmed'].pack(side='left')
                infoConfig['cmdListLineTrimmed'] = tk.Label(infoConfig['cmdListLine'], text=trimmedCmdList, font=cmdStatusFont)
                infoConfig['cmdListLineTrimmed'].pack(side='left')

                # Command copy action click
                infoConfig['fileListLineHeader'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullFileList'))
                infoConfig['fileListLineTooltip'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullFileList'))
                infoConfig['fileListLineTrimmed'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullFileList'))

                infoConfig['cmdListLineHeader'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullCmdList'))
                infoConfig['cmdListLineTooltip'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullCmdList'))
                infoConfig['cmdListLineTrimmed'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullCmdList'))
            elif item['type'] == 'fileList':
                infoConfig['fileSizeLine'] = tk.Frame(infoConfig['infoFrame'])
                infoConfig['fileSizeLine'].pack(anchor='w')
                tk.Frame(infoConfig['fileSizeLine'], width=arrowWidth).pack(side='left')
                infoConfig['fileSizeLineHeader'] = tk.Label(infoConfig['fileSizeLine'], text='Total size:', font=cmdHeaderFont)
                infoConfig['fileSizeLineHeader'].pack(side='left')
                infoConfig['fileSizeLineTotal'] = tk.Label(infoConfig['fileSizeLine'], text=human_filesize(item['size']), font=cmdStatusFont)
                infoConfig['fileSizeLineTotal'].pack(side='left')

                infoConfig['fileListLine'] = tk.Frame(infoConfig['infoFrame'])
                infoConfig['fileListLine'].pack(anchor='w')
                tk.Frame(infoConfig['fileListLine'], width=arrowWidth).pack(side='left')
                infoConfig['fileListLineHeader'] = tk.Label(infoConfig['fileListLine'], text='File list:', font=cmdHeaderFont)
                infoConfig['fileListLineHeader'].pack(side='left')
                infoConfig['fileListLineTooltip'] = tk.Label(infoConfig['fileListLine'], text='(Click to copy)', font=cmdStatusFont, fg=uiColor.FADED)
                infoConfig['fileListLineTooltip'].pack(side='left')
                infoConfig['fullFileList'] = item['fileList']

                infoConfig['currentFileLine'] = tk.Frame(infoConfig['infoFrame'])
                infoConfig['currentFileLine'].pack(anchor='w')
                tk.Frame(infoConfig['currentFileLine'], width=arrowWidth).pack(side='left')
                infoConfig['currentFileHeader'] = tk.Label(infoConfig['currentFileLine'], text='Current file:', font=cmdHeaderFont)
                infoConfig['currentFileHeader'].pack(side='left')
                infoConfig['currentFileResult'] = tk.Label(infoConfig['currentFileLine'], text='Pending' if item['enabled'] else 'Skipped', font=cmdStatusFont, fg=uiColor.PENDING if item['enabled'] else uiColor.FADED)
                infoConfig['currentFileResult'].pack(side='left')

                infoConfig['lastOutLine'] = tk.Frame(infoConfig['infoFrame'])
                infoConfig['lastOutLine'].pack(anchor='w')
                tk.Frame(infoConfig['lastOutLine'], width=arrowWidth).pack(side='left')
                infoConfig['lastOutHeader'] = tk.Label(infoConfig['lastOutLine'], text='Progress:', font=cmdHeaderFont)
                infoConfig['lastOutHeader'].pack(side='left')
                infoConfig['lastOutResult'] = tk.Label(infoConfig['lastOutLine'], text='Pending' if item['enabled'] else 'Skipped', font=cmdStatusFont, fg=uiColor.PENDING if item['enabled'] else uiColor.FADED)
                infoConfig['lastOutResult'].pack(side='left')

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

                infoConfig['fileListLineTrimmed'] = tk.Label(infoConfig['fileListLine'], text=trimmedFileList, font=cmdStatusFont)
                infoConfig['fileListLineTrimmed'].pack(side='left')

                # Command copy action click
                infoConfig['fileListLineHeader'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullFileList'))
                infoConfig['fileListLineTooltip'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullFileList'))
                infoConfig['fileListLineTrimmed'].bind('<Button-1>', lambda event, index=i: copyList(index, 'fullFileList'))

            self.cmdInfoBlocks.append(infoConfig)

            # Header toggle action click
            infoConfig['arrow'].bind('<Button-1>', lambda event, index=i: toggleCmdInfo(index))
            infoConfig['header'].bind('<Button-1>', lambda event, index=i: toggleCmdInfo(index))
        else:
            print(cmdHeaderText)

    if config['cliMode']:
        print('')

# URGENT: Replace CLI mode call for analysis with this function call
def startBackupAnalysis():
    """Start the backup analysis in a separate thread."""

    global backup

    # FIXME: If backup @analysis @thread is already running, it needs to be killed before it's rerun
    # CAVEAT: This requires some way to have the @analysis @thread itself check for the kill flag and break if it's set.
    if (not backup or not backup.isRunning()) and sourceDriveListValid:
        # TODO: There has to be a better way to handle stopping and starting this split mode toggling
        splitEnabled = destModeSplitCheckVar.get()
        splitModeStatus.configure(text='Split mode\n%s' % ('Enabled' if splitEnabled else 'Disabled'), fg=uiColor.ENABLED if splitEnabled else uiColor.DISABLED)

        backup = Backup(
            config=config,
            backupConfigDir=backupConfigDir,
            backupConfigFile=backupConfigFile,
            uiColor=uiColor,
            startBackupBtn=startBackupBtn,
            startAnalysisBtn=startAnalysisBtn,
            doCopyFn=doCopy,
            startBackupFn=startBackup,
            killBackupFn=lambda: threadManager.kill('Backup'),
            startBackupTimerFn=updateBackupTimer,
            analysisSummaryDisplayFn=displayBackupSummaryChunk,
            enumerateCommandInfoFn=enumerateCommandInfo,
            threadManager=threadManager,
            progress=progress
        )
        threadManager.start(threadManager.SINGLE, target=backup.analyze, name='Backup Analysis', daemon=True)

def loadSource():
    """Load the source share list, and display it in the tree."""
    global backup

    progress.startIndeterminate()

    # Empty tree in case this is being refreshed
    sourceTree.delete(*sourceTree.get_children())

    shareSelectedSpace.configure(text='Selected: ' + human_filesize(0))
    shareTotalSpace.configure(text='Total: ~' + human_filesize(0))

    # Enumerate list of shares in source
    for directory in next(os.walk(config['sourceDrive']))[1]:
        sourceTree.insert(parent='', index='end', text=directory, values=('Unknown', 0))

    progress.stopIndeterminate()

def startRefreshSource():
    """Start a source refresh in a new thread."""
    if sourceDriveListValid:
        threadManager.start(threadManager.SINGLE, target=loadSource, name='Load Source', daemon=True)

def changeSourceDrive(selection):
    """Change the source drive to pull shares from to a new selection.

    Args:
        selection (String): The selection to set as the default.
    """
    global config
    config['sourceDrive'] = selection
    preferences.set('sourceDrive', selection)
    startRefreshSource()

# IDEA: @Calculate total space of all @shares in background
prevShareSelection = []
def shareSelectCalc():
    """Calculate and display the filesize of a selected share, if it hasn't been calculated.

    This gets the selection in the source tree, and then calculates the filesize for
    all shares selected that haven't yet been calculated. The summary of total
    selection, and total share space is also shown below the tree.
    """
    global prevShareSelection
    global backup

    progress.startIndeterminate()

    def updateShareSize(item):
        """Update share info for a given share.

        Args:
            item (String): The identifier for a share in the source tree to be calculated.
        """
        shareName = sourceTree.item(item, 'text')
        newShareSize = get_directory_size(config['sourceDrive'] + shareName)
        sourceTree.set(item, 'size', human_filesize(newShareSize))
        sourceTree.set(item, 'rawsize', newShareSize)

        # After calculating share info, update the meta info
        selectedTotal = 0
        selectedShareList = []
        for item in sourceTree.selection():
            # Write selected shares to config
            selectedShareList.append({
                'name': sourceTree.item(item, 'text'),
                'size': int(sourceTree.item(item, 'values')[1])
            })

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

        progress.stopIndeterminate()

    selected = sourceTree.selection()

    # If selection is different than last time, invalidate the analysis
    selectMatch = [share for share in selected if share in prevShareSelection]
    if len(selected) != len(prevShareSelection) or len(selectMatch) != len(prevShareSelection):
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
    global destDriveMasterList

    if not config['cliMode']:
        progress.startIndeterminate()

    driveList = win32api.GetLogicalDriveStrings()
    driveList = driveList.split('\000')[:-1]

    # Associate logical drives with physical drives, and map them to physical serial numbers
    logicalPhysicalMap = {}
    if not config['cliMode']:
        pythoncom.CoInitialize()
    try:
        for physicalDisk in wmi.WMI().Win32_DiskDrive():
            for partition in physicalDisk.associators("Win32_DiskDriveToDiskPartition"):
                logicalPhysicalMap.update({logicalDisk.DeviceID[0]: physicalDisk.SerialNumber.strip() for logicalDisk in partition.associators("Win32_LogicalDiskToPartition")})
    finally:
        if not config['cliMode']:
            pythoncom.CoUninitialize()

    # Empty tree in case this is being refreshed
    if not config['cliMode']:
        destTree.delete(*destTree.get_children())

    # Enumerate drive list to find info about all non-source drives
    totalUsage = 0
    destDriveMasterList = []
    destDriveLetterToInfo = {}
    for drive in driveList:
        if drive != config['sourceDrive']:
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
                destDriveLetterToInfo[drive[0]] = {
                    'vid': vsn,
                    'serial': serial
                }

                driveHasConfigFile = os.path.exists('%s%s/%s' % (drive, backupConfigDir, backupConfigFile)) and os.path.isfile('%s%s/%s' % (drive, backupConfigDir, backupConfigFile))

                totalUsage = totalUsage + driveSize
                if not config['cliMode']:
                    destTree.insert(parent='', index='end', text=drive, values=(human_filesize(driveSize), driveSize, 'Yes' if driveHasConfigFile else '', vsn, serial))

                destDriveMasterList.append({
                    'name': drive,
                    'vid': vsn,
                    'serial': serial,
                    'capacity': driveSize,
                    'hasConfig': driveHasConfigFile
                })

    if not config['cliMode']:
        driveTotalSpace.configure(text='Available: ' + human_filesize(totalUsage))

        progress.stopIndeterminate()

def startRefreshDest():
    """Start the loading of the destination drive info in a new thread."""
    if not threadManager.is_alive('Refresh destination'):
        threadManager.start(threadManager.SINGLE, target=loadDest, name='Refresh destination', daemon=True)

def selectFromConfig():
    """From the current config, select the appropriate shares and drives in the GUI."""
    global driveSelectBind

    # Get list of shares in config
    shareNameList = [item['name'] for item in config['shares']]
    sourceTreeIdList = [item for item in sourceTree.get_children() if sourceTree.item(item, 'text') in shareNameList]

    sourceTree.focus(sourceTreeIdList[-1])
    sourceTree.selection_set(tuple(sourceTreeIdList))

    # Get list of drives where volume ID is in config
    connectedVidList = [drive['vid'] for drive in config['drives']]
    driveTreeIdList = [item for item in destTree.get_children() if destTree.item(item, 'values')[3] in connectedVidList]

    # If drives aren't mounted that should be, display the warning
    missingDriveCount = len(config['missingDrives'])
    if missingDriveCount > 0:
        configMissingVids = [vid for vid in config['missingDrives'].keys()]

        missingVidString = ', '.join(configMissingVids[:-2] + [' and '.join(configMissingVids[-2:])])
        warningMessage = f"The drive{'s' if len(configMissingVids) > 1 else ''} with volume ID{'s' if len(configMissingVids) > 1 else ''} {missingVidString} {'are' if len(configMissingVids) > 1 else 'is'} not available to be selected.\n\nMissing drives may be omitted or replaced, provided the total space on destination drives is equal to, or exceeds the amount of data to back up.\n\nUnless you reset the config or otherwise restart this tool, this is the last time you will be warned."
        warningTitle = f"Drive{'s' if len(configMissingVids) > 1 else ''} missing"

        splitWarningPrefix.configure(text='There %s' % ('is' if missingDriveCount == 1 else 'are'))
        splitWarningSuffix.configure(text='%s in the config that %s connected. Please connect %s, or enable split mode.' % ('drive' if missingDriveCount == 1 else 'drives', 'isn\'t' if missingDriveCount == 1 else 'aren\'t', 'it' if missingDriveCount == 1 else 'them'))
        splitWarningMissingDriveCount.configure(text='%d' % (missingDriveCount))
        destSplitWarningFrame.grid(row=3, column=0, columnspan=2, sticky='nsew', pady=(0, elemPadding), ipady=elemPadding / 4)

        messagebox.showwarning(warningTitle, warningMessage)

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
                newConfig['shares'] = [{
                    'name': share,
                    'size': None
                } for share in splitChunk[0].split(',')]
            elif header == 'drives':
                # Drives is a list, where each line is one drive, and each drive lists
                # comma separated volume ID and physical serial
                newConfig['drives'] = []
                newConfig['missingDrives'] = {}
                driveLookupList = {drive['vid']: drive for drive in destDriveMasterList}
                for drive in splitChunk:
                    driveVid = drive.split(',')[0]

                    if driveVid in driveLookupList:
                        # If drive connected, add it to the config
                        selectedDrive = driveLookupList[driveVid]
                        newConfig['drives'].append(selectedDrive)
                    else:
                        # If drive is missing, add it to the missing drive list
                        newConfig['missingDrives'][driveVid] = int(drive.split(',')[2])

                    configTotal += selectedDrive['capacity']

        config.update(newConfig)
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
    global backup

    progress.startIndeterminate()

    selected = destTree.selection()

    # If selection is different than last time, invalidate the analysis
    selectMatch = [drive for drive in selected if drive in prevDriveSelection]
    if len(selected) != len(prevDriveSelection) or len(selectMatch) != len(prevDriveSelection):
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
    driveLookupList = {drive['vid']: drive for drive in destDriveMasterList}
    for item in selected:
        # Write drive IDs to config
        selectedDrive = driveLookupList[destTree.item(item, 'values')[3]]
        selectedDriveList.append(selectedDrive)
        selectedTotal = selectedTotal + selectedDrive['capacity']

    driveSelectedSpace.configure(text='Selected: ' + human_filesize(selectedTotal))
    if not readDrivesFromConfigFile:
        config['drives'] = selectedDriveList

    progress.stopIndeterminate()

def selectDriveInBackground(event):
    """Start the drive selection handling in a new thread."""
    threadManager.start(threadManager.MULTIPLE, target=handleDriveSelectionClick, name='Drive Select', daemon=True)

backupHalted = False

def startBackup():
    """Start the backup in a new thread."""

    global backup

    if backup:
        def killBackupThread():
            # try:
            #     subprocess.run('taskkill /im robocopy.exe /f', shell=True, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            # except Exception as e:
            #     print(e)
            pass

        threadManager.start(threadManager.KILLABLE, killBackupThread, target=backup.run, name='Backup', daemon=True)

forceNonGracefulCleanup = False
def cleanupHandler(signal_received, frame):
    """Handle cleanup when exiting with Ctrl-C.

    Args:
        signal_received: The signal number received.
        frame: The current stack frame.
    """
    global forceNonGracefulCleanup

    if not forceNonGracefulCleanup:
        print(f"{bcolor.FAIL}SIGINT or Ctrl-C detected. Exiting gracefully...{bcolor.ENDC}")

        if threadManager.is_alive('Backup'):
            threadManager.kill('Backup')

            if threadManager.is_alive('Backup'):
                forceNonGracefulCleanup = True
                print(f"{bcolor.FAIL}Press Ctrl-C again to force stop{bcolor.ENDC}")

            while threadManager.is_alive('Backup'):
                pass

        if threadManager.is_alive('backupTimer'):
            threadManager.kill('backupTimer')
    else:
        print(f"{bcolor.FAIL}SIGINT or Ctrl-C detected. Force closing...{bcolor.ENDC}")

    exit(0)

# Set app defaults
backupConfigDir = '.backdrop'
backupConfigFile = 'backup.config'
appDataFolder = os.getenv('LocalAppData') + '\\BackDrop'
elemPadding = 16

preferences = Preferences(appDataFolder + '\\' + 'preferences.config')

config = {
    'sourceDrive': None,
    'splitMode': False,
    'shares': [],
    'drives': [],
    'missingDrives': {},
    'cliMode': len(sys.argv) > 1
}
destDriveMasterList = []

backup = None
commandList = []

signal(SIGINT, cleanupHandler)

threadManager = ThreadManager()

############
# CLI Mode #
############

if config['cliMode']:
    os.system('')

    commandLine = CommandLine(
        optionInfoList=[
            'Usage: backdrop [options]\n',
            ('-S', '--source', 1, 'The source drive to back up.'),
            ('-s', '--share', 1, 'The shares to back up from the source.'),
            ('-d', '--destination', 1, 'The destination drive to back up to.'),
            '',
            ('-i', '--interactive', 0, 'Run in interactive mode instead of specifying backup configuration.'),
            ('-l', '--loadconfig', 1, 'Load config file from a drive instead of specifying backup configuration.'),
            ('-sp', '--split', 0, 'Run in split mode if not all destination drives are connected.'),
            ('-u', '--unattended', 0, 'Do not prompt for confirmation, and only exit on error.'),
            '',
            ('-h', '--help', 0, 'Display this help menu.'),
            ('-v', '--version', 0, 'Display the program version.')
        ]
    )

    # FIXME: Allow destination and loadconfig to be specified with drive letter or volume ID

    if commandLine.hasParam('help'):
        commandLine.showHelp()
    elif commandLine.hasParam('version'):
        print(f'BackDrop {appVersion}')
    else:
        # Backup config mode
        print(f"\n{bcolor.WARNING}{'CLI mode is a work in progress, and may not be stable or complete': ^{os.get_terminal_size().columns}}{bcolor.ENDC}\n") # TODO: Remove CLI mode stability warning

        ### Sanity check ###
        # TODO: Add interactive mode check here
        # TODO: Add load config mode check here
        # TODO: Add split mode check here
        # TODO: Add unattended mode check here

        if not commandLine.hasParam('source') or len(commandLine.getParam('source')) == 0:
            print('Please specify a source drive')
            exit()
        elif not commandLine.hasParam('destination') or len(commandLine.getParam('destination')) == 0:
            print('Please specify at least one destination drive')
            exit()
        elif not commandLine.hasParam('share') or len(commandLine.getParam('share')) == 0:
            print('Please specify at least one share to back up')
            exit()

        sourceDrive = commandLine.getParam('source')[0][0].upper() + ':\\'
        destList = [drive[0].upper() + ':\\' for drive in commandLine.getParam('destination')]
        shareList = sorted(commandLine.getParam('share'))

        ### Input validation ###

        # Validate drive selection
        driveList = win32api.GetLogicalDriveStrings().split('\000')[:-1]
        remoteDrives = [drive for drive in driveList if win32file.GetDriveType(drive) == 4]

        if len(remoteDrives) <= 0:
            print(f"{bcolor.FAIL}No network drives are available{bcolor.ENDC}")
            exit()

        loadDest()
        if len(destDriveMasterList) <= 0:
            print(f"{bcolor.FAIL}No destination drives are available{bcolor.ENDC}")
            exit()

        if sourceDrive not in remoteDrives:
            print(f"{bcolor.FAIL}Source drive is not valid for selection{bcolor.ENDC}")
            exit()

        destDriveNameList = [drive['name'] for drive in destDriveMasterList]
        for drive in destList:
            if drive not in destDriveNameList:
                print(f"{bcolor.FAIL}One or more destinations are not valid for selection.\nAvailable drives are as follows:{bcolor.ENDC}")

                # TODO: Generalize this into function for table-izing data?
                driveNameList = ['Drive']
                driveSizeList = ['Size']
                driveConfigList = ['Config file']
                driveVidList = ['Volume ID']
                driveSerialList = ['Serial']
                driveNameList.extend([drive['name'] for drive in destDriveMasterList])
                driveSizeList.extend([human_filesize(drive['capacity']) for drive in destDriveMasterList])
                driveConfigList.extend(['Yes' if drive['hasConfig'] else '' for drive in destDriveMasterList])
                driveVidList.extend([drive['vid'] for drive in destDriveMasterList])
                driveSerialList.extend([drive['serial'] for drive in destDriveMasterList])

                driveDisplayLength = {
                    'name': len(max(driveNameList, key=len)),
                    'size': len(max(driveSizeList, key=len)),
                    'config': len(max(driveConfigList, key=len)),
                    'vid': len(max(driveVidList, key=len))
                }

                for i, curDrive in enumerate(driveNameList):
                    print(f"{curDrive: <{driveDisplayLength['name']}}  {driveSizeList[i]: <{driveDisplayLength['size']}}  {driveConfigList[i]: <{driveDisplayLength['config']}}  {driveVidList[i]: <{driveDisplayLength['vid']}}  {driveSerialList[i]}")

                exit()

        sourceShareList = [directory for directory in next(os.walk(sourceDrive))[1]]
        filteredShareInput = [share for share in shareList if share in sourceShareList]
        if len(filteredShareInput) < len(shareList):
            print(f"{bcolor.FAIL}One or more shares are not valid for selection{bcolor.ENDC}")
            exit()

        ### Save config ###

        config['sourceDrive'] = sourceDrive
        config['drives'] = [drive for drive in destDriveMasterList if drive['name'] in destList]
        config['shares'] = [{
            'name': share,
            'size': get_directory_size(sourceDrive + share)
        } for share in shareList]

        ### Show summary ###

        print(f"Source:      {sourceDrive}")
        print(f"Destination: {', '.join(destList)}")
        print(f"Shares:      {', '.join(shareList)}\n")

        ### Confirm ###

        if not commandLine.validateYesNo('Do you want to continue?', True):
            print(f"{bcolor.FAIL}Backup aborted by user{bcolor.ENDC}")
            exit()

        ### Analysis ###

        # FIXME: Find a better way to ignore these options in CLI mode than passing None
        # Could be defaulted to None in the class?
        backup = Backup(
            config=config,
            backupConfigDir=backupConfigDir,
            backupConfigFile=backupConfigFile,
            uiColor=None,
            startBackupBtn=None,
            startAnalysisBtn=None,
            doCopyFn=doCopy,
            startBackupFn=startBackup,
            killBackupFn=lambda: threadManager.kill('Backup'),
            startBackupTimerFn=updateBackupTimer,
            analysisSummaryDisplayFn=displayBackupSummaryChunk,
            enumerateCommandInfoFn=enumerateCommandInfo,
            threadManager=threadManager,
            progress=None
        )
        threadManager.start(threadManager.SINGLE, target=backup.analyze, name='Backup Analysis', daemon=True)

        while threadManager.is_alive('Backup Analysis'):
            pass

        ### Confirm ###

        if not commandLine.validateYesNo('Do you want to continue?', True):
            print(f"{bcolor.FAIL}Backup aborted by user{bcolor.ENDC}")
            exit()

        ### Backup ###

        startBackup()

        while threadManager.is_alive('Backup'):
            pass

        exit()

############
# GUI Mode #
############

if not config['cliMode']:
    os.system('')

    def resource_path(relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)

    root = tk.Tk()
    root.title('BackDrop - Network Drive Backup Tool')
    root.resizable(False, False)
    root.geometry('1300x700')
    root.iconbitmap(resource_path('media\\icon.ico'))
    center(root)

    # Create Color class instance for UI
    uiColor = Color(root, preferences.get('darkMode', False))

    if uiColor.isDarkMode():
        root.tk_setPalette(background=uiColor.BG)

    mainFrame = tk.Frame(root)
    mainFrame.pack(fill='both', expand=1, padx=elemPadding, pady=(elemPadding / 2, elemPadding))

    # Set some default styling
    tkStyle = ttk.Style()
    tkStyle.theme_use('vista')
    tkStyle.configure('TButton', padding=5)
    tkStyle.configure('danger.TButton', padding=5, background='#b00')
    tkStyle.configure('icon.TButton', width=2, height=1, padding=1, font=(None, 15), background='#00bfe6')

    tkStyle.configure('TButton', background=uiColor.BG)
    tkStyle.configure('TCheckbutton', background=uiColor.BG, foreground=uiColor.NORMAL)
    tkStyle.configure('TFrame', background=uiColor.BG, foreground=uiColor.NORMAL)

    tkStyle.element_create('custom.Treeheading.border', 'from', 'default')
    tkStyle.element_create('custom.Treeview.field', 'from', 'clam')
    tkStyle.layout('custom.Treeview.Heading', [
        ('custom.Treeheading.cell', {'sticky': 'nswe'}),
        ('custom.Treeheading.border', {'sticky': 'nswe', 'children': [
            ('custom.Treeheading.padding', {'sticky': 'nswe', 'children': [
                ('custom.Treeheading.image', {'side': 'right', 'sticky': ''}),
                ('custom.Treeheading.text', {'sticky': 'we'})
            ]})
        ]}),
    ])
    tkStyle.layout('custom.Treeview', [
        ('custom.Treeview.field', {'sticky': 'nswe', 'border': '1', 'children': [
            ('custom.Treeview.padding', {'sticky': 'nswe', 'children': [
                ('custom.Treeview.treearea', {'sticky': 'nswe'})
            ]})
        ]})
    ])
    tkStyle.configure('custom.Treeview.Heading', background=uiColor.BGACCENT, foreground=uiColor.FG, padding=2.5)
    tkStyle.configure('custom.Treeview', background=uiColor.BGACCENT2, fieldbackground=uiColor.BGACCENT2, foreground=uiColor.FG, bordercolor=uiColor.BGACCENT3)
    tkStyle.map('custom.Treeview', foreground=[('disabled', 'SystemGrayText'), ('!disabled', '!selected', uiColor.NORMAL), ('selected', uiColor.BLACK)], background=[('disabled', 'SystemButtonFace'), ('!disabled', '!selected', uiColor.BGACCENT2), ('selected', uiColor.COLORACCENT)])

    tkStyle.element_create('custom.Progressbar.trough', 'from', 'clam')
    tkStyle.layout('custom.Progressbar', [
        ('custom.Progressbar.trough', {'sticky': 'nsew', 'children': [
            ('custom.Progressbar.padding', {'sticky': 'nsew', 'children': [
                ('custom.Progressbar.pbar', {'side': 'left', 'sticky': 'ns'})
            ]})
        ]})
    ])
    tkStyle.configure('custom.Progressbar', padding=4, background=uiColor.COLORACCENT, bordercolor=uiColor.BGACCENT3, borderwidth=0, troughcolor=uiColor.BG, lightcolor=uiColor.COLORACCENT, darkcolor=uiColor.COLORACCENT)

    # tkStyle.element_create('custom.Scrollbar.trough', 'from', 'clam')
    # tkStyle.layout('custom.Scrollbar', [
    #     ('custom.Scrollbar.trough', {'sticky': 'ns', 'children': [
    #         ('custom.Scrollbar.uparrow', {'side': 'top', 'sticky': ''}),
    #         ('custom.Scrollbar.downarrow', {'side': 'bottom', 'sticky': ''}),
    #         ('custom.Scrollbar.thumb', {'sticky': 'nswe', 'unit': '1', 'children': [
    #             ('custom.Scrollbar.grip', {'sticky': ''})
    #         ]})
    #     ]})
    # ])
    # tkStyle.configure('custom.Scrollbar', troughcolor=uiColor.BG, background=uiColor.GREEN, arrowcolor=uiColor.GOLD)
    # tkStyle.configure('custom.Scrollbar.uparrow', background=uiColor.BGACCENT, arrowcolor=uiColor.BGACCENT3)
    # tkStyle.configure('custom.Scrollbar.downarrow', background=uiColor.BGACCENT, arrowcolor=uiColor.BGACCENT3)

    # Progress/status values
    progressBar = ttk.Progressbar(mainFrame, maximum=100, style='custom.Progressbar')
    progressBar.grid(row=10, column=0, columnspan=3, sticky='ew', pady=(elemPadding, 0))

    progress = Progress(
        progressBar=progressBar,
        threadsForProgressBar=5
    )

    # Set source drives and start to set up source dropdown
    sourceDriveDefault = tk.StringVar()
    driveList = win32api.GetLogicalDriveStrings().split('\000')[:-1]
    remoteDrives = [drive for drive in driveList if win32file.GetDriveType(drive) == 4]

    sourceDriveListValid = len(remoteDrives) > 0

    if sourceDriveListValid:
        config['sourceDrive'] = preferences.get('sourceDrive', remoteDrives[0], remoteDrives)
        sourceDriveDefault.set(config['sourceDrive'])

        # Tree frames for tree and scrollbar
        sourceTreeFrame = tk.Frame(mainFrame)
        sourceTreeFrame.grid(row=1, column=0, sticky='ns')

        sourceTree = ttk.Treeview(sourceTreeFrame, columns=('size', 'rawsize'), style='custom.Treeview')
        sourceTree.heading('#0', text='Share')
        sourceTree.column('#0', width=200)
        sourceTree.heading('size', text='Size')
        sourceTree.column('size', width=80)
        sourceTree['displaycolumns'] = ('size')

        sourceTree.pack(side='left')
        sourceShareScroll = ttk.Scrollbar(sourceTreeFrame, orient='vertical', command=sourceTree.yview)
        sourceShareScroll.pack(side='left', fill='y')
        sourceTree.configure(yscrollcommand=sourceShareScroll.set)

        # There's an invisible 1px background on buttons. When changing this in icon buttons, it becomes
        # visible, so 1px needs to be added back
        sourceMetaFrame = tk.Frame(mainFrame)
        sourceMetaFrame.grid(row=2, column=0, sticky='nsew', pady=(1, 0))
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
        sourceSelectMenu = ttk.OptionMenu(sourceSelectFrame, sourceDriveDefault, config['sourceDrive'], *tuple(remoteDrives), command=changeSourceDrive)
        sourceSelectMenu.pack(side='left', padx=(12, 0))

        sourceTree.bind("<<TreeviewSelect>>", loadSourceInBackground)
    else:
        sourceDriveDefault.set('No remotes')

        # sourceMissingFrame = tk.Frame(mainFrame, width=200)
        # sourceMissingFrame.grid(row=0, column=0,  rowspan=2, sticky='nsew')
        sourceWarning = tk.Label(mainFrame, text='No network drives are available to use as source', font=(None, 14), wraplength=250, bg=uiColor.ERROR)
        sourceWarning.grid(row=0, column=0, rowspan=3, sticky='nsew', padx=10, pady=10, ipadx=20, ipady=20)

    destTreeFrame = tk.Frame(mainFrame)
    destTreeFrame.grid(row=1, column=1, sticky='ns', padx=(elemPadding, 0))

    destModeFrame = tk.Frame(mainFrame)
    destModeFrame.grid(row=0, column=1, pady=(0, elemPadding / 2))

    def handleSplitModeCheck():
        """Handle toggling of split mode based on checkbox value."""
        config['splitMode'] = destModeSplitCheckVar.get()

        # TODO: Should this reference backup.isRunning() instead?
        if not backup or not backup.isAnalysisStarted():
            splitModeStatus.configure(text='Split mode\n%s' % ('Enabled' if config['splitMode'] else 'Disabled'), fg=uiColor.ENABLED if config['splitMode'] else uiColor.DISABLED)

    destModeSplitCheckVar = tk.BooleanVar()

    altTooltipFrame = tk.Frame(destModeFrame, bg=uiColor.INFO)
    altTooltipFrame.pack(side='left', ipadx=elemPadding / 2, ipady=4)
    tk.Label(altTooltipFrame, text='Hold ALT while selecting a drive to ignore config files', bg=uiColor.INFO, fg=uiColor.BLACK).pack(fill='y', expand=1)

    splitModeCheck = ttk.Checkbutton(destModeFrame, text='Backup using split mode', variable=destModeSplitCheckVar, command=handleSplitModeCheck)
    splitModeCheck.pack(side='left', padx=(12, 0))

    destTree = ttk.Treeview(destTreeFrame, columns=('size', 'rawsize', 'configfile', 'vid', 'serial'), style='custom.Treeview')
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
    destTree.configure(yscrollcommand=driveSelectScroll.set)

    # There's an invisible 1px background on buttons. When changing this in icon buttons, it becomes
    # visible, so 1px needs to be added back
    destMetaFrame = tk.Frame(mainFrame)
    destMetaFrame.grid(row=2, column=1, sticky='nsew', pady=(1, 0))
    tk.Grid.columnconfigure(destMetaFrame, 0, weight=1)

    destSplitWarningFrame = tk.Frame(mainFrame, bg=uiColor.WARNING)
    destSplitWarningFrame.rowconfigure(0, weight=1)
    destSplitWarningFrame.columnconfigure(0, weight=1)
    destSplitWarningFrame.columnconfigure(10, weight=1)

    # TODO: Can this be cleaned up?
    tk.Frame(destSplitWarningFrame).grid(row=0, column=0)
    splitWarningPrefix = tk.Label(destSplitWarningFrame, text='There are', bg=uiColor.WARNING)
    splitWarningPrefix.grid(row=0, column=1, sticky='ns')
    splitWarningMissingDriveCount = tk.Label(destSplitWarningFrame, text='0', bg=uiColor.WARNING, font=(None, 18, 'bold'))
    splitWarningMissingDriveCount.grid(row=0, column=2, sticky='ns')
    splitWarningSuffix = tk.Label(destSplitWarningFrame, text='drives in the config that aren\'t connected. Please connect them, or enable split mode.', bg=uiColor.WARNING)
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
    splitModeStatus = tk.Label(driveSpaceFrame, text='Split mode\n%s' % ('Enabled' if config['splitMode'] else 'Disabled'), fg=uiColor.ENABLED if config['splitMode'] else uiColor.DISABLED)
    splitModeStatus.grid(row=0, column=3, padx=(12, 0))

    refreshDestBtn = ttk.Button(destMetaFrame, text='\u2b6e', command=startRefreshDest, style='icon.TButton')
    refreshDestBtn.grid(row=0, column=1)
    startAnalysisBtn = ttk.Button(destMetaFrame, text='Analyze Backup', command=startBackupAnalysis, state='normal' if sourceDriveListValid else 'disabled')
    startAnalysisBtn.grid(row=0, column=2)

    driveSelectBind = destTree.bind('<<TreeviewSelect>>', selectDriveInBackground)

    # Add backup ETA info frame
    backupActivityEtaFrame = tk.Frame(mainFrame)
    backupActivityEtaFrame.grid(row=4, column=0, columnspan=2, pady=elemPadding / 2)
    backupEtaLabel = tk.Label(backupActivityEtaFrame, text='Please start a backup to show ETA')
    backupEtaLabel.pack()

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

    tk.Grid.columnconfigure(mainFrame, 2, weight=1)

    rightSideFrame = tk.Frame(mainFrame)
    rightSideFrame.grid(row=0, column=2, rowspan=6, sticky='nsew', pady=(elemPadding / 2, 0))

    backupSummaryFrame = tk.Frame(rightSideFrame)
    backupSummaryFrame.pack(fill='both', expand=1, padx=(elemPadding, 0))
    backupSummaryFrame.update()

    brandingFrame = tk.Frame(rightSideFrame)
    brandingFrame.pack()

    logoImageLoad = Image.open(resource_path(f"media\\logo_ui{'_light' if uiColor.isDarkMode() else ''}.png"))
    logoImageRender = ImageTk.PhotoImage(logoImageLoad)
    settingsIconLoad = Image.open(resource_path(f"media\\settings{'_light' if uiColor.isDarkMode() else ''}.png"))
    settingsIconRender = ImageTk.PhotoImage(settingsIconLoad)
    settingsBtn = tk.Button(brandingFrame, image=settingsIconRender, relief='sunken', borderwidth=0, highlightcolor=uiColor.BG, activebackground=uiColor.BG)
    settingsBtn.pack(side='left', padx=(0, 8))
    tk.Label(brandingFrame, image=logoImageRender).pack(side='left')
    tk.Label(brandingFrame, text='v' + appVersion, font=(None, 10), fg=uiColor.FADED).pack(side='left', anchor='s', pady=(0, 12))

    backupTitle = tk.Label(backupSummaryFrame, text='Analysis Summary', font=(None, 20))
    backupTitle.pack()

    # Add placeholder to backup analysis
    backupSummaryTextFrame = tk.Frame(backupSummaryFrame)
    backupSummaryTextFrame.pack(fill='x')
    tk.Label(backupSummaryTextFrame, text='This area will summarize the backup that\'s been configured.',
             wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')
    tk.Label(backupSummaryTextFrame, text='Please start a backup analysis to generate a summary.',
             wraplength=backupSummaryFrame.winfo_width() - 2, justify='left').pack(anchor='w')
    startBackupBtn = ttk.Button(backupSummaryFrame, text='Run Backup', command=startBackup, state='disable')
    startBackupBtn.pack(pady=elemPadding / 2)

    # QUESTION: Does init loadDest @thread_type need to be SINGLE, MULTIPLE, or OVERRIDE?
    threadManager.start(threadManager.SINGLE, target=loadDest, name='Init', daemon=True)

    settingsWin = None

    def showSettings():
        global settingsWin

        if settingsWin is None or not settingsWin.winfo_exists():
            settingsWin = tk.Toplevel(root)
            settingsWin.title('Settings - Backdrop')
            settingsWin.resizable(False, False)
            settingsWin.geometry('450x200')
            settingsWin.iconbitmap(resource_path('media\\icon.ico'))
            center(settingsWin, root)
            settingsWin.transient(root)
            settingsWin.grab_set()
            root.wm_attributes('-disabled', True)

            def onClose():
                settingsWin.destroy()
                root.wm_attributes('-disabled', False)

                ctypes.windll.user32.SetForegroundWindow(root.winfo_id())
                root.focus_set()

            settingsWin.protocol('WM_DELETE_WINDOW', onClose)

            mainFrame = tk.Frame(settingsWin)
            mainFrame.pack(fill='both', expand=True, padx=elemPadding)

            mainFrame.columnconfigure(0, weight=1)
            mainFrame.rowconfigure(0, weight=1)

            darkModeCheckVar = tk.BooleanVar(settingsWin, value=uiColor.isDarkMode())
            darkModeCheck = ttk.Checkbutton(mainFrame, text='Enable dark mode (experimental)', variable=darkModeCheckVar, command=lambda: preferences.set('darkMode', darkModeCheckVar.get()))
            darkModeCheck.grid(row=0, column=0, pady=elemPadding)

            disclaimerFrame = tk.Frame(mainFrame, bg=uiColor.INFO)
            disclaimerFrame.grid(row=1, column=0, ipadx=elemPadding / 2, ipady=4)
            tk.Label(disclaimerFrame, text='Changes are saved immediately, and will take effect on the next restart', bg=uiColor.INFO, fg=uiColor.BLACK).pack(fill='y', expand=True)

            buttonFrame = tk.Frame(mainFrame)
            buttonFrame.grid(row=2, column=0, sticky='ew', pady=elemPadding / 2)
            ttk.Button(buttonFrame, text='OK', command=onClose).pack()

    settingsBtn.configure(command=showSettings)

    def onClose():
        if threadManager.is_alive('Backup'):
            if messagebox.askyesno('Quit?', 'There\'s still a background process running. Are you sure you want to kill it?'):
                threadManager.kill('Backup')
                root.destroy()
        else:
            root.destroy()

    root.protocol('WM_DELETE_WINDOW', onClose)
    root.mainloop()
