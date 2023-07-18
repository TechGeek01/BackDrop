""" This module handles the UI, and starting the main program.

BackDrop is intended to be used as a data backup solution, to assist in
logically copying files from point A to point B. This is complete with
verification, and many other organization and integrity features.
"""

__version__ = '4.0.0-beta1'

import platform
import wx
from sys import exit
import shutil
import os
import subprocess
import webbrowser
import ctypes
from signal import signal, SIGINT
from datetime import datetime
import re
import pickle
import clipboard
from pynput import keyboard
if platform.system() == 'Windows':
    import pythoncom
    import win32api
    import win32file
    import wmi
import wx.lib.inspection
import logging

from bin.fileutils import FileUtils, human_filesize, get_directory_size, get_file_hash, do_delete
from bin.threadmanager import ThreadManager
from bin.config import Config
from bin.backup import Backup
from bin.repeatedtimer import RepeatedTimer
from bin.update import UpdateHandler
from bin.uielements import Color, RootWindow, ModalWindow, WarningPanel, ProgressBar, DetailBlock, BackupDetailBlock, resource_path
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


# FIXME: post_event() probably shouldn't hardcode the wx.Frame
def post_event(evt_type: wx.EventType, data: list = None, frame: wx.Frame = None):
    """Post a wx.PyEvent of a given type with optional data.

    Args:
        evt_type (wx.EventType): The event flag to use.
        data (tuple[]): Any data to append to the event (optional).
        frame (wx.Frame): The wxPython frame to bind the event to.
    """

    if frame is None:
        frame = main_frame

    event = wx.PyEvent()
    event.SetEventType(evt_type)

    if data is not None:
        if isinstance(data, list):
            event.data = data

    wx.PostEvent(frame, event)


def update_file_detail_lists(list_name: str, files: set):
    """Update the file lists for the detail file view.

    Args:
        list_name (String): The list name to update.
        filename (set): The file path to add to the list.
    """

    # Ignore empty filename sets
    if not files:
        return

    file_detail_list[list_name].extend([{
        'displayName': filename.split(os.path.sep)[-1],
        'filename': filename
    } for filename in files])

    if list_name == FileUtils.LIST_TOTAL_DELETE:
        file_details_pending_delete_counter.SetLabel(label=str(len(file_detail_list[FileUtils.LIST_TOTAL_DELETE])))
        file_details_pending_delete_counter.Layout()
        file_details_pending_delete_counter_total.SetLabel(label=str(len(file_detail_list[FileUtils.LIST_TOTAL_DELETE])))
        file_details_pending_delete_counter_total.Layout()
        file_details_pending_sizer.Layout()
    elif list_name == FileUtils.LIST_TOTAL_COPY:
        file_details_pending_copy_counter.SetLabel(label=str(len(file_detail_list[FileUtils.LIST_TOTAL_COPY])))
        file_details_pending_copy_counter.Layout()
        file_details_pending_copy_counter_total.SetLabel(label=str(len(file_detail_list[FileUtils.LIST_TOTAL_COPY])))
        file_details_pending_copy_counter_total.Layout()
        file_details_pending_sizer.Layout()
    elif list_name in [FileUtils.LIST_DELETE_SUCCESS, FileUtils.LIST_DELETE_FAIL, FileUtils.LIST_SUCCESS, FileUtils.LIST_FAIL]:
        # Remove file from pending list
        file_detail_list_name = FileUtils.LIST_TOTAL_COPY if list_name in [FileUtils.LIST_SUCCESS, FileUtils.LIST_FAIL] else FileUtils.LIST_TOTAL_DELETE
        file_detail_list[file_detail_list_name] = [file for file in file_detail_list[file_detail_list_name] if file['filename'] not in files]

        # Update file counter
        if list_name in [FileUtils.LIST_SUCCESS, FileUtils.LIST_FAIL]:
            file_details_pending_copy_counter.SetLabel(label=str(len(file_detail_list[file_detail_list_name])))
            file_details_pending_copy_counter.Layout()
        else:
            file_details_pending_delete_counter.SetLabel(label=str(len(file_detail_list[file_detail_list_name])))
            file_details_pending_delete_counter.Layout()
        file_details_pending_sizer.Layout()

        # Update copy list scrollable
        filenames = '\n'.join([filename.split(os.path.sep)[-1] for filename in files])
        if list_name in [FileUtils.LIST_SUCCESS, FileUtils.LIST_DELETE_SUCCESS]:
            new_file_label = wx.StaticText(file_details_success_panel, -1, label=filenames)
            if list_name == FileUtils.LIST_DELETE_SUCCESS:
                new_file_label.SetForegroundColour(Color.FADED)
            file_details_success_sizer.Add(new_file_label, 0)
            file_details_success_sizer.Layout()

            file_details_success_count.SetLabel(label=str(len(file_detail_list[FileUtils.LIST_SUCCESS]) + len(file_detail_list[FileUtils.LIST_DELETE_SUCCESS])))
            file_details_success_count.Layout()
            file_details_success_header_sizer.Layout()

            # Remove all but the most recent 250 items for performance reasons
            # FIXME: See if truncating the list like this is needed in wxPython
            # file_details_copied.show_items(250)
        else:
            new_file_label = wx.StaticText(file_details_failed_panel, -1, label=filenames)
            if list_name == FileUtils.LIST_DELETE_FAIL:
                new_file_label.SetForegroundColour(Color.FADED)
            file_details_failed_sizer.Add(new_file_label, 0)
            file_details_failed_sizer.Layout()

            file_details_failed_count.SetLabel(label=str(len(file_detail_list[FileUtils.LIST_FAIL]) + len(file_detail_list[FileUtils.LIST_DELETE_FAIL])))
            file_details_failed_count.Layout()
            file_details_failed_header_sizer.Layout()

            # Update counter in status bar
            FAILED_FILE_COUNT = len(file_detail_list[FileUtils.LIST_FAIL]) + len(file_detail_list[FileUtils.LIST_DELETE_FAIL])
            status_bar_error_count.SetLabel(label=f'{FAILED_FILE_COUNT} failed')
            status_bar_error_count.SetForegroundColour(Color.DANGER if FAILED_FILE_COUNT > 0 else Color.FADED)
            status_bar_error_count.Layout()
            status_bar_sizer.Layout()

            # HACK: The scroll yview won't see the label instantly after it's packed.
            # Sleeping for a brief time fixes that. This is acceptable as long as it's
            # not run in the main thread, else the UI will hang.
            # FIXME: See if truncating the list like this is needed in wxPython
            # file_details_failed.show_items()


backup_error_log = []


