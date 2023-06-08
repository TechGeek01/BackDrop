import platform
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, font as tkfont, filedialog
import shutil
import os
import subprocess
import webbrowser
from blake3 import blake3
import ctypes
from signal import signal, SIGINT
from datetime import datetime
import re
import pickle
import clipboard
from pynput import keyboard
from PIL import Image, ImageTk
if platform.system() == 'Windows':
    import pythoncom
    import win32api
    import win32file
    import wmi
import logging

from bin.fileutils import FileUtils, human_filesize, get_directory_size, do_delete
from bin.threadmanager import ThreadManager
from bin.config import Config
from bin.progress import Progress
from bin.backup import Backup
from bin.repeatedtimer import RepeatedTimer
from bin.update import UpdateHandler
from bin.uielements import RootWindow, AppWindow, DetailBlock, BackupDetailBlock, TabbedFrame, ScrollableFrame, resource_path
from bin.status import Status

def on_press(key):
    """Do things when keys are pressed.

    Args:
        key (keyboard.Key): The key that was pressed.
    """

    global keypresses

    if key == keyboard.Key.alt_l:
        keypresses['AltL'] = True
    if key == keyboard.Key.alt_r:
        keypresses['AltR'] = True
    if key == keyboard.Key.alt_gr:
        keypresses['AltGr'] = True

    if keypresses['AltL'] or keypresses['AltR'] or keypresses['AltGr']:
        keypresses['Alt'] = True

def on_release(key):
    """Do things when keys are pressed.

    Args:
        key (keyboard.Key): The key that was released.
    """

    global keypresses

    if key == keyboard.Key.alt_l:
        keypresses['AltL'] = False
    if key == keyboard.Key.alt_r:
        keypresses['AltR'] = False
    if key == keyboard.Key.alt_gr:
        keypresses['AltGr'] = False

    if not keypresses['AltL'] and not keypresses['AltR'] and not keypresses['AltGr']:
        keypresses['Alt'] = False


def update_file_detail_lists(list_name, files):
    """Update the file lists for the detail file view.

    Args:
        list_name (String): The list name to update.
        filename (set): The file path to add to the list.
    """

    # Ignore empty filename sets
    if not files:
        return

    for filename in files:
        file_detail_list[list_name].append({
            'displayName': filename.split(os.path.sep)[-1],
            'filename': filename
        })

    if list_name == FileUtils.LIST_TOTAL_DELETE:
        file_details_pending_delete_counter.configure(text=str(len(file_detail_list[FileUtils.LIST_TOTAL_DELETE])))
        file_details_pending_delete_counter_total.configure(text=str(len(file_detail_list[FileUtils.LIST_TOTAL_DELETE])))
    elif list_name == FileUtils.LIST_TOTAL_COPY:
        file_details_pending_copy_counter.configure(text=str(len(file_detail_list[FileUtils.LIST_TOTAL_COPY])))
        file_details_pending_copy_counter_total.configure(text=str(len(file_detail_list[FileUtils.LIST_TOTAL_COPY])))
    elif list_name in [FileUtils.LIST_DELETE_SUCCESS, FileUtils.LIST_DELETE_FAIL, FileUtils.LIST_SUCCESS, FileUtils.LIST_FAIL]:
        # Remove file from delete list
        file_detail_list_name = FileUtils.LIST_TOTAL_COPY if list_name in [FileUtils.LIST_SUCCESS, FileUtils.LIST_FAIL] else FileUtils.LIST_TOTAL_DELETE
        filename_list = [file['filename'] for file in file_detail_list[file_detail_list_name]]
        for filename in files:
            if filename in filename_list:
                del file_detail_list[file_detail_list_name][filename_list.index(filename)]

        # Update file counter
        if list_name in [FileUtils.LIST_SUCCESS, FileUtils.LIST_FAIL]:
            file_details_pending_copy_counter.configure(text=str(len(file_detail_list[file_detail_list_name])))
        else:
            file_details_pending_delete_counter.configure(text=str(len(file_detail_list[file_detail_list_name])))

        # Update copy list scrollable
        filenames = '\n'.join([filename.split(os.path.sep)[-1] for filename in files])
        if list_name in [FileUtils.LIST_SUCCESS, FileUtils.LIST_DELETE_SUCCESS]:
            tk.Label(file_details_copied.frame, text=filenames, fg=root_window.uicolor.NORMAL if list_name in [FileUtils.LIST_SUCCESS, FileUtils.LIST_FAIL] else root_window.uicolor.FADED, anchor='w').pack(fill='x', expand=True)
            file_details_copied_counter.configure(text=len(file_detail_list[FileUtils.LIST_SUCCESS]) + len(file_detail_list[FileUtils.LIST_DELETE_SUCCESS]))

            # Remove all but the most recent 250 items for performance reasons
            file_details_copied.show_items(250)
        else:
            tk.Label(file_details_failed.frame, text=filenames, fg=root_window.uicolor.NORMAL if list_name in [FileUtils.LIST_SUCCESS, FileUtils.LIST_FAIL] else root_window.uicolor.FADED, anchor='w').pack(fill='x', expand=True)
            file_details_failed_counter.configure(text=len(file_detail_list[FileUtils.LIST_FAIL]) + len(file_detail_list[FileUtils.LIST_DELETE_FAIL]))

            # Update counter in status bar
            FAILED_FILE_COUNT = len(file_detail_list[FileUtils.LIST_FAIL]) + len(file_detail_list[FileUtils.LIST_DELETE_FAIL])
            statusbar_counter_btn.configure(text=f"{FAILED_FILE_COUNT} failed", state='normal' if FAILED_FILE_COUNT > 0 else 'disabled')

            # HACK: The scroll yview won't see the label instantly after it's packed.
            # Sleeping for a brief time fixes that. This is acceptable as long as it's
            # not run in the main thread, else the UI will hang.
            file_details_failed.show_items()

backup_error_log = []

def display_backup_progress(copied, total, display_filename=None, operation=None, display_index: int = None):
    """Display the copy progress of a transfer

    Args:
        copied (int): the number of bytes copied.
        total (int): The total file size.
        display_filename (String): The filename to display inthe GUI (optional).
        operation (String): The mode to display the progress in (optional).
        display_index (int): The index to display the item in the GUI (optional).
    """

    if copied > total:
        copied = total

    if total > 0:
        percent_copied = copied / total * 100
    else:
        percent_copied = 100

    # If display index has been specified, write progress to GUI
    if display_index is not None:
        if operation == Status.FILE_OPERATION_DELETE:
            progress.set(current=backup.progress['current'])
            cmd_info_blocks[display_index].configure('progress', text=f"Deleted {display_filename}", fg=root_window.uicolor.NORMAL)
        elif operation == Status.FILE_OPERATION_COPY:
            progress.set(current=backup.progress['current'])
            cmd_info_blocks[display_index].configure('progress', text=f"{percent_copied:.2f}% \u27f6 {human_filesize(copied)} of {human_filesize(total)}", fg=root_window.uicolor.NORMAL)
        elif operation == Status.FILE_OPERATION_VERIFY:
            progress.set(current=backup.progress['current'])
            cmd_info_blocks[display_index].configure('progress', text=f"Verifying \u27f6 {percent_copied:.2f}% \u27f6 {human_filesize(copied)} of {human_filesize(total)}", fg=root_window.uicolor.BLUE)

def get_backup_killflag() -> bool:
    """Get backup thread kill flag status.

    Returns:
        bool: The kill flag of the backup thread.
    """
    return thread_manager.threadlist['Backup']['killFlag']

def display_backup_summary_chunk(title, payload: tuple, reset: bool = None):
    """Display a chunk of a backup analysis summary to the user.

    Args:
        title (String): The heading title of the chunk.
        payload (tuple[]): The chunks of data to display.
        payload tuple[0]: The subject of the data line.
        payload tuple[1]: The data to associate to the subject.
        reset (bool): Whether to clear the summary frame first (default: False).
    """

    if reset is None:
        reset = False

    if reset:
        content_tab_frame.tab['summary']['content'].empty()

    tk.Label(content_tab_frame.tab['summary']['content'].frame, text=title, font=(None, 14),
             wraplength=content_tab_frame.tab['summary']['width'] - 2, justify='left').pack(anchor='w')
    summary_frame = tk.Frame(content_tab_frame.tab['summary']['content'].frame)
    summary_frame.pack(fill='x', expand=True)
    summary_frame.columnconfigure(2, weight=1)

    for i, item in enumerate(payload):
        if len(item) > 2:
            text_color = root_window.uicolor.NORMAL if item[2] else root_window.uicolor.FADED
        else:
            text_color = root_window.uicolor.NORMAL

        tk.Label(summary_frame, text=item[0], fg=text_color, justify='left').grid(row=i, column=0, sticky='w')
        tk.Label(summary_frame, text='\u27f6', fg=text_color, justify='left').grid(row=i, column=1, sticky='w')
        wrap_frame = tk.Frame(summary_frame)
        wrap_frame.grid(row=i, column=2, sticky='ew')
        tk.Label(summary_frame, text=item[1], fg=text_color, justify='left').grid(row=i, column=2, sticky='w')

# QUESTION: Instead of the copy function handling display, can it just set variables, and have the timer handle all the UI stuff?
def update_backup_eta_timer(progress_info):
    """Update the backup timer to show ETA.

    Args:
        progress_info: The progress of the current backup
    """

    if backup.status == Status.BACKUP_ANALYSIS_RUNNING or backup.status == Status.BACKUP_ANALYSIS_FINISHED:
        backup_eta_label.configure(text='Analysis in progress. Please wait...', fg=root_window.uicolor.NORMAL)
    elif backup.status == Status.BACKUP_IDLE or backup.status == Status.BACKUP_ANALYSIS_ABORTED:
        backup_eta_label.configure(text='Please start a backup to show ETA', fg=root_window.uicolor.NORMAL)
    elif backup.status == Status.BACKUP_BACKUP_RUNNING:
        # Total is copy source, verify dest, so total data is 2 * copy
        total_to_copy = progress_info['total']['total'] - progress_info['total']['delete_total']

        running_time = datetime.now() - backup.get_backup_start_time()
        if total_to_copy > 0:
            percent_copied = progress_info['total']['current'] / total_to_copy
        else:
            percent_copied = 0

        if percent_copied > 0:
            remaining_time = running_time / percent_copied - running_time
        else:
            # Show infinity symbol if no calculated ETA
            remaining_time = '\u221e'

        backup_eta_label.configure(text=f"{str(running_time).split('.')[0]} elapsed \u27f6 {str(remaining_time).split('.')[0]} remaining", fg=root_window.uicolor.NORMAL)
    elif backup.status == Status.BACKUP_BACKUP_ABORTED:
        backup_eta_label.configure(text=f"Backup aborted in {str(datetime.now() - backup.get_backup_start_time()).split('.')[0]}", fg=root_window.uicolor.STOPPED)
    elif backup.status == Status.BACKUP_BACKUP_FINISHED:
        backup_eta_label.configure(text=f"Backup completed successfully in {str(datetime.now() - backup.get_backup_start_time()).split('.')[0]}", fg=root_window.uicolor.FINISHED)

def display_backup_command_info(display_command_list: list) -> list:
    """Enumerate the display widget with command info after a backup analysis.

    Args:
        display_command_list (list): The command list to pull data from.
    """

    global cmd_info_blocks

    content_tab_frame.tab['details']['content'].empty()

    cmd_info_blocks = []
    for i, item in enumerate(display_command_list):
        if item['type'] == Backup.COMMAND_TYPE_FILE_LIST:
            if item['mode'] == Status.FILE_OPERATION_DELETE:
                cmd_header_text = f"Delete {len(item['list'])} files from {item['drive']}"
            elif item['mode'] == Status.FILE_OPERATION_UPDATE:
                cmd_header_text = f"Update {len(item['list'])} files on {item['drive']}"
            elif item['mode'] == Status.FILE_OPERATION_COPY:
                cmd_header_text = f"Copy {len(item['list'])} new files to {item['drive']}"
            else:
                cmd_header_text = f"Work with {len(item['list'])} files on {item['drive']}"

        backup_summary_block = BackupDetailBlock(
            parent=content_tab_frame.tab['details']['content'].frame,
            title=cmd_header_text,
            backup=backup,
            uicolor=root_window.uicolor  # FIXME: Is there a better way to do this than to pass the uicolor instance from RootWindow into this?
        )
        backup_summary_block.pack(anchor='w', expand=1)

        if item['type'] == Backup.COMMAND_TYPE_FILE_LIST:
            # Handle list trimming
            list_font = tkfont.Font(family=None, size=10, weight='normal')
            trimmed_file_list = ', '.join(item['list'])[:250]
            MAX_WIDTH = content_tab_frame.tab['details']['width'] * 0.8
            actual_file_width = list_font.measure(trimmed_file_list)

            if actual_file_width > MAX_WIDTH:
                while actual_file_width > MAX_WIDTH and len(trimmed_file_list) > 1:
                    trimmed_file_list = trimmed_file_list[:-1]
                    actual_file_width = list_font.measure(f'{trimmed_file_list}...')
                trimmed_file_list = f'{trimmed_file_list}...'

            backup_summary_block.add_line('file_size', 'Total size', human_filesize(item['size']))
            backup_summary_block.add_copy_line('file_list', 'File list', trimmed_file_list, '\n'.join(item['list']))
            backup_summary_block.add_line('current_file', 'Current file', 'Pending' if item['enabled'] else 'Skipped', fg=root_window.uicolor.PENDING if item['enabled'] else root_window.uicolor.FADED)
            backup_summary_block.add_line('progress', 'Progress', 'Pending' if item['enabled'] else 'Skipped', fg=root_window.uicolor.PENDING if item['enabled'] else root_window.uicolor.FADED)

        cmd_info_blocks.append(backup_summary_block)

def backup_reset_ui():
    """Reset the UI when we run a backup analysis."""

    # Empty backup error log
    backup_error_log.clear()

    # Empty backup summary pane
    content_tab_frame.tab['summary']['content'].empty()

    # Empty backup operation list pane
    content_tab_frame.tab['details']['content'].empty()

    # Clear file lists for file details pane
    [file_detail_list[list_name].clear() for list_name in file_detail_list]

    # Reset file details counters
    file_details_pending_delete_counter.configure(text='0')
    file_details_pending_delete_counter_total.configure(text='0')
    file_details_pending_copy_counter.configure(text='0')
    file_details_pending_copy_counter_total.configure(text='0')
    file_details_copied_counter.configure(text='0')
    file_details_failed_counter.configure(text='0')

    # Empty file details list panes
    file_details_copied.empty()
    file_details_failed.empty()

def request_kill_analysis():
    """Kill a running analysis."""

    statusbar_action.configure(text='Stopping analysis')
    if backup:
        backup.kill(Backup.KILL_ANALYSIS)

def start_backup_analysis():
    """Start the backup analysis in a separate thread."""

    global backup

    # FIXME: If backup @analysis @thread is already running, it needs to be killed before it's rerun
    # CAVEAT: This requires some way to have the @analysis @thread itself check for the kill flag and break if it's set.
    if (backup and backup.is_running()) or verification_running or not source_avail_drive_list:
        return

    backup_reset_ui()
    statusbar_counter_btn.configure(text='0 failed', state='disabled')
    statusbar_details.configure(text='')

    backup = Backup(
        config=config,
        backup_config_dir=BACKUP_CONFIG_DIR,
        backup_config_file=BACKUP_CONFIG_FILE,
        analysis_pre_callback_fn=update_ui_pre_analysis,
        analysis_callback_fn=update_ui_post_analysis,
        backup_callback_fn=update_ui_post_backup
    )

    thread_manager.start(ThreadManager.KILLABLE, target=backup.analyze, name='Backup Analysis', daemon=True)

