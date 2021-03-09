import platform
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont, filedialog
import shutil
import os
import subprocess
import webbrowser
if platform.system() == 'Windows':
    import pythoncom
import hashlib
import sys
import time
import ctypes
from signal import signal, SIGINT
from datetime import datetime

import clipboard
import keyboard
from PIL import Image, ImageTk
import urllib.request
if platform.system() == 'Windows':
    import win32api
    import win32file
    import wmi

from bin.fileutils import human_filesize, get_directory_size
from bin.color import Color, bcolor
from bin.threadmanager import ThreadManager
from bin.config import Config
from bin.progress import Progress
from bin.commandline import CommandLine
from bin.backup import Backup
from bin.update import UpdateHandler
from bin.status import Status

# Platform sanity check
if not platform.system() in ['Windows', 'Linux']:
    print('This operating system is not supported')
    exit()

# Set meta info
APP_VERSION = '3.0.0-rc.1'

# Set constants
SOURCE_MODE_SINGLE = 'single'
SOURCE_MODE_MULTI = 'multiple'
SOURCE_MODE_OPTIONS = [SOURCE_MODE_SINGLE, SOURCE_MODE_MULTI]

DRIVE_TYPE_LOCAL = 3
DRIVE_TYPE_REMOTE = 4
DRIVE_TYPE_RAMDISK = 6

def center(win, center_to_window=None):
    """Center a tkinter window on screen.

    Args:
        win (tkinter.Tk): The tkinter Tk() object to center.
        center_to_window (tkinter.Tk): The window to center the child window on.
    """

    win.update_idletasks()
    WIDTH = win.winfo_width()
    FRAME_WIDTH = win.winfo_rootx() - win.winfo_x()
    WIN_WIDTH = WIDTH + 2 * FRAME_WIDTH
    HEIGHT = win.winfo_height()
    TITLEBAR_HEIGHT = win.winfo_rooty() - win.winfo_y()
    WIN_HEIGHT = HEIGHT + TITLEBAR_HEIGHT + FRAME_WIDTH

    if center_to_window is not None:
        # Center element provided, so use its position for reference
        ROOT_FRAME_WIDTH = center_to_window.winfo_rootx() - center_to_window.winfo_x()
        ROOT_WIN_WIDTH = center_to_window.winfo_width() + 2 * ROOT_FRAME_WIDTH
        ROOT_TITLEBAR_HEIGHT = center_to_window.winfo_rooty() - center_to_window.winfo_y()
        ROOT_WIN_HEIGHT = center_to_window.winfo_height() + ROOT_TITLEBAR_HEIGHT + ROOT_FRAME_WIDTH

        x = center_to_window.winfo_x() + ROOT_WIN_WIDTH // 2 - WIN_WIDTH // 2
        y = center_to_window.winfo_y() + ROOT_WIN_HEIGHT // 2 - WIN_HEIGHT // 2
    else:
        # No center element, so center on screen
        x = win.winfo_screenwidth() // 2 - WIN_WIDTH // 2
        y = win.winfo_screenheight() // 2 - WIN_HEIGHT // 2

    win.geometry('{}x{}+{}+{}'.format(WIDTH, HEIGHT, x, y))
    win.deiconify()

def update_file_detail_lists(list_name, filename):
    """Update the file lists for the detail file view.

    Args:
        list_name (String): The list name to update.
        filename (String): The file path to add to the list.
    """

    if not config['cliMode']:
        file_detail_list[list_name].append({
            'displayName': filename.split('/')[-1],
            'filename': filename
        })

        if list_name == 'delete':
            file_details_pending_delete_counter.configure(text=str(len(file_detail_list['delete'])))
            file_details_pending_delete_counter_total.configure(text=str(len(file_detail_list['delete'])))
        elif list_name == 'copy':
            file_details_pending_copy_counter.configure(text=str(len(file_detail_list['copy'])))
            file_details_pending_copy_counter_total.configure(text=str(len(file_detail_list['copy'])))
        elif list_name in ['deleteSuccess', 'deleteFail', 'success', 'fail']:
            # Remove file from delete list
            file_detail_list_name = 'copy' if list_name in ['success', 'fail'] else 'delete'
            filename_list = [file['filename'] for file in file_detail_list[file_detail_list_name]]
            if filename in filename_list:
                del file_detail_list[file_detail_list_name][filename_list.index(filename)]

            # Update file counter
            if list_name in ['success', 'fail']:
                file_details_pending_copy_counter.configure(text=str(len(file_detail_list[file_detail_list_name])))
            else:
                file_details_pending_delete_counter.configure(text=str(len(file_detail_list[file_detail_list_name])))

            # Update copy list scrollable
            if list_name in ['success', 'deleteSuccess']:
                tk.Label(file_details_copied_scrollable_frame, text=filename.split('/')[-1], fg=uicolor.NORMAL if list_name in ['success', 'fail'] else uicolor.FADED, anchor='w').pack(fill='x', expand=True)

                # HACK: The scroll yview won't see the label instantly after it's packed.
                # Sleeping for a brief time fixes that. This is acceptable as long as it's
                # not run in the main thread, else the UI will hang.
                time.sleep(0.01)
                file_details_copied_info_canvas.yview_moveto(1)
            else:
                tk.Label(file_details_failed_scrollable_frame, text=filename.split('/')[-1], fg=uicolor.NORMAL if list_name in ['success', 'fail'] else uicolor.FADED, anchor='w').pack(fill='x', expand=True)
                time.sleep(0.01)
                file_details_failed_info_canvas.yview_moveto(1)

def do_delete(filename, size, gui_options={}):
    """Delete a file or directory.

    Args:
        filename (String): The file or folder to delete.
        size (int): The size in bytes of the file or folder.
        gui_options (obj): Options to handle GUI interaction (optional).
    """

    if not thread_manager.threadlist['Backup']['killFlag'] and os.path.exists(filename):
        gui_options['mode'] = 'delete'
        gui_options['filename'] = filename.split('/')[-1]

        if os.path.isfile(filename):
            os.remove(filename)
        elif os.path.isdir(filename):
            shutil.rmtree(filename)

        # If file deleted successfully, remove it from the list
        if not os.path.exists(filename):
            display_backup_progress(size, size, gui_options)
            update_file_detail_lists('deleteSuccess', filename)
        else:
            display_backup_progress(size, size, gui_options)
            update_file_detail_lists('deleteFail', filename)

# differs from shutil.COPY_BUFSIZE on platforms != Windows
READINTO_BUFSIZE = 1024 * 1024

def copy_file(source_filename, dest_filename, callback, gui_options={}):
    """Copy a source binary file to a destination.

    Args:
        source_filename (String): The source to copy.
        dest_filename (String): The destination to copy to.
        callback (def): The function to call on progress change.
        gui_options (obj): Options to handle GUI interaction (optional).

    Returns:
        bool: True if file was copied and verified successfully, False otherwise.
    """

    global file_detail_list

    if not config['cliMode']:
        cmd_info_blocks = backup.cmd_info_blocks
        cmd_info_blocks[gui_options['displayIndex']]['currentFileResult'].configure(text=dest_filename, fg=uicolor.NORMAL)
    else:
        print(f"Copying {dest_filename}")
    gui_options['mode'] = 'copy'

    buffer_size = 1024 * 1024

    # Optimize the buffer for small files
    buffer_size = min(buffer_size, os.path.getsize(source_filename))
    if buffer_size == 0:
        buffer_size = 1024

    h = hashlib.blake2b()
    b = bytearray(buffer_size)
    mv = memoryview(b)

    copied = 0
    with open(source_filename, 'rb', buffering=0) as f:
        try:
            file_size = os.stat(f.fileno()).st_size
        except OSError:
            file_size = READINTO_BUFSIZE

        # Make sure destination path exists before copying
        path_stub = dest_filename[0:dest_filename.rindex('/')]
        if not os.path.exists(path_stub):
            os.makedirs(path_stub)

        fdst = open(dest_filename, 'wb')
        try:
            for n in iter(lambda: f.readinto(mv), 0):
                if thread_manager.threadlist['Backup']['killFlag']:
                    break

                fdst.write(mv[:n])
                h.update(mv[:n])

                copied += n
                callback(copied, file_size, gui_options)
        except OSError:
            pass
        fdst.close()

    # If file copied in full, copy meta, and verify
    if copied == file_size:
        shutil.copymode(source_filename, dest_filename)
        shutil.copystat(source_filename, dest_filename)

        dest_hash = hashlib.blake2b()
        dest_b = bytearray(buffer_size)
        dest_mv = memoryview(dest_b)

        with open(dest_filename, 'rb', buffering=0) as f:
            gui_options['mode'] = 'verify'
            copied = 0

            for n in iter(lambda: f.readinto(dest_mv), 0):
                dest_hash.update(dest_mv[:n])

                copied += n
                callback(copied, file_size, gui_options)

        if h.hexdigest() == dest_hash.hexdigest():
            update_file_detail_lists('success', dest_filename)

            if config['cliMode']:
                print(f"{bcolor.OKGREEN}Files are identical{bcolor.ENDC}")
        else:
            # If file wasn't copied successfully, delete it
            if os.path.isfile(dest_filename):
                os.remove(dest_filename)
            elif os.path.isdir(dest_filename):
                shutil.rmtree(dest_filename)

            update_file_detail_lists('fail', dest_filename)

            if config['cliMode']:
                print(f"{bcolor.FAIL}File mismatch{bcolor.ENDC}")
                print(f"    Source: {h.hexdigest()}")
                print(F"    Dest:   {dest_hash.hexdigest()}")

        return h.hexdigest() == dest_hash.hexdigest()
    else:
        # If file wasn't copied successfully, delete it
        if os.path.isfile(dest_filename):
            os.remove(dest_filename)
        elif os.path.isdir(dest_filename):
            shutil.rmtree(dest_filename)

        return False

def display_backup_progress(copied, total, gui_options):
    """Display the copy progress of a transfer

    Args:
        copied (int): the number of bytes copied.
        total (int): The total file size.
        gui_options (obj): The options for updating the GUI.
    """

    backup_totals = backup.totals

    if copied > total:
        copied = total

    if total > 0:
        percent_copied = copied / total * 100
    else:
        percent_copied = 100

    # If display index has been specified, write progress to GUI
    # URGENT: Refactor display_backup_progress so calculations are done separate from progress displaying
    if 'displayIndex' in gui_options.keys():
        display_index = gui_options['displayIndex']

        cmd_info_blocks = backup.cmd_info_blocks

        backup_totals['buffer'] = copied
        backup_totals['progressBar'] = backup_totals['running'] + copied

        if gui_options['mode'] == 'delete':
            if not config['cliMode']:
                progress.set(backup_totals['progressBar'])

                cmd_info_blocks[display_index]['lastOutResult'].configure(text=f"Deleted {gui_options['filename']}", fg=uicolor.NORMAL)
            else:
                print(f"Deleted {gui_options['filename']}")
        elif gui_options['mode'] == 'copy':
            if not config['cliMode']:
                progress.set(backup_totals['progressBar'])

                cmd_info_blocks[display_index]['lastOutResult'].configure(text=f"{percent_copied:.2f}% \u27f6 {human_filesize(copied)} of {human_filesize(total)}", fg=uicolor.NORMAL)
            else:
                print(f"{percent_copied:.2f}% => {human_filesize(copied)} of {human_filesize(total)}", end='\r', flush=True)
        elif gui_options['mode'] == 'verify':
            if not config['cliMode']:
                progress.set(backup_totals['progressBar'])

                cmd_info_blocks[display_index]['lastOutResult'].configure(text=f"Verifying \u27f6 {percent_copied:.2f}% \u27f6 {human_filesize(copied)} of {human_filesize(total)}", fg=uicolor.BLUE)
            else:
                print(f"{bcolor.OKCYAN}Verifying => {percent_copied:.2f}% => {human_filesize(copied)} of {human_filesize(total)}{bcolor.ENDC}", end='\r', flush=True)

    if copied >= total:
        backup_totals['running'] += backup_totals['buffer']

def do_copy(src, dest, gui_options={}):
    """Copy a source to a destination.

    Args:
        src (String): The source to copy.
        dest (String): The destination to copy to.
        gui_options (obj): Options to handle GUI interaction (optional).
    """

    if os.path.isfile(src):
        if not thread_manager.threadlist['Backup']['killFlag']:
            copy_file(src, dest, display_backup_progress, gui_options)
    elif os.path.isdir(src):
        # Make dir if it doesn't exist
        if not os.path.exists(dest):
            os.makedirs(dest)

        try:
            for entry in os.scandir(src):
                if thread_manager.threadlist['Backup']['killFlag']:
                    break

                filename = entry.path.split('/')[-1]
                if entry.is_file():
                    copy_file(src + '/' + filename, dest + '/' + filename, display_backup_progress, gui_options)
                elif entry.is_dir():
                    do_copy(src + '/' + filename, dest + '/' + filename)

            # Handle changing attributes of folders if we copy a new folder
            shutil.copymode(src, dest)
            shutil.copystat(src, dest)
        except Exception:
            return False
        return True

def display_backup_summary_chunk(title, payload, reset=False):
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
            for widget in backup_summary_text_frame.winfo_children():
                widget.destroy()

        tk.Label(backup_summary_text_frame, text=title, font=(None, 14),
                 wraplength=backup_summary_frame.winfo_width() - 2, justify='left').pack(anchor='w')
        summary_frame = tk.Frame(backup_summary_text_frame)
        summary_frame.pack(fill='x', expand=True)
        summary_frame.columnconfigure(2, weight=1)

        for i, item in enumerate(payload):
            if len(item) > 2:
                text_color = uicolor.NORMAL if item[2] else uicolor.FADED
            else:
                text_color = uicolor.NORMAL

            tk.Label(summary_frame, text=item[0], fg=text_color).grid(row=i, column=0, sticky='w')
            tk.Label(summary_frame, text='\u27f6', fg=text_color).grid(row=i, column=1, sticky='w')
            wrap_frame = tk.Frame(summary_frame)
            wrap_frame.grid(row=i, column=2, sticky='ew')
            wrap_frame.update_idletasks()
            tk.Label(summary_frame, text=item[1], fg=text_color,
                     wraplength=wrap_frame.winfo_width() - 2, justify='left').grid(row=i, column=2, sticky='w')
    else:
        print(f"\n{title}")

        for i, item in enumerate(payload):
            if len(item) > 2 and not item[2]:
                print(f"{bcolor.WARNING}{item[0]} => {item[1]}{bcolor.ENDC}")
            else:
                print(f"{item[0]} => {item[1]}")

# FIXME: Can progress bar and status updating be rolled into the same function?
# QUESTION: Instead of the copy function handling display, can it just set variables, and have the timer handle all the UI stuff?
def update_backup_eta_timer():
    """Update the backup timer to show ETA."""

    if not config['cliMode']:
        backup_eta_label.configure(fg=uicolor.NORMAL)

    # Total is copy source, verify dest, so total data is 2 * copy
    total_to_copy = backup.totals['master'] - backup.totals['delete']
    backup_start_time = backup.get_backup_start_time()

    while not thread_manager.threadlist['backupTimer']['killFlag']:
        backup_totals = backup.totals

        running_time = datetime.now() - backup_start_time
        percent_copied = (backup_totals['running'] + backup_totals['buffer'] - backup_totals['delete']) / total_to_copy

        if percent_copied > 0:
            remaining_time = running_time / percent_copied - running_time
        else:
            # Show infinity symbol if no calculated ETA
            remaining_time = '\u221e' if not config['cliMode'] else 'infinite'

        if not config['cliMode']:
            backup_eta_label.configure(text=f"{str(running_time).split('.')[0]} elapsed \u27f6 {str(remaining_time).split('.')[0]} remaining")
        else:
            print(f"{str(running_time).split('.')[0]} elapsed => {str(remaining_time).split('.')[0]} remaining")
        time.sleep(0.25)

    if not thread_manager.threadlist['Backup']['killFlag']:
        # Backup not killed, so completed successfully
        if not config['cliMode']:
            backup_eta_label.configure(text=f"Backup completed successfully in {str(datetime.now() - backup_start_time).split('.')[0]}", fg=uicolor.FINISHED)
        else:
            print(f"{bcolor.OKGREEN}Backup completed successfully in {str(datetime.now() - backup_start_time).split('.')[0]}{bcolor.ENDC}")
    else:
        # Backup aborted
        if not config['cliMode']:
            backup_eta_label.configure(text=f"Backup aborted in {str(datetime.now() - backup_start_time).split('.')[0]}", fg=uicolor.STOPPED)
        else:
            print(f"{bcolor.FAIL}Backup aborted in {str(datetime.now() - backup_start_time).split('.')[0]}{bcolor.ENDC}")