def display_backup_progress(copied: int, total: int, display_filename: str = None, operation: int = None, display_index: int = None):
    """Display the copy progress of a transfer

    Args:
        copied (int): the number of bytes copied.
        total (int): The total file size.
        display_filename (String): The filename to display inthe GUI (optional).
        operation (int): The mode to display the progress in (optional).
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
            progress_bar.SetValue(backup.progress['current'])
            cmd_info_blocks[display_index].SetLabel('progress', label=f"Deleted {display_filename}")
            cmd_info_blocks[display_index].SetForegroundColour('progress', Color.TEXT_DEFAULT)
        elif operation == Status.FILE_OPERATION_COPY:
            progress_bar.SetValue(backup.progress['current'])
            cmd_info_blocks[display_index].SetLabel('progress', label=f"{percent_copied:.2f}% \u27f6 {human_filesize(copied)} of {human_filesize(total)}")
            cmd_info_blocks[display_index].SetForegroundColour('progress', Color.TEXT_DEFAULT)
        elif operation == Status.FILE_OPERATION_VERIFY:
            progress_bar.SetValue(backup.progress['current'])
            cmd_info_blocks[display_index].SetLabel('progress', label=f"Verifying \u27f6 {percent_copied:.2f}% \u27f6 {human_filesize(copied)} of {human_filesize(total)}")
            cmd_info_blocks[display_index].SetForegroundColour('progress', Color.BLUE)

        cmd_info_blocks[display_index].Layout()
        summary_details_sizer.Layout()
        summary_details_box.Layout()


def get_backup_killflag() -> bool:
    """Get backup thread kill flag status.

    Returns:
        bool: The kill flag of the backup thread.
    """
    return thread_manager.threadlist['Backup']['killFlag']


def display_backup_summary_chunk(title: str, payload: list, reset: bool = None):
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
        summary_summary_sizer.Clear(True)
        summary_summary_sizer.Layout()

    heading_label = wx.StaticText(summary_summary_panel, -1, label=title, name='Backup summary chunk header label')
    heading_label.SetFont(FONT_HEADING)

    chunk_sizer = wx.GridBagSizer()

    for i, item in enumerate(payload):
        col1_label = wx.StaticText(summary_summary_panel, -1, label=item[0], name='Backup summary chunk name label')
        col2_label = wx.StaticText(summary_summary_panel, -1, label='\u27f6', name='Backup summary chunk arrow label')
        col3_label = wx.StaticText(summary_summary_panel, -1, label=item[1], name='Backup summary chunk summary label')

        if len(item) > 2 and not item[2]:
            col1_label.SetForegroundColour(Color.FADED)
            col2_label.SetForegroundColour(Color.FADED)
            col3_label.SetForegroundColour(Color.FADED)

        chunk_sizer.Add(col1_label, (i, 0))
        chunk_sizer.Add(col2_label, (i, 1))
        chunk_sizer.Add(col3_label, (i, 2))

    summary_summary_sizer.Add(heading_label, 0)
    summary_summary_sizer.Add(chunk_sizer, 0)
    summary_summary_sizer.Layout()


# QUESTION: Instead of the copy function handling display, can it just set variables, and have the timer handle all the UI stuff?
def update_backup_eta_timer(progress_info: dict):
    """Update the backup timer to show ETA.

    Args:
        progress_info (dict): The progress of the current backup
    """

    if backup.status == Status.BACKUP_ANALYSIS_RUNNING or backup.status == Status.BACKUP_ANALYSIS_FINISHED:
        backup_eta_label.SetLabel('Analysis in progress. Please wait...')
        backup_eta_label.SetForegroundColour(Color.TEXT_DEFAULT)
        backup_eta_label.Layout()
        summary_sizer.Layout()
    elif backup.status == Status.BACKUP_IDLE or backup.status == Status.BACKUP_ANALYSIS_ABORTED:
        backup_eta_label.SetLabel('Please start a backup to show ETA')
        backup_eta_label.SetForegroundColour(Color.TEXT_DEFAULT)
        backup_eta_label.Layout()
        summary_sizer.Layout()
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

        backup_eta_label.SetLabel(f'{str(running_time).split(".")[0]} elapsed \u27f6 {str(remaining_time).split(".")[0]} remaining')
        backup_eta_label.SetForegroundColour(Color.TEXT_DEFAULT)
        backup_eta_label.Layout()
        summary_sizer.Layout()
    elif backup.status == Status.BACKUP_BACKUP_ABORTED:
        backup_eta_label.SetLabel(f'Backup aborted in {str(datetime.now() - backup.get_backup_start_time()).split(".")[0]}')
        backup_eta_label.SetForegroundColour(Color.FAILED)
        backup_eta_label.Layout()
        summary_sizer.Layout()
    elif backup.status == Status.BACKUP_BACKUP_FINISHED:
        backup_eta_label.SetLabel(f'Backup completed successfully in {str(datetime.now() - backup.get_backup_start_time()).split(".")[0]}')
        backup_eta_label.SetForegroundColour(Color.FINISHED)
        backup_eta_label.Layout()
        summary_sizer.Layout()


def display_backup_command_info(display_command_list: list) -> list:
    """Enumerate the display widget with command info after a backup analysis.

    Args:
        display_command_list (list): The command list to pull data from.
    """

    global cmd_info_blocks

    summary_details_sizer.Clear(True)
    summary_details_sizer.Layout()

    cmd_info_blocks = []
    for i, item in enumerate(display_command_list):
        if item['type'] == Backup.COMMAND_TYPE_FILE_LIST:
            if item['mode'] == Status.FILE_OPERATION_DELETE:
                cmd_header_text = f"Delete {len(item['list'])} files from {item['dest']}"
            elif item['mode'] == Status.FILE_OPERATION_UPDATE:
                cmd_header_text = f"Update {len(item['list'])} files on {item['dest']}"
            elif item['mode'] == Status.FILE_OPERATION_COPY:
                cmd_header_text = f"Copy {len(item['list'])} new files to {item['dest']}"
            else:
                cmd_header_text = f"Work with {len(item['list'])} files on {item['dest']}"

        backup_summary_block = BackupDetailBlock(
            parent=summary_details_panel,
            title=cmd_header_text,
            text_font=FONT_DEFAULT,
            bold_font=FONT_BOLD
        )

        if item['type'] == Backup.COMMAND_TYPE_FILE_LIST:
            # Handle list trimming

            dc = wx.ScreenDC()

            dc.SetFont(FONT_BOLD)
            FILE_LIST_HEADER_WIDTH = dc.GetTextExtent('File list: ').GetWidth()

            dc.SetFont(FONT_DEFAULT)
            TOOLTIP_HEADER_WIDTH = dc.GetTextExtent('(Click to copy)').GetWidth()

            trimmed_file_list = ', '.join(item['list'])[:250]
            MAX_WIDTH = summary_details_panel.GetSize().GetWidth() - FILE_LIST_HEADER_WIDTH - TOOLTIP_HEADER_WIDTH - 2 * ITEM_UI_PADDING - 50  # Used to be 80%
            actual_file_width = dc.GetTextExtent(trimmed_file_list).GetWidth()

            if actual_file_width > MAX_WIDTH:
                while actual_file_width > MAX_WIDTH and len(trimmed_file_list) > 1:
                    trimmed_file_list = trimmed_file_list[:-1]
                    actual_file_width = dc.GetTextExtent(f'{trimmed_file_list}...').GetWidth()
                trimmed_file_list = f'{trimmed_file_list}...'

            backup_summary_block.add_line('file_size', 'Total size', human_filesize(item['size']))
            backup_summary_block.add_line('file_list', 'File list', trimmed_file_list, '\n'.join(item['list']))
            backup_summary_block.add_line('current_file', 'Current file', 'Pending' if item['enabled'] else 'Skipped', fg=Color.PENDING if item['enabled'] else Color.FADED)
            backup_summary_block.add_line('progress', 'Progress', 'Pending' if item['enabled'] else 'Skipped', fg=Color.PENDING if item['enabled'] else Color.FADED)

        summary_details_sizer.Add(backup_summary_block, 1, wx.EXPAND)
        summary_details_sizer.Layout()
        summary_details_box.Layout()
        cmd_info_blocks.append(backup_summary_block)


def backup_reset_ui():
    """Reset the UI when we run a backup analysis."""

    # Empty backup error log
    backup_error_log.clear()

    # Empty backup summary and detail panes
    summary_summary_sizer.Clear(True)
    summary_summary_sizer.Layout()
    summary_details_sizer.Clear(True)
    summary_details_sizer.Layout()

    # Clear file lists for file details pane
    for list_name in file_detail_list.keys():
        file_detail_list[list_name].clear()

    # Reset file details counters
    file_details_pending_delete_counter.SetLabel(label='0')
    file_details_pending_delete_counter.Layout()
    file_details_pending_delete_counter_total.SetLabel(label='0')
    file_details_pending_delete_counter_total.Layout()
    file_details_pending_copy_counter.SetLabel(label='0')
    file_details_pending_copy_counter.Layout()
    file_details_pending_copy_counter_total.SetLabel(label='0')
    file_details_pending_copy_counter_total.Layout()
    file_details_pending_sizer.Layout()
    file_details_success_count.SetLabel(label='0')
    file_details_success_count.Layout()
    file_details_success_header_sizer.Layout()
    file_details_failed_count.SetLabel(label='0')
    file_details_failed_count.Layout()
    file_details_failed_header_sizer.Layout()

    # Empty file details list panes
    file_details_success_sizer.Clear(True)
    file_details_success_sizer.Layout()
    file_details_failed_sizer.Clear(True)
    file_details_failed_sizer.Layout()


def request_kill_analysis():
    """Kill a running analysis."""

    if backup:
        status_bar_action.SetLabel(label='Stopping analysis')
        status_bar_action.Layout()
        status_bar_sizer.Layout()
        backup.kill(Backup.KILL_ANALYSIS)


def start_backup_analysis():
    """Start the backup analysis in a separate thread."""

    global backup

    # FIXME: If backup @analysis @thread is already running, it needs to be killed before it's rerun
    # CAVEAT: This requires some way to have the @analysis @thread itself check for the kill flag and break if it's set.
    if (backup and backup.is_running()) or verification_running or not source_avail_drive_list:
        return

    # TODO: Move status bar error log counter reset to reset UI function?
    backup_reset_ui()
    status_bar_error_count.SetLabel(label='0 failed')
    status_bar_error_count.SetForegroundColour(Color.FADED)
    status_bar_error_count.Layout()
    status_bar_sizer.Layout()
    update_ui_component(Status.UPDATEUI_STATUS_BAR_DETAILS, data='')

    backup = Backup(
        config=config,
        backup_config_dir=BACKUP_CONFIG_DIR,
        backup_config_file=BACKUP_CONFIG_FILE,
        analysis_pre_callback_fn=request_update_ui_pre_analysis,
        analysis_callback_fn=request_update_ui_post_analysis,
        backup_callback_fn=lambda cmd: post_event(evt_type=EVT_BACKUP_FINISHED, data=cmd)
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
    else:
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
    """Load the source destination and source lists, and display sources in the tree."""

    global LOADING_SOURCE
    global PREV_SOURCE_DRIVE
    global source_avail_drive_list
    global source_drive_default

    progress_bar.StartIndeterminate()

    LOADING_SOURCE = True

    # Empty tree in case this is being refreshed
    source_tree.DeleteAllItems()

    source_avail_drive_list = get_source_drive_list()

    if settings_source_mode in [Config.SOURCE_MODE_SINGLE_PATH, Config.SOURCE_MODE_MULTI_PATH] or source_avail_drive_list:
        # Display empty selection sizes
        source_selected_space.SetLabel('None')
        source_total_space.SetLabel('~None')
        source_selected_space.Layout()
        source_total_space.Layout()
        source_dest_selection_info_sizer.Layout()

        if source_warning_panel.IsShown():
            source_warning_panel.Hide()
            source_tree.Show()
            source_src_sizer.Layout()
            summary_sizer.Layout()
            root_sizer.Layout()

        source_src_control_dropdown.Clear()

        selected_source_mode = prefs.get('selection', 'source_mode', Config.SOURCE_MODE_SINGLE_DRIVE, verify_data=Config.SOURCE_MODE_OPTIONS)

        if selected_source_mode == Config.SOURCE_MODE_SINGLE_DRIVE:
            config['source_path'] = prefs.get('selection', 'source_drive', source_avail_drive_list[0], verify_data=source_avail_drive_list)

            source_drive_default = config['source_path']
            PREV_SOURCE_DRIVE = config['source_path']
            source_src_control_dropdown.Append(source_avail_drive_list)
            source_src_control_dropdown.SetSelection(source_src_control_dropdown.FindString(config['source_path']))

            # Enumerate list of paths in source
            if SYS_PLATFORM == PLATFORM_WINDOWS:
                config['source_path'] = config['source_path'] + os.path.sep

            for directory in next(os.walk(config['source_path']))[1]:
                source_tree.Append((directory, '', 'Unknown', 0))
        elif selected_source_mode == Config.SOURCE_MODE_MULTI_DRIVE:
            # Enumerate list of paths in source
            for drive in source_avail_drive_list:
                drive_name = prefs.get('source_names', drive, default='')
                source_tree.Append((drive, drive_name, 'Unknown', 0))
        elif selected_source_mode == Config.SOURCE_MODE_SINGLE_PATH:
            if config['source_path'] and os.path.isdir(config['source_path']):
                for directory in next(os.walk(config['source_path']))[1]:
                    # QUESTION: Should files be allowed in custom source?
                    source_tree.Append((directory, '', 'Unknown', 0))

        source_tree.Layout()
        source_src_sizer.Layout()
    elif settings_source_mode in [Config.SOURCE_MODE_SINGLE_DRIVE, Config.SOURCE_MODE_MULTI_DRIVE]:
        source_drive_default = 'No drives available'

        if not source_warning_panel.IsShown():
            source_tree.Hide()
            source_warning_panel.Show()
            source_src_sizer.Layout()
            summary_sizer.Layout()
            root_sizer.Layout()

    LOADING_SOURCE = False

    progress_bar.StopIndeterminate()


def load_source_in_background():
    """Start a source refresh in a new thread."""

    if (backup and backup.is_running()) or LOADING_SOURCE:
        return

    post_event(evt_type=EVT_REQUEST_LOAD_SOURCE)


def change_source_drive(e):
    """Change the source drive to pull sources from to a new selection."""

    global PREV_SOURCE_DRIVE
    global config

    selection = source_src_control_dropdown.GetValue()

    # If backup is running, ignore request to change
    if backup and backup.is_running():
        prev_source_index = source_src_control_dropdown.FindString(PREV_SOURCE_DRIVE)
        source_src_control_dropdown.SetSelection(prev_source_index)
        return

    # Invalidate analysis validation
    reset_analysis_output()

    config['source_path'] = selection
    PREV_SOURCE_DRIVE = selection
    prefs.set('selection', 'source_drive', selection)

    load_source_in_background()

    # If a drive type is selected for both source and destination, reload
    # destination so that the source drive doesn't show in destination list
    if ((settings_show_drives_source_local and settings_show_drives_destination_local)  # Local selected
            or (settings_show_drives_source_network and settings_show_drives_destination_network)):  # Network selected
        load_dest_in_background()


def reset_analysis_output():
    """Reset the summary panel for running an analysis."""

    summary_summary_sizer.Clear(True)
    summary_summary_sizer.Layout()
    summary_details_sizer.Clear(True)
    summary_details_sizer.Layout()

    summary_summary_sizer.Add(wx.StaticText(summary_summary_panel, -1, label="This area will summarize the backup that's been configured.", name='Backup summary placeholder tooltip 1'), 0)
    summary_summary_sizer.Add(wx.StaticText(summary_summary_panel, -1, label='Please start a backup analysis to generate a summary.', name='Backup summary placeholder tooltip 2'), 0, wx.TOP, 5)
    summary_summary_sizer.Layout()
    summary_summary_box.Layout()


def update_source_size(item: int):
    """Update source info for a given source.

    Args:
        item (String): The identifier for a source in the source tree to be calculated.
    """

    # FIXME: This crashes if you change the source, and the number of items in the tree changes while it's calculating things
    source_name = source_tree.GetItem(item, SOURCE_COL_PATH).GetText()

    if settings_source_mode in [Config.SOURCE_MODE_SINGLE_DRIVE, Config.SOURCE_MODE_SINGLE_PATH]:
        source_path = os.path.join(config['source_path'], source_name)
    elif settings_source_mode in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
        source_path = source_name

    source_dir_size = get_directory_size(source_path)
    source_tree.SetItem(item, SOURCE_COL_SIZE, label=human_filesize(source_dir_size))
    source_tree.SetItem(item, SOURCE_COL_RAWSIZE, label=str(source_dir_size))

    # After calculating source info, update the meta info
    selected_total = 0
    selected_source_list = []
    selected_item = source_tree.GetFirstSelected()
    while selected_item != -1:
        # Write selected sources to config
        source_info = {
            'size': int(source_tree.GetItem(selected_item, SOURCE_COL_RAWSIZE).GetText())
        }

        if settings_source_mode in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
            source_info['path'] = source_tree.GetItem(selected_item, SOURCE_COL_PATH).GetText()

            if SYS_PLATFORM == PLATFORM_WINDOWS:
                # Windows uses drive letters, so default name is letter
                default_name = source_info['path'][0]
            else:
                # Linux uses mount points, so get last dir name
                default_name = source_info['path'].split(os.path.sep)[-1]

            source_info['dest_name'] = source_tree.GetItem(selected_item, SOURCE_COL_NAME).GetText() if source_tree.GetItem(selected_item, SOURCE_COL_NAME).GetText() else default_name
        else:
            # If single drive mode, use source name as dest name
            source_info['dest_name'] = source_tree.GetItem(selected_item, SOURCE_COL_PATH).GetText()
            source_info['path'] = os.path.join(config['source_path'], source_info['dest_name'])

        selected_source_list.append(source_info)

        # Add total space of selection
        if source_tree.GetItem(selected_item, SOURCE_COL_SIZE).GetText() != 'Unknown':
            # Add total space of selection
            selected_total += int(source_tree.GetItem(selected_item, SOURCE_COL_RAWSIZE).GetText())

        selected_item = source_tree.GetNextSelected(selected_item)

    source_selected_space.SetLabel(human_filesize(selected_total))
    source_selected_space.SetForegroundColour(Color.TEXT_DEFAULT if selected_total > 0 else Color.FADED)
    source_src_selection_info_sizer.Layout()
    source_src_sizer.Layout()
    config['sources'] = selected_source_list

    source_total = sum([int(source_tree.GetItem(item, SOURCE_COL_RAWSIZE).GetText()) for item in range(source_tree.GetItemCount())])
    human_size_list = [source_tree.GetItem(item, SOURCE_COL_SIZE).GetText() for item in range(source_tree.GetItemCount())]

    # Recalculate and display the selected total
    source_total_space.SetLabel(f'{"~" if "Unknown" in human_size_list else ""}{human_filesize(source_total)}')
    source_total_space.SetForegroundColour(Color.TEXT_DEFAULT if source_total > 0 else Color.FADED)
    source_src_selection_info_sizer.Layout()
    source_src_sizer.Layout()

    # If everything's calculated, enable analysis button to be clicked
    selected_source_list = []
    selected_item = source_tree.GetFirstSelected()
    while selected_item != -1:
        selected_source_list.append(selected_item)
        selected_item = source_tree.GetNextSelected(selected_item)

    source_size_list = [source_tree.GetItem(item, SOURCE_COL_SIZE).GetText() for item in selected_source_list]
    if 'Unknown' not in source_size_list:
        start_analysis_btn.Enable()
        update_status_bar_selection()

    progress_bar.StopIndeterminate()


# IDEA: @Calculate total space of all @sources in background
def select_source():
    """Calculate and display the filesize of a selected source, if it hasn't been calculated.

    This gets the selection in the source tree, and then calculates the filesize for
    all sources selected that haven't yet been calculated. The summary of total
    selection, and total source space is also shown below the tree.
    """

    global prev_source_selection
    global source_selection_total
    global backup

    if not backup or not backup.is_running():
        progress_bar.StartIndeterminate()

        # If analysis was run, invalidate it
        reset_analysis_output()

        # Get selection delta to figure out what to calculate
        item = source_tree.GetFirstSelected()
        selected = []
        while item != -1:
            selected.append(item)
            item = source_tree.GetNextSelected(item)

        new_sources = []
        if selected:
            for item in selected:
                source_info = {
                    'size': int(source_tree.GetItem(item, SOURCE_COL_RAWSIZE).GetText())
                }

                if settings_source_mode in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
                    source_info['path'] = source_tree.GetItem(item, SOURCE_COL_PATH).GetText()

                    if SYS_PLATFORM == PLATFORM_WINDOWS:
                        # Windows uses drive letters, so default name is letter
                        default_name = source_info['path'][0]
                    else:
                        # Linux uses mount points, so get last dir name
                        default_name = source_info['path'].split(os.path.sep)[-1]

                    source_info['dest_name'] = source_tree.GetItem(item, SOURCE_COL_NAME).GetText() if source_tree.GetItem(item, SOURCE_COL_NAME).GetText() else default_name
                else:
                    # If single drive mode, use source name as dest name
                    source_info['dest_name'] = source_tree.GetItem(item, SOURCE_COL_PATH).GetText()
                    source_info['path'] = os.path.join(config['source_path'], source_info['dest_name'])

                new_sources.append(source_info)
        else:
            source_selected_space.SetLabel('None')
            source_selected_space.SetForegroundColour(Color.FADED)
            source_src_selection_info_sizer.Layout()
            source_src_sizer.Layout()

        config['sources'] = new_sources
        update_status_bar_selection()

        new_selected = [item for item in selected if item not in prev_source_selection]

        # Mark new selections as pending in UI
        for item in new_selected:
            source_tree.SetItem(item, SOURCE_COL_SIZE, label='Calculating')

        # Update selected meta info to known selection before calculating new selections
        selection_known_size_items = [item for item in range(source_tree.GetItemCount()) if source_tree.IsSelected(item) and item not in new_selected]
        selection_known_size = sum([int(source_tree.GetItem(item, SOURCE_COL_RAWSIZE).GetText()) for item in selection_known_size_items])
        source_selected_space.SetLabel(human_filesize(selection_known_size))
        source_selected_space.SetForegroundColour(Color.TEXT_DEFAULT if selection_known_size > 0 else Color.FADED)
        source_src_selection_info_sizer.Layout()
        source_src_sizer.Layout()

        # For each selected item, calculate size and add to total
        for item in new_selected:
            update_status_bar_selection(Status.BACKUPSELECT_CALCULATING_SOURCE)
            start_analysis_btn.Disable()

            post_event(evt_type=EVT_UPDATE_SOURCE_SIZE, data=item)

        # Set current selection to previous selection var to be referenced next call
        prev_source_selection = selected

        progress_bar.StopIndeterminate()

    else:
        # Temporarily unbind selection handlers so this function doesn't keep
        # running with every change
        source_tree.Unbind(wx.EVT_LIST_ITEM_SELECTED)
        source_tree.Unbind(wx.EVT_LIST_ITEM_DESELECTED)

        for item in range(source_tree.GetItemCount()):
            source_tree.Select(item, on=item in prev_source_selection)

        if prev_source_selection:
            source_tree.Focus(prev_source_selection[-1])

        # Re-enable the selection handlers that were temporarily disabled
        source_tree.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda e: post_event(evt_type=EVT_SELECT_SOURCE))
        source_tree.Bind(wx.EVT_LIST_ITEM_DESELECTED, lambda e: post_event(evt_type=EVT_SELECT_SOURCE))


def load_dest():
    """Load the destination path info, and display it in the tree."""

    global LOADING_DEST
    global dest_drive_master_list

    progress_bar.StartIndeterminate()

    LOADING_DEST = True

    # Empty tree in case this is being refreshed
    dest_tree.DeleteAllItems()

    if prefs.get('selection', 'dest_mode', default=Config.DEST_MODE_DRIVES, verify_data=Config.DEST_MODE_OPTIONS) == Config.DEST_MODE_DRIVES:
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
                if drive != config['source_path'] and drive != SYSTEM_DRIVE:
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
                            dest_tree.Append((
                                drive,
                                '',
                                human_filesize(drive_size),
                                'Yes' if drive_has_config_file else '',
                                vsn,
                                serial,
                                drive_size
                            ))

                            dest_drive_master_list.append({
                                'name': drive,
                                'vid': vsn,
                                'serial': serial,
                                'capacity': drive_size,
                                'hasConfig': drive_has_config_file
                            })
                        except (FileNotFoundError, OSError):
                            pass
        else:
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
            logical_drive_list = [mount for mount in logical_drive_list if mount and mount != config['source_path']]

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
                    dest_tree.Append((
                        drive,
                        '',
                        human_filesize(drive_size),
                        'Yes' if drive_has_config_file else '',
                        vsn,
                        serial,
                        drive_size
                    ))

                    dest_drive_master_list.append({
                        'name': drive,
                        'vid': vsn,
                        'serial': serial,
                        'capacity': drive_size,
                        'hasConfig': drive_has_config_file
                    })
    elif settings_dest_mode == Config.DEST_MODE_PATHS:
        total_drive_space_available = 0

    dest_total_space.SetLabel(human_filesize(total_drive_space_available))
    dest_total_space.Layout()
    source_dest_selection_info_sizer.Layout()

    LOADING_DEST = False

    progress_bar.StopIndeterminate()


def load_dest_in_background():
    """Start the loading of the destination path info in a new thread."""

    # TODO: Make load_dest and load_source replaceable, and in their own class
    # TODO: Invalidate load_source or load_dest if tree gets refreshed via some class def call
    if (backup and backup.is_running()) or LOADING_DEST:
        return

    post_event(evt_type=EVT_REQUEST_LOAD_DEST)


def gui_select_from_config():
    """From the current config, select the appropriate sources and drives in the GUI."""

    global dest_select_bind
    global prev_source_selection
    global prev_dest_selection

    # Get list of sources in config
    config_source_name_list = [item['dest_name'] for item in config['sources']]
    config_source_tree_id_list = [item for item in range(source_tree.GetItemCount()) if source_tree.GetItem(item, SOURCE_COL_PATH).GetText() in config_source_name_list]

    if config_source_tree_id_list:
        for item in range(source_tree.GetItemCount()):
            source_tree.Select(item, on=item in config_source_tree_id_list)

        if config_source_tree_id_list:
            source_tree.Focus(config_source_tree_id_list[-1])

        # Recalculate selected totals for display
        # QUESTION: Should source total be recalculated when selecting, or should it continue to use the existing total?
        known_path_sizes = [int(source_tree.GetItem(item, SOURCE_COL_RAWSIZE).GetText()) for item in config_source_tree_id_list if source_tree.GetItem(item, SOURCE_COL_RAWSIZE).GetText() != 'Unknown']
        source_selected_space.SetLabel(label=human_filesize(sum(known_path_sizes)))
        source_selected_space.Layout()
        source_src_selection_info_sizer.Layout()

    # Get list of drives where volume ID is in config
    connected_vid_list = [dest['vid'] for dest in config['destinations']]

    # If drives aren't mounted that should be, display the warning
    MISSING_DRIVE_COUNT = len(config['missing_drives'])
    if MISSING_DRIVE_COUNT > 0:
        config_missing_drive_vid_list = [vid for vid in config['missing_drives']]

        MISSING_VID_READABLE_LIST = ', '.join(config_missing_drive_vid_list[:-2] + [' and '.join(config_missing_drive_vid_list[-2:])])
        MISSING_VID_ALERT_MESSAGE = f"The drive{'s' if len(config_missing_drive_vid_list) > 1 else ''} with volume ID{'s' if len(config_missing_drive_vid_list) > 1 else ''} {MISSING_VID_READABLE_LIST} {'are' if len(config_missing_drive_vid_list) > 1 else 'is'} not available to be selected.\n\nMissing drives may be omitted or replaced, provided the total space on destination drives is equal to, or exceeds the amount of data to back up.\n\nUnless you reset the config or otherwise restart this tool, this is the last time you will be warned."
        MISSING_VID_ALERT_TITLE = f"Drive{'s' if len(config_missing_drive_vid_list) > 1 else ''} missing"

        dest_split_warning_prefix.SetLabel(label=f'There {"is" if MISSING_DRIVE_COUNT == 1 else "are"} ')
        MISSING_DRIVE_CONTRACTION = "isn't" if MISSING_DRIVE_COUNT == 1 else "aren't"
        dest_split_warning_suffix.SetLabel(label=f' {"drive" if MISSING_DRIVE_COUNT == 1 else "destinations"} in the config that {MISSING_DRIVE_CONTRACTION} connected. Please connect {"it" if MISSING_DRIVE_COUNT == 1 else "them"}, or enable split mode.')
        dest_split_warning_count.SetLabel(label=str(MISSING_DRIVE_COUNT))

        if not dest_split_warning_panel.IsShown():
            dest_split_warning_panel.Show()
            dest_split_warning_panel.sizer.Layout()
            dest_split_warning_panel.box.Layout()
            summary_sizer.Layout()

        wx.MessageBox(
            message=MISSING_VID_ALERT_MESSAGE,
            caption=MISSING_VID_ALERT_TITLE,
            style=wx.ICON_WARNING,
            parent=main_frame
        )
    else:
        if dest_split_warning_panel.IsShown():
            dest_split_warning_panel.Hide()
            summary_sizer.Layout()

    # Select any other config drives
    # QUESTION: Is there a better way to handle this @config loading @selection handler @conflict?
    if settings_dest_mode == Config.DEST_MODE_DRIVES:
        config_dest_tree_id_list = [item for item in range(dest_tree.GetItemCount()) if dest_tree.GetItem(item, DEST_COL_VID).GetText() in connected_vid_list]

        # Temporarily undind selection handler so this function doesn't keep
        # running with every change
        dest_tree.Unbind(wx.EVT_LIST_ITEM_SELECTED)

        for item in range(dest_tree.GetItemCount()):
            dest_tree.Select(item, on=item in config_dest_tree_id_list)

        prev_dest_selection = config_dest_tree_id_list

        if config_dest_tree_id_list:
            dest_tree.Focus(config_dest_tree_id_list[-1])

        # Re-enable the selection handler that was temporarily disabled
        dest_tree.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda e: post_event(evt_type=EVT_SELECT_DEST))


def get_source_path_from_name(source: str) -> str:
    """Get a source path from a source name.

    Args:
        source (String): The source to get.

    Returns:
        String: The path name for the source.
    """

    if prefs.get('selection', 'source_mode', default=Config.SOURCE_MODE_SINGLE_DRIVE, verify_data=Config.SOURCE_MODE_OPTIONS) in [Config.SOURCE_MODE_SINGLE_DRIVE, Config.SOURCE_MODE_SINGLE_PATH]:
        # Single source mode, so source is source path
        return os.path.join(config['source_path'], source)
    else:
        reference_list = {prefs.get('source_names', mountpoint, default=''): mountpoint for mountpoint in source_avail_drive_list if prefs.get('source_names', mountpoint, '')}
        return reference_list[source]


def load_config_from_file(filename: str):
    """Read a config file, and set the current config based off of it.

    Args:
        filename (String): The file to read from.
    """

    global config

    new_config = {}
    config_file = Config(filename)

    SELECTED_DEST_MODE = prefs.get('selection', 'dest_mode', default=Config.DEST_MODE_DRIVES, verify_data=Config.DEST_MODE_OPTIONS)

    # Get sources
    sources = config_file.get('selection', 'sources')
    if sources is not None and len(sources) > 0:
        new_config['sources'] = [{
            'path': [source_tree.GetItem(item, SOURCE_COL_PATH) for item in range(source_tree.GetItemCount())][0],
            'size': None,
            'dest_name': source
        } for source in sources.split(',')]

    if SELECTED_DEST_MODE == Config.DEST_MODE_DRIVES:
        # Get VID list
        vids = config_file.get('selection', 'vids').split(',')

        # Get path info
        config_dest_total = 0
        new_config['destinations'] = []
        new_config['missing_drives'] = {}
        drive_lookup_list = {drive['vid']: drive for drive in dest_drive_master_list}
        for drive in vids:
            if drive in drive_lookup_list.keys():
                # If drive connected, add to drive list
                new_config['destinations'].append(drive_lookup_list[drive])
                config_dest_total += drive_lookup_list[drive]['capacity']
            else:
                # Add drive capacity info to missing drive list
                reported_drive_capacity = config_file.get(drive, 'capacity', 0, data_type=Config.INTEGER)
                new_config['missing_drives'][drive] = reported_drive_capacity
                config_dest_total += reported_drive_capacity
    elif SELECTED_DEST_MODE == Config.DEST_MODE_PATHS:
        # Get path info
        config_dest_total = 0
        new_config['missing_drives'] = {}

    config.update(new_config)

    config_selected_space.SetLabel(label=human_filesize(config_dest_total))
    config_selected_space.SetForegroundColour(Color.TEXT_DEFAULT)
    source_dest_selection_info_sizer.Layout()
    source_dest_sizer.Layout()
    gui_select_from_config()


def select_dest():
    """Parse the current drive selection, read config data, and select other drives and sources if needed.

    If the selection involves a single drive that the user specifically clicked on,
    this function reads the config file on it if one exists, and will select any
    other drives and sources in the config.
    """

    global prev_selection
    global prev_dest_selection
    global dest_select_bind

    if backup and backup.is_running():
        # Temporarily undind selection handler so this function doesn't keep
        # running with every change
        dest_tree.Unbind(wx.EVT_LIST_ITEM_SELECTED)

        for item in range(dest_tree.GetItemCount()):
            dest_tree.Select(item, on=item in prev_dest_selection)

        if prev_dest_selection:
            dest_tree.Focus(prev_dest_selection[-1])

        # Re-enable the selection handler that was temporarily disabled
        dest_tree.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda e: post_event(evt_type=EVT_SELECT_DEST))

        return

    progress_bar.StartIndeterminate()

    # If analysis was run, invalidate it
    reset_analysis_output()

    dest_selection = []
    item = dest_tree.GetFirstSelected()
    while item != -1:
        dest_selection.append(item)
        item = dest_tree.GetNextSelected(item)

    # If selection is different than last time, invalidate the analysis
    selection_selected_last_time = [drive for drive in dest_selection if drive in prev_dest_selection]
    if len(dest_selection) != len(prev_dest_selection) or len(selection_selected_last_time) != len(prev_dest_selection):
        start_backup_btn.Disable()

    prev_dest_selection = dest_selection.copy()

    # Check if newly selected drive has a config file
    # We only want to do this if the click is the first selection (that is, there
    # are no other drives selected except the one we clicked).
    drives_read_from_config_file = False
    if len(dest_selection) > 0:
        selected_drive = dest_tree.GetItem(dest_selection[0], DEST_COL_PATH).GetText()
        SELECTED_PATH_CONFIG_FILE = os.path.join(selected_drive, BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE)
        if not keypresses['Alt'] and prev_selection <= len(dest_selection) and len(dest_selection) == 1 and os.path.isfile(SELECTED_PATH_CONFIG_FILE):
            # Found config file, so read it
            load_config_from_file(SELECTED_PATH_CONFIG_FILE)
            drives_read_from_config_file = True
        else:
            if dest_split_warning_panel.IsShown():
                dest_split_warning_panel.Hide()
                summary_sizer.Layout()
            prev_selection = len(dest_selection)

    selected_total = 0
    selected_drive_list = []

    if settings_dest_mode == Config.DEST_MODE_DRIVES:
        drive_lookup_list = {drive['vid']: drive for drive in dest_drive_master_list}
        for item in dest_selection:
            # Write drive IDs to config
            selected_drive = drive_lookup_list[dest_tree.GetItem(item, DEST_COL_VID).GetText()]
            selected_drive_list.append(selected_drive)
            selected_total += selected_drive['capacity']
    elif settings_dest_mode == Config.DEST_MODE_PATHS:
        for item in dest_selection:
            drive_path = dest_tree.GetItem(item, DEST_COL_PATH).GetText()

            drive_name = dest_tree.GetItem(item, DEST_COL_VID).GetText()
            drive_capacity = int(dest_tree.GetItem(item, DEST_COL_RAWSIZE).GetText())
            drive_has_config = True if dest_tree.GetItem(item, DEST_COL_CONFIG).GetText() == 'Yes' else False

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

    dest_selected_space.SetLabel(label=human_filesize(selected_total) if selected_total > 0 else 'None')
    dest_selected_space.SetForegroundColour(Color.TEXT_DEFAULT if selected_total > 0 else Color.FADED)
    if not drives_read_from_config_file:
        config['destinations'] = selected_drive_list
        config['missing_drives'] = {}
        config_selected_space.SetLabel(label='None')
        config_selected_space.SetForegroundColour(Color.FADED)
    source_dest_selection_info_sizer.Layout()
    source_dest_sizer.Layout()

    update_status_bar_selection()

    progress_bar.StopIndeterminate()


def start_backup():
    """Start the backup in a new thread."""

    if not backup or verification_running:
        return

    # If there are new drives, ask for confirmation before proceeding
    selected_new_drives = [drive['name'] for drive in config['destinations'] if drive['hasConfig'] is False]
    if len(selected_new_drives) > 0:
        drive_string = ', '.join(selected_new_drives[:-2] + [' and '.join(selected_new_drives[-2:])])

        new_drive_confirm_title = f"New drive{'s' if len(selected_new_drives) > 1 else ''} selected"
        new_drive_confirm_message = f"Drive{'s' if len(selected_new_drives) > 1 else ''} {drive_string} appear{'' if len(selected_new_drives) > 1 else 's'} to be new. Existing data will be deleted.\n\nAre you sure you want to continue?"

        with wx.MessageDialog(main_frame, message=new_drive_confirm_message,
                              caption=new_drive_confirm_title,
                              style=wx.CAPTION | wx.YES_NO | wx.ICON_WARNING) as confirm_dialog:
            # User changed their mind
            if confirm_dialog.ShowModal() == wx.ID_NO:
                return

    # Reset UI
    status_bar_error_count.SetLabel(label='0 failed')
    status_bar_error_count.SetForegroundColour(Color.FADED)
    status_bar_error_count.Layout()
    status_bar_sizer.Layout()
    update_ui_component(Status.UPDATEUI_STATUS_BAR_DETAILS, data='')

    # Reset file detail success and fail lists
    for list_name in [FileUtils.LIST_DELETE_SUCCESS, FileUtils.LIST_DELETE_FAIL, FileUtils.LIST_SUCCESS, FileUtils.LIST_FAIL]:
        file_detail_list[list_name].clear()

    # Reset file details counters
    FILE_DELETE_COUNT = len(file_detail_list[FileUtils.LIST_TOTAL_DELETE])
    FILE_COPY_COUNT = len(file_detail_list[FileUtils.LIST_TOTAL_COPY])
    file_details_pending_delete_counter.SetLabel(label=str(FILE_DELETE_COUNT))
    file_details_pending_delete_counter.Layout()
    file_details_pending_delete_counter_total.SetLabel(label=str(FILE_DELETE_COUNT))
    file_details_pending_delete_counter_total.Layout()
    file_details_pending_copy_counter.SetLabel(label=str(FILE_COPY_COUNT))
    file_details_pending_copy_counter.Layout()
    file_details_pending_copy_counter_total.SetLabel(label=str(FILE_COPY_COUNT))
    file_details_pending_copy_counter_total.Layout()
    file_details_pending_sizer.Layout()
    file_details_success_count.SetLabel(label='0')
    file_details_success_count.Layout()
    file_details_success_header_sizer.Layout()
    file_details_failed_count.SetLabel(label='0')
    file_details_failed_count.Layout()
    file_details_failed_header_sizer.Layout()

    # Empty file details list panes
    file_details_success_sizer.Clear(True)
    file_details_success_sizer.Layout()
    file_details_failed_sizer.Clear(True)
    file_details_failed_sizer.Layout()

    if not backup.analysis_valid or not backup.sanity_check():
        return

    update_ui_component(Status.UPDATEUI_BACKUP_START)
    update_ui_component(Status.UPDATEUI_STATUS_BAR_DETAILS, '')
    progress_bar.SetValue(0)
    progress_bar.SetRange(backup.progress['total'])

    for cmd in backup.command_list:
        cmd_info_blocks[cmd['displayIndex']].state.SetLabel(label='Pending')
        cmd_info_blocks[cmd['displayIndex']].state.SetForegroundColour(Color.PENDING)
        if cmd['type'] == Backup.COMMAND_TYPE_FILE_LIST:
            cmd_info_blocks[cmd['displayIndex']].SetLabel('current_file', label='Pending')
            cmd_info_blocks[cmd['displayIndex']].SetForegroundColour('current_file', Color.PENDING)
        cmd_info_blocks[cmd['displayIndex']].SetLabel('progress', label='Pending')
        cmd_info_blocks[cmd['displayIndex']].SetForegroundColour('progress', Color.PENDING)

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


# TODO: Move file verification to Backup class
def verify_data_integrity(path_list: list):
    """Verify itegrity of files on destination paths by checking hashes.

    Args:
        path_list (String[]): A list of mount points for paths to check.
    """

    global verification_running
    global verification_failed_list

    def recurse_for_hash(path: str, drive: str, hash_file_path: str):
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
                    update_ui_component(Status.UPDATEUI_STATUS_BAR_DETAILS, data=entry.path)

                    file_hash = get_file_hash(entry.path, lambda: thread_manager.threadlist['Data Verification']['killFlag'])

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
                            status_bar_error_count.SetLabel(label=f'{len(verification_failed_list)} failed')
                            status_bar_error_count.SetForegroundColour(Color.DANGER)
                            status_bar_error_count.Layout()
                            status_bar_sizer.Layout()

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
                elif entry.is_dir() and path_stub not in SPECIAL_IGNORE_LIST:
                    # If entry is path, recurse into it
                    recurse_for_hash(entry.path, drive, hash_file_path)

                if thread_manager.threadlist['Data Verification']['killFlag']:
                    break
        except Exception:
            pass

    if not backup or not backup.is_running():
        update_status_bar_action(Status.VERIFICATION_RUNNING)
        progress_bar.StartIndeterminate()
        status_bar_error_count.SetLabel(label='0 failed')
        status_bar_error_count.SetForegroundColour(Color.FADED)
        status_bar_error_count.Layout()
        status_bar_sizer.Layout()

        update_ui_component(Status.UPDATEUI_STATUS_BAR_DETAILS, data='')

        halt_verification_btn.pack(side='left', padx=4)

        # Empty file detail lists
        for list_name in [FileUtils.LIST_SUCCESS, FileUtils.LIST_FAIL]:
            file_detail_list[list_name].clear()

        # Reset file details counters
        file_details_pending_delete_counter.SetLabel(label='0')
        file_details_pending_delete_counter.Layout()
        file_details_pending_delete_counter_total.SetLabel(label='0')
        file_details_pending_delete_counter_total.Layout()
        file_details_pending_copy_counter.SetLabel(label='0')
        file_details_pending_copy_counter.Layout()
        file_details_pending_copy_counter_total.SetLabel(label='0')
        file_details_pending_copy_counter_total.Layout()
        file_details_pending_sizer.Layout()
        file_details_success_count.SetLabel(label='0')
        file_details_success_count.Layout()
        file_details_success_header_sizer.Layout()
        file_details_failed_count.SetLabel(label='0')
        file_details_failed_count.Layout()
        file_details_failed_header_sizer.Layout()

        # Empty file details list panes
        file_details_success_sizer.Clear(True)
        file_details_success_sizer.Layout()
        file_details_failed_sizer.Clear(True)
        file_details_failed_sizer.Layout()

        verification_running = True
        verification_failed_list = []

        # Get hash list for all drives
        bad_hash_files = []
        hash_list = {drive: {} for drive in path_list}
        for drive in path_list:
            drive_hash_file_path = os.path.join(drive, BACKUP_CONFIG_DIR, BACKUP_HASH_FILE)

            if os.path.isfile(drive_hash_file_path):
                write_trimmed_changes = False
                with open(drive_hash_file_path, 'rb') as f:
                    try:
                        drive_hash_list = pickle.load(f)
                        new_hash_list = {file_name: hash_val for file_name, hash_val in drive_hash_list.items() if file_name.split('/')[0] not in SPECIAL_IGNORE_LIST}
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
            for drive in path_list:
                drive_hash_file_path = os.path.join(drive, BACKUP_CONFIG_DIR, BACKUP_HASH_FILE)
                recurse_for_hash(drive, drive, drive_hash_file_path)
        else:
            for drive in path_list:
                drive_hash_file_path = os.path.join(drive, BACKUP_CONFIG_DIR, BACKUP_HASH_FILE)
                for file, saved_hash in hash_list[drive].items():
                    filename = os.path.join(drive, file)
                    update_ui_component(Status.UPDATEUI_STATUS_BAR_DETAILS, data=filename)
                    computed_hash = get_file_hash(filename)

                    if thread_manager.threadlist['Data Verification']['killFlag']:
                        break

                    # If file has hash mismatch, delete the corrupted file
                    if saved_hash != computed_hash:
                        do_delete(filename)

                        # Update UI counter
                        verification_failed_list.append(filename)
                        status_bar_error_count.SetLabel(label=f'{len(verification_failed_list)} failed')
                        status_bar_error_count.SetForegroundColour(Color.DANGER)
                        status_bar_error_count.Layout()
                        status_bar_sizer.Layout()

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

        progress_bar.StopIndeterminate()
        update_ui_component(Status.UPDATEUI_STATUS_BAR_DETAILS, data='')
        update_status_bar_action(Status.IDLE)


def show_update_window(update_info: dict):
    """Display information about updates.

    Args:
        update_info (dict): The update info returned by the UpdateHandler.
    """

    global update_frame
    global update_icon_sizer

    if not update_info['updateAvailable'] or update_frame.IsShown():
        return

    update_latest_version_text.SetLabel(label=f'v{update_info["latestVersion"]}')
    update_latest_version_text.Layout()
    update_version_text_sizer.Layout()

    icon_windows = wx.Bitmap(wx.Image(resource_path(f"assets/img/windows{'_light' if settings_dark_mode else ''}.png"), wx.BITMAP_TYPE_ANY))
    icon_windows_color = wx.Bitmap(wx.Image(resource_path('assets/img/windows_color.png'), wx.BITMAP_TYPE_ANY))
    icon_zip = wx.Bitmap(wx.Image(resource_path(f"assets/img/zip{'_light' if settings_dark_mode else ''}.png"), wx.BITMAP_TYPE_ANY))
    icon_zip_color = wx.Bitmap(wx.Image(resource_path('assets/img/zip_color.png'), wx.BITMAP_TYPE_ANY))
    icon_debian = wx.Bitmap(wx.Image(resource_path(f"assets/img/debian{'_light' if settings_dark_mode else ''}.png"), wx.BITMAP_TYPE_ANY))
    icon_debian_color = wx.Bitmap(wx.Image(resource_path('assets/img/debian_color.png'), wx.BITMAP_TYPE_ANY))
    icon_targz = wx.Bitmap(wx.Image(resource_path(f"assets/img/targz{'_light' if settings_dark_mode else ''}.png"), wx.BITMAP_TYPE_ANY))
    icon_targz_color = wx.Bitmap(wx.Image(resource_path('assets/img/targz_color.png'), wx.BITMAP_TYPE_ANY))

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

    if update_info and 'download' in update_info.keys():
        download_map = {url.split('/')[-1].lower(): url for url in update_info['download']}

        update_icon_sizer.Clear(True)
        update_icon_sizer.Layout()

        icon_count = 0
        for file_type, info in icon_info.items():
            if file_type in download_map.keys():
                icon_count += 1

                # If icon isn't first icon, add spacer
                if icon_count > 1:
                    update_icon_sizer.Add((12, -1), 0)

                download_btn = wx.StaticBitmap(update_frame.root_panel, -1, info['flat_icon'])
                update_icon_sizer.Add(download_btn, 0, wx.ALIGN_BOTTOM)
                download_btn.Bind(wx.EVT_ENTER_WINDOW, lambda e, icon=info['color_icon']: e.GetEventObject().SetBitmap(icon))
                download_btn.Bind(wx.EVT_LEAVE_WINDOW, lambda e, icon=info['flat_icon']: e.GetEventObject().SetBitmap(icon))
                download_btn.Bind(wx.EVT_LEFT_DOWN, lambda e, url=download_map[file_type]: webbrowser.open_new(url))

                # # Add supplemental icon if download is available
                if 'supplemental' in icon_info[file_type].keys() or info['supplemental']['name'] in download_map.keys():
                    download_btn = wx.StaticBitmap(update_frame.root_panel, -1, info['supplemental']['flat_icon'])
                    update_icon_sizer.Add(download_btn, 0, wx.ALIGN_BOTTOM | wx.LEFT, 4)
                    download_btn.Bind(wx.EVT_ENTER_WINDOW, lambda e, icon=info['supplemental']['color_icon']: e.GetEventObject().SetBitmap(icon))
                    download_btn.Bind(wx.EVT_LEAVE_WINDOW, lambda e, icon=info['supplemental']['flat_icon']: e.GetEventObject().SetBitmap(icon))
                    download_btn.Bind(wx.EVT_LEFT_DOWN, lambda e, url=download_map[info['supplemental']['name']]: webbrowser.open_new(url))

        update_icon_sizer.Layout()
        update_frame.ShowModal()


def check_for_updates(info: dict):
    """Process the update information provided by the UpdateHandler class.

    Args:
        info (dict): The Update info from the update handler.
    """

    global update_info

    update_info = info

    if info['updateAvailable']:
        post_event(evt_type=EVT_CHECK_FOR_UPDATES, data=info)


def check_for_updates_in_background():
    """Check for updates in the background."""
    thread_manager.start(
        ThreadManager.SINGLE,
        target=update_handler.check,
        name='Update Check',
        daemon=True
    )


if __name__ == '__main__':
    PLATFORM_WINDOWS = 'Windows'
    PLATFORM_LINUX = 'Linux'
    PLATFORM_MAC = 'Darwin'

    SYS_PLATFORM = platform.system()

    # Platform sanity check
    if SYS_PLATFORM not in [PLATFORM_WINDOWS, PLATFORM_LINUX, PLATFORM_MAC]:
        logging.error('This operating system is not supported')
        exit()

    # Set constants
    if SYS_PLATFORM == PLATFORM_WINDOWS:
        DRIVE_TYPE_REMOVABLE = win32file.DRIVE_REMOVABLE
        DRIVE_TYPE_FIXED = win32file.DRIVE_FIXED
        DRIVE_TYPE_LOCAL = DRIVE_TYPE_FIXED  # TODO: Make this a proper thing instead of reusing one local value
        DRIVE_TYPE_REMOTE = win32file.DRIVE_REMOTE
        DRIVE_TYPE_RAMDISK = win32file.DRIVE_RAMDISK

        SYSTEM_DRIVE = f'{os.getenv("SystemDrive")[0]}:'
        APPDATA_FOLDER = f'{os.getenv("LocalAppData")}/BackDrop'

        # Set params to allow ANSI escapes for color
        k = ctypes.windll.kernel32
        k.SetConsoleMode(k.GetStdHandle(-11), 7)
    else:
        DRIVE_TYPE_REMOVABLE = 2
        DRIVE_TYPE_FIXED = 3
        DRIVE_TYPE_LOCAL = DRIVE_TYPE_FIXED
        DRIVE_TYPE_REMOTE = 4
        DRIVE_TYPE_RAMDISK = 6

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

    # Set defaults
    prev_source_selection = []
    prev_selection = 0
    prev_dest_selection = []
    force_non_graceful_cleanup = False
    verification_running = False
    verification_failed_list = []
    update_window = None

    # Set app defaults
    BACKUP_CONFIG_DIR = '.backdrop'  # TODO: Should these backup constants be moved to the Backup class?
    BACKUP_CONFIG_FILE = 'backup.ini'
    BACKUP_HASH_FILE = 'hashes.pkl'
    PREFERENCES_CONFIG_FILE = 'preferences.ini'
    PORTABLE_PREFERENCES_CONFIG_FILE = 'backdrop.ini'
    WINDOW_ELEMENT_PADDING = 16

    # TODO: Move SPECIAL_IGNORE_LIST and verification to Backup class
    #     NOTE: This already exists in the Backup class, but the local reference
    #     is used by the data verification functions. Once those get moved to
    #     the Backup class, this can be removedq
    SPECIAL_IGNORE_LIST = [BACKUP_CONFIG_DIR, '$RECYCLE.BIN', 'System Volume Information']

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
        'source_path': last_selected_custom_source if prefs.get('selection', 'source_mode', default=Config.SOURCE_MODE_SINGLE_DRIVE, verify_data=Config.SOURCE_MODE_OPTIONS) == Config.SOURCE_MODE_SINGLE_PATH else None,
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

    # FIXME: Find a way to catch SIGINT in wxPython
    signal(SIGINT, cleanup_handler)

    thread_manager = ThreadManager()

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

        if [source for source in config['sources'] if source['size'] is None]:
            # Not all sources calculated
            status = Status.BACKUPSELECT_CALCULATING_SOURCE
        elif not config['sources'] and not config['destinations'] and len(config['missing_drives']) == 0:
            # No selection in config
            status = Status.BACKUPSELECT_NO_SELECTION
        elif not config['sources']:
            # No sources selected
            status = Status.BACKUPSELECT_MISSING_SOURCE
        elif not config['destinations'] and len(config['missing_drives']) == 0:
            # No drives selected
            status = Status.BACKUPSELECT_MISSING_DEST
        else:
            SOURCE_SELECTED_SPACE = sum((source['size'] for source in config['sources']))
            DESTINATION_SELECTED_SPACE = sum((destination['capacity'] for destination in config['destinations'])) + sum(config['missing_drives'].values())

            if SOURCE_SELECTED_SPACE < DESTINATION_SELECTED_SPACE:
                # Selected enough drive space
                status = Status.BACKUPSELECT_ANALYSIS_WAITING
            else:
                # Sources larger than drive space
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
            status_bar_selection.SetLabel(STATUS_TEXT_MAP[status])
            status_bar_selection.Layout()
            status_bar_sizer.Layout()

    def update_status_bar_action(status: int):
        """Update the status bar action status.

        Args:
            status (int): The status code to use.
        """

        if status == Status.IDLE:
            status_bar_action.SetLabel('Idle')
            status_bar_action.Layout()
            status_bar_sizer.Layout()
        elif status == Status.BACKUP_ANALYSIS_RUNNING:
            status_bar_action.SetLabel('Analysis running')
            status_bar_action.Layout()
            status_bar_sizer.Layout()
        elif status == Status.BACKUP_READY_FOR_BACKUP:
            backup_eta_label.SetLabel('Analysis finished, ready for backup')
            backup_eta_label.SetForegroundColour(Color.TEXT_DEFAULT)
            backup_eta_label.Layout()
            summary_sizer.Layout()
        elif status == Status.BACKUP_READY_FOR_ANALYSIS:
            backup_eta_label.SetLabel('Please start a backup to show ETA')
            backup_eta_label.SetForegroundColour(Color.TEXT_DEFAULT)
            backup_eta_label.Layout()
            summary_sizer.Layout()
        elif status == Status.BACKUP_BACKUP_RUNNING:
            status_bar_action.SetLabel('Backup running')
            status_bar_action.Layout()
            status_bar_sizer.Layout()
        elif status == Status.BACKUP_HALT_REQUESTED:
            status_bar_action.SetLabel('Stopping backup')
            status_bar_action.Layout()
            status_bar_sizer.Layout()
        elif status == Status.VERIFICATION_RUNNING:
            status_bar_action.SetLabel('Data verification running')
            status_bar_action.Layout()
            status_bar_sizer.Layout()

    def update_status_bar_update(status: int):
        """Update the status bar update message.

        Args:
            status (int): The status code to use.
        """

        STATUS_TEXT_MAP = {
            Status.UPDATE_CHECKING: ['Checking for updates', Color.TEXT_DEFAULT],
            Status.UPDATE_AVAILABLE: ['Update available!', Color.INFO],
            Status.UPDATE_UP_TO_DATE: ['Up to date', Color.TEXT_DEFAULT],
            Status.UPDATE_FAILED: ['Update failed', Color.FAILED]
        }

        # Set status
        if status in STATUS_TEXT_MAP.keys():
            status_bar_updates.SetLabel(STATUS_TEXT_MAP[status][0])
            status_bar_updates.SetForegroundColour(STATUS_TEXT_MAP[status][1])
            status_bar_updates.Layout()
            status_bar_sizer.Layout()

    def request_kill_backup():
        """Kill a running backup."""

        # FIXME: Timer shows aborted, but does not stop counting when aborting backup
        # FIXME: When aborting backup, file detail block shows "done" instead of "aborted"

        if backup:
            status_bar_action.SetLabel(label='Stopping backup')
            status_bar_action.Layout()
            status_bar_sizer.Layout()
            backup.kill(Backup.KILL_BACKUP)

    def update_ui_component(status: int, data=None):
        """Update UI elements with given data..

        Args:
            status (int): The status code to use.
            data (*): The data to update (optional).
        """

        if status == Status.UPDATEUI_ANALYSIS_START:
            update_status_bar_action(Status.BACKUP_ANALYSIS_RUNNING)
            start_analysis_btn.SetLabel(label='Halt Analysis')
            start_analysis_btn.Unbind(wx.EVT_LEFT_DOWN)
            start_analysis_btn.Bind(wx.EVT_LEFT_DOWN, lambda e: request_kill_analysis())
            start_analysis_btn.Layout()
            controls_sizer.Layout()
        elif status == Status.UPDATEUI_ANALYSIS_END:
            update_status_bar_action(Status.IDLE)
            start_analysis_btn.SetLabel(label='Analyze')
            start_analysis_btn.Unbind(wx.EVT_LEFT_DOWN)
            start_analysis_btn.Bind(wx.EVT_LEFT_DOWN, lambda e: start_backup_analysis())
            start_analysis_btn.Layout()
            controls_sizer.Layout()
        elif status == Status.UPDATEUI_BACKUP_START:
            update_status_bar_action(Status.BACKUP_BACKUP_RUNNING)
            start_analysis_btn.Disable()
            start_backup_btn.SetLabel(label='Halt Backup')
            start_backup_btn.Unbind(wx.EVT_LEFT_DOWN)
            start_backup_btn.Bind(wx.EVT_LEFT_DOWN, lambda e: request_kill_backup())
            start_backup_btn.Layout()
            controls_sizer.Layout()
        elif status == Status.UPDATEUI_BACKUP_END:
            update_status_bar_action(Status.IDLE)
            start_analysis_btn.Enable()
            start_backup_btn.SetLabel(label='Run Backup')
            start_backup_btn.Unbind(wx.EVT_LEFT_DOWN)
            start_backup_btn.Bind(wx.EVT_LEFT_DOWN, lambda e: start_backup())
            start_backup_btn.Layout()
            controls_sizer.Layout()
        elif status == Status.UPDATEUI_STATUS_BAR:
            update_status_bar_action(data)
        elif status == Status.UPDATEUI_STATUS_BAR_DETAILS:
            status_bar_details.SetLabel(label=data)
            status_bar_details.Layout()
            status_bar_sizer.Layout()

    def open_config_file():
        """Open a config file and load it."""

        with wx.FileDialog(main_frame, 'Select drive config', wildcard='Backup config files|backup.ini|All files (*.*)|*.*',
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as file_dialog:
            # User changed their mind
            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return

            filename = file_dialog.GetPath()
            if filename:
                load_config_from_file(filename)

    def save_config_file():
        """Save the config to selected drives."""

        if config['sources'] and config['destinations']:
            source_list = ','.join([item['dest_name'] for item in config['sources']])
            raw_vid_list = [drive['vid'] for drive in config['destinations']]
            raw_vid_list.extend(config['missing_drives'].keys())
            vid_list = ','.join(raw_vid_list)

            # For each destination that's connected, get destination info, and write file
            for dest in config['destinations']:
                # If config exists on drives, back it up first
                if os.path.isfile(os.path.join(dest['name'], BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE)):
                    shutil.move(os.path.join(dest['name'], BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE), os.path.join(dest['name'], BACKUP_CONFIG_DIR, f'{BACKUP_CONFIG_FILE}.old'))

                new_config_file = Config(os.path.join(dest['name'], BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE))

                # Write sources and paths/VIDs to config file
                new_config_file.set('selection', 'sources', source_list)
                new_config_file.set('selection', 'vids', vid_list)

                # Write info for each destination to its own section
                for current_drive in config['destinations']:
                    new_config_file.set(current_drive['vid'], 'vid', current_drive['vid'])
                    new_config_file.set(current_drive['vid'], 'serial', current_drive['serial'])
                    new_config_file.set(current_drive['vid'], 'capacity', current_drive['capacity'])

                # Write info for missing drives
                for dest_path, capacity in config['missing_drives'].items():
                    new_config_file.set(dest_path, 'vid', dest_path)
                    new_config_file.set(dest_path, 'serial', 'Unknown')
                    new_config_file.set(dest_path, 'capacity', capacity)

            # Since config files on destinations changed, refresh the destination list
            load_dest_in_background()

            wx.MessageBox(
                message='Backup config saved successfully',
                caption='Save Backup Config',
                style=wx.OK | wx.ICON_INFORMATION,
                parent=main_frame
            )

    def save_config_file_as():
        """Save the config file to a specified location."""

        with wx.FileDialog(main_frame, 'Save drive config', defaultFile='backup.ini',
                           wildcard='Backup config files|backup.ini|All files (*.*)|*.*',
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as file_dialog:
            # User changed their mind
            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return

            filename = file_dialog.GetPath()

            if config['sources'] and config['destinations']:
                source_list = ','.join([item['dest_name'] for item in config['sources']])
                raw_vid_list = [drive['vid'] for drive in config['destinations']]
                raw_vid_list.extend(config['missing_drives'].keys())
                vid_list = ','.join(raw_vid_list)

                # Get drive info, and write file
                new_config_file = Config(filename)

                # Write sources and VIDs to config file
                new_config_file.set('selection', 'sources', source_list)
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

                wx.MessageBox(
                    message='Backup config saved successfully',
                    caption='Save Backup Config',
                    style=wx.OK | wx.ICON_INFORMATION,
                    parent=main_frame
                )

    def delete_config_file_from_selected_drives():
        """Delete config files from drives in destination selection."""

        selection = []
        item = dest_tree.GetFirstSelected()
        while item != -1:
            selection.append(item)
            item = dest_tree.GetNextSelected(item)

        drive_list = [dest_tree.GetItem(item, DEST_COL_PATH).GetText().strip(os.path.sep) for item in selection]
        drive_list = [drive for drive in drive_list if os.path.isfile(os.path.join(drive, BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE))]

        if drive_list:
            # Ask for confirmation before deleting
            if wx.MessageBox(
                message='Are you sure you want to delete the config files from the selected drives?',
                caption='Delete config files?',
                style=wx.YES_NO,
                parent=main_frame
            ) == wx.YES:
                # Delete config file on each drive
                [os.remove(os.path.join(drive, BACKUP_CONFIG_DIR, BACKUP_CONFIG_FILE)) for drive in drive_list]

                # Since config files on drives changed, refresh the destination list
                load_dest_in_background()

    def show_backup_error_log():
        """Show the backup error log."""

        # TODO: Move this error log building to the UI update function.
        # This would let the UI update thread handle appending, and have this function
        # only deal with showing the window itself.
        backup_error_log_log_sizer.Clear(True)
        backup_error_log_log_sizer.Layout()

        for error in backup_error_log:
            error_summary_block = DetailBlock(
                parent=backup_error_log_log_panel,
                title=error['file'].split(os.path.sep)[-1],
                text_font=FONT_DEFAULT,
                bold_font=FONT_BOLD
            )

            error_summary_block.add_line('file_name', 'Filename', error['file'])
            error_summary_block.add_line('operation', 'Operation', error['mode'])
            error_summary_block.add_line('error', 'Error', error['error'])

            backup_error_log_log_sizer.Add(error_summary_block, 0)

        backup_error_log_frame.ShowModal()

    def browse_for_source():
        """Browse for a source path, and either make it the source, or add to the list."""

        global last_selected_custom_source

        with wx.DirDialog(main_frame, 'Select source folder', style=wx.DD_DEFAULT_STYLE) as dir_dialog:
            # User changed their mind
            if dir_dialog.ShowModal() == wx.ID_CANCEL:
                return

            dir_name = dir_dialog.GetPath()

            dir_name = os.path.sep.join(dir_name.split('/'))
            if not dir_name:
                return

            if settings_source_mode == Config.SOURCE_MODE_SINGLE_PATH:
                source_src_control_label.SetLabel(label=dir_name)
                source_src_control_label.Layout()
                source_src_control_sizer.Layout()
                config['source_path'] = dir_name

                # Log last selection to preferences
                last_selected_custom_source = dir_name
                prefs.set('selection', 'last_selected_custom_source', dir_name)

                load_source_in_background()
            elif settings_source_mode == Config.SOURCE_MODE_MULTI_PATH:
                # Get list of paths already in tree
                existing_path_list = [source_tree.GetItem(item, SOURCE_COL_PATH).GetText() for item in range(source_tree.GetItemCount())]

                # Only add item to list if it's not already there
                if dir_name not in existing_path_list:
                    # Log last selection to preferences
                    last_selected_custom_source = dir_name
                    prefs.set('selection', 'last_selected_custom_source', dir_name)

                    # Custom multi-source isn't stored in preferences, so default to
                    # dir name
                    path_name = dir_name.split(os.path.sep)[-1]

                    source_tree.Append((dir_name, path_name, 'Unknown', 0))

    def browse_for_dest():
        """Browse for a destination path, and add to the list."""

        with wx.DirDialog(main_frame, 'Select destination folder', style=wx.DD_DEFAULT_STYLE) as dir_dialog:
            # User changed their mind
            if dir_dialog.ShowModal() == wx.ID_CANCEL:
                return

            dir_name = dir_dialog.GetPath()

            dir_name = os.path.sep.join(dir_name.split('/'))
            if not dir_name:
                return

            if settings_dest_mode != Config.DEST_MODE_PATHS:
                return

            # Get list of paths already in tree
            existing_path_list = [dest_tree.GetItem(item, DEST_COL_PATH) for item in range(dest_tree.GetItemCount())]

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
                dest_tree.Append((
                    dir_name,
                    name_stub,
                    human_filesize(avail_space),
                    'Yes' if dir_has_config_file else '',
                    '',
                    '',
                    avail_space
                ))

    def rename_source_item(item):
        """Rename an item in the source tree for multi-source mode.

        Args:
            item: The TreeView item to rename.
        """

        current_name = source_tree.GetItem(item, SOURCE_COL_NAME).GetText()

        with wx.TextEntryDialog(None, message='Please enter a new name for the item',
                                caption='Rename source', value=current_name) as dialog:
            response = dialog.ShowModal()

            # User changed their mind
            if response == wx.ID_CANCEL:
                return

            new_name = dialog.GetValue().strip()
            new_name = re.search(r'[A-Za-z0-9_\- ]+', new_name)
            new_name = new_name.group(0) if new_name is not None else ''

            # Name shouldn't be changed if it's the same as current, or blank
            if new_name == current_name:
                return
            if new_name == '':
                return

        # Only set name in preferences if in drive mode
        if settings_source_mode == Config.SOURCE_MODE_MULTI_DRIVE:
            drive_name = source_tree.GetItem(item, SOURCE_COL_PATH).GetText()
            prefs.set('source_names', drive_name, new_name)

        source_tree.SetItem(item, SOURCE_COL_NAME, new_name)

    def rename_dest_item(item):
        """Rename an item in the dest tree for custom dest mode.

        Args:
            item: The TreeView item to rename.
        """

        current_name = dest_tree.GetItem(item, DEST_COL_NAME).GetText()

        with wx.TextEntryDialog(None, message='Please enter a new name for the item',
                                caption='Rename destination', value=current_name) as dialog:
            response = dialog.ShowModal()

            # User changed their mind
            if response == wx.ID_CANCEL:
                return

            new_name = dialog.GetValue().strip()
            new_name = re.search(r'[A-Za-z0-9_\- ]+', new_name)
            new_name = new_name.group(0) if new_name is not None else ''

            # Name shouldn't be changed if it's the same as current, or blank
            if new_name == current_name:
                return
            if new_name == '':
                return

        dest_tree.SetItem(item, DEST_COL_NAME, new_name)

    def show_source_right_click_menu(event):
        """Show the right click menu in the source tree for multi-source mode."""

        # Program needs to be in multi-source mode
        if settings_source_mode not in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
            return

        right_click_menu = wx.Menu()
        right_click_menu.Append(ID_SOURCE_RENAME, 'Rename', 'Rename the selected item')
        right_click_menu.Bind(wx.EVT_MENU, lambda e: rename_source_item(event.GetItem().GetId()), id=ID_SOURCE_RENAME)
        if settings_dest_mode == Config.SOURCE_MODE_MULTI_PATH:
            right_click_menu.Append(ID_SOURCE_DELETE, 'Delete', 'Delete the selected item')
            right_click_menu.Bind(wx.EVT_MENU, lambda e: source_tree.DeleteItem(event.GetItem().GetId()), id=ID_SOURCE_DELETE)

        main_frame.PopupMenu(right_click_menu, event.GetPoint())

    def show_dest_right_click_menu(event):
        """Show the right click menu in the dest tree for custom dest mode."""

        # Program needs to be in path destination mode
        if settings_dest_mode != Config.DEST_MODE_PATHS:
            return

        right_click_menu = wx.Menu()
        right_click_menu.Append(ID_DEST_RENAME, 'Rename', 'Rename the selected item')
        right_click_menu.Append(ID_DEST_DELETE, 'Delete', 'Delete the selected item')
        right_click_menu.Bind(wx.EVT_MENU, lambda e: rename_dest_item(event.GetItem().GetId()), id=ID_DEST_RENAME)
        right_click_menu.Bind(wx.EVT_MENU, lambda e: dest_tree.DeleteItem(event.GetItem().GetId()), id=ID_DEST_DELETE)

        main_frame.PopupMenu(right_click_menu, event.GetPoint())

    def change_source_mode(selection):
        """Change the mode for source selection.

        Args:
            selection: The selected source mode to change to.
        """

        global settings_source_mode

        # If backup is running, ignore request to change
        if backup and backup.is_running():
            selection_source_mode_menu_single_drive.Check(settings_source_mode == Config.SOURCE_MODE_SINGLE_DRIVE)
            selection_source_mode_menu_multi_drive.Check(settings_source_mode == Config.SOURCE_MODE_MULTI_DRIVE)
            selection_source_mode_menu_single_path.Check(settings_source_mode == Config.SOURCE_MODE_SINGLE_PATH)
            selection_source_mode_menu_multi_path.Check(settings_source_mode == Config.SOURCE_MODE_MULTI_PATH)
            return

        # If analysis is valid, invalidate it
        reset_analysis_output()

        prefs.set('selection', 'source_mode', selection)

        if selection == Config.SOURCE_MODE_SINGLE_DRIVE:
            source_src_control_label.SetLabel('Source: ')

            source_src_control_dropdown.Clear()
            if not source_src_control_dropdown.IsShown():
                source_src_control_dropdown.Show()

            if source_src_control_browse_btn.IsShown():
                source_src_control_browse_btn.Hide()
        elif selection == Config.SOURCE_MODE_MULTI_DRIVE:
            config['source_path'] = last_selected_custom_source

            source_src_control_label.SetLabel('Multi-drive mode, browse/selection disabled')

            if source_src_control_dropdown.IsShown():
                source_src_control_dropdown.Hide()

            if source_src_control_browse_btn.IsShown():
                source_src_control_browse_btn.Hide()
        elif selection == Config.SOURCE_MODE_SINGLE_PATH:
            source_src_control_label.SetLabel(last_selected_custom_source)

            if source_src_control_dropdown.IsShown():
                source_src_control_dropdown.Hide()

            if not source_src_control_browse_btn.IsShown():
                source_src_control_browse_btn.Show()
        elif selection == Config.SOURCE_MODE_MULTI_PATH:
            source_src_control_label.SetLabel('Custom multi-source mode')

            if source_src_control_dropdown.IsShown():
                source_src_control_dropdown.Hide()

            if not source_src_control_browse_btn.IsShown():
                source_src_control_browse_btn.Show()

        settings_source_mode = selection
        prefs.set('selection', 'source_mode', selection)
        config['source_mode'] == selection

        redraw_source_tree()

        load_source_in_background()

    def change_dest_mode(selection):
        """Change the mode for destination selection.

        Args:
            selection: The selected destination mode to change to.
        """

        global settings_dest_mode

        # If backup is running, ignore request to change
        if backup and backup.is_running():
            selection_dest_mode_menu_paths.Check(settings_dest_mode == Config.DEST_MODE_PATHS)
            selection_dest_mode_menu_drives.Check(settings_dest_mode == Config.DEST_MODE_DRIVES)
            return

        # If analysis is valid, invalidate it
        reset_analysis_output()

        settings_dest_mode = selection
        prefs.set('selection', 'dest_mode', selection)
        config['dest_mode'] = selection

        if selection == Config.DEST_MODE_DRIVES:
            if source_dest_control_browse_btn.IsShown():
                source_dest_control_browse_btn.Hide()
        elif selection == Config.DEST_MODE_PATHS:
            if not source_src_control_browse_btn.IsShown():
                source_dest_control_browse_btn.Show()

        redraw_dest_tree()

        if not LOADING_DEST:
            post_event(evt_type=EVT_REQUEST_LOAD_DEST)

    def change_source_type(toggle_type: int):
        """Change the drive types for source selection.

        Args:
            toggle_type (int): The drive type to toggle.
        """

        global settings_show_drives_source_network
        global settings_show_drives_source_local

        # If backup is running, ignore request to change
        if backup and backup.is_running():
            if toggle_type == DRIVE_TYPE_LOCAL:
                selection_menu_show_drives_source_local.Check(settings_show_drives_source_local)
            elif toggle_type == DRIVE_TYPE_REMOTE:
                selection_menu_show_drives_source_network.Check(settings_show_drives_source_network)
            return

        # If analysis is valid, invalidate it
        reset_analysis_output()

        selected_network = selection_menu_show_drives_source_network.IsChecked()
        selected_local = selection_menu_show_drives_source_local.IsChecked()

        # If both selections are unchecked, the last one has just been unchecked
        # In this case, re-check it, so that there's always some selection
        # TODO: This currently uses the fixed type to indicate local drives, but
        # will be used to select both fixed and removable drives. Should probably
        # find a proper solution for this...
        if not selected_local and not selected_network:
            if toggle_type == DRIVE_TYPE_LOCAL:
                selection_menu_show_drives_source_local.Check(True)
            elif toggle_type == DRIVE_TYPE_REMOTE:
                selection_menu_show_drives_source_network.Check(True)

        # Set preferences
        settings_show_drives_source_network = selection_menu_show_drives_source_network.IsChecked()
        settings_show_drives_source_local = selection_menu_show_drives_source_local.IsChecked()
        prefs.set('selection', 'source_network_drives', settings_show_drives_source_network)
        prefs.set('selection', 'source_local_drives', settings_show_drives_source_local)

        load_source_in_background()

    def change_destination_type(toggle_type: int):
        """Change the drive types for source selection.

        Args:
            toggle_type (int): The drive type to toggle.
        """

        global settings_show_drives_destination_network
        global settings_show_drives_destination_local

        # If backup is running, ignore request to change
        if backup and backup.is_running():
            if toggle_type == DRIVE_TYPE_LOCAL:
                selection_menu_show_drives_destination_local.Check(settings_show_drives_destination_local)
            elif toggle_type == DRIVE_TYPE_REMOTE:
                selection_menu_show_drives_destination_network.Check(settings_show_drives_destination_network)
            return

        # If analysis is valid, invalidate it
        reset_analysis_output()

        selected_local = selection_menu_show_drives_destination_local.IsChecked()
        selected_network = selection_menu_show_drives_destination_network.IsChecked()

        # If both selections are unchecked, the last one has just been unchecked
        # In this case, re-check it, so that there's always some selection
        # TODO: This currently uses the fixed type to indicate local drives, but
        # will be used to select both fixed and removable drives. Should probably
        # find a proper solution for this...
        if not selected_local and not selected_network:
            if toggle_type == DRIVE_TYPE_LOCAL:
                selection_menu_show_drives_destination_local.Check(True)
            elif toggle_type == DRIVE_TYPE_REMOTE:
                selection_menu_show_drives_destination_network.Check(True)

        # Set preferences
        settings_show_drives_destination_network = selection_menu_show_drives_destination_network.IsChecked()
        settings_show_drives_destination_local = selection_menu_show_drives_destination_local.IsChecked()
        prefs.set('selection', 'destination_network_drives', settings_show_drives_destination_network)
        prefs.set('selection', 'destination_local_drives', settings_show_drives_destination_local)

        load_dest_in_background()

    def start_verify_data_from_hash_list():
        """Start data verification in a new thread"""

        if backup and backup.is_running():  # Backup can't be running while data verification takes place
            return

        dest_list = [dest['name'] for dest in config['destinations']]

        post_event(evt_type=EVT_VERIFY_DATA_INTEGRITY, dest_list)

    def request_update_ui_pre_analysis():
        """Request to update the UI before analysis has been run."""

        post_event(evt_type=EVT_ANALYSIS_STARTING)

    def update_ui_pre_analysis():
        """Update the UI before an analysis is run."""

        update_ui_component(Status.UPDATEUI_STATUS_BAR, Status.BACKUP_ANALYSIS_RUNNING)
        start_backup_btn.Disable()
        update_ui_component(Status.UPDATEUI_ANALYSIS_START)

    def request_update_ui_post_analysis(files_payload: list, summary_payload: list):
        """Request to update the UI after an analysis has been run.

        Args:
            files_payload (list): The file data to display in the UI.
            summary_payload (list): The summary data to display in the UI.
        """

        event = wx.PyEvent()
        event.SetEventType(EVT_ANALYSIS_FINISHED)
        event.fp = files_payload
        event.sp = summary_payload

        wx.PostEvent(main_frame, event)

    def update_ui_post_analysis(files_payload: list, summary_payload: list):
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
            start_backup_btn.Enable()
        else:
            # If thread halted, mark analysis as invalid
            update_ui_component(Status.UPDATEUI_STATUS_BAR, Status.BACKUP_READY_FOR_ANALYSIS)
            reset_analysis_output()

        update_ui_component(Status.UPDATEUI_ANALYSIS_END)

    def request_update_ui_during_backup():
        """Request to update the user interface using a RepeatedTimer."""
        
        post_event(evt_type=EVT_BACKUP_TIMER)

    def update_ui_during_backup():
        """Update the user interface using the event sent via a RepeatedTimer."""

        if not backup:
            return

        backup_progress = backup.get_progress_updates()

        if backup.status == Status.BACKUP_ANALYSIS_RUNNING:
            progress_bar.StartIndeterminate()
        else:
            progress_bar.StopIndeterminate()

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

            if filename is None:
                filename = ''

            # Update file details info block
            if display_index is not None and display_index in cmd_info_blocks:
                dc = wx.ScreenDC()

                dc.SetFont(FONT_BOLD)
                CURRENT_FILE_HEADER_WIDTH = dc.GetTextExtent('Current file: ').GetWidth()

                dc.SetFont(FONT_DEFAULT)
                TOOLTIP_HEADER_WIDTH = dc.GetTextExtent('(Click to copy)').GetWidth()

                MAX_WIDTH = summary_details_panel.GetSize().GetWidth() - CURRENT_FILE_HEADER_WIDTH - TOOLTIP_HEADER_WIDTH - 2 * ITEM_UI_PADDING - 50  # Used to be 80%
                actual_file_width = dc.GetTextExtent(filename).GetWidth()

                if actual_file_width > MAX_WIDTH:
                    while actual_file_width > MAX_WIDTH and len(filename) > 1:
                        filename = filename[:-1]
                        actual_file_width = dc.GetTextExtent(f'{filename}...').GetWidth()
                    filename = f'{filename}...'

                cmd_info_blocks[display_index].SetLabel('current_file', label=filename)
                cmd_info_blocks[display_index].SetForegroundColour('current_file', Color.TEXT_DEFAULT)
        else:
            filename, display_index = (None, None)

        # Update backup status for each command info block
        if backup_progress['total']['command_display_index'] is not None:
            cmd_info_blocks[backup_progress['total']['command_display_index']].state.SetLabel(label='Running')
            cmd_info_blocks[backup_progress['total']['command_display_index']].state.SetForegroundColour(Color.RUNNING)
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
        if display_index is not None and buffer['display_index'] is not None:
            # FIXME: Progress bar jumps after completing backup, as though
            #     the progress or total changes when the backup completes
            progress_bar.SetValue(backup.progress['current'])
            progress_bar.SetRange(backup.progress['total'])

            cmd_info_blocks[display_index].SetLabel('current_file', label=buffer['display_filename'])
            cmd_info_blocks[display_index].SetForegroundColour('current_file', Color.TEXT_DEFAULT)
            if buffer['operation'] == Status.FILE_OPERATION_DELETE:
                cmd_info_blocks[display_index].SetLabel('progress', label=f"Deleted {buffer['display_filename']}")
                cmd_info_blocks[display_index].SetForegroundColour('progress', Color.TEXT_DEFAULT)
            elif buffer['operation'] == Status.FILE_OPERATION_COPY:
                cmd_info_blocks[display_index].SetLabel('progress', label=f"{percent_copied:.2f}% \u27f6 {human_filesize(buffer['copied'])} of {human_filesize(buffer['total'])}")
                cmd_info_blocks[display_index].SetForegroundColour('progress', Color.TEXT_DEFAULT)
            elif buffer['operation'] == Status.FILE_OPERATION_VERIFY:
                cmd_info_blocks[display_index].SetLabel('progress', label=f"Verifying \u27f6 {percent_copied:.2f}% \u27f6 {human_filesize(buffer['copied'])} of {human_filesize(buffer['total'])}")
                cmd_info_blocks[display_index].SetForegroundColour('progress', Color.BLUE)

        # Update file detail lists on deletes and copies
        delta_file_lists = {
            FileUtils.LIST_SUCCESS: set(),
            FileUtils.LIST_DELETE_SUCCESS: set(),
            FileUtils.LIST_FAIL: set(),
            FileUtils.LIST_DELETE_FAIL: set()
        }
        for file in sorted(backup_progress['delta']['files'], key=lambda x: x['timestamp']):
            filename, filesize, operation, display_index = file['file']

            if operation == Status.FILE_OPERATION_COPY:
                if file['success']:
                    delta_file_lists[FileUtils.LIST_SUCCESS].add(filename)
                else:
                    delta_file_lists[FileUtils.LIST_FAIL].add(filename)
            elif operation == Status.FILE_OPERATION_DELETE:
                display_backup_progress(
                    copied=filesize,
                    total=filesize,
                    display_filename=filename.split(os.path.sep)[-1],
                    operation=operation,
                    display_index=display_index
                )

                if not os.path.exists(filename):
                    delta_file_lists[FileUtils.LIST_DELETE_SUCCESS].add(filename)
                else:
                    delta_file_lists[FileUtils.LIST_DELETE_FAIL].add(filename)
                    backup_error_log.append({'file': filename, 'mode': Status.FILE_OPERATION_DELETE, 'error': 'File or path does not exist'})

        for (list_name, file_list) in delta_file_lists.items():
            update_file_detail_lists(list_name, file_list)

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
                cmd_info_blocks[display_index].state.SetLabel(label='Aborted')
                cmd_info_blocks[display_index].state.SetForegroundColour(Color.STOPPED)
                cmd_info_blocks[display_index].SetLabel('progress', label='Aborted')
                cmd_info_blocks[display_index].SetForegroundColour('progress', Color.STOPPED)
            else:
                cmd_info_blocks[display_index].state.SetLabel(label='Done')
                cmd_info_blocks[display_index].state.SetForegroundColour(Color.FINISHED)
                cmd_info_blocks[display_index].SetLabel('progress', label='Done')
                cmd_info_blocks[display_index].SetForegroundColour('progress', Color.FINISHED)

        # If backup stopped, 
        if backup.status != Status.BACKUP_BACKUP_RUNNING:
            update_ui_component(Status.UPDATEUI_BACKUP_END)

    # FIXME: can a function like this be generalized to set a setting and preferences?
    def change_verification_all_preferences(verify_all: bool = True):
        """Set verification preferences whether to verify all files or not.

        Args:
            verify_all (bool): Whether to verify all files (default: True).
        """

        global settings_verify_all_files

        settings_verify_all_files = verify_all
        prefs.set('verification', 'verify_all_files', verify_all)

    def change_dark_mode_preferences(dark_mode: bool = True):
        """Set dark mode preferences.

        Args:
            dark_mode (bool): Whether to enable dark mode (default: True).
        """

        global settings_dark_mode

        settings_dark_mode = dark_mode
        prefs.set('ui', 'dark_mode', dark_mode)

    def change_prerelease_preferences(allow_prereleases: bool = False):
        """Set verification preferences whether to verify all files or not.

        Args:
            allow_prereleases (bool): Whether to allow prereleases (default: False).
        """

        global settings_allow_prerelease_updates

        settings_allow_prerelease_updates = allow_prereleases
        prefs.set('ui', 'allow_prereleases', allow_prereleases)

        # Update handler doesn't check for this setting on its own, so update it
        update_handler.allow_prereleases = bool(allow_prereleases)

    def redraw_source_tree():
        """Redraw the source tree by reading preferences and setting columns and
        sizes.
        """

        if settings_source_mode in [Config.SOURCE_MODE_SINGLE_DRIVE, Config.SOURCE_MODE_SINGLE_PATH]:
            SOURCE_TREE_SIZE = (280, -1)
        elif settings_source_mode in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
            SOURCE_TREE_SIZE = (420, -1)

        source_tree.SetSize(SOURCE_TREE_SIZE)
        source_src_sizer.Layout()

        if settings_source_mode in [Config.SOURCE_MODE_SINGLE_DRIVE, Config.SOURCE_MODE_SINGLE_PATH]:
            source_tree.SetColumnWidth(SOURCE_COL_PATH, 200)
            source_tree.SetColumnWidth(SOURCE_COL_NAME, 0)
            source_tree.SetColumnWidth(SOURCE_COL_SIZE, 80)
        elif settings_source_mode in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
            source_tree.SetColumnWidth(SOURCE_COL_PATH, 170)
            source_tree.SetColumnWidth(SOURCE_COL_NAME, 170)
            source_tree.SetColumnWidth(SOURCE_COL_SIZE, 80)

    def redraw_dest_tree():
        """Redraw the destination tree by reading preferences and setting columns
        and sizes.
        """

        DEST_TREE_COLWIDTH_DRIVE = 50 if SYS_PLATFORM == PLATFORM_WINDOWS else 150
        DEST_TREE_COLWIDTH_VID = 140 if settings_dest_mode == Config.DEST_MODE_PATHS else 90
        DEST_TREE_COLWIDTH_SERIAL = 150 if SYS_PLATFORM == PLATFORM_WINDOWS else 50

        if settings_dest_mode == Config.DEST_MODE_DRIVES:
            DEST_TREE_WIDTH = DEST_TREE_COLWIDTH_DRIVE + 80 + 50 + DEST_TREE_COLWIDTH_VID + DEST_TREE_COLWIDTH_SERIAL
        elif settings_dest_mode == Config.DEST_MODE_PATHS:
            DEST_TREE_WIDTH = DEST_TREE_COLWIDTH_DRIVE + DEST_TREE_COLWIDTH_SERIAL - 50 + DEST_TREE_COLWIDTH_VID + 80 + 50

        dest_tree.SetSize(DEST_TREE_WIDTH, -1)
        source_dest_sizer.Layout()

        if settings_dest_mode == Config.DEST_MODE_DRIVES:
            dest_tree.SetColumnWidth(DEST_COL_PATH, DEST_TREE_COLWIDTH_DRIVE)
            dest_tree.SetColumnWidth(DEST_COL_NAME, 0)
            dest_tree.SetColumnWidth(DEST_COL_SIZE, 80)
            dest_tree.SetColumnWidth(DEST_COL_CONFIG, 50)
            dest_tree.SetColumnWidth(DEST_COL_VID, DEST_TREE_COLWIDTH_VID)
            dest_tree.SetColumnWidth(DEST_COL_SERIAL, DEST_TREE_COLWIDTH_SERIAL)
        elif settings_dest_mode == Config.DEST_MODE_PATHS:
            dest_tree.SetColumnWidth(DEST_COL_PATH, DEST_TREE_COLWIDTH_DRIVE + DEST_TREE_COLWIDTH_SERIAL - 50)
            dest_tree.SetColumnWidth(DEST_COL_NAME, DEST_TREE_COLWIDTH_VID)
            dest_tree.SetColumnWidth(DEST_COL_SIZE, 80)
            dest_tree.SetColumnWidth(DEST_COL_CONFIG, 50)
            dest_tree.SetColumnWidth(DEST_COL_VID, 0)
            dest_tree.SetColumnWidth(DEST_COL_SERIAL, 0)

    def show_widget_inspector():
        """Show the widget inspection tool."""
        wx.lib.inspection.InspectionTool().Show()

    def on_close():
        if thread_manager.is_alive('Backup'):
            # User changed their mind
            if wx.MessageBox(
                message="There's still a background process running. Are you sure you want to kill it?",
                caption='Quit?',
                style=wx.OK | wx.CANCEL,
                parent=main_frame
            ) == wx.CANCEL:
                return

            # Backup needs to be killed before the program can exit
            if backup:
                backup.kill()

        # RepeatedTimer needs to be killed before the window can be destroyed
        ui_update_scheduler.stop()

        exit()

    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s - %(message)s')

    file_detail_list = {
        FileUtils.LIST_TOTAL_DELETE: [],
        FileUtils.LIST_TOTAL_COPY: [],
        FileUtils.LIST_DELETE_SUCCESS: [],
        FileUtils.LIST_DELETE_FAIL: [],
        FileUtils.LIST_SUCCESS: [],
        FileUtils.LIST_FAIL: []
    }

    # Load settings from preferences
    settings_show_drives_source_network = prefs.get('selection', 'source_network_drives', default=False, data_type=Config.BOOLEAN)
    settings_show_drives_source_local = prefs.get('selection', 'source_local_drives', default=True, data_type=Config.BOOLEAN)
    settings_show_drives_destination_network = prefs.get('selection', 'destination_network_drives', default=False, data_type=Config.BOOLEAN)
    settings_show_drives_destination_local = prefs.get('selection', 'destination_local_drives', default=True, data_type=Config.BOOLEAN)
    settings_source_mode = prefs.get('selection', 'source_mode', default=Config.SOURCE_MODE_SINGLE_DRIVE)
    settings_dest_mode = prefs.get('selection', 'dest_mode', default=Config.DEST_MODE_DRIVES)
    settings_verify_all_files = prefs.get('verification', 'verify_all_files', default=True, data_type=Config.BOOLEAN)
    settings_dark_mode = prefs.get('ui', 'dark_mode', default=True, data_type=Config.BOOLEAN)
    settings_allow_prerelease_updates = prefs.get('ui', 'allow_prereleases', default=False, data_type=Config.BOOLEAN)

    update_handler = UpdateHandler(
        current_version=__version__,
        allow_prereleases=config['allow_prereleases'],
        status_change_fn=update_status_bar_update,
        update_callback=check_for_updates
    )

    if settings_dark_mode:
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

    WINDOW_BASE_WIDTH = 1300  # QUESTION: Can BASE_WIDTH and MIN_WIDTH be rolled into one now that MIN is separate from actual width?
    WINDOW_MULTI_SOURCE_EXTRA_WIDTH = 170
    WINDOW_MIN_HEIGHT = 700
    MULTI_SOURCE_TEXT_COL_WIDTH = 120 if SYS_PLATFORM == PLATFORM_WINDOWS else 200
    MULTI_SOURCE_NAME_COL_WIDTH = 220 if SYS_PLATFORM == PLATFORM_WINDOWS else 140
    SINGLE_SOURCE_TEXT_COL_WIDTH = 170
    SINGLE_SOURCE_NAME_COL_WIDTH = 170
    ITEM_UI_PADDING = 10

    WINDOW_MIN_WIDTH = WINDOW_BASE_WIDTH
    if prefs.get('selection', 'source_mode', Config.SOURCE_MODE_SINGLE_DRIVE, verify_data=Config.SOURCE_MODE_OPTIONS) in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH]:
        WINDOW_MIN_WIDTH += WINDOW_MULTI_SOURCE_EXTRA_WIDTH

    LOADING_SOURCE = False
    LOADING_DEST = False

    app = wx.App()

    wx.Font.AddPrivateFont(resource_path('assets/fonts/Roboto-Regular.ttf'))
    wx.Font.AddPrivateFont(resource_path('assets/fonts/Roboto-Bold.ttf'))

    FONT_DEFAULT = wx.Font(9, family=wx.FONTFAMILY_DEFAULT, style=0,
                           weight=wx.FONTWEIGHT_NORMAL, underline=False,
                           faceName='Roboto', encoding=wx.FONTENCODING_DEFAULT)
    FONT_BOLD = wx.Font(9, family=wx.FONTFAMILY_DEFAULT, style=0,
                        weight=wx.FONTWEIGHT_BOLD, underline=False,
                        faceName='Roboto', encoding=wx.FONTENCODING_DEFAULT)
    FONT_MEDIUM = wx.Font(11, family=wx.FONTFAMILY_DEFAULT, style=0,
                          weight=wx.FONTWEIGHT_NORMAL, underline=False,
                          faceName='Roboto', encoding=wx.FONTENCODING_DEFAULT)
    FONT_LARGE = wx.Font(16, family=wx.FONTFAMILY_DEFAULT, style=0,
                         weight=wx.FONTWEIGHT_NORMAL, underline=False,
                         faceName='Roboto', encoding=wx.FONTENCODING_DEFAULT)
    FONT_HEADING = wx.Font(11, family=wx.FONTFAMILY_DEFAULT, style=0,
                           weight=wx.FONTWEIGHT_BOLD, underline=False,
                           faceName='Roboto', encoding=wx.FONTENCODING_DEFAULT)
    FONT_GIANT = wx.Font(28, family=wx.FONTFAMILY_DEFAULT, style=0,
                         weight=wx.FONTWEIGHT_NORMAL, underline=False,
                         faceName='Roboto', encoding=wx.FONTENCODING_DEFAULT)
    FONT_UPDATE_AVAILABLE = wx.Font(32, family=wx.FONTFAMILY_DEFAULT, style=0,
                                    weight=wx.FONTWEIGHT_BOLD, underline=False,
                                    faceName='Roboto', encoding=wx.FONTENCODING_DEFAULT)

    main_frame = RootWindow(
        parent=None,
        title='BackDrop - Data Backup Tool',
        size=wx.Size(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT),
        name='Main window frame',
        icon=wx.Icon(resource_path('assets/icon.ico'))
    )
    main_frame.SetFont(FONT_DEFAULT)
    app.SetTopWindow(main_frame)

    backup_error_log_frame = ModalWindow(
        parent=main_frame,
        title='Backup Error Log',
        size=wx.Size(650, 450),
        name='Backup error log frame'
    )
    backup_error_log_frame.SetFont(FONT_DEFAULT)

    backup_error_log_frame.Panel(
        name='Backup error log root panel',
        background=Color.BACKGROUND,
        foreground=Color.TEXT_DEFAULT
    )
    backup_error_log_sizer = wx.BoxSizer(wx.VERTICAL)

    backup_error_log_header = wx.StaticText(backup_error_log_frame.root_panel, -1, label='Backup Error Log', name='Backup error log heading')
    backup_error_log_header.SetFont(FONT_HEADING)
    backup_error_log_sizer.Add(backup_error_log_header, 0, wx.ALIGN_CENTER_HORIZONTAL)

    backup_error_log_log_panel = wx.ScrolledWindow(backup_error_log_frame.root_panel, -1, style=wx.VSCROLL, name='Backup error log panel')
    backup_error_log_log_panel.SetScrollbars(20, 20, 50, 50)
    backup_error_log_log_panel.SetForegroundColour(Color.TEXT_DEFAULT)
    backup_error_log_log_sizer = wx.BoxSizer(wx.VERTICAL)
    backup_error_log_log_panel.SetSizer(backup_error_log_log_sizer)
    backup_error_log_sizer.Add(backup_error_log_log_panel, 1, wx.EXPAND | wx.TOP, ITEM_UI_PADDING)

    backup_error_log_box = wx.BoxSizer()
    backup_error_log_box.Add(backup_error_log_sizer, 1, wx.EXPAND | wx.ALL, ITEM_UI_PADDING)
    backup_error_log_frame.root_panel.SetSizerAndFit(backup_error_log_box)

    update_frame = ModalWindow(
        parent=main_frame,
        title='Update Available',
        size=wx.Size(600, 370),  # Should be 600x300, compensating for title bar with 320
        name='Update frame'
    )
    update_frame.SetFont(FONT_DEFAULT)

    update_frame.Panel(
        name='Update root panel',
        background=Color.BACKGROUND,
        foreground=Color.TEXT_DEFAULT
    )
    update_sizer = wx.BoxSizer(wx.VERTICAL)

    update_header = wx.StaticText(update_frame.root_panel, -1, label='Update Available!', name='Update available heading')
    update_header.SetFont(FONT_UPDATE_AVAILABLE)
    update_header.SetForegroundColour(Color.INFO)
    update_sizer.Add(update_header, 0, wx.ALIGN_CENTER_HORIZONTAL)
    update_description = wx.StaticText(update_frame.root_panel, -1, label='An update to BackDrop is available. Please update to get the latest features and fixes.', name='Update description text')
    update_sizer.Add(update_description, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP | wx.BOTTOM, 20)

    update_version_sizer = wx.BoxSizer()
    update_version_header_sizer = wx.BoxSizer(wx.VERTICAL)
    update_version_current_header = wx.StaticText(update_frame.root_panel, -1, label='Current: ', name='Update current version header')
    update_version_current_header.SetFont(FONT_LARGE)
    update_version_header_sizer.Add(update_version_current_header, 0, wx.ALIGN_RIGHT)
    update_version_latest_header = wx.StaticText(update_frame.root_panel, -1, label='Latest: ', name='Update latest version header')
    update_version_latest_header.SetFont(FONT_LARGE)
    update_version_header_sizer.Add(update_version_latest_header, 0, wx.ALIGN_RIGHT | wx.TOP, 5)
    update_version_sizer.Add(update_version_header_sizer, 0)
    update_version_text_sizer = wx.BoxSizer(wx.VERTICAL)
    update_current_version_text = wx.StaticText(update_frame.root_panel, -1, label=f'v{__version__}', name='Update current version text')
    update_current_version_text.SetFont(FONT_LARGE)
    update_current_version_text.SetForegroundColour(Color.FADED)
    update_version_text_sizer.Add(update_current_version_text, 0)
    update_latest_version_text = wx.StaticText(update_frame.root_panel, -1, label='Unknown', name='Update latest version text')
    update_latest_version_text.SetFont(FONT_LARGE)
    update_latest_version_text.SetForegroundColour(Color.FADED)
    update_version_text_sizer.Add(update_latest_version_text, 0, wx.TOP, 5)
    update_version_sizer.Add(update_version_text_sizer, 0)
    update_sizer.Add(update_version_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL)

    update_icon_sizer = wx.BoxSizer()
    update_sizer.Add(update_icon_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP | wx.BOTTOM, 20)

    update_download_source_sizer = wx.BoxSizer()
    update_download_source_sizer.Add(wx.StaticText(update_frame.root_panel, -1, label='Or, check out the source on ', name='Update frame GitHub description'), 0)
    github_link = wx.StaticText(update_frame.root_panel, -1, label='GitHub', name='Update frame GitHub link')
    github_link.SetForegroundColour(Color.INFO)
    github_link.Bind(wx.EVT_LEFT_DOWN, lambda e: webbrowser.open_new('https://www.github.com/TechGeek01/BackDrop'))
    update_download_source_sizer.Add(github_link, 0)
    update_sizer.Add(update_download_source_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL)

    update_box = wx.BoxSizer()
    update_box.Add(update_sizer, 1, wx.EXPAND | wx.ALL, ITEM_UI_PADDING)
    update_frame.root_panel.SetSizerAndFit(update_box)

    # Root panel stuff
    main_frame.Panel(
        name='Main window root panel',
        background=Color.BACKGROUND,
        foreground=Color.TEXT_DEFAULT
    )
    root_sizer = wx.GridBagSizer(vgap=ITEM_UI_PADDING, hgap=ITEM_UI_PADDING)

    # Source controls
    source_src_control_sizer = wx.BoxSizer()
    source_src_control_label = wx.StaticText(main_frame.root_panel, -1, label='Source: ', name='Source control label')
    source_src_control_sizer.Add(source_src_control_label, 0, wx.ALIGN_CENTER_VERTICAL)
    source_src_control_dropdown = wx.ComboBox(main_frame.root_panel, -1, style=wx.CB_READONLY, name='Source control ComboBox')
    source_src_control_sizer.Add(source_src_control_dropdown, 0, wx.ALIGN_CENTER_VERTICAL)
    source_src_control_sizer.Add((-1, -1), 1, wx.EXPAND)
    source_src_control_browse_btn = wx.Button(main_frame.root_panel, -1, label='Browse', name='Browse source button')
    source_src_control_sizer.Add(source_src_control_browse_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, ITEM_UI_PADDING)
    source_src_control_spacer_button = wx.Button(main_frame.root_panel, -1, label='', size=(0, -1), name='Spacer dummy button')
    source_src_control_spacer_button.Disable()
    source_src_control_sizer.Add(source_src_control_spacer_button, 0, wx.ALIGN_CENTER_VERTICAL)

    SOURCE_COL_PATH = 0
    SOURCE_COL_NAME = 1
    SOURCE_COL_SIZE = 2
    SOURCE_COL_RAWSIZE = 3

    # FIXME: Remove size in source tree constructor when SetSize works
    source_tree = wx.ListCtrl(main_frame.root_panel, -1, size=(420, 170), style=wx.LC_REPORT, name='Source tree')

    source_tree.AppendColumn('Path')
    source_tree.AppendColumn('Name')
    source_tree.AppendColumn('Size')
    source_tree.AppendColumn('Raw Size')
    source_tree.SetColumnWidth(SOURCE_COL_RAWSIZE, 0)

    source_tree.SetBackgroundColour(Color.WIDGET_COLOR)
    source_tree.SetTextColour(Color.WHITE)

    source_warning_panel = WarningPanel(main_frame.root_panel, size=(420, 170))
    source_warning_panel.SetFont(FONT_MEDIUM)
    source_warning_panel.SetBackgroundColour(Color.WARNING)
    source_warning_panel.SetForegroundColour(Color.BLACK)
    source_warning_panel.sizer.Add(wx.StaticText(source_warning_panel, -1, label='No source drives are available'), 0, wx.ALIGN_CENTER)

    source_src_selection_info_sizer = wx.BoxSizer()
    source_src_selection_info_sizer.Add(wx.StaticText(main_frame.root_panel, -1, label='Selected:', name='Source meta selected label'), 0, wx.ALIGN_CENTER_VERTICAL)
    source_selected_space = wx.StaticText(main_frame.root_panel, -1, label='None', name='Source meta selected value')
    source_selected_space.SetForegroundColour(Color.FADED)
    source_src_selection_info_sizer.Add(source_selected_space, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
    source_src_selection_info_sizer.Add((20, -1), 1, wx.EXPAND)
    source_src_selection_info_sizer.Add(wx.StaticText(main_frame.root_panel, -1, label='Total:', name='Source meta total label'), 0, wx.ALIGN_CENTER_VERTICAL)
    source_total_space = wx.StaticText(main_frame.root_panel, -1, label='~None', name='Source meta total value')
    source_total_space.SetForegroundColour(Color.FADED)
    source_src_selection_info_sizer.Add(source_total_space, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
    spacer_button = wx.Button(main_frame.root_panel, -1, label='', size=(0, -1), name='Spacer dummy button')
    spacer_button.Disable()
    source_src_selection_info_sizer.Add(spacer_button, 0, wx.ALIGN_CENTER_VERTICAL)

    source_src_sizer = wx.BoxSizer(wx.VERTICAL)
    source_src_sizer.Add(source_src_control_sizer, 0, wx.EXPAND)
    source_src_sizer.Add(source_tree, 0, wx.EXPAND | wx.TOP, ITEM_UI_PADDING)
    source_src_sizer.Add(source_warning_panel, 0, wx.EXPAND | wx.TOP, ITEM_UI_PADDING)
    source_warning_panel.Hide()
    source_src_sizer.Add(source_src_selection_info_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, ITEM_UI_PADDING)

    # Destination controls
    source_dest_control_sizer = wx.BoxSizer()
    source_dest_control_sizer.Add((-1, -1), 1, wx.EXPAND)
    source_dest_tooltip = wx.StaticText(main_frame.root_panel, -1, label='Hold ALT when selecting a drive to ignore config files', name='Destination select tooltip')
    source_dest_tooltip.SetForegroundColour(Color.INFO)
    source_dest_control_sizer.Add(source_dest_tooltip, 0, wx.ALIGN_CENTER_VERTICAL)
    source_dest_control_sizer.Add((-1, -1), 1, wx.EXPAND)
    source_dest_control_browse_btn = wx.Button(main_frame.root_panel, -1, label='Browse', name='Browse destination')
    source_dest_control_sizer.Add(source_dest_control_browse_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, ITEM_UI_PADDING)
    source_dest_control_spacer_button = wx.Button(main_frame.root_panel, -1, label='', size=(0, -1), name='Spacer dummy button')
    source_dest_control_spacer_button.Disable()
    source_dest_control_sizer.Add(source_dest_control_spacer_button, 0, wx.ALIGN_CENTER_VERTICAL)

    DEST_COL_PATH = 0
    DEST_COL_NAME = 1
    DEST_COL_SIZE = 2
    DEST_COL_CONFIG = 3
    DEST_COL_VID = 4
    DEST_COL_SERIAL = 5
    DEST_COL_RAWSIZE = 6

    # FIXME: Remove size in dest tree constructor when SetSize works
    dest_tree = wx.ListCtrl(main_frame.root_panel, -1, size=(420, 170), style=wx.LC_REPORT, name='Destination tree')

    dest_tree.AppendColumn('Path')
    dest_tree.AppendColumn('Name')
    dest_tree.AppendColumn('Size')
    dest_tree.AppendColumn('Config')
    dest_tree.AppendColumn('Volume ID')
    dest_tree.AppendColumn('Serial')
    dest_tree.AppendColumn('Raw Size')
    dest_tree.SetColumnWidth(DEST_COL_RAWSIZE, 0)

    dest_tree.SetBackgroundColour(Color.WIDGET_COLOR)
    dest_tree.SetTextColour(Color.WHITE)

    def update_split_mode_label():
        """ Update the split mode indicator. """
        if config['splitMode']:
            split_mode_status.SetLabel('Split mode enabled')
            split_mode_status.SetForegroundColour(Color.GREEN)
        else:
            split_mode_status.SetLabel('Split mode disabled')
            split_mode_status.SetForegroundColour(Color.FADED)

    def toggle_split_mode():
        """Handle toggling of split mode based on checkbox value."""

        if (not backup or not backup.is_running()) and not verification_running:
            config['splitMode'] = not config['splitMode']
            update_split_mode_label()

    source_dest_selection_info_sizer = wx.BoxSizer()
    source_dest_selection_info_sizer.Add((-1, -1), 1, wx.EXPAND)
    source_dest_selection_info_sizer.Add(wx.StaticText(main_frame.root_panel, -1, label='Config:', name='Destination meta config label'), 0, wx.ALIGN_CENTER_VERTICAL)
    config_selected_space = wx.StaticText(main_frame.root_panel, -1, label='None', name='Destination meta config value')
    config_selected_space.SetForegroundColour(Color.FADED)
    source_dest_selection_info_sizer.Add(config_selected_space, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
    source_dest_selection_info_sizer.Add((20, -1), 0)
    source_dest_selection_info_sizer.Add(wx.StaticText(main_frame.root_panel, -1, label='Selected:', name='Destination meta selected label'), 0, wx.ALIGN_CENTER_VERTICAL)
    dest_selected_space = wx.StaticText(main_frame.root_panel, -1, label='None', name='Destination meta selected value')
    dest_selected_space.SetForegroundColour(Color.FADED)
    source_dest_selection_info_sizer.Add(dest_selected_space, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
    source_dest_selection_info_sizer.Add((20, -1), 0)
    source_dest_selection_info_sizer.Add(wx.StaticText(main_frame.root_panel, -1, label='Avail:', name='Destination meta available label'), 0, wx.ALIGN_CENTER_VERTICAL)
    dest_total_space = wx.StaticText(main_frame.root_panel, -1, label=human_filesize(0), name='Destination meta available value')
    dest_total_space.SetForegroundColour(Color.FADED)
    source_dest_selection_info_sizer.Add(dest_total_space, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
    source_dest_selection_info_sizer.Add((-1, -1), 1, wx.EXPAND)
    split_mode_status = wx.StaticText(main_frame.root_panel, -1, label='', name='Split mode toggle status')
    update_split_mode_label()
    source_dest_selection_info_sizer.Add(split_mode_status, 0, wx.ALIGN_CENTER_VERTICAL)
    spacer_button = wx.Button(main_frame.root_panel, -1, label='', size=(0, -1), name='Spacer dummy button')
    spacer_button.Disable()
    source_dest_selection_info_sizer.Add(spacer_button, 0, wx.ALIGN_CENTER_VERTICAL)

    source_dest_sizer = wx.BoxSizer(wx.VERTICAL)
    source_dest_sizer.Add(source_dest_control_sizer, 0, wx.EXPAND)
    source_dest_sizer.Add(dest_tree, 0, wx.EXPAND | wx.TOP, ITEM_UI_PADDING)
    source_dest_sizer.Add(source_dest_selection_info_sizer, 0, wx.EXPAND | wx.TOP, ITEM_UI_PADDING)

    redraw_dest_tree()

    # Source and dest panel
    source_sizer = wx.BoxSizer()
    source_sizer.Add(source_src_sizer, 0, wx.EXPAND)
    source_sizer.Add(source_dest_sizer, 0, wx.EXPAND | wx.LEFT, ITEM_UI_PADDING)

    # Backup summary panel
    dest_split_warning_panel = WarningPanel(main_frame.root_panel)
    dest_split_warning_panel.SetFont(FONT_MEDIUM)
    dest_split_warning_panel.SetBackgroundColour(Color.WARNING)
    dest_split_warning_panel.SetForegroundColour(Color.BLACK)
    dest_split_warning_prefix = wx.StaticText(dest_split_warning_panel, -1, label='There are ')
    dest_split_warning_count = wx.StaticText(dest_split_warning_panel, -1, label='0')
    dest_split_warning_count.SetFont(FONT_LARGE)
    dest_split_warning_suffix = wx.StaticText(dest_split_warning_panel, -1, label=" drives in the config that aren't connected. Please connect them, or enable split mode.")
    dest_split_warning_line_sizer = wx.BoxSizer()
    dest_split_warning_line_sizer.Add(dest_split_warning_prefix, 0, wx.ALIGN_CENTER)
    dest_split_warning_line_sizer.Add(dest_split_warning_count, 0, wx.ALIGN_CENTER)
    dest_split_warning_line_sizer.Add(dest_split_warning_suffix, 0, wx.ALIGN_CENTER)
    dest_split_warning_panel.sizer.Add(dest_split_warning_line_sizer, 0, wx.ALIGN_CENTER)

    backup_eta_label = wx.StaticText(main_frame.root_panel, -1, label='Please start a backup to show ETA', name='Backup ETA label')

    summary_notebook = wx.Notebook(main_frame.root_panel, -1, name='Backup summary notebook')
    summary_summary_panel = wx.ScrolledWindow(summary_notebook, -1, style=wx.VSCROLL, name='Backup summary panel')
    summary_summary_panel.SetScrollbars(20, 20, 50, 50)
    summary_summary_panel.SetBackgroundColour(Color.WIDGET_COLOR)
    summary_summary_panel.SetForegroundColour(Color.TEXT_DEFAULT)
    summary_summary_sizer = wx.BoxSizer(wx.VERTICAL)
    summary_summary_box = wx.BoxSizer()
    summary_summary_box.Add(summary_summary_sizer, 1, wx.EXPAND | wx.ALL, ITEM_UI_PADDING)
    summary_summary_panel.SetSizer(summary_summary_box)
    summary_details_panel = wx.ScrolledWindow(summary_notebook, -1, style=wx.VSCROLL, name='Backup detail panel')
    summary_details_panel.SetScrollbars(20, 20, 50, 50)
    summary_details_panel.SetBackgroundColour(Color.WIDGET_COLOR)
    summary_details_panel.SetForegroundColour(Color.TEXT_DEFAULT)
    summary_details_sizer = wx.BoxSizer(wx.VERTICAL)
    summary_details_box = wx.BoxSizer()
    summary_details_box.Add(summary_details_sizer, 1, wx.EXPAND | wx.ALL, ITEM_UI_PADDING)
    summary_details_panel.SetSizer(summary_details_box)
    summary_notebook.AddPage(summary_summary_panel, 'Backup Summary')
    summary_notebook.AddPage(summary_details_panel, 'Backup Details')
    summary_sizer = wx.BoxSizer(wx.VERTICAL)
    summary_sizer.Add(dest_split_warning_panel, 0, wx.ALIGN_CENTER_HORIZONTAL)
    dest_split_warning_panel.Hide()
    summary_sizer.Add(backup_eta_label, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, ITEM_UI_PADDING)
    summary_sizer.Add(summary_notebook, 1, wx.EXPAND | wx.TOP, ITEM_UI_PADDING)

    reset_analysis_output()

    # FIle list panel
    file_details_pending_header_sizer = wx.BoxSizer()
    file_details_delete_text = wx.StaticText(main_frame.root_panel, -1, label='Files to delete', name='Files to delete header label')
    file_details_delete_text.SetFont(FONT_HEADING)
    file_details_pending_header_sizer.Add(file_details_delete_text, 0, wx.ALIGN_BOTTOM | wx.BOTTOM, -1)
    file_details_delete_copy_text = wx.StaticText(main_frame.root_panel, -1, label='(Click to copy)', name='Files to delete header clipboard label')
    file_details_delete_copy_text.SetForegroundColour(Color.FADED)
    file_details_pending_header_sizer.Add(file_details_delete_copy_text, 0, wx.ALIGN_BOTTOM | wx.LEFT, 5)
    file_details_pending_header_sizer.Add((-1, -1), 1, wx.EXPAND)
    file_details_copy_copy_text = wx.StaticText(main_frame.root_panel, -1, label='(Click to copy)', name='Files to copy header clipboard label')
    file_details_copy_copy_text.SetForegroundColour(Color.FADED)
    file_details_pending_header_sizer.Add(file_details_copy_copy_text, 0, wx.ALIGN_BOTTOM | wx.RIGHT, 5)
    file_details_copy_text = wx.StaticText(main_frame.root_panel, -1, label='Files to copy', name='Files to copy header label')
    file_details_copy_text.SetFont(FONT_HEADING)
    file_details_pending_header_sizer.Add(file_details_copy_text, 0, wx.ALIGN_BOTTOM | wx.BOTTOM, -1)

    file_details_pending_sizer = wx.BoxSizer()
    file_details_pending_delete_counter = wx.StaticText(main_frame.root_panel, -1, label='0', name='Pending delete counter')
    file_details_pending_delete_counter.SetFont(FONT_GIANT)
    file_details_pending_sizer.Add(file_details_pending_delete_counter, 0, wx.ALIGN_BOTTOM | wx.BOTTOM, -5)
    file_details_pending_delete_of = wx.StaticText(main_frame.root_panel, -1, label='of', name='Pending delete "of"')
    file_details_pending_delete_of.SetFont(FONT_MEDIUM)
    file_details_pending_delete_of.SetForegroundColour(Color.FADED)
    file_details_pending_sizer.Add(file_details_pending_delete_of, 0, wx.ALIGN_BOTTOM | wx.LEFT | wx.RIGHT, 5)
    file_details_pending_delete_counter_total = wx.StaticText(main_frame.root_panel, -1, label='0', name='Pending delete total')
    file_details_pending_delete_counter_total.SetFont(FONT_MEDIUM)
    file_details_pending_delete_counter_total.SetForegroundColour(Color.FADED)
    file_details_pending_sizer.Add(file_details_pending_delete_counter_total, 0, wx.ALIGN_BOTTOM)
    file_details_pending_sizer.Add((-1, -1), 1, wx.EXPAND)
    file_details_pending_copy_counter = wx.StaticText(main_frame.root_panel, -1, label='0', name='Pending copy counter')
    file_details_pending_copy_counter.SetFont(FONT_GIANT)
    file_details_pending_sizer.Add(file_details_pending_copy_counter, 0, wx.ALIGN_BOTTOM | wx.BOTTOM, -5)
    file_details_pending_copy_of = wx.StaticText(main_frame.root_panel, -1, label='of', name='Pending copy "of"')
    file_details_pending_copy_of.SetFont(FONT_MEDIUM)
    file_details_pending_copy_of.SetForegroundColour(Color.FADED)
    file_details_pending_sizer.Add(file_details_pending_copy_of, 0, wx.ALIGN_BOTTOM | wx.LEFT | wx.RIGHT, 5)
    file_details_pending_copy_counter_total = wx.StaticText(main_frame.root_panel, -1, label='0', name='Pending copy total')
    file_details_pending_copy_counter_total.SetFont(FONT_MEDIUM)
    file_details_pending_copy_counter_total.SetForegroundColour(Color.FADED)
    file_details_pending_sizer.Add(file_details_pending_copy_counter_total, 0, wx.ALIGN_BOTTOM)

    file_details_success_header_sizer = wx.BoxSizer()
    file_details_success_header = wx.StaticText(main_frame.root_panel, -1, label='Successful', name='Success file list header')
    file_details_success_header.SetFont(FONT_HEADING)
    file_details_success_header_sizer.Add(file_details_success_header, 0, wx.ALIGN_BOTTOM | wx.BOTTOM, -1)
    file_details_success_copy_text = wx.StaticText(main_frame.root_panel, -1, label='(Click to copy)', name='Success file list clipboard header')
    file_details_success_copy_text.SetForegroundColour(Color.FADED)
    file_details_success_header_sizer.Add(file_details_success_copy_text, 0, wx.ALIGN_BOTTOM | wx.LEFT, 5)
    file_details_success_header_sizer.Add((-1, -1), 1, wx.EXPAND)
    file_details_success_count = wx.StaticText(main_frame.root_panel, -1, label='0', name='Success file list count')
    file_details_success_count.SetFont(FONT_HEADING)
    file_details_success_header_sizer.Add(file_details_success_count, 0, wx.ALIGN_BOTTOM | wx.BOTTOM, -1)

    file_details_success_panel = wx.ScrolledWindow(main_frame.root_panel, -1, style=wx.VSCROLL, name='Success file list')
    file_details_success_panel.SetScrollbars(20, 20, 50, 50)
    file_details_success_panel.SetForegroundColour(Color.TEXT_DEFAULT)
    file_details_success_sizer = wx.BoxSizer(wx.VERTICAL)
    file_details_success_panel.SetSizer(file_details_success_sizer)

    file_details_failed_header_sizer = wx.BoxSizer()
    file_details_failed_header = wx.StaticText(main_frame.root_panel, -1, label='Failed', name='Failed file list header')
    file_details_failed_header.SetFont(FONT_HEADING)
    file_details_failed_header_sizer.Add(file_details_failed_header, 0, wx.ALIGN_BOTTOM | wx.BOTTOM, -1)
    file_details_failed_copy_text = wx.StaticText(main_frame.root_panel, -1, label='(Click to copy)', name='Failed file list clipboard header')
    file_details_failed_copy_text.SetForegroundColour(Color.FADED)
    file_details_failed_header_sizer.Add(file_details_failed_copy_text, 0, wx.ALIGN_BOTTOM | wx.LEFT, 5)
    file_details_failed_header_sizer.Add((-1, -1), 1, wx.EXPAND)
    file_details_failed_count = wx.StaticText(main_frame.root_panel, -1, label='0', name='Failed file list count')
    file_details_failed_count.SetFont(FONT_HEADING)
    file_details_failed_header_sizer.Add(file_details_failed_count, 0, wx.ALIGN_BOTTOM | wx.BOTTOM, -1)

    file_details_failed_panel = wx.ScrolledWindow(main_frame.root_panel, -1, style=wx.VSCROLL, name='Failed file list')
    file_details_failed_panel.SetScrollbars(20, 20, 50, 50)
    file_details_failed_panel.SetForegroundColour(Color.TEXT_DEFAULT)
    file_details_failed_sizer = wx.BoxSizer(wx.VERTICAL)
    file_details_failed_panel.SetSizer(file_details_failed_sizer)

    file_list_sizer = wx.BoxSizer(wx.VERTICAL)
    file_list_sizer.Add(file_details_pending_header_sizer, 0, wx.EXPAND)
    file_list_sizer.Add(file_details_pending_sizer, 0, wx.EXPAND)
    file_list_sizer.Add(file_details_success_header_sizer, 0, wx.EXPAND | wx.TOP, ITEM_UI_PADDING)
    file_list_sizer.Add(file_details_success_panel, 2, wx.EXPAND)
    file_list_sizer.Add(file_details_failed_header_sizer, 0, wx.EXPAND | wx.TOP, ITEM_UI_PADDING)
    file_list_sizer.Add(file_details_failed_panel, 1, wx.EXPAND)

    progress_bar = ProgressBar(main_frame.root_panel, style=wx.GA_SMOOTH | wx.GA_PROGRESS)
    progress_bar.SetRange(100)
    progress_bar.BindThreadManager(thread_manager)

    controls_sizer = wx.BoxSizer()
    start_analysis_btn = wx.Button(main_frame.root_panel, -1, label='Analyze', name='Analysis button')
    controls_sizer.Add(start_analysis_btn, 0)
    start_backup_btn = wx.Button(main_frame.root_panel, -1, label='Run Backup', name='Backup button')
    controls_sizer.Add(start_backup_btn, 0, wx.LEFT, ITEM_UI_PADDING)
    halt_verification_btn = wx.Button(main_frame.root_panel, -1, label='Halt Verification', name='Halt verification button')
    halt_verification_btn.Disable()
    controls_sizer.Add(halt_verification_btn, 0, wx.LEFT, ITEM_UI_PADDING)

    branding_sizer = wx.BoxSizer()
    branding_version_text = wx.StaticText(main_frame.root_panel, -1, f'v{__version__}')
    branding_version_text.SetForegroundColour(Color.FADED)
    branding_sizer.Add(branding_version_text, 0, wx.ALIGN_TOP | wx.TOP, 6)
    logo_image_path = resource_path('assets/img/logo_icon.png')
    branding_sizer.Add(wx.StaticBitmap(main_frame.root_panel, -1, wx.Bitmap(wx.Image(logo_image_path, wx.BITMAP_TYPE_ANY))), 0, wx.ALIGN_BOTTOM)

    # Status bar
    STATUS_BAR_PADDING = 8
    status_bar = wx.Panel(main_frame.root_panel, size=(-1, 20))
    status_bar.SetBackgroundColour(Color.STATUS_BAR)
    status_bar.SetForegroundColour(Color.TEXT_DEFAULT)
    status_bar_sizer = wx.BoxSizer()
    status_bar_selection = wx.StaticText(status_bar, -1, label='', name='Status bar selection')
    status_bar_sizer.Add(status_bar_selection, 0, wx.LEFT | wx.RIGHT, STATUS_BAR_PADDING)
    update_status_bar_selection()
    status_bar_action = wx.StaticText(status_bar, -1, label='', name='Status bar action')
    status_bar_sizer.Add(status_bar_action, 0, wx.LEFT | wx.RIGHT, STATUS_BAR_PADDING)
    update_status_bar_action(Status.IDLE)
    status_bar_error_count = wx.StaticText(status_bar, -1, label='0 failed', name='Status bar error count')
    status_bar_error_count.SetForegroundColour(Color.FADED)
    status_bar_sizer.Add(status_bar_error_count, 0, wx.LEFT | wx.RIGHT, STATUS_BAR_PADDING)
    status_bar_details = wx.StaticText(status_bar, -1, label='', name='Status bar detail item')
    status_bar_sizer.Add(status_bar_details, 0, wx.LEFT | wx.RIGHT, STATUS_BAR_PADDING)
    status_bar_sizer.Add((-1, -1), 1, wx.EXPAND)
    if PORTABLE_MODE:
        status_bar_portable_mode = wx.StaticText(status_bar, -1, label='Portable mode')
        status_bar_sizer.Add(status_bar_portable_mode, 0, wx.LEFT | wx.RIGHT, STATUS_BAR_PADDING)
    status_bar_updates = wx.StaticText(status_bar, -1, label='Up to date', name='Status bar update indicator')
    status_bar_sizer.Add(status_bar_updates, 0, wx.LEFT | wx.RIGHT, STATUS_BAR_PADDING)
    status_bar_outer_sizer = wx.BoxSizer(wx.VERTICAL)
    status_bar_outer_sizer.Add((-1, -1), 1, wx.EXPAND)
    status_bar_outer_sizer.Add(status_bar_sizer, 0, wx.EXPAND)
    status_bar_outer_sizer.Add((-1, -1), 1, wx.EXPAND)
    status_bar.SetSizer(status_bar_outer_sizer)

    root_sizer.Add(source_sizer, (0, 0), flag=wx.EXPAND)
    root_sizer.Add(summary_sizer, (1, 0), (3, 1), flag=wx.EXPAND)
    root_sizer.Add(file_list_sizer, (0, 1), (2, 1), flag=wx.EXPAND)
    root_sizer.Add(controls_sizer, (2, 1), flag=wx.ALIGN_CENTER_HORIZONTAL)
    root_sizer.Add(branding_sizer, (3, 1), flag=wx.ALIGN_CENTER_HORIZONTAL | wx.TOP | wx.BOTTOM, border=ITEM_UI_PADDING)
    root_sizer.Add(progress_bar, (4, 0), (1, 2), flag=wx.EXPAND)

    root_sizer.AddGrowableRow(1)
    root_sizer.AddGrowableCol(1)

    box = wx.BoxSizer(wx.VERTICAL)
    box.Add(root_sizer, 1, wx.EXPAND | wx.ALL, 10)
    box.Add(status_bar, 0, wx.EXPAND)

    # Right click menu stuff
    ID_SOURCE_RENAME = wx.NewIdRef()
    ID_SOURCE_DELETE = wx.NewIdRef()
    ID_DEST_RENAME = wx.NewIdRef()
    ID_DEST_DELETE = wx.NewIdRef()

    # Menu stuff
    menu_bar = wx.MenuBar()

    # File menu
    ID_OPEN_CONFIG = wx.NewIdRef()
    ID_SAVE_CONFIG = wx.NewIdRef()
    ID_SAVE_CONFIG_AS = wx.NewIdRef()
    file_menu = wx.Menu()
    file_menu.Append(ID_OPEN_CONFIG, '&Open Backup Config...\tCtrl+O', 'Open a previously created backup config')
    file_menu.Append(ID_SAVE_CONFIG, '&Save Backup Config\tCtrl+S', 'Save the current config to backup config file on the selected destinations')
    file_menu.Append(ID_SAVE_CONFIG_AS, 'Save Backup Config &As...\tCtrl+Shift+S', 'Save the current config to a backup config file')
    file_menu.AppendSeparator()
    file_menu_exit = file_menu.Append(104, 'E&xit', 'Terminate the program')
    menu_bar.Append(file_menu, '&File')

    # Selection menu
    ID_MENU_SOURCE_NETWORK_DRIVE = wx.NewIdRef()
    ID_MENU_SOURCE_LOCAL_DRIVE = wx.NewIdRef()
    ID_MENU_DEST_NETWORK_DRIVE = wx.NewIdRef()
    ID_MENU_DEST_LOCAL_DRIVE = wx.NewIdRef()
    ID_MENU_SOURCE_MODE_SINGLE_DRIVE = wx.NewIdRef()
    ID_MENU_SOURCE_MODE_MULTI_DRIVE = wx.NewIdRef()
    ID_MENU_SOURCE_MODE_SINGLE_PATH = wx.NewIdRef()
    ID_MENU_SOURCE_MODE_MULTI_PATH = wx.NewIdRef()
    ID_MENU_DEST_MODE_DRIVES = wx.NewIdRef()
    ID_MENU_DEST_MODE_PATHS = wx.NewIdRef()
    selection_menu = wx.Menu()
    selection_menu_show_drives_source_network = wx.MenuItem(selection_menu, ID_MENU_SOURCE_NETWORK_DRIVE, 'Source Network Drives', 'Enable network drives as sources', kind=wx.ITEM_CHECK)
    selection_menu.Append(selection_menu_show_drives_source_network)
    selection_menu_show_drives_source_network.Check(settings_show_drives_source_network)
    selection_menu_show_drives_source_local = wx.MenuItem(selection_menu, ID_MENU_SOURCE_LOCAL_DRIVE, 'Source Local Drives', 'Enable local drives as sources', kind=wx.ITEM_CHECK)
    selection_menu.Append(selection_menu_show_drives_source_local)
    selection_menu_show_drives_source_local.Check(settings_show_drives_source_local)
    selection_menu_show_drives_destination_network = wx.MenuItem(selection_menu, ID_MENU_DEST_NETWORK_DRIVE, 'Destination Network Drives', 'Enable network drives as destinations', kind=wx.ITEM_CHECK)
    selection_menu.Append(selection_menu_show_drives_destination_network)
    selection_menu_show_drives_destination_network.Check(settings_show_drives_destination_network)
    selection_menu_show_drives_destination_local = wx.MenuItem(selection_menu, ID_MENU_DEST_LOCAL_DRIVE, 'Destination Local Drives', 'Enable local drives as destinations', kind=wx.ITEM_CHECK)
    selection_menu.Append(selection_menu_show_drives_destination_local)
    selection_menu_show_drives_destination_local.Check(settings_show_drives_destination_local)
    selection_menu.AppendSeparator()
    selection_source_mode_menu = wx.Menu()
    selection_source_mode_menu_single_drive = wx.MenuItem(selection_source_mode_menu, ID_MENU_SOURCE_MODE_SINGLE_DRIVE, 'Single drive, select subfolders', 'Select subfolders from a drive to use as sources', kind=wx.ITEM_RADIO)
    selection_source_mode_menu.Append(selection_source_mode_menu_single_drive)
    selection_source_mode_menu_single_drive.Check(settings_source_mode == Config.SOURCE_MODE_SINGLE_DRIVE)
    selection_source_mode_menu_multi_drive = wx.MenuItem(selection_source_mode_menu, ID_MENU_SOURCE_MODE_MULTI_DRIVE, 'Multi drive, select drives', 'Select one or more drives to use as sources', kind=wx.ITEM_RADIO)
    selection_source_mode_menu.Append(selection_source_mode_menu_multi_drive)
    selection_source_mode_menu_multi_drive.Check(settings_source_mode == Config.SOURCE_MODE_MULTI_DRIVE)
    selection_source_mode_menu_single_path = wx.MenuItem(selection_source_mode_menu, ID_MENU_SOURCE_MODE_SINGLE_PATH, 'Single path, select subfolders', 'Specify a path, and select subfolders to use as sources', kind=wx.ITEM_RADIO)
    selection_source_mode_menu.Append(selection_source_mode_menu_single_path)
    selection_source_mode_menu_single_path.Check(settings_source_mode == Config.SOURCE_MODE_SINGLE_PATH)
    selection_source_mode_menu_multi_path = wx.MenuItem(selection_source_mode_menu, ID_MENU_SOURCE_MODE_MULTI_PATH, 'Multi path, select paths', 'Specify one or more paths to use as sources', kind=wx.ITEM_RADIO)
    selection_source_mode_menu.Append(selection_source_mode_menu_multi_path)
    selection_source_mode_menu_multi_path.Check(settings_source_mode == Config.SOURCE_MODE_MULTI_PATH)
    selection_menu.AppendSubMenu(selection_source_mode_menu, '&Source Mode')
    selection_dest_mode_menu = wx.Menu()
    selection_dest_mode_menu_drives = wx.MenuItem(selection_dest_mode_menu, ID_MENU_DEST_MODE_DRIVES, 'Drives', 'Select one or more drives as destinations', kind=wx.ITEM_RADIO)
    selection_dest_mode_menu.Append(selection_dest_mode_menu_drives)
    selection_dest_mode_menu_drives.Check(settings_dest_mode == Config.DEST_MODE_DRIVES)
    selection_dest_mode_menu_paths = wx.MenuItem(selection_dest_mode_menu, ID_MENU_DEST_MODE_PATHS, 'Paths', 'Specify one or more paths as destinations', kind=wx.ITEM_RADIO)
    selection_dest_mode_menu.Append(selection_dest_mode_menu_paths)
    selection_dest_mode_menu_paths.Check(settings_dest_mode == Config.DEST_MODE_PATHS)
    selection_menu.AppendSubMenu(selection_dest_mode_menu, '&Destination Mode')
    menu_bar.Append(selection_menu, '&Selection')

    # View menu
    ID_REFRESH_SOURCE = wx.NewIdRef()
    ID_REFRESH_DEST = wx.NewIdRef()
    ID_SHOW_ERROR_LOG = wx.NewIdRef()
    view_menu = wx.Menu()
    view_menu.Append(ID_REFRESH_SOURCE, 'Refresh Source\tCtrl+F5', 'Refresh the list of sources shown')
    view_menu.Append(ID_REFRESH_DEST, '&Refresh Destination\tF5', 'Refresh the list of destinations shown')
    view_menu.AppendSeparator()
    view_menu.Append(ID_SHOW_ERROR_LOG, 'Backup Error Log\tCtrl+E', 'Show the backup error log')
    menu_bar.Append(view_menu, '&View')

    # Actions menu
    ID_VERIFY_DATA = wx.NewIdRef()
    ID_DELETE_CONFIG_FROM_DRIVES = wx.NewIdRef()
    actions_menu = wx.Menu()
    actions_menu.Append(ID_VERIFY_DATA, '&Verify Data Integrity on Selected Destinations', 'Verify files on selected destinations against the saved hash to check for errors')
    actions_menu.Append(ID_DELETE_CONFIG_FROM_DRIVES, 'Delete Config from Selected Destinations', 'Delete the saved backup config from the selected destinations')
    menu_bar.Append(actions_menu, '&Actions')

    # Preferences menu
    ID_VERIFY_KNOWN_FILES = wx.NewIdRef()
    ID_VERIFY_ALL_FILES = wx.NewIdRef()
    ID_DARK_MODE = wx.NewIdRef()
    preferences_menu = wx.Menu()
    preferences_verification_menu = wx.Menu()
    preferences_verification_menu_verify_known_files = wx.MenuItem(preferences_verification_menu, ID_VERIFY_KNOWN_FILES, 'Verify Known Files', 'Verify files with known hashes, skip unknown files', kind=wx.ITEM_RADIO)
    preferences_verification_menu.Append(preferences_verification_menu_verify_known_files)
    preferences_verification_menu_verify_known_files.Check(not settings_verify_all_files)
    preferences_verification_menu_verify_all_files = wx.MenuItem(preferences_verification_menu, ID_VERIFY_ALL_FILES, 'Verify All Files', 'Verify files with known hashes, compute and save the hash of unknown files', kind=wx.ITEM_RADIO)
    preferences_verification_menu.Append(preferences_verification_menu_verify_all_files)
    preferences_verification_menu_verify_all_files.Check(settings_verify_all_files)
    preferences_menu.AppendSubMenu(preferences_verification_menu, '&Data Integrity Verification')
    preferences_menu_dark_mode = wx.MenuItem(preferences_menu, 502, 'Enable Dark Mode (requires restart)', 'Enable or disable dark mode', kind=wx.ITEM_CHECK)
    preferences_menu.Append(preferences_menu_dark_mode)
    preferences_menu_dark_mode.Check(settings_dark_mode)
    menu_bar.Append(preferences_menu, '&Preferences')

    # Debug menu
    ID_SHOW_WIDGET_INSPECTION = wx.NewIdRef()
    debug_menu = wx.Menu()
    debug_menu.Append(ID_SHOW_WIDGET_INSPECTION, 'Show &Widget Inspection Tool\tF6', 'Show the widget inspection tool')
    menu_bar.Append(debug_menu, '&Debug')

    # Help menu
    ID_CHECK_FOR_UPDATES = wx.NewIdRef()
    ID_ALLOW_PRERELEASE_UPDATES = wx.NewIdRef()
    help_menu = wx.Menu()
    help_menu.Append(ID_CHECK_FOR_UPDATES, 'Check for Updates', 'Check for program updates, and prompt to download them, if there are any')
    help_menu_allow_prerelease_updates = wx.MenuItem(help_menu, ID_ALLOW_PRERELEASE_UPDATES, 'Allow Prereleases', 'Allow prerelease versions when checking for updates', kind=wx.ITEM_CHECK)
    help_menu.Append(help_menu_allow_prerelease_updates)
    help_menu_allow_prerelease_updates.Check(settings_allow_prerelease_updates)
    menu_bar.Append(help_menu, '&Help')

    main_frame.SetMenuBar(menu_bar)

    # Menu item bindings
    main_frame.Bind(wx.EVT_MENU, lambda e: open_config_file(), id=ID_OPEN_CONFIG)
    main_frame.Bind(wx.EVT_MENU, lambda e: save_config_file(), id=ID_SAVE_CONFIG)
    main_frame.Bind(wx.EVT_MENU, lambda e: save_config_file_as(), id=ID_SAVE_CONFIG_AS)
    main_frame.Bind(wx.EVT_MENU, lambda e: on_close(), file_menu_exit)

    main_frame.Bind(wx.EVT_MENU, lambda e: change_source_type(DRIVE_TYPE_REMOTE), id=ID_MENU_SOURCE_NETWORK_DRIVE)
    main_frame.Bind(wx.EVT_MENU, lambda e: change_source_type(DRIVE_TYPE_LOCAL), id=ID_MENU_SOURCE_LOCAL_DRIVE)
    main_frame.Bind(wx.EVT_MENU, lambda e: change_destination_type(DRIVE_TYPE_REMOTE), id=ID_MENU_DEST_NETWORK_DRIVE)
    main_frame.Bind(wx.EVT_MENU, lambda e: change_destination_type(DRIVE_TYPE_LOCAL), id=ID_MENU_DEST_LOCAL_DRIVE)
    main_frame.Bind(wx.EVT_MENU, lambda e: change_source_mode(Config.SOURCE_MODE_SINGLE_DRIVE), id=ID_MENU_SOURCE_MODE_SINGLE_DRIVE)
    main_frame.Bind(wx.EVT_MENU, lambda e: change_source_mode(Config.SOURCE_MODE_MULTI_DRIVE), id=ID_MENU_SOURCE_MODE_MULTI_DRIVE)
    main_frame.Bind(wx.EVT_MENU, lambda e: change_source_mode(Config.SOURCE_MODE_SINGLE_PATH), id=ID_MENU_SOURCE_MODE_SINGLE_PATH)
    main_frame.Bind(wx.EVT_MENU, lambda e: change_source_mode(Config.SOURCE_MODE_MULTI_PATH), id=ID_MENU_SOURCE_MODE_MULTI_PATH)
    main_frame.Bind(wx.EVT_MENU, lambda e: change_dest_mode(Config.DEST_MODE_DRIVES), id=ID_MENU_DEST_MODE_DRIVES)
    main_frame.Bind(wx.EVT_MENU, lambda e: change_dest_mode(Config.DEST_MODE_PATHS), id=ID_MENU_DEST_MODE_PATHS)

    main_frame.Bind(wx.EVT_MENU, lambda e: load_source_in_background(), id=ID_REFRESH_SOURCE)
    main_frame.Bind(wx.EVT_MENU, lambda e: load_dest_in_background(), id=ID_REFRESH_DEST)
    main_frame.Bind(wx.EVT_MENU, lambda e: show_backup_error_log(), id=ID_SHOW_ERROR_LOG)

    main_frame.Bind(wx.EVT_MENU, lambda e: start_verify_data_from_hash_list(), id=ID_VERIFY_DATA)
    main_frame.Bind(wx.EVT_MENU, lambda e: delete_config_file_from_selected_drives(), id=ID_DELETE_CONFIG_FROM_DRIVES)

    main_frame.Bind(wx.EVT_MENU, lambda e: change_verification_all_preferences(False), id=ID_VERIFY_KNOWN_FILES)
    main_frame.Bind(wx.EVT_MENU, lambda e: change_verification_all_preferences(True), id=ID_VERIFY_ALL_FILES)
    main_frame.Bind(wx.EVT_MENU, lambda e: change_dark_mode_preferences(preferences_menu_dark_mode.IsChecked()), id=ID_DARK_MODE)

    main_frame.Bind(wx.EVT_MENU, lambda e: show_widget_inspector(), id=ID_SHOW_WIDGET_INSPECTION)

    main_frame.Bind(wx.EVT_MENU, lambda e: check_for_updates_in_background(), id=ID_CHECK_FOR_UPDATES)
    main_frame.Bind(wx.EVT_MENU, lambda e: change_prerelease_preferences(help_menu_allow_prerelease_updates.IsChecked()), id=ID_ALLOW_PRERELEASE_UPDATES)

    # Key bindings
    accelerators = [wx.AcceleratorEntry() for x in range(7)]
    accelerators[0].Set(wx.ACCEL_CTRL, ord('O'), ID_OPEN_CONFIG)
    accelerators[1].Set(wx.ACCEL_CTRL, ord('S'), ID_SAVE_CONFIG)
    accelerators[2].Set(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('S'), ID_SAVE_CONFIG_AS)
    accelerators[3].Set(wx.ACCEL_CTRL, wx.WXK_F5, ID_REFRESH_SOURCE)
    accelerators[4].Set(wx.ACCEL_NORMAL, wx.WXK_F5, ID_REFRESH_DEST)
    accelerators[5].Set(wx.ACCEL_CTRL, ord('E'), ID_SHOW_ERROR_LOG)
    accelerators[6].Set(wx.ACCEL_NORMAL, wx.WXK_F6, ID_SHOW_WIDGET_INSPECTION)
    main_frame.SetAcceleratorTable(wx.AcceleratorTable(accelerators))

    # Mouse bindings
    source_src_control_dropdown.Bind(wx.EVT_COMBOBOX, change_source_drive)
    source_src_control_browse_btn.Bind(wx.EVT_LEFT_DOWN, lambda e: post_event(evt_type=EVT_REQUEST_OPEN_SOURCE))
    source_tree.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda e: post_event(evt_type=EVT_SELECT_SOURCE))
    source_tree.Bind(wx.EVT_LIST_ITEM_DESELECTED, lambda e: post_event(evt_type=EVT_SELECT_SOURCE))
    source_tree.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, show_source_right_click_menu)
    source_dest_control_browse_btn.Bind(wx.EVT_LEFT_DOWN, lambda e: post_event(evt_type=EVT_REQUEST_OPEN_DEST))
    dest_tree.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda e: post_event(evt_type=EVT_SELECT_DEST))
    dest_tree.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, show_dest_right_click_menu)
    split_mode_status.Bind(wx.EVT_LEFT_DOWN, lambda e: toggle_split_mode())

    file_details_delete_text.Bind(wx.EVT_LEFT_DOWN, lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_TOTAL_DELETE]])))
    file_details_delete_copy_text.Bind(wx.EVT_LEFT_DOWN, lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_TOTAL_DELETE]])))
    file_details_copy_copy_text.Bind(wx.EVT_LEFT_DOWN, lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_TOTAL_COPY]])))
    file_details_copy_text.Bind(wx.EVT_LEFT_DOWN, lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_TOTAL_COPY]])))
    file_details_success_header.Bind(wx.EVT_LEFT_DOWN, lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_SUCCESS]])))
    file_details_success_copy_text.Bind(wx.EVT_LEFT_DOWN, lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_SUCCESS]])))
    file_details_success_count.Bind(wx.EVT_LEFT_DOWN, lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_SUCCESS]])))
    file_details_failed_header.Bind(wx.EVT_LEFT_DOWN, lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_FAIL]])))
    file_details_failed_copy_text.Bind(wx.EVT_LEFT_DOWN, lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_FAIL]])))
    file_details_failed_count.Bind(wx.EVT_LEFT_DOWN, lambda event: clipboard.copy('\n'.join([file['filename'] for file in file_detail_list[FileUtils.LIST_FAIL]])))

    start_analysis_btn.Bind(wx.EVT_LEFT_DOWN, lambda e: start_backup_analysis())
    start_backup_btn.Bind(wx.EVT_LEFT_DOWN, lambda e: start_backup())
    halt_verification_btn.Bind(wx.EVT_LEFT_DOWN, lambda e: thread_manager.kill('Data Verification'))

    status_bar_error_count.Bind(wx.EVT_LEFT_DOWN, lambda e: show_backup_error_log())
    status_bar_updates.Bind(wx.EVT_LEFT_DOWN, lambda e: show_update_window(update_info))

    # PyEvent bindings
    EVT_REQUEST_LOAD_SOURCE = wx.NewEventType()
    EVT_UPDATE_SOURCE_SIZE = wx.NewEventType()
    EVT_SELECT_SOURCE = wx.NewEventType()
    EVT_REQUEST_LOAD_DEST = wx.NewEventType()
    EVT_SELECT_DEST = wx.NewEventType()
    EVT_REQUEST_OPEN_SOURCE = wx.NewEventType()
    EVT_REQUEST_OPEN_DEST = wx.NewEventType()
    EVT_ANALYSIS_STARTING = wx.NewEventType()
    EVT_ANALYSIS_FINISHED = wx.NewEventType()
    EVT_BACKUP_FINISHED = wx.NewEventType()
    EVT_CHECK_FOR_UPDATES = wx.NewEventType()
    EVT_VERIFY_DATA_INTEGRITY = wx.NewEventType()
    main_frame.Connect(-1, -1, EVT_REQUEST_LOAD_SOURCE, lambda e: load_source())
    main_frame.Connect(-1, -1, EVT_UPDATE_SOURCE_SIZE, lambda e: update_source_size(e.data))
    main_frame.Connect(-1, -1, EVT_SELECT_SOURCE, lambda e: select_source())
    main_frame.Connect(-1, -1, EVT_REQUEST_LOAD_DEST, lambda e: load_dest())
    main_frame.Connect(-1, -1, EVT_SELECT_DEST, lambda e: select_dest())
    main_frame.Connect(-1, -1, EVT_REQUEST_OPEN_SOURCE, lambda e: browse_for_source())
    main_frame.Connect(-1, -1, EVT_REQUEST_OPEN_DEST, lambda e: browse_for_dest())
    main_frame.Connect(-1, -1, EVT_ANALYSIS_STARTING, lambda e: update_ui_pre_analysis())
    main_frame.Connect(-1, -1, EVT_ANALYSIS_FINISHED, lambda e: update_ui_post_analysis(e.fp, e.sp))
    main_frame.Connect(-1, -1, EVT_BACKUP_FINISHED, lambda e: update_ui_post_backup(e.data))
    main_frame.Connect(-1, -1, EVT_CHECK_FOR_UPDATES, lambda e: show_update_window(e.data))
    main_frame.Connect(-1, -1, EVT_VERIFY_DATA_INTEGRITY, lambda e: verify_data_integrity(e.data))

    # Catch close event for graceful exit
    main_frame.Bind(wx.EVT_CLOSE, lambda e: on_close())

    # Keyboard listener
    listener = keyboard.Listener(
        on_press=on_press,
        on_release=on_release)
    listener.start()

    main_frame.root_panel.SetSizerAndFit(box)
    main_frame.Show()

    # Check for updates on startup
    check_for_updates_in_background()

    source_avail_drive_list = []
    source_drive_default = ''

    # Load UI and configure for preferences
    change_source_mode(settings_source_mode)
    change_dest_mode(settings_dest_mode)

    # Add placeholder to backup analysis
    reset_analysis_output()

    # Load data
    load_source_in_background()

    # Continuously update UI using data from Backup instance
    EVT_BACKUP_TIMER = wx.NewEventType()
    main_frame.Connect(-1, -1, EVT_BACKUP_TIMER, lambda e: update_ui_during_backup())
    ui_update_scheduler = RepeatedTimer(0.25, request_update_ui_during_backup)

    app.MainLoop()