def get_source_drive_list() -> list:
    """Get the list of available source drives.

    Returns:
        list: The list of source drives.
    """

    source_avail_drive_list = []

    if SYS_PLATFORM == PLATFORM_WINDOWS:
        drive_list = win32api.GetLogicalDriveStrings().split('\000')[:-1]
        drive_type_list = []
        if prefs.get('selection', 'source_network_drives', default=False, data_type=Config.BOOLEAN):
            drive_type_list.append(DRIVE_TYPE_REMOTE)
        if prefs.get('selection', 'source_local_drives', default=True, data_type=Config.BOOLEAN):
            drive_type_list.append(DRIVE_TYPE_FIXED)
            drive_type_list.append(DRIVE_TYPE_REMOVABLE)
        source_avail_drive_list = [drive[:2] for drive in drive_list if win32file.GetDriveType(drive) in drive_type_list and drive[:2] != SYSTEM_DRIVE]
    elif SYS_PLATFORM == PLATFORM_LINUX:
        local_selected = prefs.get('selection', 'source_local_drives', default=True, data_type=Config.BOOLEAN)
        network_selected = prefs.get('selection', 'source_network_drives', default=False, data_type=Config.BOOLEAN)

        if network_selected and not local_selected:
            cmd = ['df', '-tcifs', '-tnfs', '--output=target']
        elif local_selected and not network_selected:
            cmd = ['df', '-xtmpfs', '-xsquashfs', '-xdevtmpfs', '-xcifs', '-xnfs', '--output=target']
        elif local_selected and network_selected:
            cmd = ['df', '-xtmpfs', '-xsquashfs', '-xdevtmpfs', '--output=target']

        out = subprocess.run(cmd,
                             stdout=subprocess.PIPE,
                             stdin=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        logical_drive_list = out.stdout.decode('utf-8').split('\n')[1:]
        logical_drive_list = [mount for mount in logical_drive_list if mount]

        # Filter system drive out from available selection
        source_avail_drive_list = []
        for drive in logical_drive_list:
            drive_name = f'"{drive}"'

            out = subprocess.run("mount | grep " + drive_name + " | awk 'NR==1{print $1}' | sed 's/[0-9]*//g'",
                                 stdout=subprocess.PIPE,
                                 stdin=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 shell=True)
            physical_disk = out.stdout.decode('utf-8').split('\n')[0].strip()

            # Only process mount point if it's not on the system drive
            if physical_disk != SYSTEM_DRIVE and drive != '/':
                source_avail_drive_list.append(drive)

    return source_avail_drive_list

def load_source():
    """Load the source drive and share lists, and display shares in the tree."""

    global PREV_SOURCE_DRIVE
    global source_avail_drive_list

    progress.start_indeterminate()

    # Empty tree in case this is being refreshed
    tree_source.delete(*tree_source.get_children())

    if not source_warning.grid_info() and not tree_source_frame.grid_info():
        tree_source_frame.grid(row=1, column=1, sticky='ns')
        source_meta_frame.grid(row=2, column=1, sticky='nsew', pady=(WINDOW_ELEMENT_PADDING / 2, 0))

    source_avail_drive_list = get_source_drive_list()

    if source_avail_drive_list or settings_sourceMode.get() in [Config.SOURCE_MODE_SINGLE_PATH, Config.SOURCE_MODE_MULTI_PATH]:
        # Display empty selection sizes
        share_selected_space.configure(text='None', fg=root_window.uicolor.FADED)
        share_total_space.configure(text='~None', fg=root_window.uicolor.FADED)

        source_warning.grid_forget()
        tree_source_frame.grid(row=1, column=1, sticky='ns')
        source_meta_frame.grid(row=2, column=1, sticky='nsew', pady=(WINDOW_ELEMENT_PADDING / 2, 0))

        selected_source_mode = prefs.get('selection', 'source_mode', Config.SOURCE_MODE_SINGLE_DRIVE, verify_data=Config.SOURCE_MODE_OPTIONS)

        if selected_source_mode == Config.SOURCE_MODE_SINGLE_DRIVE:
            config['source_drive'] = prefs.get('selection', 'source_drive', source_avail_drive_list[0], verify_data=source_avail_drive_list)

            source_select_custom_single_frame.pack_forget()
            source_select_custom_multi_frame.pack_forget()
            source_select_multi_frame.pack_forget()
            source_select_single_frame.pack()

            source_drive_default.set(config['source_drive'])
            PREV_SOURCE_DRIVE = config['source_drive']
            source_select_menu.config(state='normal')
            source_select_menu.set_menu(config['source_drive'], *tuple(source_avail_drive_list))

            # Enumerate list of shares in source
            if SYS_PLATFORM == PLATFORM_WINDOWS:
                config['source_drive'] = config['source_drive'] + os.path.sep

            for directory in next(os.walk(config['source_drive']))[1]:
                tree_source.insert(parent='', index='end', text=directory, values=('Unknown', 0))
        elif selected_source_mode == Config.SOURCE_MODE_MULTI_DRIVE:
            source_select_single_frame.pack_forget()
            source_select_custom_single_frame.pack_forget()
            source_select_custom_multi_frame.pack_forget()
            source_select_multi_frame.pack()

            # Enumerate list of shares in source
            for drive in source_avail_drive_list:
                drive_name = prefs.get('source_names', drive, default='')
                tree_source.insert(parent='', index='end', text=drive, values=('Unknown', 0, drive_name))
        elif selected_source_mode == Config.SOURCE_MODE_SINGLE_PATH:
            source_select_single_frame.pack_forget()
            source_select_multi_frame.pack_forget()
            source_select_custom_multi_frame.pack_forget()
            source_select_custom_single_frame.pack(fill='x', expand=1)

            if not source_select_frame.grid_info():
                source_select_frame.grid(row=0, column=1, pady=(0, WINDOW_ELEMENT_PADDING / 2), sticky='ew')

            if config['source_drive'] and os.path.isdir(config['source_drive']):
                for directory in next(os.walk(config['source_drive']))[1]:
                    # QUESTION: Should files be allowed in custom source?
                    tree_source.insert(parent='', index='end', text=directory, values=('Unknown', 0))
        elif selected_source_mode == Config.SOURCE_MODE_MULTI_PATH:
            source_select_single_frame.pack_forget()
            source_select_multi_frame.pack_forget()
            source_select_custom_single_frame.pack_forget()
            source_select_custom_multi_frame.pack(fill='x', expand=1)

            if not source_select_frame.grid_info():
                source_select_frame.grid(row=0, column=1, pady=(0, WINDOW_ELEMENT_PADDING / 2), sticky='ew')

    elif settings_sourceMode.get() in [Config.SOURCE_MODE_SINGLE_DRIVE, Config.SOURCE_MODE_MULTI_DRIVE]:
        source_drive_default.set('No drives available')

        tree_source_frame.grid_forget()
        source_meta_frame.grid_forget()
        source_select_frame.grid_forget()
        source_warning.grid(row=0, column=1, rowspan=3, sticky='nsew', padx=10, pady=10, ipadx=20, ipady=20)

    progress.stop_indeterminate()

def load_source_in_background():
    """Start a source refresh in a new thread."""

    if (backup and backup.is_running()) or thread_manager.is_alive('Refresh Source'):
        return

    thread_manager.start(ThreadManager.SINGLE, is_progress_thread=True, target=load_source, name='Refresh Source', daemon=True)

def change_source_drive(selection):
    """Change the source drive to pull shares from to a new selection.

    Args:
        selection (String): The selection to set as the default.
    """

    global PREV_SOURCE_DRIVE
    global config

    # If backup is running, ignore request to change
    if backup and backup.is_running():
        source_select_menu.set_menu(config['source_drive'], *tuple(source_avail_drive_list))
        return

    # Invalidate analysis validation
    reset_analysis_output()

    config['source_drive'] = selection
    PREV_SOURCE_DRIVE = selection
    prefs.set('selection', 'source_drive', selection)

    load_source_in_background()

    # If a drive type is selected for both source and destination, reload
    # destination so that the source drive doesn't show in destination list
    if ((settings_showDrives_source_local.get() and settings_showDrives_dest_local.get())  # Local selected
            or (settings_showDrives_source_network.get() and settings_showDrives_dest_network.get())):  # Network selected
        load_dest_in_background()

def reset_analysis_output():
    content_tab_frame.tab['summary']['content'].empty()
    content_tab_frame.tab['details']['content'].empty()

    tk.Label(content_tab_frame.tab['summary']['content'].frame, text='This area will summarize the backup that\'s been configured.',
             wraplength=content_tab_frame.tab['summary']['width'] - 2, justify='left').pack(anchor='w')
    tk.Label(content_tab_frame.tab['summary']['content'].frame, text='Please start a backup analysis to generate a summary.',
             wraplength=content_tab_frame.tab['summary']['width'] - 2, justify='left').pack(anchor='w')

# IDEA: @Calculate total space of all @shares in background
def select_source():
    """Calculate and display the filesize of a selected share, if it hasn't been calculated.

    This gets the selection in the source tree, and then calculates the filesize for
    all shares selected that haven't yet been calculated. The summary of total
    selection, and total share space is also shown below the tree.
    """

    global prev_source_selection
    global source_select_bind
    global backup

    def update_share_size(item):
        """Update share info for a given share.

        Args:
            item (String): The identifier for a share in the source tree to be calculated.
        """

        # FIXME: This crashes if you change the source drive, and the number of items in the tree changes while it's calculating things
        share_name = tree_source.item(item, 'text')

        if settings_sourceMode.get() in [Config.SOURCE_MODE_SINGLE_DRIVE, Config.SOURCE_MODE_SINGLE_PATH]:
            share_path = os.path.join(config['source_drive'], share_name)
        elif settings_sourceMode.get() in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
            share_path = share_name

        share_dir_size = get_directory_size(share_path)
        tree_source.set(item, 'size', human_filesize(share_dir_size))
        tree_source.set(item, 'rawsize', share_dir_size)

        # After calculating share info, update the meta info
        selected_total = 0
        selected_share_list = []
        for item in tree_source.selection():
            # Write selected shares to config
            share_info = {
                'size': int(tree_source.item(item, 'values')[1])
            }

            if settings_sourceMode.get() in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
                share_info['path'] = tree_source.item(item, 'text')

                share_vals = tree_source.item(item, 'values')

                if SYS_PLATFORM == PLATFORM_WINDOWS:
                    # Windows uses drive letters, so default name is letter
                    default_name = tree_source.item(item, 'text')[0]
                elif SYS_PLATFORM == PLATFORM_LINUX:
                    # Linux uses mount points, so get last dir name
                    default_name = tree_source.item(item, 'text').split(os.path.sep)[-1]

                share_info['dest_name'] = share_vals[2] if len(share_vals) >= 3 and share_vals[2] else default_name
            else:
                # If single drive mode, use share name as dest name
                share_info['path'] = os.path.join(config['source_drive'], tree_source.item(item, 'text'))
                share_info['dest_name'] = tree_source.item(item, 'text')

            selected_share_list.append(share_info)

            # Add total space of selection
            if tree_source.item(item, 'values')[0] != 'Unknown':
                # Add total space of selection
                share_size = tree_source.item(item, 'values')[1]
                selected_total = selected_total + int(share_size)

        share_selected_space.configure(text=human_filesize(selected_total), fg=root_window.uicolor.NORMAL if selected_total > 0 else root_window.uicolor.FADED)
        config['sources'] = selected_share_list

        share_total = 0
        is_total_approximate = False
        total_prefix = ''
        for item in tree_source.get_children():
            share_total += int(tree_source.item(item, 'values')[1])

            # If total is not yet approximate, check if the item hasn't been calculated
            if not is_total_approximate and tree_source.item(item, 'values')[0] == 'Unknown':
                is_total_approximate = True
                total_prefix += '~'

        share_total_space.configure(text=total_prefix + human_filesize(share_total), fg=root_window.uicolor.NORMAL if share_total > 0 else root_window.uicolor.FADED)

        # If everything's calculated, enable analysis button to be clicked
        # IDEA: Is it better to assume calculations are out of date, and always calculate on the fly during analysis?
        share_size_list = [tree_source.item(item, 'values')[0] for item in tree_source.selection()]
        if 'Unknown' not in share_size_list:
            start_analysis_btn.configure(state='normal')
            update_status_bar_selection()

        progress.stop_indeterminate()

    if not backup or not backup.is_running():
        progress.start_indeterminate()

        # If analysis was run, invalidate it
        reset_analysis_output()

        selected = tree_source.selection()

        new_shares = []
        if selected:
            for item in selected:
                share_info = {
                    'size': int(tree_source.item(item, 'values')[1]) if tree_source.item(item, 'values')[0] != 'Unknown' else None
                }

                if settings_sourceMode.get() in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
                    share_info['path'] = tree_source.item(item, 'text')

                    share_vals = tree_source.item(item, 'values')

                    if SYS_PLATFORM == PLATFORM_WINDOWS:
                        # Windows uses drive letters, so default name is letter
                        default_name = tree_source.item(item, 'text')[0]
                    elif SYS_PLATFORM == PLATFORM_LINUX:
                        # Linux uses mount points, so get last dir name
                        default_name = tree_source.item(item, 'text').split(os.path.sep)[-1]

                    share_info['dest_name'] = share_vals[2] if len(share_vals) >= 3 and share_vals[2] else default_name
                else:
                    # If single drive mode, use share name as dest name
                    share_info['path'] = os.path.join(config['source_drive'], tree_source.item(item, 'text'))
                    share_info['dest_name'] = tree_source.item(item, 'text')

                new_shares.append(share_info)
        else:
            # Nothing selected, so empty the meta counter
            share_selected_space.configure(text='None', fg=root_window.uicolor.FADED)

        config['sources'] = new_shares
        update_status_bar_selection()

        # If selection is different than last time, invalidate the analysis
        selection_unchanged_items = [share for share in selected if share in prev_source_selection]
        if ((not backup or not backup.is_running())  # Make sure backup isn't already running
                and len(selected) != len(prev_source_selection) or len(selection_unchanged_items) != len(prev_source_selection)):  # Selection has changed from last time
            start_backup_btn.configure(state='disable')

        prev_source_selection = [share for share in selected]

        # Check if items in selection need to be calculated
        all_shares_known = True
        for item in selected:
            # If new selected item hasn't been calculated, calculate it on the fly
            if tree_source.item(item, 'values')[0] == 'Unknown':
                all_shares_known = False
                update_status_bar_selection(Status.BACKUPSELECT_CALCULATING_SOURCE)
                start_analysis_btn.configure(state='disable')
                share_name = tree_source.item(item, 'text')
                thread_manager.start(ThreadManager.SINGLE, is_progress_thread=True, target=lambda: update_share_size(item), name=f"shareCalc_{share_name}", daemon=True)

        if all_shares_known:
            progress.stop_indeterminate()
    else:
        # Tree selection locked, so keep selection the same
        try:
            tree_source.unbind('<<TreeviewSelect>>', source_select_bind)
        except tk._tkinter.TclError:
            pass

        if prev_source_selection:
            tree_source.focus(prev_source_selection[-1])
        tree_source.selection_set(tuple(prev_source_selection))

        source_select_bind = tree_source.bind("<<TreeviewSelect>>", select_source_in_background)

def select_source_in_background(event):
    """Start a calculation of source filesize in a new thread."""

    thread_manager.start(ThreadManager.MULTIPLE, is_progress_thread=True, target=select_source, name='Load Source Selection', daemon=True)

def load_dest():
    """Load the destination drive info, and display it in the tree."""

    global dest_drive_master_list

    progress.start_indeterminate()

    # Empty tree in case this is being refreshed
    tree_dest.delete(*tree_dest.get_children())

    if prefs.get('selection', 'dest_mode', default=Config.DEST_MODE_DRIVES, verify_data=Config.DEST_MODE_OPTIONS) == Config.DEST_MODE_DRIVES:
        dest_select_custom_frame.pack_forget()
        dest_select_normal_frame.pack()

        if SYS_PLATFORM == PLATFORM_WINDOWS:
            logical_drive_list = win32api.GetLogicalDriveStrings().split('\000')[:-1]
            logical_drive_list = [drive[:2] for drive in logical_drive_list]

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
            total_drive_space_available = 0
            dest_drive_master_list = []
            for drive in logical_drive_list:
                if drive != config['source_drive'] and drive != SYSTEM_DRIVE:
                    drive_type = win32file.GetDriveType(drive)

                    drive_type_list = []
                    if prefs.get('selection', 'destination_network_drives', default=False, data_type=Config.BOOLEAN):
                        drive_type_list.append(DRIVE_TYPE_REMOTE)
                    if prefs.get('selection', 'destination_local_drives', default=True, data_type=Config.BOOLEAN):
                        drive_type_list.append(DRIVE_TYPE_FIXED)
                        drive_type_list.append(DRIVE_TYPE_REMOVABLE)

                    if drive_type in drive_type_list:
                        try:
                            drive_size = shutil.disk_usage(drive).total
                            vsn = os.stat(drive).st_dev
                            vsn = '{:04X}-{:04X}'.format(vsn >> 16, vsn & 0xffff)
                            try:
                                serial = logical_to_physical_map[drive[0]]
                            except KeyError:
                                serial = 'Not Found'

                            drive_has_config_file = os.path.exists(os.path.join(drive, BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE)) and os.path.isfile(os.path.join(drive, BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE))

                            total_drive_space_available = total_drive_space_available + drive_size
                            tree_dest.insert(parent='', index='end', text=drive, values=(human_filesize(drive_size), drive_size, 'Yes' if drive_has_config_file else '', vsn, serial))

                            dest_drive_master_list.append({
                                'name': drive,
                                'vid': vsn,
                                'serial': serial,
                                'capacity': drive_size,
                                'hasConfig': drive_has_config_file
                            })
                        except (FileNotFoundError, OSError):
                            pass
        elif SYS_PLATFORM == PLATFORM_LINUX:
            local_selected = prefs.get('selection', 'destination_local_drives', default=True, data_type=Config.BOOLEAN)
            network_selected = prefs.get('selection', 'destination_network_drives', default=False, data_type=Config.BOOLEAN)

            if network_selected and not local_selected:
                cmd = ['df', ' -tcifs', '-tnfs', '--output=target']
            elif local_selected and not network_selected:
                cmd = ['df', ' -xtmpfs', '-xsquashfs', '-xdevtmpfs', '-xcifs', '-xnfs', '--output=target']
            elif local_selected and network_selected:
                cmd = ['df', ' -xtmpfs', '-xsquashfs', '-xdevtmpfs', '--output=target']

            out = subprocess.run(cmd,
                                 stdout=subprocess.PIPE,
                                 stdin=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            logical_drive_list = out.stdout.decode('utf-8').split('\n')[1:]
            logical_drive_list = [mount for mount in logical_drive_list if mount and mount != config['source_drive']]

            total_drive_space_available = 0
            dest_drive_master_list = []
            for drive in logical_drive_list:
                drive_name = f'"{drive}"'

                out = subprocess.run("mount | grep " + drive_name + " | awk 'NR==1{print $1}' | sed 's/[0-9]*//g'",
                                     stdout=subprocess.PIPE,
                                     stdin=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL,
                                     shell=True)
                physical_disk = out.stdout.decode('utf-8').split('\n')[0].strip()

                # Only process mount point if it's not on the system drive
                if physical_disk != SYSTEM_DRIVE and drive != '/':
                    drive_size = shutil.disk_usage(drive).total

                    # Get volume ID, remove dashes, and format the last 8 characters
                    out = subprocess.run(f"df {drive_name} --output=source | awk 'NR==2' | xargs lsblk -o uuid | awk 'NR==2'",
                                         stdout=subprocess.PIPE,
                                         stdin=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL,
                                         shell=True)
                    vsn = out.stdout.decode('utf-8').split('\n')[0].strip().replace('-', '').upper()
                    vsn = f'{vsn[-8:-4]}-{vsn[-4:]}'

                    # Get drive serial, if present
                    out = subprocess.run(f"lsblk -o serial '{physical_disk}' | awk 'NR==2'",
                                         stdout=subprocess.PIPE,
                                         stdin=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL,
                                         shell=True)
                    serial = out.stdout.decode('utf-8').split('\n')[0].strip()

                    # Set default if serial not found
                    serial = serial if serial else 'Not Found'

                    drive_has_config_file = os.path.exists(os.path.join(drive, BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE)) and os.path.isfile(os.path.join(drive, BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE))

                    total_drive_space_available += drive_size
                    tree_dest.insert(parent='', index='end', text=drive, values=(human_filesize(drive_size), drive_size, 'Yes' if drive_has_config_file else '', vsn, serial))

                    dest_drive_master_list.append({
                        'name': drive,
                        'vid': vsn,
                        'serial': serial,
                        'capacity': drive_size,
                        'hasConfig': drive_has_config_file
                    })
    elif settings_destMode.get() == Config.DEST_MODE_PATHS:
        dest_select_normal_frame.pack_forget()
        dest_select_custom_frame.pack(fill='x', expand=1)

        total_drive_space_available = 0

    drive_total_space.configure(text=human_filesize(total_drive_space_available), fg=root_window.uicolor.NORMAL if total_drive_space_available > 0 else root_window.uicolor.FADED)

    progress.stop_indeterminate()

def load_dest_in_background():
    """Start the loading of the destination drive info in a new thread."""

    # TODO: Make load_dest and load_source replaceable, and in their own class
    # TODO: Invalidate load_source or load_dest if tree gets refreshed via some class def call
    if (backup and backup.is_running()) or thread_manager.is_alive('Refresh Destination'):
        return

    thread_manager.start(ThreadManager.SINGLE, target=load_dest, is_progress_thread=True, name='Refresh Destination', daemon=True)

def gui_select_from_config():
    """From the current config, select the appropriate shares and drives in the GUI."""

    global dest_select_bind
    global prev_source_selection
    global prev_dest_selection

    # Get list of shares in config
    config_share_name_list = [item['dest_name'] for item in config['sources']]
    if settings_sourceMode.get() in [Config.SOURCE_MODE_SINGLE_DRIVE, Config.SOURCE_MODE_SINGLE_PATH]:
        config_source_tree_id_list = [item for item in tree_source.get_children() if tree_source.item(item, 'text') in config_share_name_list]
    else:
        config_source_tree_id_list = [item for item in tree_source.get_children() if len(tree_source.item(item, 'values')) >= 3 and tree_source.item(item, 'values')[2] in config_share_name_list]

    if config_source_tree_id_list:
        tree_source.focus(config_source_tree_id_list[-1])
        prev_source_selection = config_source_tree_id_list
        tree_source.selection_set(tuple(config_source_tree_id_list))

        # Recalculate selected totals for display
        # QUESTION: Should source total be recalculated when selecting, or should it continue to use the existing total?
        known_path_sizes = [int(tree_source.item(item, 'values')[1]) for item in config_source_tree_id_list if tree_source.item(item, 'values')[1] != 'Unknown']
        share_selected_space.configure(text=human_filesize(sum(known_path_sizes)))

    # Get list of drives where volume ID is in config
    connected_vid_list = [drive['vid'] for drive in config['destinations']]

    # If drives aren't mounted that should be, display the warning
    MISSING_DRIVE_COUNT = len(config['missing_drives'])
    if MISSING_DRIVE_COUNT > 0:
        config_missing_drive_vid_list = [vid for vid in config['missing_drives']]

        MISSING_VID_READABLE_LIST = ', '.join(config_missing_drive_vid_list[:-2] + [' and '.join(config_missing_drive_vid_list[-2:])])
        MISSING_VID_ALERT_MESSAGE = f"The drive{'s' if len(config_missing_drive_vid_list) > 1 else ''} with volume ID{'s' if len(config_missing_drive_vid_list) > 1 else ''} {MISSING_VID_READABLE_LIST} {'are' if len(config_missing_drive_vid_list) > 1 else 'is'} not available to be selected.\n\nMissing drives may be omitted or replaced, provided the total space on destination drives is equal to, or exceeds the amount of data to back up.\n\nUnless you reset the config or otherwise restart this tool, this is the last time you will be warned."
        MISSING_VID_ALERT_TITLE = f"Drive{'s' if len(config_missing_drive_vid_list) > 1 else ''} missing"

        split_warning_prefix.configure(text=f"There {'is' if MISSING_DRIVE_COUNT == 1 else 'are'}")
        MISSING_DRIVE_CONTRACTION = 'isn\'t' if MISSING_DRIVE_COUNT == 1 else 'aren\'t'
        split_warning_suffix.configure(text=f"{'drive' if MISSING_DRIVE_COUNT == 1 else 'destinations'} in the config that {MISSING_DRIVE_CONTRACTION} connected. Please connect {'it' if MISSING_DRIVE_COUNT == 1 else 'them'}, or enable split mode.")
        split_warning_missing_drive_count.configure(text=str(MISSING_DRIVE_COUNT))
        dest_split_warning_frame.grid(row=3, column=0, columnspan=3, sticky='nsew', pady=(0, WINDOW_ELEMENT_PADDING), ipady=WINDOW_ELEMENT_PADDING / 4)

        messagebox.showwarning(MISSING_VID_ALERT_TITLE, MISSING_VID_ALERT_MESSAGE)

    # Only redo the selection if the config data is different from the current
    # selection (that is, the drive we selected to load a config is not the only
    # drive listed in the config)
    # Because of the <<TreeviewSelect>> handler, re-selecting the same single item
    # would get stuck into an endless loop of trying to load the config
    # QUESTION: Is there a better way to handle this @config loading @selection handler @conflict?
    if settings_destMode.get() == Config.DEST_MODE_DRIVES:
        config_dest_tree_id_list = [item for item in tree_dest.get_children() if tree_dest.item(item, 'values')[3] in connected_vid_list]
        if len(config_dest_tree_id_list) > 0 and tree_dest.selection() != tuple(config_dest_tree_id_list):
            try:
                tree_dest.unbind('<<TreeviewSelect>>', dest_select_bind)
            except tk._tkinter.TclError:
                pass

            if config_dest_tree_id_list:
                tree_dest.focus(config_dest_tree_id_list[-1])
            prev_dest_selection = config_dest_tree_id_list
            tree_dest.selection_set(tuple(config_dest_tree_id_list))

            dest_select_bind = tree_dest.bind("<<TreeviewSelect>>", select_dest_in_background)

def get_share_path_from_name(share) -> str:
    """Get a share path from a share name.

    Args:
        share (String): The share to get.

    Returns:
        String: The path name for the share.
    """

    if prefs.get('selection', 'source_mode', default=Config.SOURCE_MODE_SINGLE_DRIVE, verify_data=Config.SOURCE_MODE_OPTIONS) in [Config.SOURCE_MODE_SINGLE_DRIVE, Config.SOURCE_MODE_SINGLE_PATH]:
        # Single source mode, so source is source drive
        return os.path.join(config['source_drive'], share)
    else:
        reference_list = {prefs.get('source_names', mountpoint, default=''): mountpoint for mountpoint in source_avail_drive_list if prefs.get('source_names', mountpoint, '')}
        return reference_list[share]

def load_config_from_file(filename):
    """Read a config file, and set the current config based off of it.

    Args:
        filename (String): The file to read from.
    """

    global config

    new_config = {}
    config_file = Config(filename)

    SELECTED_DEST_MODE = prefs.get('selection', 'dest_mode', default=Config.DEST_MODE_DRIVES, verify_data=Config.DEST_MODE_OPTIONS)

    # Get shares
    shares = config_file.get('selection', 'sources')
    if shares is not None and len(shares) > 0:
        new_config['sources'] = [{
            'path': [tree_source.item(item, 'text') if (len(tree_source.item(item, 'values')) >= 3 and tree_source.item(item, 'values')[2] == share) else tree_source.item(item, 'text') for item in tree_source.get_children()][0],
            'size': None,
            'dest_name': share
        } for share in shares.split(',')]

    if SELECTED_DEST_MODE == Config.DEST_MODE_DRIVES:
        # Get VID list
        vids = config_file.get('selection', 'vids').split(',')

        # Get drive info
        config_drive_total = 0
        new_config['destinations'] = []
        new_config['missing_drives'] = {}
        drive_lookup_list = {drive['vid']: drive for drive in dest_drive_master_list}
        for drive in vids:
            if drive in drive_lookup_list.keys():
                # If drive connected, add to drive list
                new_config['destinations'].append(drive_lookup_list[drive])
                config_drive_total += drive_lookup_list[drive]['capacity']
            else:
                # Add drive capacity info to missing drive list
                reported_drive_capacity = config_file.get(drive, 'capacity', 0, data_type=Config.INTEGER)
                new_config['missing_drives'][drive] = reported_drive_capacity
                config_drive_total += reported_drive_capacity
    elif SELECTED_DEST_MODE == Config.DEST_MODE_PATHS:
        # Get drive info
        config_drive_total = 0
        new_config['missing_drives'] = {}

    config.update(new_config)

    config_selected_space.configure(text=human_filesize(config_drive_total), fg=root_window.uicolor.NORMAL)
    gui_select_from_config()

def select_dest():
    """Parse the current drive selection, read config data, and select other drives and shares if needed.

    If the selection involves a single drive that the user specifically clicked on,
    this function reads the config file on it if one exists, and will select any
    other drives and shares in the config.
    """

    global prev_selection
    global prev_dest_selection
    global dest_select_bind

    if backup and backup.is_running():
        # Tree selection locked, so keep selection the same
        try:
            tree_dest.unbind('<<TreeviewSelect>>', dest_select_bind)
        except tk._tkinter.TclError:
            pass

        if prev_dest_selection:
            tree_dest.focus(prev_dest_selection[-1])
        tree_dest.selection_set(tuple(prev_dest_selection))

        dest_select_bind = tree_dest.bind("<<TreeviewSelect>>", select_dest_in_background)

        return

    progress.start_indeterminate()

    # If analysis was run, invalidate it
    reset_analysis_output()

    dest_selection = tree_dest.selection()

    # If selection is different than last time, invalidate the analysis
    selection_selected_last_time = [drive for drive in dest_selection if drive in prev_dest_selection]
    if len(dest_selection) != len(prev_dest_selection) or len(selection_selected_last_time) != len(prev_dest_selection):
        start_backup_btn.configure(state='disable')

    prev_dest_selection = [share for share in dest_selection]

    # Check if newly selected drive has a config file
    # We only want to do this if the click is the first selection (that is, there
    # are no other drives selected except the one we clicked).
    drives_read_from_config_file = False
    if len(dest_selection) > 0:
        selected_drive = tree_dest.item(dest_selection[0], 'text')
        SELECTED_PATH_CONFIG_FILE = os.path.join(selected_drive, BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE)
        if not keypresses['Alt'] and prev_selection <= len(dest_selection) and len(dest_selection) == 1 and os.path.isfile(SELECTED_PATH_CONFIG_FILE):
            # Found config file, so read it
            load_config_from_file(SELECTED_PATH_CONFIG_FILE)
            dest_selection = tree_dest.selection()
            drives_read_from_config_file = True
        else:
            dest_split_warning_frame.grid_remove()
            prev_selection = len(dest_selection)

    selected_total = 0
    selected_drive_list = []

    if settings_destMode.get() == Config.DEST_MODE_DRIVES:
        drive_lookup_list = {drive['vid']: drive for drive in dest_drive_master_list}
        for item in dest_selection:
            # Write drive IDs to config
            selected_drive = drive_lookup_list[tree_dest.item(item, 'values')[3]]
            selected_drive_list.append(selected_drive)
            selected_total += selected_drive['capacity']
    elif settings_destMode.get() == Config.DEST_MODE_PATHS:
        for item in dest_selection:
            drive_path = tree_dest.item(item, 'text')
            drive_vals = tree_dest.item(item, 'values')

            drive_name = drive_vals[3] if len(drive_vals) >= 4 else ''
            drive_capacity = int(drive_vals[1])
            drive_has_config = True if drive_vals[2] == 'Yes' else False

            drive_data = {
                'name': drive_path,
                'vid': drive_name,
                'serial': None,
                'capacity': drive_capacity,
                'hasConfig': drive_has_config
            }

            selected_drive_list.append(drive_data)
            selected_total += drive_capacity

        config['destinations'] = selected_drive_list

    drive_selected_space.configure(text=human_filesize(selected_total) if selected_total > 0 else 'None', fg=root_window.uicolor.NORMAL if selected_total > 0 else root_window.uicolor.FADED)
    if not drives_read_from_config_file:
        config['destinations'] = selected_drive_list
        config['missing_drives'] = {}
        config_selected_space.configure(text='None', fg=root_window.uicolor.FADED)

    update_status_bar_selection()

    progress.stop_indeterminate()

def select_dest_in_background(event):
    """Start the drive selection handling in a new thread."""

    thread_manager.start(ThreadManager.MULTIPLE, is_progress_thread=True, target=select_dest, name='Drive Select', daemon=True)

def start_backup():
    """Start the backup in a new thread."""

    if not backup or verification_running:
        return

    # Reset UI
    statusbar_counter_btn.configure(text='0 failed', state='disabled')
    statusbar_details.configure(text='')

    # Reset file detail success and fail lists
    for list_name in [FileUtils.LIST_DELETE_SUCCESS, FileUtils.LIST_DELETE_FAIL, FileUtils.LIST_SUCCESS, FileUtils.LIST_FAIL]:
        file_detail_list[list_name].clear()

    # Reset file details counters
    FILE_DELETE_COUNT = len(file_detail_list[FileUtils.LIST_TOTAL_DELETE])
    FILE_COPY_COUNT = len(file_detail_list[FileUtils.LIST_TOTAL_COPY])
    file_details_pending_delete_counter.configure(text=str(FILE_DELETE_COUNT))
    file_details_pending_delete_counter_total.configure(text=str(FILE_DELETE_COUNT))
    file_details_pending_copy_counter.configure(text=str(FILE_COPY_COUNT))
    file_details_pending_copy_counter_total.configure(text=str(FILE_COPY_COUNT))
    file_details_copied_counter.configure(text='0')
    file_details_failed_counter.configure(text='0')

    # Empty file details list panes
    file_details_copied.empty()
    file_details_failed.empty()

    if not backup.analysis_valid or not backup.sanity_check():
        return

    update_ui_component(Status.UPDATEUI_BACKUP_START)
    update_ui_component(Status.UPDATEUI_STATUS_BAR_DETAILS, '')
    progress.set(current=0, total=backup.progress['total'])

    for cmd in backup.command_list:
        cmd_info_blocks[cmd['displayIndex']].state.configure(text='Pending', fg=root_window.uicolor.PENDING)
        if cmd['type'] == Backup.COMMAND_TYPE_FILE_LIST:
            cmd_info_blocks[cmd['displayIndex']].configure('current_file', text='Pending', fg=root_window.uicolor.PENDING)
        cmd_info_blocks[cmd['displayIndex']].configure('progress', text='Pending', fg=root_window.uicolor.PENDING)

    thread_manager.start(ThreadManager.KILLABLE, is_progress_thread=True, target=backup.run, name='Backup', daemon=True)

def cleanup_handler(signal_received, frame):
    """Handle cleanup when exiting with Ctrl-C.

    Args:
        signal_received: The signal number received.
        frame: The current stack frame.
    """

    global force_non_graceful_cleanup

    if not force_non_graceful_cleanup:
        logging.error('SIGINT or Ctrl-C detected. Exiting gracefully...')

        if thread_manager.is_alive('Backup'):
            if backup:
                backup.kill()

            if thread_manager.is_alive('Backup'):
                force_non_graceful_cleanup = True
                logging.error('Press Ctrl-C again to force stop')

            while thread_manager.is_alive('Backup'):
                pass

            logging.error('Exiting...')

        if thread_manager.is_alive('backupTimer'):
            thread_manager.kill('backupTimer')
    else:
        logging.error('SIGINT or Ctrl-C detected. Force closing...')

    exit(0)

# TODO: Move file verification to backup class
def verify_data_integrity(drive_list):
    """Verify itegrity of files on destination drives by checking hashes.

    Args:
        drive_list (String[]): A list of mount points for drives to check.
    """

    global verification_running
    global verification_failed_list

    def get_file_hash(filename) -> str:
        """Get the hash of a file.

        Args:
            filename (String): The file to get the hash of.

        Returns:
            String: The blake3 hash of the file if readable. None otherwise.
        """

        buffer_size = 1024 * 1024

        # Optimize the buffer for small files
        buffer_size = min(buffer_size, os.path.getsize(filename))
        if buffer_size == 0:
            buffer_size = 1024

        h = blake3()
        b = bytearray(buffer_size)
        mv = memoryview(b)

        with open(filename, 'rb', buffering=0) as f:
            for n in iter(lambda: f.readinto(mv), 0):
                if thread_manager.threadlist['Data Verification']['killFlag']:  # TODO: Refactor this into separate function
                    break
                h.update(mv[:n])

        if thread_manager.threadlist['Data Verification']['killFlag']:
            return ''

        return h.hexdigest()

    def recurse_for_hash(path, drive, hash_file_path):
        """Recurse a given path and check hashes.

        Args:
            path (String): The path to check.
            drive (String): The mountpoint of the drive.
            hash_file_path (String): The path to the hash file.
        """

        try:
            for entry in os.scandir(path):
                path_stub = entry.path.split(drive)[1].strip(os.path.sep)
                if entry.is_file():
                    # If entry is a file, hash it, and check for a computed hash
                    statusbar_details.configure(text=entry.path)

                    file_hash = get_file_hash(entry.path)

                    if thread_manager.threadlist['Data Verification']['killFlag']:
                        break

                    if path_stub in hash_list[drive].keys():
                        # Hash saved, so check integrity against saved file
                        saved_hash = hash_list[drive][path_stub]

                        if file_hash != saved_hash:
                            # Computed hash different from saved, so delete
                            # corrupted file
                            if os.path.isfile(entry.path):
                                os.remove(entry.path)
                            elif os.path.isdir(entry.path):
                                shutil.rmtree(entry.path)

                            # Update UI counter
                            verification_failed_list.append(entry.path)
                            statusbar_counter_btn.configure(text=f"{len(verification_failed_list)} failed", state='normal')

                            # Also delete the saved hash
                            if path_stub in hash_list[drive].keys():
                                del hash_list[drive][path_stub]
                            with open(drive_hash_file_path, 'wb') as f:
                                pickle.dump({'/'.join(file_name.split(os.path.sep)): hash_val for file_name, hash_val in hash_list[drive].items()}, f)

                        # Update file detail lists
                        if file_hash == saved_hash:
                            update_file_detail_lists(FileUtils.LIST_SUCCESS, {entry.path})
                        else:
                            update_file_detail_lists(FileUtils.LIST_FAIL, {entry.path})
                            backup_error_log.append({'file': entry.path, 'mode': 'copy', 'error': 'File hash mismatch'})
                    else:
                        # Hash not saved, so store it
                        hash_list[drive][path_stub] = file_hash
                        with open(drive_hash_file_path, 'wb') as f:
                            pickle.dump({'/'.join(file_name.split(os.path.sep)): hash_val for file_name, hash_val in hash_list[drive].items()}, f)
                elif entry.is_dir() and path_stub not in special_ignore_list:
                    # If entry is path, recurse into it
                    recurse_for_hash(entry.path, drive, hash_file_path)

                if thread_manager.threadlist['Data Verification']['killFlag']:
                    break
        except Exception:
            pass

    if not backup or not backup.is_running():
        update_status_bar_action(Status.VERIFICATION_RUNNING)
        progress.start_indeterminate()
        statusbar_counter_btn.configure(text='0 failed', state='disabled')
        statusbar_details.configure(text='')

        halt_verification_btn.pack(side='left', padx=4)

        # Empty file detail lists
        for list_name in [FileUtils.LIST_SUCCESS, FileUtils.LIST_FAIL]:
            file_detail_list[list_name].clear()

        # Reset file details counters
        file_details_pending_delete_counter.configure(text='0')
        file_details_pending_delete_counter_total.configure(text='0')
        file_details_pending_copy_counter.configure(text='0')
        file_details_pending_copy_counter_total.configure(text='0')
        file_details_copied_counter.configure(text='0')
        file_details_failed_counter.configure(text='0')

        # Empty file details list panes
        file_details_copied.empty()
        file_details_failed.empty()

        verification_running = True
        verification_failed_list = []

        # Get hash list for all drives
        bad_hash_files = []
        hash_list = {drive: {} for drive in drive_list}
        special_ignore_list = [BACKUP_CONFIG_DIR]
        if SYS_PLATFORM == PLATFORM_WINDOWS:
            special_ignore_list.extend(['$RECYCLE.BIN', 'System Volume Information'])
        for drive in drive_list:
            drive_hash_file_path = os.path.join(drive, BACKUP_CONFIG_DIR, BACKUP_HASH_FILE)

            if os.path.isfile(drive_hash_file_path):
                write_trimmed_changes = False
                with open(drive_hash_file_path, 'rb') as f:
                    try:
                        drive_hash_list = pickle.load(f)
                        new_hash_list = {file_name: hash_val for file_name, hash_val in drive_hash_list.items() if file_name.split('/')[0] not in special_ignore_list}
                        new_hash_list = {os.path.sep.join(file_name.split('/')): hash_val for file_name, hash_val in new_hash_list.items() if os.path.isfile(os.path.join(drive, file_name))}

                        # If trimmed list is shorter, new changes have to be written to the file
                        if len(new_hash_list) < len(drive_hash_list):
                            write_trimmed_changes = True

                        hash_list[drive] = new_hash_list
                    except Exception:
                        # Hash file is corrupt
                        bad_hash_files.append(drive_hash_file_path)

                # If trimmed list is different length than original, write changes to file
                if write_trimmed_changes:
                    with open(drive_hash_file_path, 'wb') as f:
                        pickle.dump({'/'.join(file_name.split(os.path.sep)): hash_val for file_name, hash_val in hash_list[drive].items()}, f)
            else:
                bad_hash_files.append(drive_hash_file_path)

        # If there are missing or corrupted pickle files, write empty data
        if bad_hash_files:
            for file in bad_hash_files:
                with open(file, 'wb') as f:
                    pickle.dump({}, f)

        verify_all_files = prefs.get('verification', 'verify_all_files', default=False, data_type=Config.BOOLEAN)
        if verify_all_files:
            for drive in drive_list:
                drive_hash_file_path = os.path.join(drive, BACKUP_CONFIG_DIR, BACKUP_HASH_FILE)
                recurse_for_hash(drive, drive, drive_hash_file_path)
        else:
            for drive in drive_list:
                drive_hash_file_path = os.path.join(drive, BACKUP_CONFIG_DIR, BACKUP_HASH_FILE)
                for file, saved_hash in hash_list[drive].items():
                    filename = os.path.join(drive, file)
                    statusbar_details.configure(text=filename)
                    computed_hash = get_file_hash(filename)

                    if thread_manager.threadlist['Data Verification']['killFlag']:
                        break

                    # If file has hash mismatch, delete the corrupted file
                    if saved_hash != computed_hash:
                        do_delete(filename)

                        # Update UI counter
                        verification_failed_list.append(filename)
                        statusbar_counter_btn.configure(text=f"{len(verification_failed_list)} failed", state='normal')

                        # Delete the saved hash, and write changes to the hash file
                        if file in hash_list[drive].keys():
                            del hash_list[drive][file]
                        with open(drive_hash_file_path, 'wb') as f:
                            pickle.dump({'/'.join(file_name.split(os.path.sep)): hash_val for file_name, hash_val in hash_list[drive].items()}, f)

                    # Update file detail lists
                    if saved_hash == computed_hash:
                        update_file_detail_lists(FileUtils.LIST_SUCCESS, {filename})
                    else:
                        update_file_detail_lists(FileUtils.LIST_FAIL, {filename})
                        backup_error_log.append({'file': filename, 'mode': 'copy', 'error': 'File hash mismatch'})

                    if thread_manager.threadlist['Data Verification']['killFlag']:
                        break

                if thread_manager.threadlist['Data Verification']['killFlag']:
                    break

        verification_running = False
        halt_verification_btn.pack_forget()

        progress.stop_indeterminate()
        statusbar_details.configure(text='')
        update_status_bar_action(Status.IDLE)

def display_update_screen(update_info: dict):
    """Display information about updates.

    Args:
        update_info (dict): The update info returned by the UpdateHandler.
    """

    global update_window

    if not update_info['updateAvailable'] or (update_window and update_window.winfo_exists()):
        return

    update_window = AppWindow(
        root=root_window,
        title='Update Available',
        width=600,
        height=300,
        center=True,
        center_content=True,
        resizable=(False, False),
        modal=True
    )

    if SYS_PLATFORM == PLATFORM_WINDOWS:
        update_window.iconbitmap(resource_path('media/icon.ico'))

    update_header = tk.Label(update_window.main_frame, text='Update Available!', font=(None, 30, 'bold italic'), fg=root_window.uicolor.INFOTEXTDARK)
    update_header.pack()

    update_text = tk.Label(update_window.main_frame, text='An update to BackDrop is available. Please update to get the latest features and fixes.', font=(None, 10))
    update_text.pack(pady=16)

    current_version_frame = tk.Frame(update_window.main_frame)
    current_version_frame.pack()
    tk.Label(current_version_frame, text='Current Version:', font=(None, 14)).pack(side='left')
    tk.Label(current_version_frame, text=APP_VERSION, font=(None, 14), fg=root_window.uicolor.FADED).pack(side='left')

    latest_version_frame = tk.Frame(update_window.main_frame)
    latest_version_frame.pack(pady=(2, 12))
    tk.Label(latest_version_frame, text='Latest Version:', font=(None, 14)).pack(side='left')
    tk.Label(latest_version_frame, text=update_info['latestVersion'], font=(None, 14), fg=root_window.uicolor.FADED).pack(side='left')

    download_frame = tk.Frame(update_window.main_frame)
    download_frame.pack()

    download_source_frame = tk.Frame(update_window.main_frame)
    download_source_frame.pack()
    tk.Label(download_source_frame, text='Or, check out the source on').pack(side='left')
    github_link = tk.Label(download_source_frame, text='GitHub', fg=root_window.uicolor.INFOTEXT)
    github_link.pack(side='left')
    github_link.bind('<Button-1>', lambda e: webbrowser.open_new('https://www.github.com/TechGeek01/BackDrop'))

    icon_info = {
        'backdrop.exe': {
            'flat_icon': icon_windows,
            'color_icon': icon_windows_color,
            'supplemental': {
                'name': 'backdrop.zip',
                'flat_icon': icon_zip,
                'color_icon': icon_zip_color
            }
        },
        'backdrop-debian': {
            'flat_icon': icon_debian,
            'color_icon': icon_debian_color,
            'supplemental': {
                'name': 'backdrop-debian.tar.gz',
                'flat_icon': icon_targz,
                'color_icon': icon_targz_color
            }
        }
    }
    download_map = {url.split('/')[-1].lower(): url for url in update_info['download']}

    for file_type, info in icon_info.items():
        if file_type in download_map.keys():
            download_btn = tk.Label(download_frame, image=info['flat_icon'])
            download_btn.pack(side='left', padx=(12, 4))
            download_btn.bind('<Enter>', lambda e, icon=info['color_icon']: e.widget.configure(image=icon))
            download_btn.bind('<Leave>', lambda e, icon=info['flat_icon']: e.widget.configure(image=icon))
            download_btn.bind('<Button-1>', lambda e, url=download_map[file_type]: webbrowser.open_new(url))

            # Add supplemental icon if download is available
            if 'supplemental' in icon_info[file_type].keys() or info['supplemental']['name'] in download_map.keys():
                download_btn = tk.Label(download_frame, image=info['supplemental']['flat_icon'])
                download_btn.pack(side='left', padx=(0, 4))
                download_btn.bind('<Enter>', lambda e, icon=info['supplemental']['color_icon']: e.widget.configure(image=icon))
                download_btn.bind('<Leave>', lambda e, icon=info['supplemental']['flat_icon']: e.widget.configure(image=icon))
                download_btn.bind('<Button-1>', lambda e, url=download_map[info['supplemental']['name']]: webbrowser.open_new(url))

    update_window.transient(root_window)
    update_window.grab_set()
    root_window.wm_attributes('-disabled', True)

def check_for_updates(info: dict):
    """Process the update information provided by the UpdateHandler class.

    Args:
        info (dict): The Update info from the update handler.
    """

    global update_info

    update_info = info

    if info['updateAvailable']:
        display_update_screen(info)

if __name__ == '__main__':
    PLATFORM_WINDOWS = 'Windows'
    PLATFORM_LINUX = 'Linux'

    # Platform sanity check
    if not platform.system() in [PLATFORM_WINDOWS, PLATFORM_LINUX]:
        logging.error('This operating system is not supported')
        exit()

    # Set meta info
    APP_VERSION = '4.0.0-alpha2'

    # Set constants
    SYS_PLATFORM = platform.system()
    if SYS_PLATFORM == PLATFORM_WINDOWS:
        DRIVE_TYPE_REMOVABLE = win32file.DRIVE_REMOVABLE
        DRIVE_TYPE_FIXED = win32file.DRIVE_FIXED
        DRIVE_TYPE_LOCAL = DRIVE_TYPE_FIXED  # TODO: Make this a proper thing instead of reusing one local value
        DRIVE_TYPE_REMOTE = win32file.DRIVE_REMOTE
        DRIVE_TYPE_RAMDISK = win32file.DRIVE_RAMDISK
    else:
        DRIVE_TYPE_REMOVABLE = 2
        DRIVE_TYPE_FIXED = 3
        DRIVE_TYPE_LOCAL = DRIVE_TYPE_FIXED
        DRIVE_TYPE_REMOTE = 4
        DRIVE_TYPE_RAMDISK = 6
    READINTO_BUFSIZE = FileUtils.READINTO_BUFSIZE  # differs from shutil.COPY_BUFSIZE on platforms != Windows

    # Set defaults
    prev_source_selection = []
    prev_selection = 0
    prev_dest_selection = []
    force_non_graceful_cleanup = False
    verification_running = False
    verification_failed_list = []
    update_window = None

    if SYS_PLATFORM == PLATFORM_WINDOWS:
        SYSTEM_DRIVE = f'{os.getenv("SystemDrive")[0]}:'
        APPDATA_FOLDER = f'{os.getenv("LocalAppData")}/BackDrop'
    elif SYS_PLATFORM == PLATFORM_LINUX:
        # Get system drive by querying mount points
        out = subprocess.run('mount | grep "on / type"' + " | awk 'NR==1{print $1}' | sed 's/[0-9]*//g'",
                             stdout=subprocess.PIPE,
                             stdin=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             shell=True)
        SYSTEM_DRIVE = out.stdout.decode('utf-8').split('\n')[0].strip()

        # If user runs as sudo, username has to be grabbed through sudo to get the
        # appropriate home dir, since ~ with sudo resolves to /root
        USER_HOME_VAR = '~'
        if os.getenv('SUDO_USER') is not None:
            USER_HOME_VAR += os.getenv('SUDO_USER')
        APPDATA_FOLDER = f"{os.path.expanduser(USER_HOME_VAR)}/.config/BackDrop"

    # Set app defaults
    BACKUP_CONFIG_DIR = '.backdrop'
    BACKUP_CONFIG_FILE = 'backup.ini'
    BACKUP_HASH_FILE = 'hashes.pkl'
    PREFERENCES_CONFIG_FILE = 'preferences.ini'
    PORTABLE_PREFERENCES_CONFIG_FILE = 'backdrop.ini'
    WINDOW_ELEMENT_PADDING = 16

    PORTABLE_CONFIG_FILE_PATH = os.path.join(os.getcwd(), PORTABLE_PREFERENCES_CONFIG_FILE)

    PORTABLE_MODE = os.path.isfile(PORTABLE_CONFIG_FILE_PATH)

    if not PORTABLE_MODE:
        CONFIG_FILE_PATH = os.path.join(APPDATA_FOLDER, PREFERENCES_CONFIG_FILE)
    else:
        # Portable mode
        CONFIG_FILE_PATH = PORTABLE_CONFIG_FILE_PATH

    prefs = Config(CONFIG_FILE_PATH)
    last_selected_custom_source = prefs.get('selection', 'last_selected_custom_source', default=None)
    config = {
        'source_drive': last_selected_custom_source if prefs.get('selection', 'source_mode', default=Config.SOURCE_MODE_SINGLE_DRIVE, verify_data=Config.SOURCE_MODE_OPTIONS) == Config.SOURCE_MODE_SINGLE_PATH else None,
        'source_mode': prefs.get('selection', 'source_mode', default=Config.SOURCE_MODE_SINGLE_DRIVE, verify_data=Config.SOURCE_MODE_OPTIONS),
        'dest_mode': prefs.get('selection', 'dest_mode', default=Config.DEST_MODE_DRIVES, verify_data=Config.DEST_MODE_OPTIONS),
        'splitMode': False,
        'sources': [],
        'destinations': [],
        'missing_drives': {},
        'allow_prereleases': prefs.get('ui', 'allow_prereleases', default=False, data_type=Config.BOOLEAN)
    }
    dest_drive_master_list = []

    backup = None
    command_list = []

    signal(SIGINT, cleanup_handler)

    thread_manager = ThreadManager()

    # If running on Windows, set params to allow ANSI escapes for color
    if os.name == 'nt':
        k = ctypes.windll.kernel32
        k.SetConsoleMode(k.GetStdHandle(-11), 7)

    keypresses = {
        'AltL': False,
        'AltR': False,
        'AltGr': False,
        'Alt': False
    }

    def update_status_bar_selection(status: int = None):
        """Update the status bar selection status.

        Args:
            status (int): The status code to use.
        """

        if [share for share in config['sources'] if share['size'] is None]:
            # Not all shares calculated
            status = Status.BACKUPSELECT_CALCULATING_SOURCE
        elif not config['sources'] and not config['destinations'] and len(config['missing_drives']) == 0:
            # No selection in config
            status = Status.BACKUPSELECT_NO_SELECTION
        elif not config['sources']:
            # No shares selected
            status = Status.BACKUPSELECT_MISSING_SOURCE
        elif not config['destinations'] and len(config['missing_drives']) == 0:
            # No drives selected
            status = Status.BACKUPSELECT_MISSING_DEST
        else:
            SHARE_SELECTED_SPACE = sum((share['size'] for share in config['sources']))
            DRIVE_SELECTED_SPACE = sum((drive['capacity'] for drive in config['destinations'])) + sum(config['missing_drives'].values())

            if SHARE_SELECTED_SPACE < DRIVE_SELECTED_SPACE:
                # Selected enough drive space
                status = Status.BACKUPSELECT_ANALYSIS_WAITING
            else:
                # Shares larger than drive space
                status = Status.BACKUPSELECT_INSUFFICIENT_SPACE

        STATUS_TEXT_MAP = {
            Status.BACKUPSELECT_NO_SELECTION: 'No selection',
            Status.BACKUPSELECT_MISSING_SOURCE: 'No sources selected',
            Status.BACKUPSELECT_MISSING_DEST: 'No destinations selected',
            Status.BACKUPSELECT_CALCULATING_SOURCE: 'Calculating source size',
            Status.BACKUPSELECT_INSUFFICIENT_SPACE: 'Not enough space on destination',
            Status.BACKUPSELECT_ANALYSIS_WAITING: 'Selection OK'
        }

        # Set status
        if status in STATUS_TEXT_MAP.keys():
            statusbar_selection.configure(text=STATUS_TEXT_MAP[status])

    def update_status_bar_action(status: int):
        """Update the status bar action status.

        Args:
            status (int): The status code to use.
        """

        if status == Status.IDLE:
            statusbar_action.configure(text='Idle')
        elif status == Status.BACKUP_ANALYSIS_RUNNING:
            statusbar_action.configure(text='Analysis running')
        elif status == Status.BACKUP_READY_FOR_BACKUP:
            backup_eta_label.configure(text='Analysis finished, ready for backup', fg=root_window.uicolor.NORMAL)
        elif status == Status.BACKUP_READY_FOR_ANALYSIS:
            backup_eta_label.configure(text='Please start a backup to show ETA', fg=root_window.uicolor.NORMAL)
        elif status == Status.BACKUP_BACKUP_RUNNING:
            statusbar_action.configure(text='Backup running')
        elif status == Status.BACKUP_HALT_REQUESTED:
            statusbar_action.configure(text='Stopping backup')
        elif status == Status.VERIFICATION_RUNNING:
            statusbar_action.configure(text='Data verification running')

    def update_status_bar_update(status: int):
        """Update the status bar update message.

        Args:
            status (int): The status code to use.
        """

        STATUS_TEXT_MAP = {
            Status.UPDATE_CHECKING: ['Checking for updates', root_window.uicolor.NORMAL],
            Status.UPDATE_AVAILABLE: ['Update available!', root_window.uicolor.INFOTEXT],
            Status.UPDATE_UP_TO_DATE: ['Up to date', root_window.uicolor.NORMAL],
            Status.UPDATE_FAILED: ['Update failed', root_window.uicolor.FAILED]
        }

        # Set status
        if status in STATUS_TEXT_MAP.keys():
            statusbar_update.configure(text=STATUS_TEXT_MAP[status][0], fg=STATUS_TEXT_MAP[status][1])

    def request_kill_backup():
        """Kill a running backup."""

        statusbar_action.configure(text='Stopping backup')
        if backup:
            backup.kill(Backup.KILL_BACKUP)

    def update_ui_component(status: int, data=None):
        """Update UI elements with given data..

        Args:
            status (int): The status code to use.
            data (*): The data to update (optional).
        """

        if status == Status.UPDATEUI_ANALYSIS_BTN:
            start_analysis_btn.configure(**data)
        elif status == Status.UPDATEUI_BACKUP_BTN:
            start_backup_btn.configure(**data)
        elif status == Status.UPDATEUI_ANALYSIS_START:
            update_status_bar_action(Status.BACKUP_ANALYSIS_RUNNING)
            start_analysis_btn.configure(text='Halt Analysis', command=request_kill_analysis, style='danger.TButton')
        elif status == Status.UPDATEUI_ANALYSIS_END:
            update_status_bar_action(Status.IDLE)
            start_analysis_btn.configure(text='Analyze', command=start_backup_analysis, style='TButton')
        elif status == Status.UPDATEUI_BACKUP_START:
            update_status_bar_action(Status.BACKUP_BACKUP_RUNNING)
            start_analysis_btn.configure(state='disabled')
            start_backup_btn.configure(text='Halt Backup', command=request_kill_backup, style='danger.TButton')
        elif status == Status.UPDATEUI_BACKUP_END:
            update_status_bar_action(Status.IDLE)
            start_analysis_btn.configure(state='normal')
            start_backup_btn.configure(text='Run Backup', command=start_backup, style='TButton')
        elif status == Status.UPDATEUI_STATUS_BAR:
            update_status_bar_action(data)
        elif status == Status.UPDATEUI_STATUS_BAR_DETAILS:
            statusbar_details.configure(text=data)
        elif status == Status.RESET_ANALYSIS_OUTPUT:
            reset_analysis_output()

    def open_config_file():
        """Open a config file and load it."""

        filename = filedialog.askopenfilename(initialdir='', title='Select drive config', filetypes=(('Backup config files', 'backup.ini'), ('All files', '*.*')))
        if filename:
            load_config_from_file(filename)

    def save_config_file():
        """Save the config to selected drives."""

        if config['sources'] and config['destinations']:
            share_list = ','.join([item['dest_name'] for item in config['sources']])
            raw_vid_list = [drive['vid'] for drive in config['destinations']]
            raw_vid_list.extend(config['missing_drives'].keys())
            vid_list = ','.join(raw_vid_list)

            # For each drive letter that's connected, get drive info, and write file
            for drive in config['destinations']:
                # If config exists on drives, back it up first
                if os.path.isfile(os.path.join(drive['name'], BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE)):
                    shutil.move(os.path.join(drive['name'], BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE), os.path.join(drive['name'], BACKUP_CONFIG_DIR, f'{BACKUP_CONFIG_FILE}.old'))

                new_config_file = Config(os.path.join(drive['name'], BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE))

                # Write shares and VIDs to config file
                new_config_file.set('selection', 'sources', share_list)
                new_config_file.set('selection', 'vids', vid_list)

                # Write info for each drive to its own section
                for current_drive in config['destinations']:
                    new_config_file.set(current_drive['vid'], 'vid', current_drive['vid'])
                    new_config_file.set(current_drive['vid'], 'serial', current_drive['serial'])
                    new_config_file.set(current_drive['vid'], 'capacity', current_drive['capacity'])

                # Write info for missing drives
                for drive_vid, capacity in config['missing_drives'].items():
                    new_config_file.set(drive_vid, 'vid', drive_vid)
                    new_config_file.set(drive_vid, 'serial', 'Unknown')
                    new_config_file.set(drive_vid, 'capacity', capacity)

            # Since config files on drives changed, refresh the destination list
            load_dest_in_background()

            messagebox.showinfo(title='Save Backup Config', message='Backup config saved successfully')

    def save_config_file_as():
        """Save the config file to a specified location."""

        filename = filedialog.asksaveasfilename(initialdir='', initialfile='backup.ini', title='Save drive config', filetypes=(('Backup config files', 'backup.ini'), ('All files', '*.*')))

        if config['sources'] and config['destinations']:
            share_list = ','.join([item['dest_name'] for item in config['sources']])
            raw_vid_list = [drive['vid'] for drive in config['destinations']]
            raw_vid_list.extend(config['missing_drives'].keys())
            vid_list = ','.join(raw_vid_list)

            # Get drive info, and write file
            new_config_file = Config(filename)

            # Write shares and VIDs to config file
            new_config_file.set('selection', 'sources', share_list)
            new_config_file.set('selection', 'vids', vid_list)

            # Write info for each drive to its own section
            for current_drive in config['destinations']:
                new_config_file.set(current_drive['vid'], 'vid', current_drive['vid'])
                new_config_file.set(current_drive['vid'], 'serial', current_drive['serial'])
                new_config_file.set(current_drive['vid'], 'capacity', current_drive['capacity'])

            # Write info for missing drives
            for drive_vid, capacity in config['missing_drives'].items():
                new_config_file.set(drive_vid, 'vid', drive_vid)
                new_config_file.set(drive_vid, 'serial', 'Unknown')
                new_config_file.set(drive_vid, 'capacity', capacity)

            messagebox.showinfo(title='Save Backup Config', message='Backup config saved successfully')

    def delete_config_file_from_selected_drives():
        """Delete config files from drives in destination selection."""

        drive_list = [tree_dest.item(drive, 'text').strip(os.path.sep) for drive in tree_dest.selection()]
        drive_list = [drive for drive in drive_list if os.path.isfile(os.path.join(drive, BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE))]

        if drive_list:
            # Ask for confirmation before deleting
            if messagebox.askyesno('Delete config files?', 'Are you sure you want to delete the config files from the selected drives?'):
                # Delete config file on each drive
                [os.remove(os.path.join(drive, BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE)) for drive in drive_list]

                # Since config files on drives changed, refresh the destination list
                load_dest_in_background()

    window_backup_error_log = None

    def show_backup_error_log():
        """Show the backup error log."""

        global window_backup_error_log

        if window_backup_error_log is None or not window_backup_error_log.winfo_exists():
            # Initialize window
            window_backup_error_log = AppWindow(
                root=root_window,
                title='Backup Error Log',
                width=650,
                height=450,
                center=True,
                resizable=(False, False)
            )

            window_backup_error_log.main_frame.grid_columnconfigure(0, weight=1)
            window_backup_error_log.main_frame.grid_rowconfigure(1, weight=1)

            if SYS_PLATFORM == PLATFORM_WINDOWS:
                window_backup_error_log.iconbitmap(resource_path('media/icon.ico'))

            tk.Label(window_backup_error_log.main_frame, text='Error Log', font=(None, 20)).grid(row=0, column=0, sticky='ew', pady=WINDOW_ELEMENT_PADDING / 2)
            errorlog_error_list_frame = ScrollableFrame(window_backup_error_log.main_frame)
            errorlog_error_list_frame.grid(row=1, column=0, sticky='nsew')

            for error in backup_error_log:
                error_summary_block = DetailBlock(
                    parent=errorlog_error_list_frame.frame,
                    title=error['file'].split(os.path.sep)[-1],
                    uicolor=root_window.uicolor  # FIXME: Is there a better way to do this than to pass the uicolor instance from RootWindow into this?
                )

                error_summary_block.add_line('file_name', 'Filename', error['file'])
                error_summary_block.add_line('operation', 'Operation', error['mode'])
                error_summary_block.add_line('error', 'Error', error['error'])

                error_summary_block.pack(anchor='w', expand=1)

    def browse_for_source():
        """Browse for a source path, and either make it the source, or add to the list."""

        global last_selected_custom_source

        dir_name = filedialog.askdirectory(initialdir='', title='Select source folder')
        dir_name = os.path.sep.join(dir_name.split('/'))
        if not dir_name:
            return

        if settings_sourceMode.get() == Config.SOURCE_MODE_SINGLE_PATH:
            source_select_custom_single_path_label.configure(text=dir_name)
            config['source_drive'] = dir_name

            # Log last selection to preferences
            last_selected_custom_source = dir_name
            prefs.set('selection', 'last_selected_custom_source', dir_name)

            load_source_in_background()
        elif settings_sourceMode.get() == Config.SOURCE_MODE_MULTI_PATH:
            # Get list of paths already in tree
            existing_path_list = [tree_source.item(item, 'text') for item in tree_source.get_children()]

            # Only add item to list if it's not already there
            if dir_name not in existing_path_list:
                # Log last selection to preferences
                last_selected_custom_source = dir_name
                prefs.set('selection', 'last_selected_custom_source', dir_name)

                # Custom multi-source isn't stored in preferences, so default to
                # dir name
                path_name = dir_name.split(os.path.sep)[-1]
                tree_source.insert(parent='', index='end', text=dir_name, values=('Unknown', 0, path_name))

    def browse_for_source_in_background():
        """Load a browsed source in the background."""

        thread_manager.start(ThreadManager.SINGLE, is_progress_thread=True, target=browse_for_source, name='Browse for source', daemon=True)

    def browse_for_dest():
        """Browse for a destination path, and add to the list."""

        dir_name = filedialog.askdirectory(initialdir='', title='Select destination folder')
        dir_name = os.path.sep.join(dir_name.split('/'))
        if not dir_name:
            return

        if settings_destMode.get() != Config.DEST_MODE_PATHS:
            return

        # Get list of paths already in tree
        existing_path_list = [tree_dest.item(item, 'text') for item in tree_dest.get_children()]

        # Only add item to list if it's not already there
        if dir_name not in existing_path_list:
            # Custom dest isn't stored in preferences, so default to
            # dir name
            drive_free_space = shutil.disk_usage(dir_name).free
            path_space = get_directory_size(dir_name)
            config_space = get_directory_size(os.path.join(dir_name, BACKUP_CONFIG_DIR))

            dir_has_config_file = os.path.isfile(os.path.join(dir_name, BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE))
            name_stub = dir_name.split(os.path.sep)[-1].strip()
            avail_space = drive_free_space + path_space - config_space
            tree_dest.insert(parent='', index='end', text=dir_name, values=(human_filesize(avail_space), avail_space, 'Yes' if dir_has_config_file else '', name_stub))

    def browse_for_dest_in_background():
        """Load a browsed destination in the background."""

        thread_manager.start(ThreadManager.SINGLE, is_progress_thread=True, target=browse_for_dest, name='Browse for destination', daemon=True)

    def rename_source_item(item):
        """Rename an item in the source tree for multi-source mode.

        Args:
            item: The TreeView item to rename.
        """

        current_vals = tree_source.item(item, 'values')
        current_name = current_vals[2] if len(current_vals) >= 3 else ''

        new_name = simpledialog.askstring('Input', 'Enter a new name', initialvalue=current_name, parent=root_window)
        if new_name is not None:
            new_name = new_name.strip()
            new_name = re.search(r'[A-Za-z0-9_\- ]+', new_name)
            new_name = new_name.group(0) if new_name is not None else ''
        else:
            new_name = ''

        # Only set name in preferences if not in custom source mode
        if settings_sourceMode.get() == Config.SOURCE_MODE_MULTI_DRIVE:
            drive_name = tree_source.item(item, 'text')
            prefs.set('source_names', drive_name, new_name)

        tree_source.set(item, 'name', new_name)

    def delete_source_item(item):
        """Delete an item in the source tree for multi-source mode.

        Args:
            item: The TreeView item to rename.
        """

        tree_source.delete(item)

    def rename_dest_item(item):
        """Rename an item in the dest tree for custom dest mode.

        Args:
            item: The TreeView item to rename.
        """

        current_vals = tree_dest.item(item, 'values')
        current_name = current_vals[3] if len(current_vals) >= 4 else ''

        new_name = simpledialog.askstring('Input', 'Enter a new name', initialvalue=current_name, parent=root_window)
        if new_name is not None:
            new_name = new_name.strip()
            new_name = re.search(r'[A-Za-z0-9_\- ]+', new_name)
            new_name = new_name.group(0) if new_name is not None else ''
        else:
            new_name = ''

        tree_dest.set(item, 'vid', new_name)

    def delete_dest_item(item):
        """Delete an item in the dest tree for custom dest mode.

        Args:
            item: The TreeView item to rename.
        """

        tree_dest.delete(item)

    def show_source_right_click_menu(event):
        """Show the right click menu in the source tree for multi-source mode."""

        # Program needs to be in multi-source mode
        if settings_sourceMode.get() not in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
            return

        item = tree_source.identify_row(event.y)
        if not item:  # Don't do anything if no item was clicked on
            return

        tree_source.selection_set(item)
        source_right_click_menu.entryconfig('Rename', command=lambda: rename_source_item(item))
        if settings_sourceMode.get() == Config.SOURCE_MODE_MULTI_PATH:
            source_right_click_menu.entryconfig('Delete', command=lambda: delete_source_item(item))
        source_right_click_menu.post(event.x_root_window, event.y_root)

    def show_dest_right_click_menu(event):
        """Show the right click menu in the dest tree for custom dest mode."""

        # Program needs to be in path destination mode
        if settings_destMode.get() != Config.DEST_MODE_PATHS:
            return

        item = tree_dest.identify_row(event.y)
        if not item:  # Don't do anything if no item was clicked on
            return

        tree_dest.selection_set(item)
        dest_right_click_menu.entryconfig('Rename', command=lambda: rename_dest_item(item))
        dest_right_click_menu.entryconfig('Delete', command=lambda: delete_dest_item(item))
        dest_right_click_menu.post(event.x_root, event.y_root)

    def change_source_mode():
        """Change the mode for source selection."""

        global source_right_click_bind
        global WINDOW_MIN_WIDTH
        global PREV_SOURCE_MODE

        # If backup is running, ignore request to change
        if backup and backup.is_running():
            settings_sourceMode.set(PREV_SOURCE_MODE)
            return

        # If analysis is valid, invalidate it
        reset_analysis_output()

        prefs.set('selection', 'source_mode', settings_sourceMode.get())
        root_geom = root_window.geometry().split('+')
        root_size_geom = root_geom[0].split('x')
        CUR_WIN_WIDTH = int(root_size_geom[0])
        CUR_WIN_HEIGHT = int(root_size_geom[1])
        POS_X = int(root_geom[1])
        POS_Y = int(root_geom[2])

        if settings_sourceMode.get() in [Config.SOURCE_MODE_SINGLE_DRIVE, Config.SOURCE_MODE_SINGLE_PATH] and PREV_SOURCE_MODE not in [Config.SOURCE_MODE_SINGLE_DRIVE, Config.SOURCE_MODE_SINGLE_PATH]:
            tree_source.column('#0', width=SINGLE_SOURCE_TEXT_COL_WIDTH)
            tree_source.column('name', width=SINGLE_SOURCE_NAME_COL_WIDTH)
            tree_source['displaycolumns'] = ('size')

            WINDOW_MIN_WIDTH -= WINDOW_MULTI_SOURCE_EXTRA_WIDTH
            CUR_WIN_WIDTH -= WINDOW_MULTI_SOURCE_EXTRA_WIDTH
            root_window.geometry(f'{CUR_WIN_WIDTH}x{CUR_WIN_HEIGHT}+{POS_X}+{POS_Y}')
            root_window.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

            # Unbind right click menu
            try:
                tree_source.unbind('<Button-3>', source_right_click_bind)
            except tk._tkinter.TclError:
                pass

            config['source_mode'] == settings_sourceMode.get()
            PREV_SOURCE_MODE = settings_sourceMode.get()

            if settings_sourceMode.get() == Config.SOURCE_MODE_SINGLE_PATH:
                config['source_drive'] = last_selected_custom_source
        elif settings_sourceMode.get() in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH] and PREV_SOURCE_MODE not in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
            WINDOW_MIN_WIDTH += WINDOW_MULTI_SOURCE_EXTRA_WIDTH
            CUR_WIN_WIDTH += WINDOW_MULTI_SOURCE_EXTRA_WIDTH
            root_window.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
            root_window.geometry(f'{CUR_WIN_WIDTH}x{CUR_WIN_HEIGHT}+{POS_X}+{POS_Y}')

            tree_source.column('#0', width=MULTI_SOURCE_TEXT_COL_WIDTH)
            tree_source.column('name', width=MULTI_SOURCE_NAME_COL_WIDTH)
            tree_source['displaycolumns'] = ('name', 'size')

            # Bind right click menu
            if settings_sourceMode.get() == Config.SOURCE_MODE_MULTI_DRIVE:  # Delete option should only show in custom mode
                source_right_click_bind = tree_source.bind('<Button-3>', show_source_right_click_menu)

            config['source_mode'] == settings_sourceMode.get()
            PREV_SOURCE_MODE = settings_sourceMode.get()

        load_source_in_background()

    def change_dest_mode():
        """Change the mode for destination selection."""

        global dest_right_click_bind
        global PREV_DEST_MODE

        # If backup is running, ignore request to change
        if backup and backup.is_running():
            settings_destMode.set(PREV_DEST_MODE)
            return

        # If analysis is valid, invalidate it
        reset_analysis_output()

        prefs.set('selection', 'dest_mode', settings_destMode.get())

        if settings_destMode.get() == Config.DEST_MODE_DRIVES:
            tree_dest.column('#0', width=DEST_TREE_COLWIDTH_DRIVE)
            tree_dest.heading('vid', text='Volume ID')
            tree_dest.column('vid', width=90)
            tree_dest['displaycolumns'] = ('size', 'configfile', 'vid', 'serial')

            tree_dest.unbind('<Button-3>', dest_right_click_bind)

            config['dest_mode'] = settings_destMode.get()
            PREV_DEST_MODE = settings_destMode.get()
        elif settings_destMode.get() == Config.DEST_MODE_PATHS:
            tree_dest.column('#0', width=DEST_TREE_COLWIDTH_DRIVE + DEST_TREE_COLWIDTH_SERIAL - 50)
            tree_dest.column('vid', width=140)
            tree_dest.heading('vid', text='Name')
            tree_dest['displaycolumns'] = ('vid', 'size', 'configfile')

            dest_right_click_bind = tree_dest.bind('<Button-3>', show_dest_right_click_menu)

            config['dest_mode'] = settings_destMode.get()
            PREV_DEST_MODE = settings_destMode.get()

        if not thread_manager.is_alive('Refresh Destination'):
            thread_manager.start(ThreadManager.SINGLE, target=load_dest, is_progress_thread=True, name='Refresh Destination', daemon=True)

    def change_source_type(toggle_type: int):
        """Change the drive types for source selection.

        Args:
            toggle_type (int): The drive type to toggle.
        """

        global PREV_LOCAL_SOURCE_DRIVE
        global PREV_NETWORK_SOURCE_DRIVE

        # If backup is running, ignore request to change
        if backup and backup.is_running():
            settings_showDrives_source_local.set(PREV_LOCAL_SOURCE_DRIVE)
            settings_showDrives_source_network.set(PREV_NETWORK_SOURCE_DRIVE)
            return

        # If analysis is valid, invalidate it
        reset_analysis_output()

        selected_local = settings_showDrives_source_local.get()
        selected_network = settings_showDrives_source_network.get()

        # If both selections are unchecked, the last one has just been unchecked
        # In this case, re-check it, so that there's always some selection
        # TODO: This currently uses the fixed type to indicate local drives, but
        # will be used to select both fixed and removable drives. Should probably
        # find a proper solution for this...
        if not selected_local and not selected_network:
            if toggle_type == DRIVE_TYPE_LOCAL:
                settings_showDrives_source_local.set(True)
            elif toggle_type == DRIVE_TYPE_REMOTE:
                settings_showDrives_source_network.set(True)

        PREV_LOCAL_SOURCE_DRIVE = settings_showDrives_source_local.get()
        PREV_NETWORK_SOURCE_DRIVE = settings_showDrives_source_network.get()
        prefs.set('selection', 'source_network_drives', settings_showDrives_source_network.get())
        prefs.set('selection', 'source_local_drives', settings_showDrives_source_local.get())

        load_source_in_background()

    def change_destination_type(toggle_type: int):
        """Change the drive types for source selection.

        Args:
            toggle_type (int): The drive type to toggle.
        """

        global PREV_LOCAL_DEST_DRIVE
        global PREV_NETWORK_DEST_DRIVE

        # If backup is running, ignore request to change
        if backup and backup.is_running():
            settings_showDrives_dest_local.set(PREV_LOCAL_DEST_DRIVE)
            settings_showDrives_dest_network.set(PREV_NETWORK_DEST_DRIVE)
            return

        # If analysis is valid, invalidate it
        reset_analysis_output()

        selected_local = settings_showDrives_dest_local.get()
        selected_network = settings_showDrives_dest_network.get()

        # If both selections are unchecked, the last one has just been unchecked
        # In this case, re-check it, so that there's always some selection
        if not selected_local and not selected_network:
            if toggle_type == DRIVE_TYPE_LOCAL:
                settings_showDrives_dest_local.set(True)
            elif toggle_type == DRIVE_TYPE_REMOTE:
                settings_showDrives_dest_network.set(True)

        PREV_LOCAL_DEST_DRIVE = settings_showDrives_dest_local.get()
        PREV_NETWORK_DEST_DRIVE = settings_showDrives_dest_network.get()
        prefs.set('selection', 'destination_network_drives', settings_showDrives_dest_network.get())
        prefs.set('selection', 'destination_local_drives', settings_showDrives_dest_local.get())

        load_dest_in_background()

    def start_verify_data_from_hash_list():
        """Start data verification in a new thread"""

        if backup and backup.is_running():  # Backup can't be running while data verification takes place
            return

        drive_list = [drive['name'] for drive in config['destinations']]
        thread_manager.start(ThreadManager.KILLABLE, target=lambda: verify_data_integrity(drive_list), name='Data Verification', is_progress_thread=True, daemon=True)

    def update_ui_pre_analysis():
        """Update the UI before an analysis is run."""

        update_ui_component(Status.UPDATEUI_STATUS_BAR, Status.BACKUP_ANALYSIS_RUNNING)
        update_ui_component(Status.UPDATEUI_BACKUP_BTN, {'state': 'disable'})
        update_ui_component(Status.UPDATEUI_ANALYSIS_START)

    def update_ui_post_analysis(files_payload, summary_payload):
        """Update the UI after an analysis has been run.

        Args:
            files_payload (list): The file data to display in the UI.
            summary_payload (list): The summary data to display in the UI.
        """

        # Only run if there's a backup configured.
        if not backup:
            return

        if backup.status != Status.BACKUP_ANALYSIS_ABORTED:
            display_backup_command_info(backup.command_list)

            display_backup_summary_chunk(
                title='Files',
                payload=files_payload
            )

            display_backup_summary_chunk(
                title='Summary',
                payload=summary_payload
            )

            update_ui_component(Status.UPDATEUI_STATUS_BAR, Status.BACKUP_READY_FOR_BACKUP)
            update_ui_component(Status.UPDATEUI_BACKUP_BTN, {'state': 'normal'})
            update_ui_component(Status.UPDATEUI_ANALYSIS_END)
        else:
            # If thread halted, mark analysis as invalid
            update_ui_component(Status.UPDATEUI_STATUS_BAR, Status.BACKUP_READY_FOR_ANALYSIS)
            update_ui_component(Status.UPDATEUI_ANALYSIS_END)
            update_ui_component(Status.RESET_ANALYSIS_OUTPUT)

    def update_ui_during_backup():
        """Update the user interface using a RepeatedTimer."""

        if not backup:
            return

        backup_progress = backup.get_progress_updates()

        if backup.status == Status.BACKUP_ANALYSIS_RUNNING:
            progress.start_indeterminate()
        else:
            progress.stop_indeterminate()

        # Update ETA timer
        update_backup_eta_timer(backup_progress)

        # Update analysis file lists
        analysis_dict = {}
        for file_list, filename in backup_progress['delta']['analysis']:
            analysis_dict.setdefault(file_list, set()).add(filename)
        for file_list, filenames in analysis_dict.items():
            update_file_detail_lists(file_list, filenames)

        # Update working file for copies
        if backup_progress['total']['current_file'] is not None:
            filename, size, operation, display_index = backup_progress['total']['current_file']

            # Update file details info block
            if display_index is not None and display_index in cmd_info_blocks:
                cmd_info_blocks[display_index].configure('current_file', text=filename if filename is not None else '', fg=root_window.uicolor.NORMAL)
        else:
            filename, display_index = (None, None)

        # Update backup status for each command info block
        if backup_progress['total']['command_display_index'] is not None:
            cmd_info_blocks[backup_progress['total']['command_display_index']].state.configure(text='Running', fg=root_window.uicolor.RUNNING)
            backup.progress['command_display_index'] = None

        # Update status bar
        update_ui_component(Status.UPDATEUI_STATUS_BAR_DETAILS, filename if filename is not None else '')

        # Update copied files
        buffer = backup_progress['total']['buffer']

        if buffer['copied'] > buffer['total']:
            buffer['copied'] = buffer['total']

        if buffer['total'] > 0:
            percent_copied = buffer['copied'] / buffer['total'] * 100
        else:
            percent_copied = 100

        # If display index has been specified, write progress to GUI
        # URGENT: Fix updates stopping in status bar and file detail blocks
        #     after many operations have been completed
        # URGENT: When aborting backup after many operations, files continue copying
        #     This seems to be related to time. The longer the backups have
        #     been running, the more operations in continues to do before
        #     stopping after aborting the backup
        if display_index is not None:
            # FIXME: Progress bar jumps after completing backup, as though
            #     the progress or total changes when the backup completes
            progress.set(current=backup.progress['current'], total=backup.progress['total'])

            cmd_info_blocks[display_index].configure('current_file', text=buffer['display_filename'], fg=root_window.uicolor.NORMAL)
            if buffer['operation'] == Status.FILE_OPERATION_DELETE:
                cmd_info_blocks[display_index].configure('progress', text=f"Deleted {buffer['display_filename']}", fg=root_window.uicolor.NORMAL)
            elif buffer['operation'] == Status.FILE_OPERATION_COPY:
                cmd_info_blocks[display_index].configure('progress', text=f"{percent_copied:.2f}% \u27f6 {human_filesize(buffer['copied'])} of {human_filesize(buffer['total'])}", fg=root_window.uicolor.NORMAL)
            elif buffer['operation'] == Status.FILE_OPERATION_VERIFY:
                cmd_info_blocks[display_index].configure('progress', text=f"Verifying \u27f6 {percent_copied:.2f}% \u27f6 {human_filesize(buffer['copied'])} of {human_filesize(buffer['total'])}", fg=root_window.uicolor.BLUE)

        # Update file detail lists on deletes and copies
        for file in backup_progress['delta']['files']:
            filename, filesize, operation, display_index = file

            if operation == Status.FILE_OPERATION_DELETE:
                display_backup_progress(
                    copied=filesize,
                    total=filesize,
                    display_filename=filename.split(os.path.sep)[-1],
                    operation=operation,
                    display_index=display_index
                )

                if not os.path.exists(filename):
                    update_file_detail_lists(FileUtils.LIST_DELETE_SUCCESS, {filename})
                else:
                    update_file_detail_lists(FileUtils.LIST_DELETE_FAIL, {filename})
                    backup_error_log.append({'file': filename, 'mode': Status.FILE_OPERATION_DELETE, 'error': 'File or path does not exist'})
            elif operation == Status.FILE_OPERATION_COPY:
                update_file_detail_lists(FileUtils.LIST_SUCCESS, {filename})

        for file in backup_progress['delta']['failed']:
            filename, filesize, operation, display_index = file

            if operation == Status.FILE_OPERATION_DELETE:
                display_backup_progress(
                    copied=filesize,
                    total=filesize,
                    display_filename=filename.split(os.path.sep)[-1],
                    operation=operation,
                    display_index=display_index,
                )

                if os.path.exists(filename):
                    update_file_detail_lists(FileUtils.LIST_DELETE_FAIL, {filename})
                    backup_error_log.append({'file': filename, 'mode': Status.FILE_OPERATION_DELETE, 'error': 'File or path does not exist'})
                else:
                    update_file_detail_lists(FileUtils.LIST_DELETE_SUCCESS, {filename})
            elif operation == Status.FILE_OPERATION_COPY:
                update_file_detail_lists(FileUtils.LIST_FAIL, {filename})

    def update_ui_post_backup(command=None):
        """Update the UI after the backup finishes.

        Args:
            command: The backup command to pull data from (optional).
        """

        # Only run if a backup has been configured
        if not backup:
            return

        if command is not None:
            display_index = command['displayIndex']
            if backup.status == Status.BACKUP_BACKUP_ABORTED and backup.progress['current'] < backup.progress['total']:
                cmd_info_blocks[display_index].state.configure(text='Aborted', fg=root_window.uicolor.STOPPED)
                cmd_info_blocks[display_index].configure('progress', text='Aborted', fg=root_window.uicolor.STOPPED)
            else:
                cmd_info_blocks[display_index].state.configure(text='Done', fg=root_window.uicolor.FINISHED)
                cmd_info_blocks[display_index].configure('progress', text='Done', fg=root_window.uicolor.FINISHED)

        # If backup stopped, 
        if backup.status != Status.BACKUP_BACKUP_RUNNING:
            update_ui_component(Status.UPDATEUI_BACKUP_END)

    LOGGING_LEVEL = logging.INFO
    LOGGING_FORMAT = '[%(levelname)s] %(asctime)s - %(message)s'
    logging.basicConfig(level=LOGGING_LEVEL, format=LOGGING_FORMAT)

    file_detail_list = {
        FileUtils.LIST_TOTAL_DELETE: [],
        FileUtils.LIST_TOTAL_COPY: [],
        FileUtils.LIST_DELETE_SUCCESS: [],
        FileUtils.LIST_DELETE_FAIL: [],
        FileUtils.LIST_SUCCESS: [],
        FileUtils.LIST_FAIL: []
    }

    update_handler = UpdateHandler(
        current_version=APP_VERSION,
        allow_prereleases=config['allow_prereleases'],
        status_change_fn=update_status_bar_update,
        update_callback=check_for_updates
    )

    WINDOW_BASE_WIDTH = 1200  # QUESTION: Can BASE_WIDTH and MIN_WIDTH be rolled into one now that MIN is separate from actual width?
    WINDOW_MULTI_SOURCE_EXTRA_WIDTH = 170
    WINDOW_MIN_HEIGHT = 700
    MULTI_SOURCE_TEXT_COL_WIDTH = 120 if SYS_PLATFORM == PLATFORM_WINDOWS else 200
    MULTI_SOURCE_NAME_COL_WIDTH = 220 if SYS_PLATFORM == PLATFORM_WINDOWS else 140
    SINGLE_SOURCE_TEXT_COL_WIDTH = 170
    SINGLE_SOURCE_NAME_COL_WIDTH = 170

    WINDOW_MIN_WIDTH = WINDOW_BASE_WIDTH
    if prefs.get('selection', 'source_mode', Config.SOURCE_MODE_SINGLE_DRIVE, verify_data=Config.SOURCE_MODE_OPTIONS) in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
        WINDOW_MIN_WIDTH += WINDOW_MULTI_SOURCE_EXTRA_WIDTH

    root_window = RootWindow(
        title='BackDrop - Data Backup Tool',
        width=WINDOW_MIN_WIDTH,
        height=WINDOW_MIN_HEIGHT,
        center=True,
        status_bar=True,
        dark_mode=prefs.get('ui', 'dark_mode', True, data_type=Config.BOOLEAN)
    )

    appicon_image = ImageTk.PhotoImage(Image.open(resource_path('media/icon.png')))

    if SYS_PLATFORM == PLATFORM_WINDOWS:
        root_window.iconbitmap(resource_path('media/icon.ico'))
    elif SYS_PLATFORM == PLATFORM_LINUX:
        root_window.iconphoto(True, appicon_image)

    default_font = tkfont.nametofont("TkDefaultFont")
    default_font.configure(size=9)
    heading_font = tkfont.nametofont("TkHeadingFont")
    heading_font.configure(size=9, weight='normal')
    menu_font = tkfont.nametofont("TkMenuFont")
    menu_font.configure(size=9)

    # Selection and backup status, left side
    statusbar_selection = tk.Label(root_window.status_bar_frame, bg=root_window.uicolor.STATUS_BAR)
    statusbar_selection.grid(row=0, column=0, padx=6)
    update_status_bar_selection()
    statusbar_action = tk.Label(root_window.status_bar_frame, bg=root_window.uicolor.STATUS_BAR)
    statusbar_action.grid(row=0, column=1, padx=6)
    update_status_bar_action(Status.IDLE)
    statusbar_counter_btn = ttk.Button(root_window.status_bar_frame, text='0 failed', width=0, command=show_backup_error_log, state='disabled', style='danger.statusbar.TButton')
    statusbar_counter_btn.grid(row=0, column=2, ipadx=3, padx=3)
    statusbar_details = tk.Label(root_window.status_bar_frame, bg=root_window.uicolor.STATUS_BAR)
    statusbar_details.grid(row=0, column=3, padx=6)

    # Portable mode indicator and update status, right side
    if PORTABLE_MODE:
        statusbar_portablemode = tk.Label(root_window.status_bar_frame, text='Portable mode', bg=root_window.uicolor.STATUS_BAR)
        statusbar_portablemode.grid(row=0, column=99, padx=6)
    statusbar_update = tk.Label(root_window.status_bar_frame, text='', bg=root_window.uicolor.STATUS_BAR)
    statusbar_update.grid(row=0, column=100, padx=6)
    statusbar_update.bind('<Button-1>', lambda e: display_update_screen(update_info))

    # Set some default styling
    tk_style = ttk.Style()
    if SYS_PLATFORM == PLATFORM_WINDOWS:
        tk_style.theme_use('vista')
    elif SYS_PLATFORM == PLATFORM_LINUX:
        tk_style.theme_use('clam')

    tk_style.element_create('TButton', 'from', 'clam')
    tk_style.layout('TButton', [
        ('TButton.border', {'sticky': 'nswe', 'border': '1', 'children': [
            ('TButton.focus', {'sticky': 'nswe', 'children': [
                ('TButton.padding', {'sticky': 'nswe', 'children': [
                    ('TButton.label', {'sticky': 'nswe'})
                ]})
            ]})
        ]})
    ])

    if root_window.dark_mode:
        BUTTON_NORMAL_COLOR = '#585858'
        BUTTON_TEXT_COLOR = '#fff'
        BUTTON_ACTIVE_COLOR = '#666'
        BUTTON_PRESSED_COLOR = '#525252'
        BUTTON_DISABLED_COLOR = '#484848'
        BUTTON_DISABLED_TEXT_COLOR = '#888'

        DANGER_BUTTON_DISABLED_COLOR = '#700'
        DANGER_BUTTON_DISABLED_TEXT_COLOR = '#988'
    else:
        BUTTON_NORMAL_COLOR = '#ccc'
        BUTTON_TEXT_COLOR = '#000'
        BUTTON_ACTIVE_COLOR = '#d7d7d7'
        BUTTON_PRESSED_COLOR = '#c8c8c8'
        BUTTON_DISABLED_COLOR = '#ddd'
        BUTTON_DISABLED_TEXT_COLOR = '#777'

        DANGER_BUTTON_DISABLED_COLOR = '#900'
        DANGER_BUTTON_DISABLED_TEXT_COLOR = '#caa'

    tk_style.map(
        'TButton',
        background=[('pressed', '!disabled', BUTTON_PRESSED_COLOR), ('active', '!disabled', BUTTON_ACTIVE_COLOR), ('disabled', BUTTON_DISABLED_COLOR)],
        foreground=[('disabled', BUTTON_DISABLED_TEXT_COLOR)]
    )
    tk_style.map(
        'danger.TButton',
        background=[('pressed', '!disabled', '#900'), ('active', '!disabled', '#c00'), ('disabled', DANGER_BUTTON_DISABLED_COLOR)],
        foreground=[('disabled', DANGER_BUTTON_DISABLED_TEXT_COLOR)]
    )
    tk_style.map(
        'statusbar.TButton',
        background=[('pressed', '!disabled', root_window.uicolor.STATUS_BAR), ('active', '!disabled', root_window.uicolor.STATUS_BAR), ('disabled', root_window.uicolor.STATUS_BAR)],
        foreground=[('disabled', root_window.uicolor.FADED)]
    )
    tk_style.map(
        'tab.TButton',
        background=[('pressed', '!disabled', root_window.uicolor.BG), ('active', '!disabled', root_window.uicolor.BG), ('disabled', root_window.uicolor.BG)],
        foreground=[('disabled', root_window.uicolor.FADED), ('active', '!disabled', root_window.uicolor.FG)]
    )
    tk_style.configure('TButton', background=BUTTON_NORMAL_COLOR, foreground=BUTTON_TEXT_COLOR, bordercolor=BUTTON_NORMAL_COLOR, borderwidth=0, padding=(6, 4))
    tk_style.configure('danger.TButton', background='#b00', foreground='#fff', bordercolor='#b00', borderwidth=0)
    tk_style.configure('slim.TButton', padding=(2, 2))
    tk_style.configure('statusbar.TButton', padding=(3, 0), background=root_window.uicolor.STATUS_BAR, foreground=root_window.uicolor.FG)
    tk_style.configure('tab.TButton', padding=(3, 0), background=root_window.uicolor.BG, foreground=root_window.uicolor.FADED)
    tk_style.configure('active.tab.TButton', foreground=root_window.uicolor.FG)
    tk_style.configure('danger.statusbar.TButton', foreground=root_window.uicolor.DANGER)

    tk_style.configure('tooltip.TLabel', background=root_window.uicolor.BG, foreground=root_window.uicolor.TOOLTIP)
    tk_style.configure('on.toggle.TLabel', background=root_window.uicolor.BG, foreground=root_window.uicolor.GREEN)
    tk_style.configure('off.toggle.TLabel', background=root_window.uicolor.BG, foreground=root_window.uicolor.FADED)

    tk_style.configure('TCheckbutton', background=root_window.uicolor.BG, foreground=root_window.uicolor.NORMAL)
    tk_style.configure('TFrame', background=root_window.uicolor.BG, foreground=root_window.uicolor.NORMAL)

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
    tk_style.configure('custom.Treeview.Heading', background=root_window.uicolor.BGACCENT, foreground=root_window.uicolor.FG, padding=2.5)
    tk_style.configure('custom.Treeview', background=root_window.uicolor.BGACCENT2, fieldbackground=root_window.uicolor.BGACCENT2, foreground=root_window.uicolor.FG, bordercolor=root_window.uicolor.BGACCENT3)
    tk_style.map('custom.Treeview', foreground=[('disabled', 'SystemGrayText'), ('!disabled', '!selected', root_window.uicolor.NORMAL), ('selected', root_window.uicolor.BLACK)], background=[('disabled', 'SystemButtonFace'), ('!disabled', '!selected', root_window.uicolor.BGACCENT2), ('selected', root_window.uicolor.COLORACCENT)])

    tk_style.element_create('custom.Progressbar.trough', 'from', 'clam')
    tk_style.element_create('custom.Progressbar.pbar', 'from', 'default')
    tk_style.layout('custom.Progressbar', [
        ('custom.Progressbar.trough', {'sticky': 'nsew', 'children': [
            ('custom.Progressbar.padding', {'sticky': 'nsew', 'children': [
                ('custom.Progressbar.pbar', {'side': 'left', 'sticky': 'ns'})
            ]})
        ]})
    ])
    tk_style.configure('custom.Progressbar', padding=4, background=root_window.uicolor.COLORACCENT, bordercolor=root_window.uicolor.BGACCENT3, borderwidth=0, troughcolor=root_window.uicolor.BG, lightcolor=root_window.uicolor.COLORACCENT, darkcolor=root_window.uicolor.COLORACCENT)

    def on_close():
        if not thread_manager.is_alive('Backup'):
            root_window.quit()
            exit()

        if messagebox.askokcancel('Quit?', 'There\'s still a background process running. Are you sure you want to kill it?', parent=root_window):
            if backup:
                backup.kill()
            root_window.quit()
            exit()

    # Add menu bar
    menubar = tk.Menu(root_window)

    # File menu
    file_menu = tk.Menu(menubar, tearoff=0, bg=root_window.uicolor.DEFAULT_BG, fg=root_window.uicolor.BLACK)
    file_menu.add_command(label='Open Backup Config...', underline=0, accelerator='Ctrl+O', command=open_config_file)
    file_menu.add_command(label='Save Backup Config', underline=0, accelerator='Ctrl+S', command=save_config_file)
    file_menu.add_command(label='Save Backup Config As...', underline=19, accelerator='Ctrl+Shift+S', command=save_config_file_as)
    file_menu.add_separator()
    file_menu.add_command(label='Exit', underline=1, command=on_close)
    menubar.add_cascade(label='File', underline=0, menu=file_menu)

    # Selection menu
    selection_menu = tk.Menu(menubar, tearoff=0, bg=root_window.uicolor.DEFAULT_BG, fg=root_window.uicolor.BLACK)
    settings_showDrives_source_network = tk.BooleanVar(value=prefs.get('selection', 'source_network_drives', default=False, data_type=Config.BOOLEAN))
    settings_showDrives_source_local = tk.BooleanVar(value=prefs.get('selection', 'source_local_drives', default=True, data_type=Config.BOOLEAN))
    PREV_NETWORK_SOURCE_DRIVE = settings_showDrives_source_network.get()
    PREV_LOCAL_SOURCE_DRIVE = settings_showDrives_source_local.get()
    selection_menu.add_checkbutton(label='Source Network Drives', onvalue=True, offvalue=False, variable=settings_showDrives_source_network, command=lambda: change_source_type(DRIVE_TYPE_REMOTE))
    selection_menu.add_checkbutton(label='Source Local Drives', onvalue=True, offvalue=False, variable=settings_showDrives_source_local, command=lambda: change_source_type(DRIVE_TYPE_LOCAL))
    settings_showDrives_dest_network = tk.BooleanVar(value=prefs.get('selection', 'destination_network_drives', default=False, data_type=Config.BOOLEAN))
    settings_showDrives_dest_local = tk.BooleanVar(value=prefs.get('selection', 'destination_local_drives', default=True, data_type=Config.BOOLEAN))
    PREV_NETWORK_DEST_DRIVE = settings_showDrives_dest_network.get()
    PREV_LOCAL_DEST_DRIVE = settings_showDrives_dest_local.get()
    selection_menu.add_checkbutton(label='Destination Network Drives', onvalue=True, offvalue=False, variable=settings_showDrives_dest_network, command=lambda: change_destination_type(DRIVE_TYPE_REMOTE))
    selection_menu.add_checkbutton(label='Destination Local Drives', onvalue=True, offvalue=False, variable=settings_showDrives_dest_local, command=lambda: change_destination_type(DRIVE_TYPE_LOCAL))
    selection_menu.add_separator()
    selection_source_mode_menu = tk.Menu(selection_menu, tearoff=0, bg=root_window.uicolor.DEFAULT_BG, fg=root_window.uicolor.BLACK)
    settings_sourceMode = tk.StringVar(value=prefs.get('selection', 'source_mode', verify_data=Config.SOURCE_MODE_OPTIONS, default=Config.SOURCE_MODE_SINGLE_DRIVE))
    PREV_SOURCE_MODE = settings_sourceMode.get()
    selection_source_mode_menu.add_checkbutton(label='Single drive, select subfolders', onvalue=Config.SOURCE_MODE_SINGLE_DRIVE, offvalue=Config.SOURCE_MODE_SINGLE_DRIVE, variable=settings_sourceMode, command=change_source_mode)
    selection_source_mode_menu.add_checkbutton(label='Multi drive, select drives', onvalue=Config.SOURCE_MODE_MULTI_DRIVE, offvalue=Config.SOURCE_MODE_MULTI_DRIVE, variable=settings_sourceMode, command=change_source_mode)
    selection_source_mode_menu.add_separator()
    selection_source_mode_menu.add_checkbutton(label='Single path, select subfolders', onvalue=Config.SOURCE_MODE_SINGLE_PATH, offvalue=Config.SOURCE_MODE_SINGLE_PATH, variable=settings_sourceMode, command=change_source_mode)
    selection_source_mode_menu.add_checkbutton(label='Multi path, select paths', onvalue=Config.SOURCE_MODE_MULTI_PATH, offvalue=Config.SOURCE_MODE_MULTI_PATH, variable=settings_sourceMode, command=change_source_mode)
    selection_menu.add_cascade(label='Source Mode', underline=0, menu=selection_source_mode_menu)
    selection_dest_mode_menu = tk.Menu(selection_menu, tearoff=0, bg=root_window.uicolor.DEFAULT_BG, fg=root_window.uicolor.BLACK)
    settings_destMode = tk.StringVar(value=prefs.get('selection', 'dest_mode', verify_data=Config.DEST_MODE_OPTIONS, default=Config.DEST_MODE_DRIVES))
    PREV_DEST_MODE = settings_destMode.get()
    selection_dest_mode_menu.add_checkbutton(label='Drives', onvalue=Config.DEST_MODE_DRIVES, offvalue=Config.DEST_MODE_DRIVES, variable=settings_destMode, command=change_dest_mode)
    selection_dest_mode_menu.add_checkbutton(label='Paths', onvalue=Config.DEST_MODE_PATHS, offvalue=Config.DEST_MODE_PATHS, variable=settings_destMode, command=change_dest_mode)
    selection_menu.add_cascade(label='Destination Mode', underline=0, menu=selection_dest_mode_menu)
    menubar.add_cascade(label='Selection', underline=0, menu=selection_menu)

    # View menu
    view_menu = tk.Menu(menubar, tearoff=0, bg=root_window.uicolor.DEFAULT_BG, fg=root_window.uicolor.BLACK)
    view_menu.add_command(label='Refresh Source', accelerator='Ctrl+F5', command=load_source_in_background)
    view_menu.add_command(label='Refresh Destination', underline=0, accelerator='F5', command=load_dest_in_background)
    show_file_details_pane = tk.BooleanVar()
    view_menu.add_separator()
    view_menu.add_command(label='Backup Error Log', accelerator='Ctrl+E', command=show_backup_error_log)
    menubar.add_cascade(label='View', underline=0, menu=view_menu)

    # Actions menu
    actions_menu = tk.Menu(menubar, tearoff=0, bg=root_window.uicolor.DEFAULT_BG, fg=root_window.uicolor.BLACK)
    actions_menu.add_command(label='Verify Data Integrity on Selected Destinations', underline=0, command=start_verify_data_from_hash_list)
    actions_menu.add_command(label='Delete Config from Selected Destinations', command=delete_config_file_from_selected_drives)
    menubar.add_cascade(label='Actions', underline=0, menu=actions_menu)

    # Preferences menu
    preferences_menu = tk.Menu(menubar, tearoff=0, bg=root_window.uicolor.DEFAULT_BG, fg=root_window.uicolor.BLACK)
    preferences_verification_menu = tk.Menu(preferences_menu, tearoff=0, bg=root_window.uicolor.DEFAULT_BG, fg=root_window.uicolor.BLACK)
    settings_verifyAllFiles = tk.BooleanVar(value=prefs.get('verification', 'verify_all_files', default=False, data_type=Config.BOOLEAN))
    preferences_verification_menu.add_checkbutton(label='Verify Known Files', onvalue=False, offvalue=False, variable=settings_verifyAllFiles, command=lambda: prefs.set('verification', 'verify_all_files', settings_verifyAllFiles.get()))
    preferences_verification_menu.add_checkbutton(label='Verify All Files', onvalue=True, offvalue=True, variable=settings_verifyAllFiles, command=lambda: prefs.set('verification', 'verify_all_files', settings_verifyAllFiles.get()))
    preferences_menu.add_cascade(label='Data Integrity Verification', underline=0, menu=preferences_verification_menu)
    settings_darkModeEnabled = tk.BooleanVar(value=root_window.dark_mode)
    preferences_menu.add_checkbutton(label='Enable Dark Mode (requires restart)', onvalue=1, offvalue=0, variable=settings_darkModeEnabled, command=lambda: prefs.set('ui', 'dark_mode', settings_darkModeEnabled.get()))
    menubar.add_cascade(label='Preferences', underline=0, menu=preferences_menu)

    # Help menu
    help_menu = tk.Menu(menubar, tearoff=0, bg=root_window.uicolor.DEFAULT_BG, fg=root_window.uicolor.BLACK)
    help_menu.add_command(label='Check for Updates', command=lambda: thread_manager.start(
        ThreadManager.SINGLE,
        target=update_handler.check,
        name='Update Check',
        daemon=True
    ))
    settings_allow_prerelease_updates = tk.BooleanVar(value=config['allow_prereleases'])
    help_menu.add_checkbutton(label='Allow Prereleases', onvalue=True, offvalue=False, variable=settings_allow_prerelease_updates, command=lambda: prefs.set('ui', 'allow_prereleases', settings_allow_prerelease_updates.get()))
    menubar.add_cascade(label='Help', underline=0, menu=help_menu)

    # Key bindings
    root_window.bind('<Control-o>', lambda e: open_config_file())
    root_window.bind('<Control-s>', lambda e: save_config_file())
    root_window.bind('<Control-Shift-S>', lambda e: save_config_file_as())
    root_window.bind('<Control-e>', lambda e: show_backup_error_log())

    root_window.config(menu=menubar)

    icon_windows = ImageTk.PhotoImage(Image.open(resource_path(f"media/windows{'_light' if root_window.dark_mode else ''}.png")))
    icon_windows_color = ImageTk.PhotoImage(Image.open(resource_path('media/windows_color.png')))
    icon_zip = ImageTk.PhotoImage(Image.open(resource_path(f"media/zip{'_light' if root_window.dark_mode else ''}.png")))
    icon_zip_color = ImageTk.PhotoImage(Image.open(resource_path('media/zip_color.png')))
    icon_debian = ImageTk.PhotoImage(Image.open(resource_path(f"media/debian{'_light' if root_window.dark_mode else ''}.png")))
    icon_debian_color = ImageTk.PhotoImage(Image.open(resource_path('media/debian_color.png')))
    icon_targz = ImageTk.PhotoImage(Image.open(resource_path(f"media/targz{'_light' if root_window.dark_mode else ''}.png")))
    icon_targz_color = ImageTk.PhotoImage(Image.open(resource_path('media/targz_color.png')))

    # Progress/status values
    progress_bar = ttk.Progressbar(root_window.main_frame, maximum=100, style='custom.Progressbar')
    progress_bar.grid(row=10, column=1, columnspan=3, sticky='ew', padx=(0, WINDOW_ELEMENT_PADDING), pady=(WINDOW_ELEMENT_PADDING, 0))

    progress = Progress(
        progress_bar=progress_bar,
        thread_manager=thread_manager
    )

    source_avail_drive_list = []
    source_drive_default = tk.StringVar()

    # Tree frames for tree and scrollbar
    tree_source_frame = tk.Frame(root_window.main_frame)

    tree_source = ttk.Treeview(tree_source_frame, columns=('size', 'rawsize', 'name'), style='custom.Treeview')
    if settings_sourceMode.get() in [Config.SOURCE_MODE_SINGLE_DRIVE, Config.SOURCE_MODE_SINGLE_PATH]:
        tree_source_display_cols = ('size')
    elif settings_sourceMode.get() in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
        tree_source_display_cols = ('name', 'size')

    if settings_sourceMode.get() in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
        SOURCE_TEXT_COL_WIDTH = 200  # Windows 120
        SOURCE_NAME_COL_WIDTH = 140  # Windows 220
    else:
        SOURCE_TEXT_COL_WIDTH = 170
        SOURCE_NAME_COL_WIDTH = 170

    tree_source.heading('#0', text='Path')
    tree_source.column('#0', width=SOURCE_TEXT_COL_WIDTH)
    tree_source.heading('name', text='Name')
    tree_source.column('name', width=SOURCE_NAME_COL_WIDTH)
    tree_source.heading('size', text='Size')
    tree_source.column('size', width=80)
    tree_source['displaycolumns'] = tree_source_display_cols

    tree_source.pack(side='left')
    tree_source_scrollbar = ttk.Scrollbar(tree_source_frame, orient='vertical', command=tree_source.yview)
    tree_source_scrollbar.pack(side='left', fill='y')
    tree_source.configure(yscrollcommand=tree_source_scrollbar.set)

    source_meta_frame = tk.Frame(root_window.main_frame)
    tk.Grid.columnconfigure(source_meta_frame, 0, weight=1)

    share_space_frame = tk.Frame(source_meta_frame)
    share_space_frame.grid(row=0, column=0)
    share_selected_space_frame = tk.Frame(share_space_frame)
    share_selected_space_frame.grid(row=0, column=0)
    share_selected_space_label = tk.Label(share_selected_space_frame, text='Selected:').pack(side='left')
    share_selected_space = tk.Label(share_selected_space_frame, text='None', fg=root_window.uicolor.FADED)
    share_selected_space.pack(side='left')
    share_total_space_frame = tk.Frame(share_space_frame)
    share_total_space_frame.grid(row=0, column=1, padx=(12, 0))
    share_total_space_label = tk.Label(share_total_space_frame, text='Total:').pack(side='left')
    share_total_space = tk.Label(share_total_space_frame, text='~None', fg=root_window.uicolor.FADED)
    share_total_space.pack(side='left')

    source_select_frame = tk.Frame(root_window.main_frame)
    source_select_frame.grid(row=0, column=1, pady=WINDOW_ELEMENT_PADDING / 4, sticky='ew')

    source_select_single_frame = tk.Frame(source_select_frame)
    tk.Label(source_select_single_frame, text='Source:').pack(side='left')
    PREV_SOURCE_DRIVE = source_drive_default
    source_select_menu = ttk.OptionMenu(source_select_single_frame, source_drive_default, '', *tuple([]), command=change_source_drive)
    source_select_menu['menu'].config(selectcolor=root_window.uicolor.FG)
    source_select_menu.pack(side='left', padx=(12, 0))

    source_select_multi_frame = tk.Frame(source_select_frame)
    tk.Label(source_select_multi_frame, text='Multi-source mode, selection disabled').pack()

    source_select_custom_single_frame = tk.Frame(source_select_frame)
    source_select_custom_single_frame.grid_columnconfigure(0, weight=1)
    selected_custom_source_text = last_selected_custom_source if last_selected_custom_source and os.path.isdir(last_selected_custom_source) else 'Custom source'
    source_select_custom_single_path_label = tk.Label(source_select_custom_single_frame, text=selected_custom_source_text)
    source_select_custom_single_path_label.grid(row=0, column=0, sticky='w')
    source_select_custom_single_browse_button = ttk.Button(source_select_custom_single_frame, text='Browse', command=browse_for_source_in_background, style='slim.TButton')
    source_select_custom_single_browse_button.grid(row=0, column=1)

    source_select_custom_multi_frame = tk.Frame(source_select_frame)
    source_select_custom_multi_frame.grid_columnconfigure(0, weight=1)
    source_select_custom_multi_path_label = tk.Label(source_select_custom_multi_frame, text='Custom multi-source mode')
    source_select_custom_multi_path_label.grid(row=0, column=0)
    source_select_custom_multi_browse_button = ttk.Button(source_select_custom_multi_frame, text='Browse', command=browse_for_source_in_background, style='slim.TButton')
    source_select_custom_multi_browse_button.grid(row=0, column=1)

    # Source tree right click menu
    source_right_click_menu = tk.Menu(tree_source, tearoff=0)
    source_right_click_menu.add_command(label='Rename', underline=0)
    if settings_sourceMode.get() == Config.SOURCE_MODE_MULTI_PATH:
        source_right_click_menu.add_command(label='Delete')

    source_select_bind = tree_source.bind("<<TreeviewSelect>>", select_source_in_background)
    if settings_sourceMode.get() in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
        source_right_click_bind = tree_source.bind('<Button-3>', show_source_right_click_menu)
    else:
        source_right_click_bind = None

    source_warning = tk.Label(root_window.main_frame, text='No source drives are available', font=(None, 14), wraplength=250, bg=root_window.uicolor.ERROR, fg=root_window.uicolor.BLACK)

    root_window.bind('<Control-F5>', lambda x: load_source_in_background())

    tree_dest_frame = tk.Frame(root_window.main_frame)
    tree_dest_frame.grid(row=1, column=2, sticky='ns', padx=(WINDOW_ELEMENT_PADDING, 0))

    dest_mode_frame = tk.Frame(root_window.main_frame)
    dest_mode_frame.grid(row=0, column=2, pady=WINDOW_ELEMENT_PADDING / 4, sticky='ew')

    def toggle_split_mode(event):
        """Handle toggling of split mode based on checkbox value."""

        if (not backup or not backup.is_running()) and not verification_running:
            config['splitMode'] = not config['splitMode']

            if config['splitMode']:
                split_mode_frame.configure(highlightbackground=root_window.uicolor.GREEN)
                split_mode_status.configure(style='on.toggle.TLabel')
            else:
                split_mode_frame.configure(highlightbackground=root_window.uicolor.FADED)
                split_mode_status.configure(style='off.toggle.TLabel')

    dest_select_normal_frame = tk.Frame(dest_mode_frame)
    dest_select_normal_frame.pack()
    alt_tooltip_normal_frame = tk.Frame(dest_select_normal_frame, highlightbackground=root_window.uicolor.TOOLTIP, highlightthickness=1)
    alt_tooltip_normal_frame.pack(side='left', ipadx=WINDOW_ELEMENT_PADDING / 2, ipady=4)
    ttk.Label(alt_tooltip_normal_frame, text='Hold ALT when selecting a drive to ignore config files', style='tooltip.TLabel').pack(fill='y', expand=1)

    dest_select_custom_frame = tk.Frame(dest_mode_frame)
    dest_select_custom_frame.grid_columnconfigure(0, weight=1)
    alt_tooltip_custom_frame = tk.Frame(dest_select_custom_frame, highlightbackground=root_window.uicolor.TOOLTIP, highlightthickness=1)
    alt_tooltip_custom_frame.grid(row=0, column=0, ipadx=WINDOW_ELEMENT_PADDING / 2, ipady=4)
    ttk.Label(alt_tooltip_custom_frame, text='Hold ALT when selecting a drive to ignore config files', style='tooltip.TLabel').pack(fill='y', expand=1)
    dest_select_custom_browse_button = ttk.Button(dest_select_custom_frame, text='Browse', command=browse_for_dest_in_background, style='slim.TButton')
    dest_select_custom_browse_button.grid(row=0, column=1)

    DEST_TREE_COLWIDTH_DRIVE = 50 if SYS_PLATFORM == PLATFORM_WINDOWS else 150
    DEST_TREE_COLWIDTH_VID = 140 if settings_destMode.get() == Config.DEST_MODE_PATHS else 90
    DEST_TREE_COLWIDTH_SERIAL = 150 if SYS_PLATFORM == PLATFORM_WINDOWS else 50

    tree_dest = ttk.Treeview(tree_dest_frame, columns=('size', 'rawsize', 'configfile', 'vid', 'serial'), style='custom.Treeview')
    tree_dest.heading('#0', text='Drive')
    if settings_destMode.get() == Config.DEST_MODE_PATHS:
        tree_dest.column('#0', width=DEST_TREE_COLWIDTH_DRIVE + DEST_TREE_COLWIDTH_SERIAL - 50)
    else:
        tree_dest.column('#0', width=DEST_TREE_COLWIDTH_DRIVE)
    tree_dest.heading('size', text='Size')
    tree_dest.column('size', width=80)
    tree_dest.heading('configfile', text='Config')
    tree_dest.column('configfile', width=50)
    if settings_destMode.get() == Config.DEST_MODE_DRIVES:
        tree_dest.heading('vid', text='Volume ID')
    elif settings_destMode.get() == Config.DEST_MODE_PATHS:
        tree_dest.heading('vid', text='Name')
    tree_dest.column('vid', width=DEST_TREE_COLWIDTH_VID)
    tree_dest.heading('serial', text='Serial')
    tree_dest.column('serial', width=DEST_TREE_COLWIDTH_SERIAL)

    if settings_destMode.get() == Config.DEST_MODE_DRIVES:
        tree_dest_display_cols = ('size', 'configfile', 'vid', 'serial')
    elif settings_destMode.get() == Config.DEST_MODE_PATHS:
        tree_dest_display_cols = ('vid', 'size', 'configfile')
    tree_dest['displaycolumns'] = tree_dest_display_cols

    tree_dest.pack(side='left')
    tree_dest_scrollbar = ttk.Scrollbar(tree_dest_frame, orient='vertical', command=tree_dest.yview)
    tree_dest_scrollbar.pack(side='left', fill='y')
    tree_dest.configure(yscrollcommand=tree_dest_scrollbar.set)

    root_window.bind('<F5>', lambda x: load_dest_in_background())

    # Dest tree right click menu
    dest_right_click_menu = tk.Menu(tree_source, tearoff=0)
    dest_right_click_menu.add_command(label='Rename', underline=0)
    dest_right_click_menu.add_command(label='Delete')

    if settings_destMode.get() == Config.DEST_MODE_PATHS:
        dest_right_click_bind = tree_dest.bind('<Button-3>', show_dest_right_click_menu)
    else:
        dest_right_click_bind = None

    # There's an invisible 1px background on buttons. When changing this in icon buttons, it becomes
    # visible, so 1px needs to be added back
    dest_meta_frame = tk.Frame(root_window.main_frame)
    dest_meta_frame.grid(row=2, column=2, sticky='nsew', pady=(1, 0))
    tk.Grid.columnconfigure(dest_meta_frame, 0, weight=1)

    dest_split_warning_frame = tk.Frame(root_window.main_frame, bg=root_window.uicolor.WARNING)
    dest_split_warning_frame.rowconfigure(0, weight=1)
    dest_split_warning_frame.columnconfigure(0, weight=1)
    dest_split_warning_frame.columnconfigure(10, weight=1)

    # TODO: Can this be cleaned up?
    tk.Frame(dest_split_warning_frame).grid(row=0, column=1)
    split_warning_prefix = tk.Label(dest_split_warning_frame, text='There are', bg=root_window.uicolor.WARNING, fg=root_window.uicolor.BLACK)
    split_warning_prefix.grid(row=0, column=1, sticky='ns')
    split_warning_missing_drive_count = tk.Label(dest_split_warning_frame, text='0', bg=root_window.uicolor.WARNING, fg=root_window.uicolor.BLACK, font=(None, 18, 'bold'))
    split_warning_missing_drive_count.grid(row=0, column=2, sticky='ns')
    split_warning_suffix = tk.Label(dest_split_warning_frame, text='drives in the config that aren\'t connected. Please connect them, or enable split mode.', bg=root_window.uicolor.WARNING, fg=root_window.uicolor.BLACK)
    split_warning_suffix.grid(row=0, column=3, sticky='ns')
    tk.Frame(dest_split_warning_frame).grid(row=0, column=10)

    drive_space_frame = tk.Frame(dest_meta_frame)
    drive_space_frame.grid(row=0, column=0)

    config_selected_space_frame = tk.Frame(drive_space_frame)
    config_selected_space_frame.grid(row=0, column=0)
    tk.Label(config_selected_space_frame, text='Config:').pack(side='left')
    config_selected_space = tk.Label(config_selected_space_frame, text='None', fg=root_window.uicolor.FADED)
    config_selected_space.pack(side='left')

    drive_selected_space_frame = tk.Frame(drive_space_frame)
    drive_selected_space_frame.grid(row=0, column=1, padx=(12, 0))
    tk.Label(drive_selected_space_frame, text='Selected:').pack(side='left')
    drive_selected_space = tk.Label(drive_selected_space_frame, text='None', fg=root_window.uicolor.FADED)
    drive_selected_space.pack(side='left')

    drive_total_space_frame = tk.Frame(drive_space_frame)
    drive_total_space_frame.grid(row=0, column=2, padx=(12, 0))
    tk.Label(drive_total_space_frame, text='Avail:').pack(side='left')
    drive_total_space = tk.Label(drive_total_space_frame, text=human_filesize(0), fg=root_window.uicolor.FADED)
    drive_total_space.pack(side='left')
    split_mode_frame = tk.Frame(drive_space_frame, highlightbackground=root_window.uicolor.GREEN if config['splitMode'] else root_window.uicolor.FADED, highlightthickness=1)
    split_mode_frame.grid(row=0, column=3, padx=(12, 0), pady=4, ipadx=WINDOW_ELEMENT_PADDING / 2, ipady=3)
    split_mode_status = ttk.Label(split_mode_frame, text='Split mode', style='on.toggle.TLabel' if config['splitMode'] else 'off.toggle.TLabel')
    split_mode_status.pack(fill='y', expand=1)

    split_mode_frame.bind('<Button-1>', toggle_split_mode)
    split_mode_status.bind('<Button-1>', toggle_split_mode)

    dest_select_bind = tree_dest.bind('<<TreeviewSelect>>', select_dest_in_background)

    # Add tab frame for main detail views
    content_tab_frame = TabbedFrame(root_window.main_frame, tabs={
        'summary': 'Backup summary',
        'details': 'Backup details'
    })
    content_tab_frame.tab['summary']['content'] = ScrollableFrame(content_tab_frame.frame)
    content_tab_frame.tab['details']['content'] = ScrollableFrame(content_tab_frame.frame)
    content_tab_frame.grid(row=5, column=1, columnspan=2, sticky='nsew')
    tk.Grid.rowconfigure(root_window.main_frame, 5, weight=1)
    content_tab_frame.change_tab('details')
    # FIXME: Canvas returning wrong width that's smaller than actual width of canvas
    content_tab_frame.tab['details']['width'] = content_tab_frame.tab['details']['content'].winfo_width()
    content_tab_frame.change_tab('summary')
    content_tab_frame.tab['summary']['width'] = content_tab_frame.tab['summary']['content'].winfo_width()

    # Backup ETA (tab gutter)
    backup_eta_label = tk.Label(content_tab_frame.gutter, text='Please start a backup to show ETA')
    backup_eta_label.pack()

    # Right side frame
    tk.Grid.columnconfigure(root_window.main_frame, 3, weight=1)
    right_side_frame = tk.Frame(root_window.main_frame)
    right_side_frame.grid(row=0, column=3, rowspan=7, sticky='nsew', pady=(WINDOW_ELEMENT_PADDING / 2, 0))

    backup_file_details_frame = tk.Frame(right_side_frame)
    backup_file_details_frame.pack(fill='both', expand=True, padx=WINDOW_ELEMENT_PADDING)
    backup_file_details_frame.pack_propagate(0)

    file_details_pending_delete_header_line = tk.Frame(backup_file_details_frame)
    file_details_pending_delete_header_line.grid(row=0, column=0, sticky='w')
    file_details_pending_delete_header = tk.Label(file_details_pending_delete_header_line, text='Files to delete', font=(None, 11, 'bold'))
    file_details_pending_delete_header.pack(side='left')
    file_details_pending_delete_tooltip = tk.Label(file_details_pending_delete_header_line, text='(Click to copy)', fg=root_window.uicolor.FADED)
    file_details_pending_delete_tooltip.pack(side='left')
    file_details_pending_delete_counter_frame = tk.Frame(backup_file_details_frame)
    file_details_pending_delete_counter_frame.grid(row=1, column=0, sticky='w')
    file_details_pending_delete_counter = tk.Label(file_details_pending_delete_counter_frame, text='0', font=(None, 28))
    file_details_pending_delete_counter.pack(side='left', anchor='s')
    tk.Label(file_details_pending_delete_counter_frame, text='of', font=(None, 11), fg=root_window.uicolor.FADED).pack(side='left', anchor='s', pady=(0, 5))
    file_details_pending_delete_counter_total = tk.Label(file_details_pending_delete_counter_frame, text='0', font=(None, 12), fg=root_window.uicolor.FADED)
    file_details_pending_delete_counter_total.pack(side='left', anchor='s', pady=(0, 5))

    file_details_pending_copy_header_line = tk.Frame(backup_file_details_frame)
    file_details_pending_copy_header_line.grid(row=0, column=1, sticky='e')
    file_details_pending_copy_header = tk.Label(file_details_pending_copy_header_line, text='Files to copy', font=(None, 11, 'bold'))
    file_details_pending_copy_header.pack(side='right')
    file_details_pending_copy_tooltip = tk.Label(file_details_pending_copy_header_line, text='(Click to copy)', fg=root_window.uicolor.FADED)
    file_details_pending_copy_tooltip.pack(side='right')
    file_details_pending_copy_counter_frame = tk.Frame(backup_file_details_frame)
    file_details_pending_copy_counter_frame.grid(row=1, column=1, sticky='e')
    file_details_pending_copy_counter = tk.Label(file_details_pending_copy_counter_frame, text='0', font=(None, 28))
    file_details_pending_copy_counter.pack(side='left', anchor='s')
    tk.Label(file_details_pending_copy_counter_frame, text='of', font=(None, 11), fg=root_window.uicolor.FADED).pack(side='left', anchor='s', pady=(0, 5))
    file_details_pending_copy_counter_total = tk.Label(file_details_pending_copy_counter_frame, text='0', font=(None, 12), fg=root_window.uicolor.FADED)
    file_details_pending_copy_counter_total.pack(side='left', anchor='s', pady=(0, 5))

    file_details_copied_header_line = tk.Frame(backup_file_details_frame)
    file_details_copied_header_line.grid(row=2, column=0, columnspan=2, sticky='ew')
    file_details_copied_header_line.grid_columnconfigure(1, weight=1)
    file_details_copied_header = tk.Label(file_details_copied_header_line, text='Successful', font=(None, 11, 'bold'))
    file_details_copied_header.grid(row=0, column=0)
    file_details_copied_tooltip = tk.Label(file_details_copied_header_line, text='(Click to copy)', fg=root_window.uicolor.FADED)
    file_details_copied_tooltip.grid(row=0, column=1, sticky='w')
    file_details_copied_counter = tk.Label(file_details_copied_header_line, text='0', font=(None, 11, 'bold'))
    file_details_copied_counter.grid(row=0, column=2)
    file_details_copied = ScrollableFrame(backup_file_details_frame)
    file_details_copied.grid(row=3, column=0, columnspan=2, pady=(0, WINDOW_ELEMENT_PADDING / 2), sticky='nsew')

    file_details_failed_header_line = tk.Frame(backup_file_details_frame)
    file_details_failed_header_line.grid(row=4, column=0, columnspan=2, sticky='ew')
    file_details_failed_header_line.grid_columnconfigure(1, weight=1)
    file_details_failed_header = tk.Label(file_details_failed_header_line, text='Failed', font=(None, 11, 'bold'))
    file_details_failed_header.grid(row=0, column=0)
    file_details_failed_tooltip = tk.Label(file_details_failed_header_line, text='(Click to copy)', fg=root_window.uicolor.FADED)
    file_details_failed_tooltip.grid(row=0, column=1, sticky='w')
    file_details_failed_counter = tk.Label(file_details_failed_header_line, text='0', font=(None, 11, 'bold'))
    file_details_failed_counter.grid(row=0, column=2)
    file_details_failed = ScrollableFrame(backup_file_details_frame)
    file_details_failed.grid(row=5, column=0, columnspan=2, sticky='nsew')

    # Set grid weights
    tk.Grid.rowconfigure(backup_file_details_frame, 3, weight=2)
    tk.Grid.rowconfigure(backup_file_details_frame, 5, weight=1)
    tk.Grid.columnconfigure(backup_file_details_frame, (0, 1), weight=1)

    # Set click to copy key bindings
    file_details_pending_delete_header.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_TOTAL_DELETE]])))
    file_details_pending_delete_tooltip.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_TOTAL_DELETE]])))
    file_details_pending_copy_header.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_TOTAL_COPY]])))
    file_details_pending_copy_tooltip.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_TOTAL_COPY]])))
    file_details_copied_header.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_SUCCESS]])))
    file_details_copied_tooltip.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_SUCCESS]])))
    file_details_copied_counter.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_SUCCESS]])))
    file_details_failed_header.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_FAIL]])))
    file_details_failed_tooltip.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_FAIL]])))
    file_details_failed_counter.bind('<Button-1>', lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_FAIL]])))

    # Add placeholder to backup analysis
    reset_analysis_output()
    backup_action_button_frame = tk.Frame(right_side_frame)
    backup_action_button_frame.pack(padx=WINDOW_ELEMENT_PADDING, pady=WINDOW_ELEMENT_PADDING / 2)
    start_analysis_btn = ttk.Button(backup_action_button_frame, text='Analyze', width=0, command=start_backup_analysis, state='normal')
    start_analysis_btn.pack(side='left', padx=4)
    start_backup_btn = ttk.Button(backup_action_button_frame, text='Run Backup', width=0, command=start_backup, state='disabled')
    start_backup_btn.pack(side='left', padx=4)
    halt_verification_btn = ttk.Button(backup_action_button_frame, text='Halt Verification', width=0, command=lambda: thread_manager.kill('Data Verification'), style='danger.TButton')

    branding_frame = tk.Frame(right_side_frame)
    branding_frame.pack(padx=WINDOW_ELEMENT_PADDING / 2)

    image_logo = ImageTk.PhotoImage(Image.open(resource_path(f"media/logo_ui{'_light' if root_window.dark_mode else ''}.png")))
    tk.Label(branding_frame, image=image_logo).pack(side='left')
    tk.Label(branding_frame, text=f"v{APP_VERSION}", font=(None, 10), fg=root_window.uicolor.FADED).pack(side='left', anchor='s', pady=(0, 12))

    # Keyboard listener
    listener = keyboard.Listener(
        on_press=on_press,
        on_release=on_release)
    listener.start()

    load_source_in_background()
    # QUESTION: Does init load_dest @thread_type need to be SINGLE, MULTIPLE, or REPLACEABLE?
    thread_manager.start(ThreadManager.SINGLE, is_progress_thread=True, target=load_dest, name='Init', daemon=True)

    # Check for updates on startup
    thread_manager.start(
        ThreadManager.SINGLE,
        target=update_handler.check,
        name='Update Check',
        daemon=True
    )

    ui_update_scheduler = RepeatedTimer(0.25, update_ui_during_backup)

    root_window.protocol('WM_DELETE_WINDOW', on_close)
    root_window.mainloop()