# FIXME: There's definitely a better way to handle working with items in the Backup instance than passing self into this function
def display_backup_command_info(self, display_command_list):
    """Enumerate the display widget with command info after a backup analysis."""

    CMD_INFO_HEADER_FONT = (None, 9, 'bold')
    CMD_INFO_STATUS_FONT = (None, 9)

    def handle_expand_toggle_click(index):
        """Toggle the command info for a given indexed command.

        Args:
            index (int): The index of the command to expand or hide.
        """

        # Expand only if analysis is not running and the list isn't still being built
        if not self.analysis_running:
            # Check if arrow needs to be expanded
            if not self.cmd_info_blocks[index]['is_expanded']:
                # Collapsed turns into expanded
                self.cmd_info_blocks[index]['is_expanded'] = True
                self.cmd_info_blocks[index]['arrow'].configure(image=down_nav_arrow)
                self.cmd_info_blocks[index]['infoFrame'].grid(row=1, column=1, sticky='w')
            else:
                # Expanded turns into collapsed
                self.cmd_info_blocks[index]['is_expanded'] = False
                self.cmd_info_blocks[index]['arrow'].configure(image=right_nav_arrow)
                self.cmd_info_blocks[index]['infoFrame'].grid_forget()

        # For some reason, .configure() loses the function bind, so we need to re-set this
        self.cmd_info_blocks[index]['arrow'].bind('<Button-1>', lambda event, index=index: handle_expand_toggle_click(index))

    def copy_chunk_list_to_clipboard(index, item):
        """Copy a given indexed command to the clipboard.

        Args:
            index (int): The index of the command to copy.
            item (String): The name of the list to copy
        """

        clipboard.copy('\n'.join(self.cmd_info_blocks[index][item]))

    if not config['cliMode']:
        for widget in backup_activity_scrollable_frame.winfo_children():
            widget.destroy()
    else:
        print('')

    self.cmd_info_blocks = []
    for i, item in enumerate(display_command_list):
        if item['type'] == 'fileList':
            if item['mode'] == 'delete':
                cmd_header_text = f"Delete {len(item['fileList'])} files from {item['drive']}"
            elif item['mode'] == 'replace':
                cmd_header_text = f"Update {len(item['fileList'])} files on {item['drive']}"
            elif item['mode'] == 'copy':
                cmd_header_text = f"Copy {len(item['fileList'])} new files to {item['drive']}"
            else:
                cmd_header_text = f"Work with {len(item['fileList'])} files on {item['drive']}"

        if not config['cliMode']:
            backup_summary_block = {}

            backup_summary_block['mainFrame'] = tk.Frame(backup_activity_scrollable_frame)
            backup_summary_block['mainFrame'].pack(anchor='w', expand=1)
            backup_summary_block['mainFrame'].grid_columnconfigure(1, weight=1)

            # Set up header arrow, trimmed command, and status
            backup_summary_block['is_expanded'] = False
            backup_summary_block['arrow'] = tk.Label(backup_summary_block['mainFrame'], image=right_nav_arrow)
            backup_summary_block['arrow'].grid(row=0, column=0)
            backup_summary_block['headLine'] = tk.Frame(backup_summary_block['mainFrame'])
            backup_summary_block['headLine'].grid(row=0, column=1, sticky='w')

            backup_summary_block['header'] = tk.Label(backup_summary_block['headLine'], text=cmd_header_text, font=CMD_INFO_HEADER_FONT, fg=uicolor.NORMAL if item['enabled'] else uicolor.FADED)
            backup_summary_block['header'].pack(side='left')
            backup_summary_block['state'] = tk.Label(backup_summary_block['headLine'], text='Pending' if item['enabled'] else 'Skipped', font=CMD_INFO_STATUS_FONT, fg=uicolor.PENDING if item['enabled'] else uicolor.FADED)
            backup_summary_block['state'].pack(side='left')

            # Set up info frame
            backup_summary_block['infoFrame'] = tk.Frame(backup_summary_block['mainFrame'])

            if item['type'] == 'fileList':
                backup_summary_block['fileSizeLine'] = tk.Frame(backup_summary_block['infoFrame'])
                backup_summary_block['fileSizeLine'].pack(anchor='w')
                backup_summary_block['fileSizeLineHeader'] = tk.Label(backup_summary_block['fileSizeLine'], text='Total size:', font=CMD_INFO_HEADER_FONT)
                backup_summary_block['fileSizeLineHeader'].pack(side='left')
                backup_summary_block['fileSizeLineTotal'] = tk.Label(backup_summary_block['fileSizeLine'], text=human_filesize(item['size']), font=CMD_INFO_STATUS_FONT)
                backup_summary_block['fileSizeLineTotal'].pack(side='left')

                backup_summary_block['fileListLine'] = tk.Frame(backup_summary_block['infoFrame'])
                backup_summary_block['fileListLine'].pack(anchor='w')
                backup_summary_block['fileListLineHeader'] = tk.Label(backup_summary_block['fileListLine'], text='File list:', font=CMD_INFO_HEADER_FONT)
                backup_summary_block['fileListLineHeader'].pack(side='left')
                backup_summary_block['fileListLineTooltip'] = tk.Label(backup_summary_block['fileListLine'], text='(Click to copy)', font=CMD_INFO_STATUS_FONT, fg=uicolor.FADED)
                backup_summary_block['fileListLineTooltip'].pack(side='left')
                backup_summary_block['fullFileList'] = item['fileList']

                backup_summary_block['currentFileLine'] = tk.Frame(backup_summary_block['infoFrame'])
                backup_summary_block['currentFileLine'].pack(anchor='w')
                backup_summary_block['currentFileHeader'] = tk.Label(backup_summary_block['currentFileLine'], text='Current file:', font=CMD_INFO_HEADER_FONT)
                backup_summary_block['currentFileHeader'].pack(side='left')
                backup_summary_block['currentFileResult'] = tk.Label(backup_summary_block['currentFileLine'], text='Pending' if item['enabled'] else 'Skipped', font=CMD_INFO_STATUS_FONT, fg=uicolor.PENDING if item['enabled'] else uicolor.FADED)
                backup_summary_block['currentFileResult'].pack(side='left')

                backup_summary_block['lastOutLine'] = tk.Frame(backup_summary_block['infoFrame'])
                backup_summary_block['lastOutLine'].pack(anchor='w')
                backup_summary_block['lastOutHeader'] = tk.Label(backup_summary_block['lastOutLine'], text='Progress:', font=CMD_INFO_HEADER_FONT)
                backup_summary_block['lastOutHeader'].pack(side='left')
                backup_summary_block['lastOutResult'] = tk.Label(backup_summary_block['lastOutLine'], text='Pending' if item['enabled'] else 'Skipped', font=CMD_INFO_STATUS_FONT, fg=uicolor.PENDING if item['enabled'] else uicolor.FADED)
                backup_summary_block['lastOutResult'].pack(side='left')

                # Handle list trimming
                list_font = tkfont.Font(family=None, size=10, weight='normal')
                trimmed_file_list = ', '.join(item['fileList'])[:500]
                MAX_WIDTH = backup_activity_info_canvas.winfo_width() * 0.8
                actual_file_witdth = list_font.measure(trimmed_file_list)

                if actual_file_witdth > MAX_WIDTH:
                    while actual_file_witdth > MAX_WIDTH and len(trimmed_file_list) > 1:
                        trimmed_file_list = trimmed_file_list[:-1]
                        actual_file_witdth = list_font.measure(trimmed_file_list + '...')
                    trimmed_file_list = trimmed_file_list + '...'

                backup_summary_block['fileListLineTrimmed'] = tk.Label(backup_summary_block['fileListLine'], text=trimmed_file_list, font=CMD_INFO_STATUS_FONT)
                backup_summary_block['fileListLineTrimmed'].pack(side='left')

                # Command copy action click
                backup_summary_block['fileListLineHeader'].bind('<Button-1>', lambda event, index=i: copy_chunk_list_to_clipboard(index, 'fullFileList'))
                backup_summary_block['fileListLineTooltip'].bind('<Button-1>', lambda event, index=i: copy_chunk_list_to_clipboard(index, 'fullFileList'))
                backup_summary_block['fileListLineTrimmed'].bind('<Button-1>', lambda event, index=i: copy_chunk_list_to_clipboard(index, 'fullFileList'))

            self.cmd_info_blocks.append(backup_summary_block)

            # Header toggle action click
            backup_summary_block['arrow'].bind('<Button-1>', lambda event, index=i: handle_expand_toggle_click(index))
            backup_summary_block['header'].bind('<Button-1>', lambda event, index=i: handle_expand_toggle_click(index))
        else:
            print(cmd_header_text)

    if config['cliMode']:
        print('')

def reset_ui():
    """Reset the UI when we run a backup analysis."""

    if not config['cliMode']:
        # Empty backup summary pane
        for child in backup_summary_text_frame.winfo_children():
            child.destroy()

        # Reset ETA counter
        backup_eta_label.configure(text='Analysis in progress. Please wait...', fg=uicolor.NORMAL)

        # Empty backup operation list pane
        for child in backup_activity_scrollable_frame.winfo_children():
            child.destroy()

        # Clear file lists for file details pane
        [file_detail_list[list_name].clear() for list_name in file_detail_list.keys()]

        # Reset file details counters
        file_details_pending_delete_counter.configure(text='0')
        file_details_pending_delete_counter_total.configure(text='0')
        file_details_pending_copy_counter.configure(text='0')
        file_details_pending_copy_counter_total.configure(text='0')

        # Empty file details list panes
        for child in file_details_copied_scrollable_frame.winfo_children():
            child.destroy()
        for child in file_details_failed_scrollable_frame.winfo_children():
            child.destroy()

def start_backup_analysis():
    """Start the backup analysis in a separate thread."""

    global backup

    # FIXME: If backup @analysis @thread is already running, it needs to be killed before it's rerun
    # CAVEAT: This requires some way to have the @analysis @thread itself check for the kill flag and break if it's set.
    if (not backup or not backup.is_running()) and (config['cliMode'] or source_drive_list_valid):
        # TODO: There has to be a better way to handle stopping and starting this split mode toggling
        if not config['cliMode']:
            split_mode_enabled = dest_mode_split_check_var.get()
            split_mode_text = 'Enabled' if split_mode_enabled else 'Disabled'
            split_mode_color = uicolor.ENABLED if split_mode_enabled else uicolor.DISABLED
            split_mode_status.configure(text=f"Split mode\n{split_mode_text}", fg=split_mode_color)

        reset_ui()

        if not config['cliMode']:
            backup = Backup(
                config=config,
                backup_config_dir=BACKUP_CONFIG_DIR,
                backup_config_file=BACKUP_CONFIG_FILE,
                uicolor=uicolor,
                do_copy_fn=do_copy,
                do_del_fn=do_delete,
                start_backup_timer_fn=update_backup_eta_timer,
                update_ui_component_fn=update_ui_component,
                update_file_detail_list_fn=update_file_detail_lists,
                analysis_summary_display_fn=display_backup_summary_chunk,
                display_backup_command_info_fn=display_backup_command_info,
                thread_manager=thread_manager,
                progress=progress
            )
        else:
            backup = Backup(
                config=config,
                backup_config_dir=BACKUP_CONFIG_DIR,
                backup_config_file=BACKUP_CONFIG_FILE,
                do_copy_fn=do_copy,
                do_del_fn=do_delete,
                start_backup_timer_fn=update_backup_eta_timer,
                update_file_detail_list_fn=update_file_detail_lists,
                analysis_summary_display_fn=display_backup_summary_chunk,
                display_backup_command_info_fn=display_backup_command_info,
                thread_manager=thread_manager
            )
        thread_manager.start(thread_manager.KILLABLE, target=backup.analyze, name='Backup Analysis', daemon=True)

def load_source():
    """Load the source drive and share lists, and display shares in the tree."""

    global source_avail_drive_list

    if not config['cliMode']:
        progress.start_indeterminate()

        # Empty tree in case this is being refreshed
        tree_source.delete(*tree_source.get_children())

    if platform.system() == 'Windows':
        drive_list = win32api.GetLogicalDriveStrings().split('\000')[:-1]
        drive_type_list = []
        if prefs.get('selection', 'source_network_drives', data_type=Config.BOOLEAN):
            drive_type_list.append(DRIVE_TYPE_REMOTE)
        if prefs.get('selection', 'source_local_drives', data_type=Config.BOOLEAN):
            drive_type_list.append(DRIVE_TYPE_LOCAL)
        source_avail_drive_list = [drive[:2] for drive in drive_list if win32file.GetDriveType(drive) in drive_type_list and drive[:2] != SYSTEM_DRIVE]
        drive_list = [drive[:2] for drive in drive_list]
    elif platform.system() == 'Linux':
        local_selected = settings_showDrives_source_local.get()
        network_selected = settings_showDrives_source_network.get()

        if network_selected and not local_selected:
            cmd = 'df -tcifs -tnfs --output=target'
        elif local_selected and not network_selected:
            cmd = 'df -xtmpfs -xsquashfs -xdevtmpfs -xcifs -xnfs --output=target'
        elif local_selected and network_selected:
            cmd = 'df -xtmpfs -xsquashfs -xdevtmpfs --output=target'

        out = subprocess.run(cmd, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
        logical_drive_list = out.stdout.decode('utf-8').split('\n')[1:]
        logical_drive_list = [mount for mount in logical_drive_list if mount]

        # Filter system drive out from available selection
        source_avail_drive_list = []
        for drive in logical_drive_list:
            drive_name = f'"{drive}"'

            out = subprocess.run("mount | grep " + drive_name + " | awk 'NR==1{print $1}' | sed 's/[0-9]*//g'", stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
            physical_disk = out.stdout.decode('utf-8').split('\n')[0].strip()

            # Only process mount point if it's not on the system drive
            if physical_disk != SYSTEM_DRIVE and drive != '/':
                source_avail_drive_list.append(drive)

    source_drive_list_valid = len(source_avail_drive_list) > 0

    if source_drive_list_valid:
        config['sourceDrive'] = prefs.get('selection', 'sourceDrive', source_avail_drive_list[0], verify_data=source_avail_drive_list)

        if not config['cliMode']:
            source_drive_default.set(config['sourceDrive'])
            source_select_menu.set_menu(config['sourceDrive'], *tuple(source_avail_drive_list))

            source_warning.grid_forget()
            tree_source_frame.grid(row=1, column=1, sticky='ns')
            source_meta_frame.grid(row=2, column=1, sticky='nsew', pady=(WINDOW_ELEMENT_PADDING / 2, 0))
            source_select_frame.grid(row=0, column=1, pady=(0, WINDOW_ELEMENT_PADDING / 2))
    elif not config['cliMode']:
        source_drive_default.set('No remotes')

        tree_source_frame.grid_forget()
        source_meta_frame.grid_forget()
        source_select_frame.grid_forget()
        source_warning.grid(row=0, column=1, rowspan=3, sticky='nsew', padx=10, pady=10, ipadx=20, ipady=20)

    if not config['cliMode']:
        share_selected_space.configure(text='Selected: ' + human_filesize(0))
        share_total_space.configure(text='Total: ~' + human_filesize(0))

        # Enumerate list of shares in source
        for directory in next(os.walk(config['sourceDrive']))[1]:
            tree_source.insert(parent='', index='end', text=directory, values=('Unknown', 0))

        progress.stop_indeterminate()

def load_source_in_background():
    """Start a source refresh in a new thread."""

    thread_manager.start(thread_manager.SINGLE, is_progress_thread=True, target=load_source, name='Load Source', daemon=True)

def change_source_drive(selection):
    """Change the source drive to pull shares from to a new selection.

    Args:
        selection (String): The selection to set as the default.
    """

    global config

    config['sourceDrive'] = selection
    prefs.set('selection', 'sourceDrive', selection)

    load_source_in_background()

# IDEA: @Calculate total space of all @shares in background
prev_share_selection = []
def calculate_selected_shares():
    """Calculate and display the filesize of a selected share, if it hasn't been calculated.

    This gets the selection in the source tree, and then calculates the filesize for
    all shares selected that haven't yet been calculated. The summary of total
    selection, and total share space is also shown below the tree.
    """

    global prev_share_selection
    global backup

    progress.start_indeterminate()

    def update_share_size(item):
        """Update share info for a given share.

        Args:
            item (String): The identifier for a share in the source tree to be calculated.
        """

        # FIXME: This crashes if you change the source drive, and the number of items in the tree changes while it's calculating things
        share_name = tree_source.item(item, 'text')

        if platform.system() == 'Windows':
            share_path = config['sourceDrive'] + share_name
        elif platform.system() == 'Linux':
            share_path = config['sourceDrive'] + DIR_SLASH + share_name

        share_dir_size = get_directory_size(share_path)
        tree_source.set(item, 'size', human_filesize(share_dir_size))
        tree_source.set(item, 'rawsize', share_dir_size)

        # After calculating share info, update the meta info
        selected_total = 0
        selected_share_list = []
        for item in tree_source.selection():
            # Write selected shares to config
            selected_share_list.append({
                'name': tree_source.item(item, 'text'),
                'size': int(tree_source.item(item, 'values')[1])
            })

            # Add total space of selection
            if tree_source.item(item, 'values')[0] != 'Unknown':
                # Add total space of selection
                share_size = tree_source.item(item, 'values')[1]
                selected_total = selected_total + int(share_size)

        share_selected_space.configure(text='Selected: ' + human_filesize(selected_total))
        config['shares'] = selected_share_list

        share_total = 0
        is_total_approximate = False
        total_prefix = 'Total: '
        for item in tree_source.get_children():
            share_total += int(tree_source.item(item, 'values')[1])

            # If total is not yet approximate, check if the item hasn't been calculated
            if not is_total_approximate and tree_source.item(item, 'values')[0] == 'Unknown':
                is_total_approximate = True
                total_prefix += '~'

        share_total_space.configure(text=total_prefix + human_filesize(share_total))

        # If everything's calculated, enable analysis button to be clicked
        all_shares_known = True
        for item in tree_source.selection():
            if tree_source.item(item, 'values')[0] == 'Unknown':
                all_shares_known = False
        if all_shares_known:
            start_analysis_btn.configure(state='normal')
            update_status_bar_selection()

        progress.stop_indeterminate()

    selected = tree_source.selection()

    config['shares'] = [{
        'name': tree_source.item(item, 'text'),
        'size': int(tree_source.item(item, 'values')[1]) if tree_source.item(item, 'values')[0] != 'Unknown' else None
    } for item in tree_source.selection()]
    update_status_bar_selection()

    # If selection is different than last time, invalidate the analysis
    selection_unchanged_items = [share for share in selected if share in prev_share_selection]
    if len(selected) != len(prev_share_selection) or len(selection_unchanged_items) != len(prev_share_selection):
        start_backup_btn.configure(state='disable')

    prev_share_selection = [share for share in selected]

    # Check if items in selection need to be calculated
    for item in selected:
        # If new selected item hasn't been calculated, calculate it on the fly
        if tree_source.item(item, 'values')[0] == 'Unknown':
            update_status_bar_selection(Status.BACKUPSELECT_CALCULATING_SOURCE)
            start_analysis_btn.configure(state='disable')
            share_name = tree_source.item(item, 'text')
            thread_manager.start(thread_manager.SINGLE, is_progress_thread=True, target=lambda: update_share_size(item), name=f"shareCalc_{share_name}", daemon=True)

def calculate_source_size_in_background(event):
    """Start a calculation of source filesize in a new thread."""

    thread_manager.start(thread_manager.MULTIPLE, is_progress_thread=True, target=calculate_selected_shares, name='Load Source Selection', daemon=True)

def load_dest():
    """Load the destination drive info, and display it in the tree."""

    global dest_drive_master_list

    if not config['cliMode']:
        progress.start_indeterminate()

    # Empty tree in case this is being refreshed
    if not config['cliMode']:
        tree_dest.delete(*tree_dest.get_children())

    if platform.system() == 'Windows':
        logical_drive_list = win32api.GetLogicalDriveStrings().split('\000')[:-1]
        logical_drive_list = [drive[:2] for drive in logical_drive_list]

        # Associate logical drives with physical drives, and map them to physical serial numbers
        logical_to_physical_map = {}
        if not config['cliMode']:
            pythoncom.CoInitialize()
        try:
            for physical_disk in wmi.WMI().Win32_DiskDrive():
                for partition in physical_disk.associators("Win32_DiskDriveToDiskPartition"):
                    logical_to_physical_map.update({logical_disk.DeviceID[0]: physical_disk.SerialNumber.strip() for logical_disk in partition.associators("Win32_LogicalDiskToPartition")})
        finally:
            if not config['cliMode']:
                pythoncom.CoUninitialize()

        # Enumerate drive list to find info about all non-source drives
        total_drive_space_available = 0
        dest_drive_master_list = []
        for drive in logical_drive_list:
            if drive != config['sourceDrive'] and drive != SYSTEM_DRIVE:
                drive_type = win32file.GetDriveType(drive)
                if ((prefs.get('selection', 'destination_local_drives', data_type=Config.BOOLEAN) and drive_type == DRIVE_TYPE_LOCAL)  # Drive is LOCAL
                        or (prefs.get('selection', 'destination_network_drives', data_type=Config.BOOLEAN) and drive_type == DRIVE_TYPE_REMOTE)):  # Drive is REMOTE
                    try:
                        drive_size = shutil.disk_usage(drive).total
                        vsn = os.stat(drive).st_dev
                        vsn = '{:04X}-{:04X}'.format(vsn >> 16, vsn & 0xffff)
                        try:
                            serial = logical_to_physical_map[drive[0]]
                        except KeyError:
                            serial = 'Not Found'

                        drive_has_config_file = os.path.exists(f"{drive}{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}") and os.path.isfile(f"{drive}{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}")

                        total_drive_space_available = total_drive_space_available + drive_size
                        if not config['cliMode']:
                            tree_dest.insert(parent='', index='end', text=drive, values=(human_filesize(drive_size), drive_size, 'Yes' if drive_has_config_file else '', vsn, serial))

                        dest_drive_master_list.append({
                            'name': drive,
                            'vid': vsn,
                            'serial': serial,
                            'capacity': drive_size,
                            'hasConfig': drive_has_config_file
                        })
                    except FileNotFoundError:
                        pass
    elif platform.system() == 'Linux':
        local_selected = settings_showDrives_dest_local.get()
        network_selected = settings_showDrives_dest_network.get()

        if network_selected and not local_selected:
            cmd = 'df -tcifs -tnfs --output=target'
        elif local_selected and not network_selected:
            cmd = 'df -xtmpfs -xsquashfs -xdevtmpfs -xcifs -xnfs --output=target'
        elif local_selected and network_selected:
            cmd = 'df -xtmpfs -xsquashfs -xdevtmpfs --output=target'

        out = subprocess.run(cmd, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
        logical_drive_list = out.stdout.decode('utf-8').split('\n')[1:]
        logical_drive_list = [mount for mount in logical_drive_list if mount and mount != config['sourceDrive']]

        total_drive_space_available = 0
        dest_drive_master_list = []
        for drive in logical_drive_list:
            drive_name = f'"{drive}"'

            out = subprocess.run("mount | grep " + drive_name + " | awk 'NR==1{print $1}' | sed 's/[0-9]*//g'", stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
            physical_disk = out.stdout.decode('utf-8').split('\n')[0].strip()

            # Only process mount point if it's not on the system drive
            if physical_disk != SYSTEM_DRIVE and drive != '/':
                drive_size = shutil.disk_usage(drive).total

                # Get volume ID, remove dashes, and format the last 8 characters
                out = subprocess.run(f"df {drive_name} --output=source | awk 'NR==2' | xargs lsblk -o uuid | awk 'NR==2'", stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
                vsn = out.stdout.decode('utf-8').split('\n')[0].strip().replace('-', '').upper()
                vsn = vsn[-8:-4] + '-' + vsn[-4:]

                # Get drive serial, if present
                out = subprocess.run(f"lsblk -o serial '{physical_disk}' | awk 'NR==2'", stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
                serial = out.stdout.decode('utf-8').split('\n')[0].strip()

                # Set default if serial not found
                serial = serial if serial else 'Not Found'

                drive_has_config_file = os.path.exists(f"{drive}/{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}") and os.path.isfile(f"{drive}/{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}")

                total_drive_space_available += drive_size
                if not config['cliMode']:
                    tree_dest.insert(parent='', index='end', text=drive, values=(human_filesize(drive_size), drive_size, 'Yes' if drive_has_config_file else '', vsn, serial))

                dest_drive_master_list.append({
                    'name': drive,
                    'vid': vsn,
                    'serial': serial,
                    'capacity': drive_size,
                    'hasConfig': drive_has_config_file
                })

    if not config['cliMode']:
        drive_total_space.configure(text=human_filesize(total_drive_space_available), fg=uicolor.NORMAL if total_drive_space_available > 0 else uicolor.FADED)

        progress.stop_indeterminate()

def load_dest_in_background():
    """Start the loading of the destination drive info in a new thread."""

    # URGENT: Make load_dest replaceable or, queueable
    if not thread_manager.is_alive('Refresh destination'):
        thread_manager.start(thread_manager.SINGLE, target=load_dest, is_progress_thread=True, name='Refresh destination', daemon=True)

def gui_select_from_config():
    """From the current config, select the appropriate shares and drives in the GUI."""

    global drive_select_bind

    # Get list of shares in config
    config_share_name_list = [item['name'] for item in config['shares']]
    config_shares_source_tree_id_list = [item for item in tree_source.get_children() if tree_source.item(item, 'text') in config_share_name_list]

    if config_shares_source_tree_id_list:
        tree_source.focus(config_shares_source_tree_id_list[-1])
        tree_source.selection_set(tuple(config_shares_source_tree_id_list))

    # Get list of drives where volume ID is in config
    connected_vid_list = [drive['vid'] for drive in config['drives']]
    config_drive_tree_id_list = [item for item in tree_dest.get_children() if tree_dest.item(item, 'values')[3] in connected_vid_list]

    # If drives aren't mounted that should be, display the warning
    MISSING_DRIVE_COUNT = len(config['missingDrives'])
    if MISSING_DRIVE_COUNT > 0:
        config_missing_drive_vid_list = [vid for vid in config['missingDrives'].keys()]

        MISSING_VID_READABLE_LIST = ', '.join(config_missing_drive_vid_list[:-2] + [' and '.join(config_missing_drive_vid_list[-2:])])
        MISSING_VID_ALERT_MESSAGE = f"The drive{'s' if len(config_missing_drive_vid_list) > 1 else ''} with volume ID{'s' if len(config_missing_drive_vid_list) > 1 else ''} {MISSING_VID_READABLE_LIST} {'are' if len(config_missing_drive_vid_list) > 1 else 'is'} not available to be selected.\n\nMissing drives may be omitted or replaced, provided the total space on destination drives is equal to, or exceeds the amount of data to back up.\n\nUnless you reset the config or otherwise restart this tool, this is the last time you will be warned."
        MISSING_VID_ALERT_TITLE = f"Drive{'s' if len(config_missing_drive_vid_list) > 1 else ''} missing"

        split_warning_prefix.configure(text=f"There {'is' if MISSING_DRIVE_COUNT == 1 else 'are'}")
        MISSING_DRIVE_CONTRACTION = 'isn\'t' if MISSING_DRIVE_COUNT == 1 else 'aren\'t'
        split_warning_suffix.configure(text=f"{'drive' if MISSING_DRIVE_COUNT == 1 else 'drives'} in the config that {MISSING_DRIVE_CONTRACTION} connected. Please connect {'it' if MISSING_DRIVE_COUNT == 1 else 'them'}, or enable split mode.")
        split_warning_missing_drive_count.configure(text=str(MISSING_DRIVE_COUNT))
        dest_split_warning_frame.grid(row=3, column=0, columnspan=3, sticky='nsew', pady=(0, WINDOW_ELEMENT_PADDING), ipady=WINDOW_ELEMENT_PADDING / 4)

        messagebox.showwarning(MISSING_VID_ALERT_TITLE, MISSING_VID_ALERT_MESSAGE)

    # Only redo the selection if the config data is different from the current
    # selection (that is, the drive we selected to load a config is not the only
    # drive listed in the config)
    # Because of the <<TreeviewSelect>> handler, re-selecting the same single item
    # would get stuck into an endless loop of trying to load the config
    # QUESTION: Is there a better way to handle this @config loading @selection handler @conflict?
    if len(config_drive_tree_id_list) > 0 and tree_dest.selection() != tuple(config_drive_tree_id_list):
        tree_dest.unbind('<<TreeviewSelect>>', drive_select_bind)

        tree_dest.focus(config_drive_tree_id_list[-1])
        tree_dest.selection_set(tuple(config_drive_tree_id_list))

        drive_select_bind = tree_dest.bind("<<TreeviewSelect>>", select_drive_in_background)

def load_config_from_file(filename):
    """Read a config file, and set the current config based off of it.

    Args:
        filename (String): The file to read from.
    """

    global config

    new_config = {}
    config_file = Config(filename)

    # Get shares
    shares = config_file.get('selection', 'shares')
    if shares is not None and len(shares) > 0:
        new_config['shares'] = [{
            'name': share,
            'size': None
        } for share in shares.split(',')]

    # Get VID list
    vids = config_file.get('selection', 'vids').split(',')

    # Get drive info
    config_drive_total = 0
    new_config['drives'] = []
    new_config['missingDrives'] = {}
    drive_lookup_list = {drive['vid']: drive for drive in dest_drive_master_list}
    for drive in vids:
        if drive in drive_lookup_list.keys():
            # If drive connected, add to drive list
            new_config['drives'].append(drive_lookup_list[drive])
            config_drive_total += drive_lookup_list[drive]['capacity']
        else:
            # Add drive capacity info to missing drive list
            reported_drive_capacity = config_file.get(drive, 'capacity', 0, data_type=Config.INTEGER)
            new_config['missingDrives'][drive] = reported_drive_capacity
            config_drive_total += reported_drive_capacity

    config.update(new_config)

    if not config['cliMode']:
        config_selected_space.configure(text=human_filesize(config_drive_total), fg=uicolor.NORMAL)
        gui_select_from_config()

prev_selection = 0
prev_drive_selection = []

# BUG: keyboard module seems to be returning false for keypress on first try. No idea how to fix this
keyboard.is_pressed('alt')
def handle_drive_selection_click():
    """Parse the current drive selection, read config data, and select other drives and shares if needed.

    If the selection involves a single drive that the user specifically clicked on,
    this function reads the config file on it if one exists, and will select any
    other drives and shares in the config.
    """

    global prev_selection
    global prev_drive_selection

    progress.start_indeterminate()

    dest_selection = tree_dest.selection()

    # If selection is different than last time, invalidate the analysis
    selection_selected_last_time = [drive for drive in dest_selection if drive in prev_drive_selection]
    if len(dest_selection) != len(prev_drive_selection) or len(selection_selected_last_time) != len(prev_drive_selection):
        start_backup_btn.configure(state='disable')

    prev_drive_selection = [share for share in dest_selection]

    # Check if newly selected drive has a config file
    # We only want to do this if the click is the first selection (that is, there
    # are no other drives selected except the one we clicked).
    if len(dest_selection) > 0:
        selected_drive = tree_dest.item(dest_selection[0], 'text')
        SELECTED_DRIVE_CONFIG_FILE = f"{selected_drive}/{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}"
        drives_read_from_config_file = False
        if not keyboard.is_pressed('alt') and prev_selection <= len(dest_selection) and len(dest_selection) == 1 and os.path.exists(SELECTED_DRIVE_CONFIG_FILE) and os.path.isfile(SELECTED_DRIVE_CONFIG_FILE):
            # Found config file, so read it
            load_config_from_file(SELECTED_DRIVE_CONFIG_FILE)
            dest_selection = tree_dest.selection()
            drives_read_from_config_file = True
        else:
            dest_split_warning_frame.grid_remove()
            prev_selection = len(dest_selection)

    selected_total = 0
    selected_drive_list = []
    drive_lookup_list = {drive['vid']: drive for drive in dest_drive_master_list}
    for item in dest_selection:
        # Write drive IDs to config
        selected_drive = drive_lookup_list[tree_dest.item(item, 'values')[3]]
        selected_drive_list.append(selected_drive)
        selected_total = selected_total + selected_drive['capacity']

    drive_selected_space.configure(text=human_filesize(selected_total), fg=uicolor.NORMAL if selected_total > 0 else uicolor.FADED)
    if not drives_read_from_config_file:
        config['drives'] = selected_drive_list
        config_selected_space.configure(text='None', fg=uicolor.FADED)

    update_status_bar_selection()

    progress.stop_indeterminate()

def select_drive_in_background(event):
    """Start the drive selection handling in a new thread."""

    thread_manager.start(thread_manager.MULTIPLE, is_progress_thread=True, target=handle_drive_selection_click, name='Drive Select', daemon=True)

def start_backup():
    """Start the backup in a new thread."""

    if backup:
        thread_manager.start(thread_manager.KILLABLE, is_progress_thread=True, target=backup.run, name='Backup', daemon=True)

force_non_graceful_cleanup = False
def cleanup_handler(signal_received, frame):
    """Handle cleanup when exiting with Ctrl-C.

    Args:
        signal_received: The signal number received.
        frame: The current stack frame.
    """

    global force_non_graceful_cleanup

    if not force_non_graceful_cleanup:
        print(f"{bcolor.FAIL}SIGINT or Ctrl-C detected. Exiting gracefully...{bcolor.ENDC}")

        if thread_manager.is_alive('Backup'):
            thread_manager.kill('Backup')

            if thread_manager.is_alive('Backup'):
                force_non_graceful_cleanup = True
                print(f"{bcolor.FAIL}Press Ctrl-C again to force stop{bcolor.ENDC}")

            while thread_manager.is_alive('Backup'):
                pass

        if thread_manager.is_alive('backupTimer'):
            thread_manager.kill('backupTimer')
    else:
        print(f"{bcolor.FAIL}SIGINT or Ctrl-C detected. Force closing...{bcolor.ENDC}")

    exit(0)

update_window = None

def display_update_screen(update_info):
    """Display information about updates.

    Args:
        update_info (dict): The update info returned by the UpdateHandler.
    """

    global update_window

    if update_info['updateAvailable'] and (update_window is None or not update_window.winfo_exists()):
        update_window = tk.Toplevel(root)
        update_window.title('Update Available')
        update_window.resizable(False, False)
        update_window.geometry('600x300')

        if platform.system() == 'Windows':
            update_window.iconbitmap(resource_path('media/icon.ico'))

        center(update_window, root)
        update_window.transient(root)
        update_window.grab_set()
        root.wm_attributes('-disabled', True)

        def on_close():
            update_window.destroy()
            root.wm_attributes('-disabled', False)

            ctypes.windll.user32.SetForegroundWindow(root.winfo_id())
            root.focus_set()

        update_window.protocol('WM_DELETE_WINDOW', on_close)

        main_frame = tk.Frame(update_window)
        main_frame.grid(row=0, column=0, sticky='')
        update_window.grid_rowconfigure(0, weight=1)
        update_window.grid_columnconfigure(0, weight=1)

        update_header = tk.Label(main_frame, text='Update Available!', font=(None, 30, 'bold italic'), fg=uicolor.INFOTEXTDARK)
        update_header.pack()

        update_text = tk.Label(main_frame, text='An update to BackDrop is avaiable. Please update to get the latest features and fixes.', font=(None, 10))
        update_text.pack(pady=16)

        current_version_frame = tk.Frame(main_frame)
        current_version_frame.pack()
        tk.Label(current_version_frame, text='Current Version:', font=(None, 14)).pack(side='left')
        tk.Label(current_version_frame, text=APP_VERSION, font=(None, 14), fg=uicolor.FADED).pack(side='left')

        latest_version_frame = tk.Frame(main_frame)
        latest_version_frame.pack(pady=(2, 12))
        tk.Label(latest_version_frame, text='Latest Version:', font=(None, 14)).pack(side='left')
        tk.Label(latest_version_frame, text=update_info['latestVersion'], font=(None, 14), fg=uicolor.FADED).pack(side='left')

        download_frame = tk.Frame(main_frame)
        download_frame.pack()

        icon_info = {
            'exe': {
                'flat': icon_windows,
                'color': icon_windows_color
            },
            'zip': {
                'flat': icon_zip,
                'color': icon_zip_color
            }
        }
        download_map = {url[-3:].lower(): url for url in update_info['download']}

        for file_type, icons in icon_info.items():
            if file_type in download_map.keys():
                download_btn = tk.Label(download_frame, image=icons['flat'])
                download_btn.pack(side='left', padx=8)
                download_btn.bind('<Enter>', lambda e, icon=icons['color']: e.widget.configure(image=icon))
                download_btn.bind('<Leave>', lambda e, icon=icons['flat']: e.widget.configure(image=icon))
                download_btn.bind('<Button-1>', lambda e, url=download_map[file_type]: webbrowser.open_new(url))

def check_for_updates(info):
    """Process the update information provided by the UpdateHandler class.

    Args:
        info (dict): The Update info from the update handler.
    """

    global update_info

    update_info = info

    if info['updateAvailable']:
        if not config['cliMode']:
            display_update_screen(info)
        else:
            download_url = None
            for item in info['download']:
                # TODO: For cross platform, make sure the right filetype is selected
                if item[-4:].lower() == '.exe':
                    download_url = item
                    break

            if download_url is not None:
                print('Downloading update. Please wait...')

                download_filename = f"{os.getcwd()}/{download_url.split('/')[-1]}"
                urllib.request.urlretrieve(download_url, download_filename)

                print('Update downloaded successfully')
            else:
                print('Unable to find suitable download. Please try again, or update manually.')

# Set constants
if platform.system() == 'Windows':
    SYSTEM_DRIVE = f"{os.getenv('SystemDrive')[0]}:"
    APPDATA_FOLDER = os.getenv('LocalAppData') + '/BackDrop'
elif platform.system() == 'Linux':
    # Get system drive by querying mount points
    out = subprocess.run('mount | grep "on / type"' + " | awk 'NR==1{print $1}' | sed 's/[0-9]*//g'", stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
    SYSTEM_DRIVE = out.stdout.decode('utf-8').split('\n')[0].strip()

    # If user runs as sudo, username has to be grabbed through sudo to get the
    # appropriate home dir, since ~ with sudo resolves to /root
    if os.getenv('SUDO_USER') is not None:
        USER_HOME_VAR = '~' + os.getenv('SUDO_USER')
    else:
        USER_HOME_VAR = '~'
    APPDATA_FOLDER = f"{os.path.expanduser(USER_HOME_VAR)}/.config/BackDrop"

# Set app defaults
BACKUP_CONFIG_DIR = '.backdrop'
BACKUP_CONFIG_FILE = 'backup.ini'
PREFERENCES_CONFIG_FILE = 'preferences.ini'
WINDOW_ELEMENT_PADDING = 16

if platform.system() == 'Windows':
    DIR_SLASH = '\\'
elif platform.system() == 'Linux':
    DIR_SLASH = '/'

prefs = Config(APPDATA_FOLDER + '/' + PREFERENCES_CONFIG_FILE)
config = {
    'sourceDrive': None,
    'splitMode': False,
    'shares': [],
    'drives': [],
    'missingDrives': {},
    'cliMode': len(sys.argv) > 1
}
dest_drive_master_list = []

backup = None
command_list = []

signal(SIGINT, cleanup_handler)

thread_manager = ThreadManager()

############
# CLI Mode #
############

if config['cliMode']:
    # Colored text does not work without this empty call first
    os.system('')

    command_line = CommandLine(
        [
            'Usage: backdrop [options]\n',
            ('-S', '--source', 1, 'The source drive to back up.'),
            ('-s', '--share', 1, 'The shares to back up from the source.'),
            ('-d', '--destination', 1, 'The destination drive to back up to.'),
            '',
            ('-i', '--interactive', 0, 'Run in interactive mode instead of specifying backup configuration.'),
            ('-l', '--config', 1, 'Load config file from a drive instead of specifying backup configuration.'),
            ('-m', '--split-mode', 0, 'Run in split mode if not all destination drives are connected.'),
            ('-U', '--unattended', 0, 'Do not prompt for confirmation, and only exit on error.'),
            '',
            ('-h', '--help', 0, 'Display this help menu.'),
            ('-v', '--version', 0, 'Display the program version.'),
            ('-u', '--update', 0, 'Check for and download updates.')
        ]
    )

    # FIXME: Allow destination and config to be specified with drive letter or volume ID

    if command_line.has_param('help'):
        command_line.show_help()
    elif command_line.has_param('version'):
        print(f'BackDrop {APP_VERSION}')
    elif command_line.has_param('update'):
        update_handler = UpdateHandler(
            current_version=APP_VERSION,
            update_callback=check_for_updates
        )
        update_handler.check()
    else:
        # Backup config mode
        # TODO: Remove CLI mode stability warning
        print(f"\n{bcolor.WARNING}{'CLI mode is a work in progress, and may not be stable or complete': ^{os.get_terminal_size().columns}}{bcolor.ENDC}\n")

        # ## Input validation ## #

        # Validate drive selection
        load_source()
        if len(source_avail_drive_list) <= 0:
            print(f"{bcolor.FAIL}No network drives are available{bcolor.ENDC}")
            exit()

        load_dest()
        if len(dest_drive_master_list) <= 0:
            print(f"{bcolor.FAIL}No destination drives are available{bcolor.ENDC}")
            exit()
        dest_drive_name_list = [drive['name'] for drive in dest_drive_master_list]

        # Source drive
        if command_line.has_param('interactive'):
            source_drive = prefs.get('selection', 'sourceDrive', source_avail_drive_list[0], verify_data=source_avail_drive_list)
        else:
            source_drive = prefs.get('selection', 'sourceDrive', source_avail_drive_list[0], verify_data=source_avail_drive_list)
            source_drive = command_line.get_param('source')[0][0].upper() + ':' if command_line.has_param('source') and command_line.get_param('source')[0] in source_avail_drive_list else source_drive

        if command_line.has_param('interactive') and not command_line.validate_yes_no(f"Source drive {source_drive} loaded from preferences. Is this ok?", True):
            print('\nAvailable drives are as follows:\n')
            print(f"Available drives: {', '.join(source_avail_drive_list)}\n")
            config['sourceDrive'] = command_line.validate_choice(
                message='Which source drive would you like to use?',
                choices=source_avail_drive_list,
                default=source_drive,
                chars_required=1
            )
        else:
            if source_drive is None:
                exit()
            elif source_drive not in source_avail_drive_list:
                print(f"{bcolor.FAIL}Source drive is not valid for selection{bcolor.ENDC}")
                exit()

            config['sourceDrive'] = source_drive

        shares_loaded_from_config = False

        # Destination drives
        if command_line.has_param('interactive'):
            print('\nAvailable destination drives are as follows:\n')

            # TODO: Generalize this into function for table-izing data?
            drive_name_list = ['Drive']
            drive_size_list = ['Size']
            drive_config_list = ['Config file']
            drive_vid_list = ['Volume ID']
            drive_serial_list = ['Serial']
            drive_name_list.extend([drive['name'] for drive in dest_drive_master_list])
            drive_size_list.extend([human_filesize(drive['capacity']) for drive in dest_drive_master_list])
            drive_config_list.extend(['Yes' if drive['hasConfig'] else '' for drive in dest_drive_master_list])
            drive_vid_list.extend([drive['vid'] for drive in dest_drive_master_list])
            drive_serial_list.extend([drive['serial'] for drive in dest_drive_master_list])

            drive_display_length = {
                'name': len(max(drive_name_list, key=len)),
                'size': len(max(drive_size_list, key=len)),
                'config': len(max(drive_config_list, key=len)),
                'vid': len(max(drive_vid_list, key=len))
            }

            for i, cur_drive in enumerate(drive_name_list):
                print(f"{cur_drive: <{drive_display_length['name']}}  {drive_size_list[i]: <{drive_display_length['size']}}  {drive_config_list[i]: <{drive_display_length['config']}}  {drive_vid_list[i]: <{drive_display_length['vid']}}  {drive_serial_list[i]}")
            print('')

            drive_list = command_line.validate_choice_list(
                message='Which destination drives (space separated) would you like to use?',
                choices=[drive['name'] for drive in dest_drive_master_list],
                default=None,
                chars_required=1
            )

            config['drives'] = [drive for drive in dest_drive_master_list if drive['name'] in drive_list]
        else:
            # Load from config
            split_mode = command_line.has_param('split')
            load_config_drive = command_line.get_param('config')[0]
            if platform.system() == 'Windows':
                load_config_drive = load_config_drive[0].upper() + ':'
            if type(load_config_drive) is list and load_config_drive in dest_drive_name_list:
                load_config_from_file(f"{load_config_drive}/{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}")

                shares_loaded_from_config = True

                dest_list = [drive['name'] for drive in config['drives']]

                # If drives aren't mounted that should be, display the warning
                missing_drive_count = len(config['missingDrives'])
                if missing_drive_count > 0 and not split_mode:
                    config_missing_vids = [vid for vid in config['missingDrives'].keys()]

                    missing_vid_string = ', '.join(config_missing_vids[:-2] + [' and '.join(config_missing_vids[-2:])])
                    warning_message = f"The drive{'s' if len(config_missing_vids) > 1 else ''} with volume ID{'s' if len(config_missing_vids) > 1 else ''} {missing_vid_string} {'are' if len(config_missing_vids) > 1 else 'is'} not available to be selected.\n\nMissing drives may be omitted or replaced, provided the total space on destination drives is equal to, or exceeds the amount of data to back up.\n\nUnless you reset the config or otherwise restart this tool, this is the last time you will be warned."
                    warning_title = f"Drive{'s' if len(config_missing_vids) > 1 else ''} missing"

                    drive_parts = [
                        'is' if missing_drive_count == 1 else 'are',
                        'drive' if missing_drive_count == 1 else 'drives',
                        'isn\'t' if missing_drive_count == 1 else 'aren\'t',
                        'it' if missing_drive_count == 1 else 'them'
                    ]
                    print(f"{bcolor.WARNING}There {drive_parts[0]} {missing_drive_count} {drive_parts[1]} in the config that {drive_parts[2]} connected. Please connect {drive_parts[3]}, or enable split mode.{bcolor.ENDC}\n")
            else:
                if not config['drives'] and (not command_line.has_param('destination') or not command_line.get_param('destination')):
                    print('Please specify at least one destination drive')
                    exit()

                dest_list = [drive[0].upper() + ':' for drive in command_line.get_param('destination')]

                for drive in dest_list:
                    if drive not in dest_drive_name_list:
                        print(f"{bcolor.FAIL}One or more destinations are not valid for selection.\nAvailable drives are as follows:{bcolor.ENDC}")

                        drive_name_list = ['Drive']
                        drive_size_list = ['Size']
                        drive_config_list = ['Config file']
                        drive_vid_list = ['Volume ID']
                        drive_serial_list = ['Serial']
                        drive_name_list.extend([drive['name'] for drive in dest_drive_master_list])
                        drive_size_list.extend([human_filesize(drive['capacity']) for drive in dest_drive_master_list])
                        drive_config_list.extend(['Yes' if drive['hasConfig'] else '' for drive in dest_drive_master_list])
                        drive_vid_list.extend([drive['vid'] for drive in dest_drive_master_list])
                        drive_serial_list.extend([drive['serial'] for drive in dest_drive_master_list])

                        drive_display_length = {
                            'name': len(max(drive_name_list, key=len)),
                            'size': len(max(drive_size_list, key=len)),
                            'config': len(max(drive_config_list, key=len)),
                            'vid': len(max(drive_vid_list, key=len))
                        }

                        for i, cur_drive in enumerate(drive_name_list):
                            print(f"{cur_drive: <{drive_display_length['name']}}  {drive_size_list[i]: <{drive_display_length['size']}}  {drive_config_list[i]: <{drive_display_length['config']}}  {drive_vid_list[i]: <{drive_display_length['vid']}}  {drive_serial_list[i]}")

                        exit()

            config['drives'] = [drive for drive in dest_drive_master_list if drive['name'] in dest_list]
            config['splitMode'] = split_mode

        # Shares
        if command_line.has_param('interactive'):
            print('\nAvailable shares drives are as follows:\n')

            all_share_list = [share for share in next(os.walk(config['sourceDrive']))[1]]
            print('\n'.join(all_share_list) + '\n')

            config['shares'] = [{
                'name': share,
                'size': get_directory_size(config['sourceDrive'] + DIR_SLASH + share)
            } for share in command_line.validate_choice_list(
                message='Which shares (space separated) would you like to use?',
                choices=all_share_list,
                default=None,
                case_sensitive=True
            )]
        else:
            # TODO: Can has_param and get_param be merged?
            if not config['shares'] and (not command_line.has_param('share') or not command_line.get_param('share')):
                print('Please specify at least one share to back up')
                exit()

            if not shares_loaded_from_config:
                share_list = sorted(command_line.get_param('share'))
            else:
                share_list = [share['name'] for share in config['shares']]

            source_share_list = [directory for directory in next(os.walk(config['sourceDrive']))[1]]
            filtered_share_input = [share for share in share_list if share in source_share_list]
            if len(filtered_share_input) < len(share_list):
                print(f"{bcolor.FAIL}One or more shares are not valid for selection{bcolor.ENDC}")
                exit()

            config['shares'] = [{
                'name': share,
                'size': get_directory_size(config['sourceDrive'] + DIR_SLASH + share)
            } for share in share_list]

        # ## Show summary ## #

        header_list = ['Source', 'Destination', 'Shares']
        if len(config['missingDrives']) > 0:
            header_list.extend(['Missing drives', 'Split mode'])
        header_spacing = len(max(header_list, key=len)) + 1

        print('')
        print(f"{'Source:': <{header_spacing}} {config['sourceDrive']}")
        print(f"{'Destination:': <{header_spacing}} {', '.join([drive['name'] for drive in config['drives']])}")

        if len(config['missingDrives']) > 0:
            print(f"{'Missing drives:': <{header_spacing}} {', '.join([drive for drive in config['missingDrives'].keys()])}")
            print(f"{'Split mode:': <{header_spacing}} {bcolor.OKGREEN + 'Enabled' + bcolor.ENDC if split_mode else bcolor.FAIL + 'Disabled' + bcolor.ENDC}")

        print(f"{'Shares:': <{header_spacing}} {', '.join([share['name'] for share in config['shares']])}\n")

        if len(config['missingDrives']) > 0 and not split_mode:
            print(f"{bcolor.FAIL}Missing drives; split mode disabled{bcolor.ENDC}")
            exit()

        # ## Confirm ## #

        if not command_line.has_param('unattended') and not command_line.validate_yes_no('Do you want to continue?', True):
            print(f"{bcolor.FAIL}Backup aborted by user{bcolor.ENDC}")
            exit()

        # ## Analysis ## #

        start_backup_analysis()

        while thread_manager.is_alive('Backup Analysis'):
            pass

        # ## Confirm ## #

        if not command_line.has_param('unattended') and not command_line.validate_yes_no('Do you want to continue?', True):
            print(f"{bcolor.FAIL}Backup aborted by user{bcolor.ENDC}")
            exit()

        # ## Backup ## #

        start_backup()

        while thread_manager.is_alive('Backup'):
            pass

        exit()

def update_status_bar_selection(status=None):
    """Update the status bar selection status.

    Args:
        status (int): The status code to use.
    """

    if [share for share in config['shares'] if share['size'] is None]:
        # Not all shares calculated
        status = Status.BACKUPSELECT_CALCULATING_SOURCE
    elif not config['shares'] and not config['drives'] and len(config['missingDrives']) == 0:
        # No selection in config
        status = Status.BACKUPSELECT_NO_SELECTION
    elif not config['shares']:
        # No shares selected
        status = Status.BACKUPSELECT_MISSING_SOURCE
    elif not config['drives'] and len(config['missingDrives']) == 0:
        # No drives selected
        status = Status.BACKUPSELECT_MISSING_DEST
    else:
        SHARE_SELECTED_SPACE = sum([share['size'] for share in config['shares']])
        DRIVE_SELECTED_SPACE = sum([drive['capacity'] for drive in config['drives']]) + sum(config['missingDrives'].values())

        if SHARE_SELECTED_SPACE < DRIVE_SELECTED_SPACE:
            # Selected enough drive space
            status = Status.BACKUPSELECT_ANALYSIS_WAITING
        else:
            # Shares larger than drive space
            status = Status.BACKUPSELECT_INSUFFICIENT_SPACE

    # Set status
    if status == Status.BACKUPSELECT_NO_SELECTION:
        statusbar_selection.configure(text='No selection')
    elif status == Status.BACKUPSELECT_MISSING_SOURCE:
        statusbar_selection.configure(text='No shares selected')
    elif status == Status.BACKUPSELECT_MISSING_DEST:
        statusbar_selection.configure(text='No drives selected')
    elif status == Status.BACKUPSELECT_CALCULATING_SOURCE:
        statusbar_selection.configure(text='Calculating share size')
    elif status == Status.BACKUPSELECT_INSUFFICIENT_SPACE:
        statusbar_selection.configure(text='Destination too small for shares')
    elif status == Status.BACKUPSELECT_ANALYSIS_WAITING:
        statusbar_selection.configure(text='Selection OK, ready for analysis')

def update_status_bar_backup(status):
    """Update the status bar backup status.

    Args:
        status (int): The status code to use.
    """

    if status == Status.BACKUP_IDLE:
        statusbar_backup.configure(text='Idle')
    elif status == Status.BACKUP_ANALYSIS_RUNNING:
        statusbar_backup.configure(text='Analysis running')
    elif status == Status.BACKUP_READY_FOR_BACKUP:
        statusbar_backup.configure(text='Analysis finished, ready for backup')
    elif status == Status.BACKUP_BACKUP_RUNNING:
        statusbar_backup.configure(text='Backup running')
    elif status == Status.BACKUP_HALT_REQUESTED:
        statusbar_backup.configure(text='Stopping backup')

def update_status_bar_update(status):
    """Update the status bar update message.

    Args:
        status (int): The status code to use.
    """

    if status == Status.UPDATE_CHECKING:
        statusbar_update.configure(text='Checking for updates', fg=uicolor.NORMAL)
    elif status == Status.UPDATE_AVAILABLE:
        statusbar_update.configure(text='Update available!', fg=uicolor.INFOTEXT)
    elif status == Status.UPDATE_UP_TO_DATE:
        statusbar_update.configure(text='Up to date', fg=uicolor.NORMAL)

def update_ui_component(status, data=None):
    """Update UI elements with given data..

    Args:
        status (int): The status code to use.
        data (*): The data to update (optional).
    """

    if status == Status.UPDATEUI_ANALYSIS_BTN:
        start_analysis_btn.configure(**data)
    elif status == Status.UPDATEUI_BACKUP_BTN:
        start_backup_btn.configure(**data)
    elif status == Status.UPDATEUI_START_BACKUP_BTN:
        update_status_bar_backup(Status.BACKUP_HALT_REQUESTED)
        start_backup_btn.configure(text='Run Backup', command=start_backup, style='win.TButton')
    elif status == Status.UPDATEUI_STOP_BACKUP_BTN:
        start_backup_btn.configure(text='Halt Backup', command=lambda: thread_manager.kill('Backup'), style='danger.TButton')
    elif status == Status.UPDATEUI_STATUS_BAR:
        update_status_bar_backup(data)

def open_config_file():
    """Open a config file and load it."""

    filename = filedialog.askopenfilename(initialdir='', title='Select drive config', filetypes=(('Backup config files', 'backup.ini'), ('All files', '*.*')))
    if filename:
        load_config_from_file(filename)

def save_config_file():
    """Save the config to selected drives."""

    if config['shares'] and config['drives']:
        share_list = ','.join([item['name'] for item in config['shares']])
        raw_vid_list = [drive['vid'] for drive in config['drives']]
        raw_vid_list.extend(config['missingDrives'].keys())
        vid_list = ','.join(raw_vid_list)

        # For each drive letter that's connected, get drive info, and write file
        for drive in config['drives']:
            # If config exists on drives, back it up first
            if os.path.isfile(f"{drive['name']}{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}"):
                shutil.move(f"{drive['name']}{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}", f"{drive['name']}{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}.old")

            new_config_file = Config(f"{drive['name']}{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}")

            # Write shares and VIDs to config file
            new_config_file.set('selection', 'shares', share_list)
            new_config_file.set('selection', 'vids', vid_list)

            # Write info for each drive to its own section
            for current_drive in config['drives']:
                new_config_file.set(current_drive['vid'], 'vid', current_drive['vid'])
                new_config_file.set(current_drive['vid'], 'serial', current_drive['serial'])
                new_config_file.set(current_drive['vid'], 'capacity', current_drive['capacity'])

            # Write info for missing drives
            for drive_vid, capacity in config['missingDrives'].items():
                new_config_file.set(drive_vid, 'vid', drive_vid)
                new_config_file.set(drive_vid, 'serial', 'Unknown')
                new_config_file.set(drive_vid, 'capacity', capacity)

        # Since config files on drives changed, refresh the destination list
        load_dest_in_background()

        messagebox.showinfo(title='Save Backup Config', message='Backup config saved successfully')

def save_config_file_as():
    """Save the config file to a specified location."""

    filename = filedialog.asksaveasfilename(initialdir='', initialfile='backup.ini', title='Save drive config', filetypes=(('Backup config files', 'backup.ini'), ('All files', '*.*')))

    if config['shares'] and config['drives']:
        share_list = ','.join([item['name'] for item in config['shares']])
        raw_vid_list = [drive['vid'] for drive in config['drives']]
        raw_vid_list.extend(config['missingDrives'].keys())
        vid_list = ','.join(raw_vid_list)

        # Get drive info, and write file
        new_config_file = Config(filename)

        # Write shares and VIDs to config file
        new_config_file.set('selection', 'shares', share_list)
        new_config_file.set('selection', 'vids', vid_list)

        # Write info for each drive to its own section
        for current_drive in config['drives']:
            new_config_file.set(current_drive['vid'], 'vid', current_drive['vid'])
            new_config_file.set(current_drive['vid'], 'serial', current_drive['serial'])
            new_config_file.set(current_drive['vid'], 'capacity', current_drive['capacity'])

        # Write info for missing drives
        for drive_vid, capacity in config['missingDrives'].items():
            new_config_file.set(drive_vid, 'vid', drive_vid)
            new_config_file.set(drive_vid, 'serial', 'Unknown')
            new_config_file.set(drive_vid, 'capacity', capacity)

        messagebox.showinfo(title='Save Backup Config', message='Backup config saved successfully')

def delete_config_file_from_selected_drives():
    """Delete config files from drives in destination selection."""

    drive_list = [tree_dest.item(drive, 'text')[0] for drive in tree_dest.selection()]
    drive_list = [drive for drive in drive_list if os.path.isfile(f"{drive}:/{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}")]

    if drive_list:
        # Ask for confirmation before deleting
        if messagebox.askyesno('Delete config files?', 'Are you sure you want to delete the config files from the selected drives?'):
            # Delete config file on each drive
            for drive in drive_list:
                config_file_path = f"{drive}:/{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}"
                os.remove(config_file_path)

            # Since config files on drives changed, refresh the destination list
            load_dest_in_background()

window_config_builder = None
def show_config_builder():
    """Show the config builder."""

    global window_config_builder
    global builder_has_pending_changes

    def builder_update_status_bar_save(status):
        """Update the builder status bar save status.

        Args:
            status (int): The status code to use.
        """

        if status == Status.SAVE_PENDING_CHANGES:
            builder_statusbar_changes.configure(text='Unsaved changes', fg=uicolor.INFOTEXT)
        elif status == Status.SAVE_ALL_SAVED:
            builder_statusbar_changes.configure(text='All changes saved', fg=uicolor.NORMAL)

    def builder_load_connected():
        """Load the connected drive info, and display it in the tree."""

        # Empty tree in case this is being refreshed
        tree_current_connected.delete(*tree_current_connected.get_children())

        if platform.system() == 'Windows':
            drive_list = win32api.GetLogicalDriveStrings().split('\000')[:-1]
            drive_list = [drive[:2] for drive in drive_list]

            # Associate logical drives with physical drives, and map them to physical serial numbers
            logical_to_physical_map = {}
            pythoncom.CoInitialize()
            try:
                for physical_disk in wmi.WMI().Win32_DiskDrive():
                    for partition in physical_disk.associators("Win32_DiskDriveToDiskPartition"):
                        logical_to_physical_map.update({logical_disk.DeviceID[0]: physical_disk.SerialNumber.strip() for logical_disk in partition.associators("Win32_LogicalDiskToPartition")})
            finally:
                pythoncom.CoUninitialize()

            # Enumerate drive list to find info about all non-source drives
            total_usage = 0
            dest_drive_master_list = []
            dest_drive_letter_to_info = {}
            for drive in drive_list:
                if drive != config['sourceDrive'] and drive != SYSTEM_DRIVE:
                    drive_type = win32file.GetDriveType(drive)
                    if ((settings_showDrives_dest_local.get() and drive_type == DRIVE_TYPE_LOCAL)  # Drive is LOCAL
                            or (settings_showDrives_dest_network.get() and drive_type == DRIVE_TYPE_REMOTE)):  # Drive is REMOTE
                        try:
                            drive_size = shutil.disk_usage(drive).total
                            vsn = os.stat(drive).st_dev
                            vsn = '{:04X}-{:04X}'.format(vsn >> 16, vsn & 0xffff)
                            try:
                                serial = logical_to_physical_map[drive[0]]
                            except KeyError:
                                serial = 'Not Found'

                            # Add drive to drive list
                            dest_drive_letter_to_info[drive[0]] = {
                                'vid': vsn,
                                'serial': serial
                            }

                            drive_has_config_file = os.path.exists(f"{drive}{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}") and os.path.isfile(f"{drive}{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}")

                            total_usage = total_usage + drive_size
                            tree_current_connected.insert(parent='', index='end', text=drive, values=(human_filesize(drive_size), drive_size, 'Yes' if drive_has_config_file else '', vsn, serial))

                            dest_drive_master_list.append({
                                'name': drive,
                                'vid': vsn,
                                'serial': serial,
                                'capacity': drive_size,
                                'hasConfig': drive_has_config_file
                            })
                        except FileNotFoundError:
                            pass
        elif platform.system() == 'Linux':
            out = subprocess.run('df -xtmpfs -xsquashfs -xdevtmpfs -xcifs -xnfs --output=target', stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
            drive_list = out.stdout.decode('utf-8').split('\n')[1:]
            drive_list = [mount for mount in drive_list if mount]

            total_drive_space_available = 0
            dest_drive_master_list = []
            for drive in drive_list:
                drive_name = f'"{drive}"'

                out = subprocess.run("mount | grep " + drive_name + " | awk 'NR==1{print $1}' | sed 's/[0-9]*//g'", stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
                physical_disk = out.stdout.decode('utf-8').split('\n')[0].strip()

                # Only process mount point if it's not on the system drive
                if physical_disk != SYSTEM_DRIVE and drive != '/':
                    drive_size = shutil.disk_usage(drive).total

                    # Get volume ID, remove dashes, and format the last 8 characters
                    out = subprocess.run(f"df {drive_name} --output=source | awk 'NR==2' | xargs lsblk -o uuid | awk 'NR==2'", stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
                    vsn = out.stdout.decode('utf-8').split('\n')[0].strip().replace('-', '').upper()
                    vsn = vsn[-8:-4] + '-' + vsn[-4:]

                    out = subprocess.run(f"lsblk -o serial '{physical_disk}' | awk 'NR==2'", stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
                    serial = out.stdout.decode('utf-8').split('\n')[0].strip()

                    # Set default if serial not found
                    serial = serial if serial else 'Not Found'

                    drive_has_config_file = os.path.exists(f"{drive}/{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}") and os.path.isfile(f"{drive}/{BACKUP_CONFIG_DIR}/{BACKUP_CONFIG_FILE}")

                    total_drive_space_available += drive_size
                    tree_current_connected.insert(parent='', index='end', text=drive, values=(human_filesize(drive_size), drive_size, 'Yes' if drive_has_config_file else '', vsn, serial))

                    dest_drive_master_list.append({
                        'name': drive,
                        'vid': vsn,
                        'serial': serial,
                        'capacity': drive_size,
                        'hasConfig': drive_has_config_file
                    })

    def builder_open_config_file():
        """Open a config file and load it."""

        global builder_has_pending_changes

        # Empty tree
        tree_builder_configured.delete(*tree_builder_configured.get_children())

        filename = filedialog.askopenfilename(initialdir='', title='Select drive config', filetypes=(('Backup config files', 'backup.ini'), ('All files', '*.*')), parent=window_config_builder)
        if filename:
            builder_has_pending_changes = True
            builder_update_status_bar_save(Status.SAVE_PENDING_CHANGES)

            config_file = Config(filename)

            # Get VID list
            vids = config_file.get('selection', 'vids').split(',')

            # Get drive info
            config_total = 0
            for drive in vids:
                # Add drive capacity info to missing drive list
                drive_capacity = config_file.get(drive, 'capacity', 0, data_type=Config.INTEGER)
                drive_serial = config_file.get(drive, 'serial', 'Not Found')

                # Insert drive into tree, and update capacity
                tree_builder_configured.insert(parent='', index='end', text=drive, values=(human_filesize(drive_capacity), drive_capacity, drive_serial))
                config_total += drive_capacity

    def builder_save_config_file():
        """Save the config file to a specified location."""

        global builder_has_pending_changes

        filename = filedialog.asksaveasfilename(initialdir='', initialfile='backup.ini', title='Save drive config', filetypes=(('Backup config files', 'backup.ini'), ('All files', '*.*')), parent=window_config_builder)

        if filename and len(tree_builder_configured.get_children()) > 0:
            # Get already added drives to prevent adding drives twice
            existing_drive_vids = [tree_builder_configured.item(drive, 'text') for drive in tree_builder_configured.get_children()]

            # Get drive info, and write file
            new_config_file = Config(filename)

            # Write shares and VIDs to config file
            new_config_file.set('selection', 'shares', '')
            new_config_file.set('selection', 'vids', ','.join(existing_drive_vids))

            # Write info for each drive to its own section
            for drive in tree_builder_configured.get_children():
                drive_vid = tree_builder_configured.item(drive, 'text')
                new_config_file.set(drive_vid, 'vid', drive_vid)
                new_config_file.set(drive_vid, 'serial', tree_builder_configured.item(drive, 'values')[2])
                new_config_file.set(drive_vid, 'capacity', tree_builder_configured.item(drive, 'values')[1])

            builder_has_pending_changes = False
            builder_update_status_bar_save(Status.SAVE_ALL_SAVED)
            messagebox.showinfo(title='Save Backup Config', message='Backup config saved successfully', parent=window_config_builder)

    def builder_start_refresh_connected():
        """Start the loading of the connected drive info in a new thread."""

        if not thread_manager.is_alive('Refresh connected'):
            thread_manager.start(thread_manager.SINGLE, target=builder_load_connected, name='Refresh connected', daemon=True)

    def builder_add_drives():
        """Add selected connected drives to config builder."""

        global builder_has_pending_changes

        # Get already added drives to prevent adding drives twice
        existing_drive_vids = [tree_builder_configured.item(drive, 'text') for drive in tree_builder_configured.get_children()]

        for drive in tree_current_connected.selection():
            drive_vid = tree_current_connected.item(drive, 'values')[3]
            drive_serial = tree_current_connected.item(drive, 'values')[4]
            drive_size = int(tree_current_connected.item(drive, 'values')[1])

            if drive_vid not in existing_drive_vids:
                builder_has_pending_changes = True
                builder_update_status_bar_save(Status.SAVE_PENDING_CHANGES)
                tree_builder_configured.insert(parent='', index='end', text=drive_vid, values=(human_filesize(drive_size), drive_size, drive_serial))

    def builder_remove_drives():
        """Remove selected connected drives from config builder."""

        global builder_has_pending_changes

        # Remove all selected items from tree
        if len(tree_builder_configured.selection()) > 0:
            builder_has_pending_changes = True
            builder_update_status_bar_save(Status.SAVE_PENDING_CHANGES)

        tree_builder_configured.delete(*tree_builder_configured.selection())

    if window_config_builder is None or not window_config_builder.winfo_exists():
        # Initialize window
        window_config_builder = tk.Toplevel(root)
        window_config_builder.title('Config Builder')
        window_config_builder.resizable(False, False)
        window_config_builder.geometry('960x380')

        if platform.system() == 'Windows':
            window_config_builder.iconbitmap(resource_path('media/icon.ico'))

        center(window_config_builder, root)

        def on_close():
            if not builder_has_pending_changes or messagebox.askokcancel('Discard changes?', 'You have unsaved changes. Are you sure you want to discard them?', parent=window_config_builder):
                window_config_builder.destroy()

        window_config_builder.protocol('WM_DELETE_WINDOW', on_close)

        builder_has_pending_changes = False

        # Add menu bar
        menubar = tk.Menu(root)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label='Open Config', underline=0, accelerator='Ctrl+O', command=builder_open_config_file)
        file_menu.add_command(label='Save Config', underline=0, accelerator='Ctrl+S', command=builder_save_config_file)
        file_menu.add_separator()
        file_menu.add_command(label='Exit', underline=1, command=on_close)
        menubar.add_cascade(label='File', underline=0, menu=file_menu)

        # Selection menu
        selection_menu = tk.Menu(menubar, tearoff=0)
        selection_menu.add_command(label='Add Selected to Config', command=builder_add_drives)
        selection_menu.add_command(label='Remove Selected from Config', command=builder_remove_drives)
        menubar.add_cascade(label='Selection', underline=0, menu=selection_menu)

        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label='Refresh', underline=0, accelerator='F5', command=builder_start_refresh_connected)
        menubar.add_cascade(label='View', underline=0, menu=view_menu)

        window_config_builder.config(menu=menubar)

        # Key bindings
        window_config_builder.bind('<Control-o>', lambda e: builder_open_config_file())
        window_config_builder.bind('<Control-s>', lambda e: builder_save_config_file())
        window_config_builder.bind('<F5>', lambda e: builder_start_refresh_connected())

        RIGHT_ARROW = '>>'
        LEFT_ARROW = '<<'

        main_frame = tk.Frame(window_config_builder)
        main_frame.pack(fill='both', expand=True, padx=WINDOW_ELEMENT_PADDING, pady=(0, WINDOW_ELEMENT_PADDING))
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)

        # Headings
        tk.Label(main_frame, text='Currently Connected').grid(row=0, column=0, pady=WINDOW_ELEMENT_PADDING / 2)
        tk.Label(main_frame, text='Configured for Backup').grid(row=0, column=2, pady=WINDOW_ELEMENT_PADDING / 2)

        tree_current_connected_frame = tk.Frame(main_frame)
        tree_current_connected_frame.grid(row=1, column=0, sticky='ns')

        tree_current_connected = ttk.Treeview(tree_current_connected_frame, columns=('size', 'rawsize', 'configfile', 'vid', 'serial'), style='custom.Treeview')
        tree_current_connected.heading('#0', text='Drive')
        tree_current_connected.column('#0', width=50 if platform.system() == 'Windows' else 150)
        tree_current_connected.heading('size', text='Size')
        tree_current_connected.column('size', width=80)
        tree_current_connected.heading('configfile', text='Config')
        tree_current_connected.column('configfile', width=50)
        tree_current_connected.heading('vid', text='Volume ID')
        tree_current_connected.column('vid', width=90)
        tree_current_connected.heading('serial', text='Serial')
        tree_current_connected.column('serial', width=150 if platform.system() == 'Windows' else 100)
        tree_current_connected['displaycolumns'] = ('size', 'configfile', 'vid', 'serial')

        tree_current_connected.pack(side='left')
        current_select_scroll = ttk.Scrollbar(tree_current_connected_frame, orient='vertical', command=tree_current_connected.yview)
        current_select_scroll.pack(side='left', fill='y')
        tree_current_connected.configure(yscrollcommand=current_select_scroll.set)

        tree_builder_configured_frame = tk.Frame(main_frame)
        tree_builder_configured_frame.grid(row=1, column=2, sticky='ns')

        tree_builder_configured = ttk.Treeview(tree_builder_configured_frame, columns=('size', 'rawsize', 'serial'), style='custom.Treeview')
        tree_builder_configured.heading('#0', text='Volume ID')
        tree_builder_configured.column('#0', width=100)
        tree_builder_configured.heading('size', text='Size')
        tree_builder_configured.column('size', width=80)
        tree_builder_configured.heading('serial', text='Serial')
        tree_builder_configured.column('serial', width=150 if platform.system() == 'Windows' else 100)
        tree_builder_configured['displaycolumns'] = ('size', 'serial')

        tree_builder_configured.pack(side='left')
        buider_configured_select_scroll = ttk.Scrollbar(tree_builder_configured_frame, orient='vertical', command=tree_builder_configured.yview)
        buider_configured_select_scroll.pack(side='left', fill='y')
        tree_builder_configured.configure(yscrollcommand=buider_configured_select_scroll.set)

        # Create tree control pane
        tree_control_frame = tk.Frame(main_frame)
        tree_control_frame.grid(row=1, column=1)

        builder_refresh_btn = ttk.Button(tree_control_frame, text='Refresh', command=builder_start_refresh_connected, style='win.TButton')
        builder_refresh_btn.pack(pady=(0, 50))
        builder_add_btn = ttk.Button(tree_control_frame, text=f"Add {RIGHT_ARROW}", command=builder_add_drives, style='win.TButton')
        builder_add_btn.pack()
        builder_remove_btn = ttk.Button(tree_control_frame, text=f"{LEFT_ARROW} Remove", command=builder_remove_drives, style='win.TButton')
        builder_remove_btn.pack()

        # Create main control pane
        main_control_frame = tk.Frame(main_frame, bg='orange')
        main_control_frame.grid(row=2, column=0, columnspan=3, pady=(WINDOW_ELEMENT_PADDING, 0))

        save_config_btn = ttk.Button(main_control_frame, text='Save config', command=builder_save_config_file, style='win.TButton')
        save_config_btn.pack()

        builder_statusbar_frame = tk.Frame(window_config_builder, bg=uicolor.STATUS_BAR)
        builder_statusbar_frame.pack(fill='x', pady=0)
        builder_statusbar_frame.columnconfigure(50, weight=1)

        # Save status, left side
        builder_statusbar_changes = tk.Label(builder_statusbar_frame, bg=uicolor.STATUS_BAR)
        builder_statusbar_changes.grid(row=0, column=0, padx=6)
        builder_update_status_bar_save(Status.SAVE_ALL_SAVED)

        # Load connected drives
        builder_start_refresh_connected()

def change_source_mode():
    """Change the mode for source selection."""

    prefs.set('source', 'mode', settings_sourceMode.get())

def change_source_type(toggle_type):
    """Change the drive types for source selection.

    Args:
        toggle_type (int): The drive type to toggle.
    """

    selected_local = settings_showDrives_source_local.get()
    selected_network = settings_showDrives_source_network.get()

    # If both selections are unchecked, the last one has just been unchecked
    # In this case, re-check it, so that there's always some selection
    if not selected_local and not selected_network:
        if toggle_type == DRIVE_TYPE_LOCAL:
            settings_showDrives_source_local.set(True)
        elif toggle_type == DRIVE_TYPE_REMOTE:
            settings_showDrives_source_network.set(True)

    prefs.set('selection', 'source_network_drives', settings_showDrives_source_network.get())
    prefs.set('selection', 'source_local_drives', settings_showDrives_source_local.get())

    load_source_in_background()

def change_destination_type(toggle_type):
    """Change the drive types for source selection.

    Args:
        toggle_type (int): The drive type to toggle.
    """

    selected_local = settings_showDrives_dest_local.get()
    selected_network = settings_showDrives_dest_network.get()

    # If both selections are unchecked, the last one has just been unchecked
    # In this case, re-check it, so that there's always some selection
    if not selected_local and not selected_network:
        if toggle_type == DRIVE_TYPE_LOCAL:
            settings_showDrives_dest_local.set(True)
        elif toggle_type == DRIVE_TYPE_REMOTE:
            settings_showDrives_dest_network.set(True)

    prefs.set('selection', 'destination_network_drives', settings_showDrives_dest_network.get())
    prefs.set('selection', 'destination_local_drives', settings_showDrives_dest_local.get())

    load_dest_in_background()

############
# GUI Mode #
############

file_detail_list = {
    'delete': [],
    'copy': [],
    'deleteSuccess': [],
    'deleteFail': [],
    'success': [],
    'fail': []
}

if not config['cliMode']:
    os.system('')

    update_handler = UpdateHandler(
        current_version=APP_VERSION,
        status_change_fn=update_status_bar_update,
        update_callback=check_for_updates
    )

    def resource_path(relative_path):
        """Get absolute path to resource, works for dev and for PyInstaller."""

        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)

    root = tk.Tk()
    root.title('BackDrop - Network Drive Backup Tool')
    root.resizable(False, False)
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 720
    root.geometry(f'{WINDOW_WIDTH}x{WINDOW_HEIGHT}')

    appicon_image = ImageTk.PhotoImage(Image.open(resource_path('media/icon.png')))

    if platform.system() == 'Windows':
        root.iconbitmap(resource_path('media/icon.ico'))
    elif platform.system() == 'Linux':
        root.iconphoto(True, appicon_image)

    center(root)

    default_font = tkfont.nametofont("TkDefaultFont")
    default_font.configure(size=9)
    heading_font = tkfont.nametofont("TkHeadingFont")
    heading_font.configure(size=9, weight='normal')
    menu_font = tkfont.nametofont("TkMenuFont")
    menu_font.configure(size=9)

    # Create Color class instance for UI
    uicolor = Color(root, prefs.get('ui', 'darkMode', False, data_type=Config.BOOLEAN))

    if uicolor.is_dark_mode():
        root.tk_setPalette(background=uicolor.BG)

    # Navigation arrow glyphs
    right_nav_arrow = ImageTk.PhotoImage(Image.open(resource_path(f"media/right_nav{'_light' if uicolor.is_dark_mode() else ''}.png")))
    down_nav_arrow = ImageTk.PhotoImage(Image.open(resource_path(f"media/down_nav{'_light' if uicolor.is_dark_mode() else ''}.png")))

    main_frame = tk.Frame(root)
    main_frame.pack(fill='both', expand=1, padx=WINDOW_ELEMENT_PADDING, pady=(WINDOW_ELEMENT_PADDING / 2, WINDOW_ELEMENT_PADDING))

    statusbar_frame = tk.Frame(root, bg=uicolor.STATUS_BAR)
    statusbar_frame.pack(fill='x', pady=0)
    statusbar_frame.columnconfigure(50, weight=1)

    # Selection and backup status, left side
    statusbar_selection = tk.Label(statusbar_frame, bg=uicolor.STATUS_BAR)
    statusbar_selection.grid(row=0, column=0, padx=6)
    update_status_bar_selection()
    statusbar_backup = tk.Label(statusbar_frame, bg=uicolor.STATUS_BAR)
    statusbar_backup.grid(row=0, column=1, padx=6)
    update_status_bar_backup(Status.BACKUP_IDLE)

    # Update status, right side
    statusbar_update = tk.Label(statusbar_frame, text='', bg=uicolor.STATUS_BAR)
    statusbar_update.grid(row=0, column=100, padx=6)
    statusbar_update.bind('<Button-1>', lambda e: display_update_screen(update_info))

    # Set some default styling
    tk_style = ttk.Style()
    if platform.system() == 'Windows':
        tk_style.theme_use('vista')
    elif platform.system() == 'Linux':
        tk_style.theme_use('clam')
    tk_style.configure('TButton', padding=(6, 4))
    tk_style.configure('danger.TButton', padding=(6, 4), background='#b00')
    tk_style.configure('icon.TButton', width=2, height=1, padding=0, font=(None, 15), background='#00bfe6')

    if platform.system() == 'Linux':
        tk_style.configure('danger.TButton', foreground='#fff', bordercolor='#600', borderwidth=0, padding=(8, 6))
        tk_style.map(
            'danger.TButton',
            # foreground=[('pressed', '#fff'), ('active', '#fff')],
            background=[('pressed', '!disabled', '#900'), ('active', '!disabled', '#c00')]
        )

    tk_style.configure('TCheckbutton', background=uicolor.BG, foreground=uicolor.NORMAL)
    tk_style.configure('TFrame', background=uicolor.BG, foreground=uicolor.NORMAL)

    tk_style.element_create('custom.Treeheading.border', 'from', 'default')
    tk_style.element_create('custom.Treeview.field', 'from', 'clam')
    tk_style.layout('custom.Treeview.Heading', [
        ('custom.Treeheading.cell', {'sticky': 'nswe'}),
        ('custom.Treeheading.border', {'sticky': 'nswe', 'children': [
            ('custom.Treeheading.padding', {'sticky': 'nswe', 'children': [
                ('custom.Treeheading.image', {'side': 'right', 'sticky': ''}),
                ('custom.Treeheading.text', {'sticky': 'we'})
            ]})
        ]}),
    ])
    tk_style.layout('custom.Treeview', [
        ('custom.Treeview.field', {'sticky': 'nswe', 'border': '1', 'children': [
            ('custom.Treeview.padding', {'sticky': 'nswe', 'children': [
                ('custom.Treeview.treearea', {'sticky': 'nswe'})
            ]})
        ]})
    ])
    tk_style.configure('custom.Treeview.Heading', background=uicolor.BGACCENT, foreground=uicolor.FG, padding=2.5)
    tk_style.configure('custom.Treeview', background=uicolor.BGACCENT2, fieldbackground=uicolor.BGACCENT2, foreground=uicolor.FG, bordercolor=uicolor.BGACCENT3)
    tk_style.map('custom.Treeview', foreground=[('disabled', 'SystemGrayText'), ('!disabled', '!selected', uicolor.NORMAL), ('selected', uicolor.BLACK)], background=[('disabled', 'SystemButtonFace'), ('!disabled', '!selected', uicolor.BGACCENT2), ('selected', uicolor.COLORACCENT)])

    tk_style.element_create('custom.Progressbar.trough', 'from', 'clam')
    tk_style.element_create('custom.Progressbar.pbar', 'from', 'default')
    tk_style.layout('custom.Progressbar', [
        ('custom.Progressbar.trough', {'sticky': 'nsew', 'children': [
            ('custom.Progressbar.padding', {'sticky': 'nsew', 'children': [
                ('custom.Progressbar.pbar', {'side': 'left', 'sticky': 'ns'})
            ]})
        ]})
    ])
    tk_style.configure('custom.Progressbar', padding=4, background=uicolor.COLORACCENT, bordercolor=uicolor.BGACCENT3, borderwidth=0, troughcolor=uicolor.BG, lightcolor=uicolor.COLORACCENT, darkcolor=uicolor.COLORACCENT)

    def on_close():
        if thread_manager.is_alive('Backup'):
            if messagebox.askokcancel('Quit?', 'There\'s still a background process running. Are you sure you want to kill it?', parent=root):
                thread_manager.kill('Backup')
                root.quit()
        else:
            root.quit()

    # Add menu bar
    menubar = tk.Menu(root)

    # File menu
    file_menu = tk.Menu(menubar, tearoff=0)
    file_menu.add_command(label='Open Backup Config', underline=0, accelerator='Ctrl+O', command=open_config_file)
    file_menu.add_command(label='Save Backup Config', underline=0, accelerator='Ctrl+S', command=save_config_file)
    file_menu.add_command(label='Save Backup Config As', underline=19, accelerator='Ctrl+Shift+S', command=save_config_file_as)
    file_menu.add_separator()
    file_menu.add_command(label='Exit', underline=1, command=on_close)
    menubar.add_cascade(label='File', underline=0, menu=file_menu)

    # Selection menu
    selection_menu = tk.Menu(menubar, tearoff=0)
    selection_source_select_menu = tk.Menu(selection_menu, tearoff=0)
    settings_showDrives_source_network = tk.BooleanVar(value=prefs.get('selection', 'source_network_drives', default=True, data_type=Config.BOOLEAN))
    settings_showDrives_source_local = tk.BooleanVar(value=prefs.get('selection', 'source_local_drives', default=False, data_type=Config.BOOLEAN))
    selection_source_select_menu.add_checkbutton(label='Network Drives', onvalue=True, offvalue=False, variable=settings_showDrives_source_network, command=lambda: change_source_type(DRIVE_TYPE_REMOTE), selectcolor=uicolor.FG)
    selection_source_select_menu.add_checkbutton(label='Local Drives', onvalue=True, offvalue=False, variable=settings_showDrives_source_local, command=lambda: change_source_type(DRIVE_TYPE_LOCAL), selectcolor=uicolor.FG)
    selection_menu.add_cascade(label='Source Type', menu=selection_source_select_menu)
    selection_dest_select_menu = tk.Menu(selection_menu, tearoff=0)
    settings_showDrives_dest_network = tk.BooleanVar(value=prefs.get('selection', 'destination_network_drives', default=False, data_type=Config.BOOLEAN))
    settings_showDrives_dest_local = tk.BooleanVar(value=prefs.get('selection', 'destination_local_drives', default=True, data_type=Config.BOOLEAN))
    selection_dest_select_menu.add_checkbutton(label='Network Drives', onvalue=True, offvalue=False, variable=settings_showDrives_dest_network, command=lambda: change_destination_type(DRIVE_TYPE_REMOTE), selectcolor=uicolor.FG)
    selection_dest_select_menu.add_checkbutton(label='Local Drives', onvalue=True, offvalue=False, variable=settings_showDrives_dest_local, command=lambda: change_destination_type(DRIVE_TYPE_LOCAL), selectcolor=uicolor.FG)
    selection_menu.add_cascade(label='Destination Type', menu=selection_dest_select_menu)
    selection_source_mode_menu = tk.Menu(selection_menu, tearoff=0)
    settings_sourceMode = tk.StringVar(value=prefs.get('source', 'mode', verify_data=SOURCE_MODE_OPTIONS, default=SOURCE_MODE_SINGLE))
    selection_source_mode_menu.add_checkbutton(label='Single source, select folders', accelerator='WIP', onvalue=SOURCE_MODE_SINGLE, offvalue=SOURCE_MODE_SINGLE, variable=settings_sourceMode, command=change_source_mode, selectcolor=uicolor.FG)
    selection_source_mode_menu.add_checkbutton(label='Show all, select sources', accelerator='WIP', onvalue=SOURCE_MODE_MULTI, offvalue=SOURCE_MODE_MULTI, variable=settings_sourceMode, command=change_source_mode, selectcolor=uicolor.FG)
    selection_menu.add_cascade(label='Source Mode', underline=7, menu=selection_source_mode_menu)
    selection_menu.add_separator()
    selection_menu.add_command(label='Delete Config from Selected Drives', command=delete_config_file_from_selected_drives)
    menubar.add_cascade(label='Selection', underline=0, menu=selection_menu)

    # View menu
    view_menu = tk.Menu(menubar, tearoff=0)
    view_menu.add_command(label='Refresh Source', accelerator='Ctrl+F5', command=load_source_in_background)
    view_menu.add_command(label='Refresh Destination', underline=0, accelerator='F5', command=load_dest_in_background)
    menubar.add_cascade(label='View', underline=0, menu=view_menu)

    # Tools menu
    tools_menu = tk.Menu(menubar, tearoff=0)
    tools_menu.add_command(label='Config Builder', underline=7, accelerator='Ctrl+B', command=show_config_builder)
    menubar.add_cascade(label='Tools', underline=0, menu=tools_menu)

    # Preferences menu
    preferences_menu = tk.Menu(menubar, tearoff=0)
    settings_darkModeEnabled = tk.BooleanVar(value=uicolor.is_dark_mode())
    preferences_menu.add_checkbutton(label='Enable Dark Mode', onvalue=1, offvalue=0, variable=settings_darkModeEnabled, command=lambda: prefs.set('ui', 'darkMode', settings_darkModeEnabled.get()), selectcolor=uicolor.FG)
    menubar.add_cascade(label='Preferences', underline=0, menu=preferences_menu)

    # Help menu
    help_menu = tk.Menu(menubar, tearoff=0)
    help_menu.add_command(label='Check for Updates', command=lambda: thread_manager.start(
        thread_manager.SINGLE,
        target=update_handler.check,
        name='Update Check',
        daemon=True
    ))
    menubar.add_cascade(label='Help', underline=0, menu=help_menu)

    def toggle_file_details_with_hotkey():
        show_file_details_pane.set(not show_file_details_pane.get())
        toggle_file_details_pane()

    # Key bindings
    root.bind('<Control-o>', lambda e: open_config_file())
    root.bind('<Control-s>', lambda e: save_config_file())
    root.bind('<Control-Shift-S>', lambda e: save_config_file_as())
    root.bind('<Control-d>', lambda e: toggle_file_details_with_hotkey())
    root.bind('<Control-b>', lambda e: show_config_builder())

    root.config(menu=menubar)

    icon_windows = ImageTk.PhotoImage(Image.open(resource_path(f"media/windows{'_light' if uicolor.is_dark_mode() else ''}.png")))
    icon_windows_color = ImageTk.PhotoImage(Image.open(resource_path('media/windows_color.png')))
    icon_zip = ImageTk.PhotoImage(Image.open(resource_path(f"media/zip{'_light' if uicolor.is_dark_mode() else ''}.png")))
    icon_zip_color = ImageTk.PhotoImage(Image.open(resource_path('media/zip_color.png')))

    # Progress/status values
    progress_bar = ttk.Progressbar(main_frame, maximum=100, style='custom.Progressbar')
    progress_bar.grid(row=10, column=1, columnspan=3, sticky='ew', pady=(WINDOW_ELEMENT_PADDING, 0))

    progress = Progress(
        progress_bar=progress_bar,
        thread_manager=thread_manager
    )

    source_drive_list_valid = False
    source_drive_default = tk.StringVar()

    # Tree frames for tree and scrollbar
    tree_source_frame = tk.Frame(main_frame)

    tree_source = ttk.Treeview(tree_source_frame, columns=('size', 'rawsize'), style='custom.Treeview')
    tree_source.heading('#0', text='Share')
    tree_source.column('#0', width=170)
    tree_source.heading('size', text='Size')
    tree_source.column('size', width=80)
    tree_source['displaycolumns'] = ('size')

    tree_source.pack(side='left')
    tree_source_scrollbar = ttk.Scrollbar(tree_source_frame, orient='vertical', command=tree_source.yview)
    tree_source_scrollbar.pack(side='left', fill='y')
    tree_source.configure(yscrollcommand=tree_source_scrollbar.set)

    source_meta_frame = tk.Frame(main_frame)
    tk.Grid.columnconfigure(source_meta_frame, 0, weight=1)

    share_space_frame = tk.Frame(source_meta_frame)
    share_space_frame.grid(row=0, column=0)
    share_selected_space = tk.Label(share_space_frame, text='Selected: ' + human_filesize(0))
    share_selected_space.grid(row=0, column=0)
    share_total_space = tk.Label(share_space_frame, text='Total: ~' + human_filesize(0))
    share_total_space.grid(row=0, column=1, padx=(12, 0))

    source_select_frame = tk.Frame(main_frame)
    source_select_menu = ttk.OptionMenu(source_select_frame, source_drive_default, config['sourceDrive'], *tuple([]), command=change_source_drive)
    source_select_menu.pack(side='left')

    tree_source.bind("<<TreeviewSelect>>", calculate_source_size_in_background)

    source_warning = tk.Label(main_frame, text='No source drives are available', font=(None, 14), wraplength=250, bg=uicolor.ERROR, fg=uicolor.BLACK)

    load_source_in_background()
    root.bind('<Control-F5>', lambda x: load_source_in_background())

    tree_dest_frame = tk.Frame(main_frame)
    tree_dest_frame.grid(row=1, column=2, sticky='ns', padx=(WINDOW_ELEMENT_PADDING, 0))

    dest_mode_frame = tk.Frame(main_frame)
    dest_mode_frame.grid(row=0, column=2, pady=(0, WINDOW_ELEMENT_PADDING / 2))

    def toggle_split_mode_with_checkbox():
        """Handle toggling of split mode based on checkbox value."""

        config['splitMode'] = dest_mode_split_check_var.get()

        if not backup or not backup.analysis_started:
            split_mode_status.configure(text=f"Split mode\n{'Enabled' if config['splitMode'] else 'Disabled'}", fg=uicolor.ENABLED if config['splitMode'] else uicolor.DISABLED)

    dest_mode_split_check_var = tk.BooleanVar()

    alt_tooltip_frame = tk.Frame(dest_mode_frame, bg=uicolor.INFO)
    alt_tooltip_frame.pack(side='left', ipadx=WINDOW_ELEMENT_PADDING / 2, ipady=4)
    tk.Label(alt_tooltip_frame, text='Hold ALT when selecting a drive to ignore config files', bg=uicolor.INFO, fg=uicolor.BLACK).pack(fill='y', expand=1)

    # Split mode checkbox
    ttk.Checkbutton(dest_mode_frame, text='Use split mode', variable=dest_mode_split_check_var, command=toggle_split_mode_with_checkbox).pack(side='left', padx=(12, 0))

    tree_dest = ttk.Treeview(tree_dest_frame, columns=('size', 'rawsize', 'configfile', 'vid', 'serial'), style='custom.Treeview')
    tree_dest.heading('#0', text='Drive')
    tree_dest.column('#0', width=50 if platform.system() == 'Windows' else 150)
    tree_dest.heading('size', text='Size')
    tree_dest.column('size', width=80)
    tree_dest.heading('configfile', text='Config')
    tree_dest.column('configfile', width=50)
    tree_dest.heading('vid', text='Volume ID')
    tree_dest.column('vid', width=90)
    tree_dest.heading('serial', text='Serial')
    tree_dest.column('serial', width=200 if platform.system() == 'Windows' else 100)
    tree_dest['displaycolumns'] = ('size', 'configfile', 'vid', 'serial')

    tree_dest.pack(side='left')
    tree_dest_scrollbar = ttk.Scrollbar(tree_dest_frame, orient='vertical', command=tree_dest.yview)
    tree_dest_scrollbar.pack(side='left', fill='y')
    tree_dest.configure(yscrollcommand=tree_dest_scrollbar.set)

    root.bind('<F5>', lambda x: load_dest_in_background())

    # There's an invisible 1px background on buttons. When changing this in icon buttons, it becomes
    # visible, so 1px needs to be added back
    dest_meta_frame = tk.Frame(main_frame)
    dest_meta_frame.grid(row=2, column=2, sticky='nsew', pady=(1, 0))
    tk.Grid.columnconfigure(dest_meta_frame, 0, weight=1)

    dest_split_warning_frame = tk.Frame(main_frame, bg=uicolor.WARNING)
    dest_split_warning_frame.rowconfigure(0, weight=1)
    dest_split_warning_frame.columnconfigure(0, weight=1)
    dest_split_warning_frame.columnconfigure(10, weight=1)

    # TODO: Can this be cleaned up?
    tk.Frame(dest_split_warning_frame).grid(row=0, column=1)
    split_warning_prefix = tk.Label(dest_split_warning_frame, text='There are', bg=uicolor.WARNING, fg=uicolor.BLACK)
    split_warning_prefix.grid(row=0, column=1, sticky='ns')
    split_warning_missing_drive_count = tk.Label(dest_split_warning_frame, text='0', bg=uicolor.WARNING, fg=uicolor.BLACK, font=(None, 18, 'bold'))
    split_warning_missing_drive_count.grid(row=0, column=2, sticky='ns')
    split_warning_suffix = tk.Label(dest_split_warning_frame, text='drives in the config that aren\'t connected. Please connect them, or enable split mode.', bg=uicolor.WARNING, fg=uicolor.BLACK)
    split_warning_suffix.grid(row=0, column=3, sticky='ns')
    tk.Frame(dest_split_warning_frame).grid(row=0, column=10)

    drive_space_frame = tk.Frame(dest_meta_frame)
    drive_space_frame.grid(row=0, column=0)

    config_selected_space_frame = tk.Frame(drive_space_frame)
    config_selected_space_frame.grid(row=0, column=0)
    tk.Label(config_selected_space_frame, text='Config:').pack(side='left')
    config_selected_space = tk.Label(config_selected_space_frame, text='None', fg=uicolor.FADED)
    config_selected_space.pack(side='left')

    drive_selected_space_frame = tk.Frame(drive_space_frame)
    drive_selected_space_frame.grid(row=0, column=1, padx=(12, 0))
    tk.Label(drive_selected_space_frame, text='Selected:').pack(side='left')
    drive_selected_space = tk.Label(drive_selected_space_frame, text=human_filesize(0), fg=uicolor.FADED)
    drive_selected_space.pack(side='left')

    drive_total_space_frame = tk.Frame(drive_space_frame)
    drive_total_space_frame.grid(row=0, column=2, padx=(12, 0))
    tk.Label(drive_total_space_frame, text='Available:').pack(side='left')
    drive_total_space = tk.Label(drive_total_space_frame, text=human_filesize(0), fg=uicolor.FADED)
    drive_total_space.pack(side='left')
    split_mode_status = tk.Label(drive_space_frame, text=f"Split mode\n{'Enabled' if config['splitMode'] else 'Disabled'}", fg=uicolor.ENABLED if config['splitMode'] else uicolor.DISABLED)
    split_mode_status.grid(row=0, column=3, padx=(12, 0))

    drive_select_bind = tree_dest.bind('<<TreeviewSelect>>', select_drive_in_background)

    backup_middle_control_frame = tk.Frame(main_frame)
    backup_middle_control_frame.grid(row=4, column=1, columnspan=2, pady=(0, WINDOW_ELEMENT_PADDING / 2), sticky='ew')

    # Add backup ETA info frame
    backup_eta_frame = tk.Frame(backup_middle_control_frame)
    backup_eta_frame.grid(row=0, column=1)
    tk.Grid.columnconfigure(backup_middle_control_frame, 1, weight=1)

    backup_eta_label = tk.Label(backup_eta_frame, text='Please start a backup to show ETA')
    backup_eta_label.pack()

    # Add activity frame for backup status output
    tk.Grid.rowconfigure(main_frame, 5, weight=1)
    backup_activity_frame = tk.Frame(main_frame)
    backup_activity_frame.grid(row=5, column=1, columnspan=2, sticky='nsew')

    backup_activity_info_canvas = tk.Canvas(backup_activity_frame)
    backup_activity_info_canvas.pack(side='left', fill='both', expand=1)
    backup_activity_scrollbar = ttk.Scrollbar(backup_activity_frame, orient='vertical', command=backup_activity_info_canvas.yview)
    backup_activity_scrollbar.pack(side='left', fill='y')
    backup_activity_scrollable_frame = ttk.Frame(backup_activity_info_canvas)
    backup_activity_scrollable_frame.bind('<Configure>', lambda e: backup_activity_info_canvas.configure(
        scrollregion=backup_activity_info_canvas.bbox('all')
    ))

    backup_activity_info_canvas.create_window((0, 0), window=backup_activity_scrollable_frame, anchor='nw')
    backup_activity_info_canvas.configure(yscrollcommand=backup_activity_scrollbar.set)

    backup_file_details_frame = tk.Frame(main_frame, width=400)
    backup_file_details_frame.grid_propagate(0)

    file_details_pending_delete_header_line = tk.Frame(backup_file_details_frame)
    file_details_pending_delete_header_line.grid(row=0, column=0, sticky='w')
    file_details_pending_delete_header = tk.Label(file_details_pending_delete_header_line, text='Files to delete', font=(None, 11, 'bold'))
    file_details_pending_delete_header.pack()
    file_details_pending_delete_tooltip = tk.Label(file_details_pending_delete_header_line, text='(Click to copy)', fg=uicolor.FADED)
    file_details_pending_delete_tooltip.pack()
    file_details_pending_delete_counter_frame = tk.Frame(backup_file_details_frame)
    file_details_pending_delete_counter_frame.grid(row=1, column=0)
    file_details_pending_delete_counter = tk.Label(file_details_pending_delete_counter_frame, text='0', font=(None, 28))
    file_details_pending_delete_counter.pack(side='left', anchor='s')
    tk.Label(file_details_pending_delete_counter_frame, text='of', font=(None, 11), fg=uicolor.FADED).pack(side='left', anchor='s', pady=(0, 5))
    file_details_pending_delete_counter_total = tk.Label(file_details_pending_delete_counter_frame, text='0', font=(None, 12), fg=uicolor.FADED)
    file_details_pending_delete_counter_total.pack(side='left', anchor='s', pady=(0, 5))

    file_details_pending_copy_header_line = tk.Frame(backup_file_details_frame)
    file_details_pending_copy_header_line.grid(row=0, column=1, sticky='e')
    file_details_pending_copy_header = tk.Label(file_details_pending_copy_header_line, text='Files to copy', font=(None, 11, 'bold'))
    file_details_pending_copy_header.pack()
    file_details_pending_copy_tooltip = tk.Label(file_details_pending_copy_header_line, text='(Click to copy)', fg=uicolor.FADED)
    file_details_pending_copy_tooltip.pack()
    file_details_pending_copy_counter_frame = tk.Frame(backup_file_details_frame)
    file_details_pending_copy_counter_frame.grid(row=1, column=1)
    file_details_pending_copy_counter = tk.Label(file_details_pending_copy_counter_frame, text='0', font=(None, 28))
    file_details_pending_copy_counter.pack(side='left', anchor='s')
    tk.Label(file_details_pending_copy_counter_frame, text='of', font=(None, 11), fg=uicolor.FADED).pack(side='left', anchor='s', pady=(0, 5))
    file_details_pending_copy_counter_total = tk.Label(file_details_pending_copy_counter_frame, text='0', font=(None, 12), fg=uicolor.FADED)
    file_details_pending_copy_counter_total.pack(side='left', anchor='s', pady=(0, 5))

    file_details_copied_header_line = tk.Frame(backup_file_details_frame)
    file_details_copied_header_line.grid(row=2, column=0, columnspan=2, sticky='w')
    file_details_copied_header = tk.Label(file_details_copied_header_line, text='Successful', font=(None, 11, 'bold'))
    file_details_copied_header.pack(side='left')
    file_details_copied_tooltip = tk.Label(file_details_copied_header_line, text='(Click to copy)', fg=uicolor.FADED)
    file_details_copied_tooltip.pack(side='left')
    file_details_copied_frame = tk.Frame(backup_file_details_frame)
    file_details_copied_frame.grid(row=3, column=0, columnspan=2, pady=(0, WINDOW_ELEMENT_PADDING / 2), sticky='nsew')
    file_details_copied_frame.pack_propagate(0)
    file_details_copied_info_canvas = tk.Canvas(file_details_copied_frame)
    file_details_copied_info_canvas.pack(side='left', fill='both', expand=1)
    file_details_copied_scrollbar = ttk.Scrollbar(file_details_copied_frame, orient='vertical', command=file_details_copied_info_canvas.yview)
    file_details_copied_scrollbar.pack(side='left', fill='y')
    file_details_copied_scrollable_frame = ttk.Frame(file_details_copied_info_canvas)
    file_details_copied_scrollable_frame.bind('<Configure>', lambda e: file_details_copied_info_canvas.configure(
        scrollregion=file_details_copied_info_canvas.bbox('all')
    ))

    file_details_copied_info_canvas.create_window((0, 0), window=file_details_copied_scrollable_frame, anchor='nw')
    file_details_copied_info_canvas.configure(yscrollcommand=file_details_copied_scrollbar.set)

    file_details_failed_header_line = tk.Frame(backup_file_details_frame)
    file_details_failed_header_line.grid(row=4, column=0, columnspan=2, sticky='w')
    file_details_failed_header = tk.Label(file_details_failed_header_line, text='Failed', font=(None, 11, 'bold'))
    file_details_failed_header.pack(side='left')
    file_details_failed_tooltip = tk.Label(file_details_failed_header_line, text='(Click to copy)', fg=uicolor.FADED)
    file_details_failed_tooltip.pack(side='left')
    file_details_failed_frame = tk.Frame(backup_file_details_frame)
    file_details_failed_frame.grid(row=5, column=0, columnspan=2, sticky='nsew')
    file_details_failed_frame.pack_propagate(0)
    file_details_failed_info_canvas = tk.Canvas(file_details_failed_frame)
    file_details_failed_info_canvas.pack(side='left', fill='both', expand=1)
    file_details_failed_scrollbar = ttk.Scrollbar(file_details_failed_frame, orient='vertical', command=file_details_failed_info_canvas.yview)
    file_details_failed_scrollbar.pack(side='left', fill='y')
    file_details_failed_scrollable_frame = ttk.Frame(file_details_failed_info_canvas)
    file_details_failed_scrollable_frame.bind('<Configure>', lambda e: file_details_failed_info_canvas.configure(
        scrollregion=file_details_failed_info_canvas.bbox('all')
    ))

    file_details_failed_info_canvas.create_window((0, 0), window=file_details_failed_scrollable_frame, anchor='nw')
    file_details_failed_info_canvas.configure(yscrollcommand=file_details_failed_scrollbar.set)

    # Set grid weights
    tk.Grid.rowconfigure(backup_file_details_frame, 3, weight=2)
    tk.Grid.rowconfigure(backup_file_details_frame, 5, weight=1)
    tk.Grid.columnconfigure(backup_file_details_frame, (0, 1), weight=1)

    # Set click to copy key bindings
    file_details_pending_delete_header.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list['delete']])))
    file_details_pending_delete_tooltip.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list['delete']])))
    file_details_pending_copy_header.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list['copy']])))
    file_details_pending_copy_tooltip.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list['copy']])))
    file_details_copied_header.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list['success']])))
    file_details_copied_tooltip.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list['success']])))
    file_details_failed_header.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list['fail']])))
    file_details_failed_tooltip.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list['fail']])))

    def toggle_file_details_pane():
        root_geom = root.geometry().split('+')
        pos_x = int(root_geom[1])
        pos_y = int(root_geom[2])

        # FIXME: Is fixing the flicker effect here possible?
        if bool(backup_file_details_frame.grid_info()):
            backup_file_details_frame.grid_remove()
            root.geometry(f'{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{pos_x + 400 + WINDOW_ELEMENT_PADDING}+{pos_y}')
        else:
            root.geometry(f'{1600 + WINDOW_ELEMENT_PADDING}x{WINDOW_HEIGHT}+{pos_x - 400 - WINDOW_ELEMENT_PADDING}+{pos_y}')
            backup_file_details_frame.grid(row=0, column=0, rowspan=11, sticky='nsew', padx=(0, WINDOW_ELEMENT_PADDING), pady=(WINDOW_ELEMENT_PADDING / 2, 0))

    show_file_details_pane = tk.BooleanVar()
    view_menu.add_separator()
    view_menu.add_checkbutton(label='File details pane', onvalue=1, offvalue=0, variable=show_file_details_pane, accelerator='Ctrl+D', command=toggle_file_details_pane, selectcolor=uicolor.FG)

    tk.Grid.columnconfigure(main_frame, 3, weight=1)

    right_side_frame = tk.Frame(main_frame)
    right_side_frame.grid(row=0, column=3, rowspan=7, sticky='nsew', pady=(WINDOW_ELEMENT_PADDING / 2, 0))

    backup_summary_frame = tk.Frame(right_side_frame)
    backup_summary_frame.pack(fill='both', expand=1, padx=(WINDOW_ELEMENT_PADDING, 0))
    backup_summary_frame.update()

    branding_frame = tk.Frame(right_side_frame)
    branding_frame.pack()

    image_logo = ImageTk.PhotoImage(Image.open(resource_path(f"media/logo_ui{'_light' if uicolor.is_dark_mode() else ''}.png")))
    tk.Label(branding_frame, image=image_logo).pack(side='left')
    tk.Label(branding_frame, text=f"v{APP_VERSION}", font=(None, 10), fg=uicolor.FADED).pack(side='left', anchor='s', pady=(0, 12))

    tk.Label(backup_summary_frame, text='Analysis Summary', font=(None, 20)).pack()

    # Add placeholder to backup analysis
    backup_summary_text_frame = tk.Frame(backup_summary_frame)
    backup_summary_text_frame.pack(fill='x')
    tk.Label(backup_summary_text_frame, text='This area will summarize the backup that\'s been configured.',
             wraplength=backup_summary_frame.winfo_width() - 2, justify='left').pack(anchor='w')
    tk.Label(backup_summary_text_frame, text='Please start a backup analysis to generate a summary.',
             wraplength=backup_summary_frame.winfo_width() - 2, justify='left').pack(anchor='w')
    backup_summary_button_frame = tk.Frame(backup_summary_frame)
    backup_summary_button_frame.pack(pady=WINDOW_ELEMENT_PADDING / 2)
    start_analysis_btn = ttk.Button(backup_summary_button_frame, text='Analyze', width=7, command=start_backup_analysis, state='normal' if source_drive_list_valid else 'disabled')
    start_analysis_btn.pack(side='left', padx=4)
    start_backup_btn = ttk.Button(backup_summary_button_frame, text='Run Backup', command=start_backup, state='disable')
    start_backup_btn.pack(side='left', padx=4)

    # QUESTION: Does init load_dest @thread_type need to be SINGLE, MULTIPLE, or OVERRIDE?
    thread_manager.start(thread_manager.SINGLE, is_progress_thread=True, target=load_dest, name='Init', daemon=True)

    # Check for updates on startup
    thread_manager.start(
        thread_manager.SINGLE,
        target=update_handler.check,
        name='Update Check',
        daemon=True
    )

    root.protocol('WM_DELETE_WINDOW', on_close)
    root.mainloop()
