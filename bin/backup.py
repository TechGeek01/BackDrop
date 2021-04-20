from tkinter import messagebox
import os
import itertools
from datetime import datetime
import shutil
import pickle

from bin.fileutils import human_filesize, get_directory_size
from bin.color import bcolor
from bin.threadmanager import ThreadManager
from bin.config import Config
from bin.status import Status

class Backup:
    def __init__(self, config, backup_config_dir, backup_config_file, do_copy_fn, do_del_fn, start_backup_timer_fn, update_file_detail_list_fn, analysis_summary_display_fn, display_backup_command_info_fn, thread_manager, update_ui_component_fn=None, uicolor=None, progress=None):
        """Configure a backup to be run on a set of drives.

        Args:
            config (dict): The backup config to be processed.
            backup_config_dir (String): The directory to store backup configs on each drive.
            backup_config_file (String): The file to store backup configs on each drive.
            do_copy_fn (def): The function to be used to handle file copying. TODO: Move do_copy_fn outside of Backup class.
            do_del_fn (def): The function to be used to handle file copying. TODO: Move do_del_fn outside of Backup class.
            start_backup_timer_fn (def): The function to be used to start the backup timer.
            update_ui_component_fn (def): The function to be used to update UI components (default None).
            update_file_detail_list_fn (def): The function to be used to update file lists.
            analysis_summary_display_fn (def): The function to be used to show an analysis
                    summary.
            display_backup_command_info_fn (def): The function to be used to enumerate command info
                    in the UI.
            thread_manager (ThreadManager): The thread manager to check for kill flags.
            uicolor (Color): The UI color instance to reference for styling (default None). TODO: Move uicolor outside of Backup class
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

        self.confirm_wipe_existing_drives = False
        self.analysis_valid = False
        self.analysis_started = False
        self.analysis_running = False
        self.backup_running = False
        self.backup_start_time = 0

        self.command_list = []
        self.delete_file_list = {}
        self.replace_file_list = {}
        self.new_file_list = {}

        self.config = config
        self.DRIVE_VID_INFO = {drive['vid']: drive for drive in config['destinations']}
        self.SHARE_NAME_PATH_INFO = {share['dest_name']: share['path'] for share in config['sources']}

        self.BACKUP_CONFIG_DIR = backup_config_dir
        self.BACKUP_CONFIG_FILE = backup_config_file
        self.BACKUP_HASH_FILE = 'hashes.pkl'

        self.CLI_MODE = self.config['cli_mode']

        self.file_hashes = {drive['name']: {} for drive in self.config['destinations']}

        self.uicolor = uicolor
        self.do_copy_fn = do_copy_fn
        self.do_del_fn = do_del_fn
        self.start_backup_timer_fn = start_backup_timer_fn
        self.update_ui_component_fn = update_ui_component_fn
        self.update_file_detail_list_fn = update_file_detail_list_fn
        self.analysis_summary_display_fn = analysis_summary_display_fn
        self.display_backup_command_info_fn = display_backup_command_info_fn
        self.thread_manager = thread_manager
        self.progress = progress

    def sanity_check(self):
        """Check to make sure everything is correct before a backup.

        Before running a backup, or an analysis, both shares and drives need to be
        selected, and the drive space on selected drives needs to be larger than the
        total size of the selected shares.

        Returns:
            bool: True if conditions are good, False otherwise.
        """

        if len(self.config['destinations']) > 0 and len(self.config['sources']) > 0:
            share_total = 0
            drive_total = 0

            # Shares and destinations need identifiers
            if self.config['source_mode'] in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH] and [share for share in self.config['sources'] if not share['dest_name']]:
                return False
            if self.config['dest_mode'] == Config.DEST_MODE_PATHS and [drive for drive in self.config['destinations'] if not drive['vid']]:
                return False

            shares_known = True
            for share in self.config['sources']:
                if share['size'] is None:
                    shares_known = False
                    break

                # Add total space of selection
                share_total += share['size']

            drive_total = sum([drive['capacity'] for drive in self.config['destinations']])
            config_total = drive_total + sum([size for drive, size in self.config['missing_drives'].items()])

            if shares_known and ((len(self.config['missing_drives']) == 0 and share_total < drive_total) or (share_total < config_total and self.config['splitMode'])):
                # Sanity check pass if more drive selected than shares, OR, split mode and more config drives selected than shares

                selected_new_drives = [drive['name'] for drive in self.config['destinations'] if drive['hasConfig'] is False]
                if not self.confirm_wipe_existing_drives and len(selected_new_drives) > 0:
                    drive_string = ', '.join(selected_new_drives[:-2] + [' and '.join(selected_new_drives[-2:])])

                    new_drive_confirm_title = f"New drive{'s' if len(selected_new_drives) > 1 else ''} selected"
                    new_drive_confirm_message = f"Drive{'s' if len(selected_new_drives) > 1 else ''} {drive_string} appear{'' if len(selected_new_drives) > 1 else 's'} to be new. Existing data will be deleted.\n\nAre you sure you want to continue?"
                    self.confirm_wipe_existing_drives = messagebox.askyesno(new_drive_confirm_title, new_drive_confirm_message)

                    return self.confirm_wipe_existing_drives

                return True

        return False

    def get_share_source_path(self, share):
        """Convert a share name into a share path.

        Args:
            share (String): The share to convert.

        Returns:
            String: The source path for the given share.
        """

        share_base = share.split(os.path.sep)[0]
        share_slug = share[len(share_base):].strip(os.path.sep)
        share_base_path = self.SHARE_NAME_PATH_INFO[share_base]
        share_full_path = os.path.join(share_base_path, share_slug).strip(os.path.sep)

        return share_full_path

    # IDEA: When we ignore other stuff on the drives, and delete it, have a dialog popup that summarizes what's being deleted, and ask the user to confirm
    def analyze(self):
        """Analyze the list of selected shares and drives and figure out how to split files.

        Args:
            shares (dict[]): The list of selected shares.
            shares.name (String): The name of the share.
            shares.size (int): The size in bytes of the share.
            drives (tuple(String)): The list of selected drives.

        This function is run in a new thread, but is only run if the backup config is valid.
        If sanity_check() returns False, the analysis isn't run.
        """

        # Sanity check for space requirements
        if not self.sanity_check():
            return

        self.analysis_running = True
        self.analysis_started = True

        if not self.CLI_MODE:
            self.progress.start_indeterminate()
            self.update_ui_component_fn(Status.UPDATEUI_STATUS_BAR, Status.BACKUP_ANALYSIS_RUNNING)
            self.update_ui_component_fn(Status.UPDATEUI_BACKUP_BTN, {'state': 'disable'})
            self.update_ui_component_fn(Status.UPDATEUI_ANALYSIS_BTN, {'state': 'disable'})
            self.update_ui_component_fn(Status.LOCK_TREE_SELECTION)

        share_info = {share['dest_name']: share['size'] for share in self.config['sources']}
        all_share_info = {share['dest_name']: share['size'] for share in self.config['sources']}

        self.analysis_summary_display_fn(
            title='Source',
            payload=[(share['dest_name'], human_filesize(share['size'])) for share in self.config['sources']],
            reset=True
        )

        # Get hash list for all drives
        bad_hash_files = []
        self.file_hashes = {drive['name']: {} for drive in self.config['destinations']}
        special_ignore_list = [self.BACKUP_CONFIG_DIR, '$RECYCLE.BIN', 'System Volume Information']
        for drive in self.config['destinations']:
            drive_hash_file_path = os.path.join(drive['name'], self.BACKUP_CONFIG_DIR, self.BACKUP_HASH_FILE)

            if os.path.isfile(drive_hash_file_path):
                write_trimmed_changes = False
                with open(drive_hash_file_path, 'rb') as f:
                    try:
                        # Load hash list, and filter out ignored folders
                        hash_list = pickle.load(f)
                        new_hash_list = {file_name: hash_val for file_name, hash_val in hash_list.items() if file_name.split('/')[0] not in special_ignore_list}
                        new_hash_list = {os.path.sep.join(file_name.split('/')): hash_val for file_name, hash_val in new_hash_list.items() if os.path.isfile(os.path.join(drive['name'], file_name))}

                        # If trimmed list is shorter, new changes have to be written to the file
                        if len(new_hash_list) < len(hash_list):
                            write_trimmed_changes = True

                        self.file_hashes[drive['name']] = new_hash_list
                    except Exception:
                        # Hash file is corrupt
                        bad_hash_files.append(drive_hash_file_path)

                # If trimmed list is different length than original, write changes to file
                if write_trimmed_changes:
                    with open(drive_hash_file_path, 'wb') as f:
                        pickle.dump({'/'.join(file_name.split(os.path.sep)): hash_val for file_name, hash_val in new_hash_list.items()}, f)
            else:
                # Hash file doesn't exist, so create it
                if not os.path.exists(os.path.join(drive['name'], self.BACKUP_CONFIG_DIR)):
                    os.makedirs(os.path.join(drive['name'], self.BACKUP_CONFIG_DIR))
                with open(drive_hash_file_path, 'wb') as f:
                    pickle.dump({}, f)

        # If there are missing or corrupted pickle files, write empty data
        if bad_hash_files:
            for file in bad_hash_files:
                with open(file, 'wb') as f:
                    pickle.dump({}, f)

        drive_info = []
        drive_share_list = {}
        master_drive_list = [drive for drive in self.config['destinations']]
        master_drive_list.extend([{'vid': vid, 'capacity': capacity} for vid, capacity in self.config['missing_drives'].items()])
        connected_vid_list = [drive['vid'] for drive in self.config['destinations']]
        show_drive_info = []
        for i, drive in enumerate(master_drive_list):
            drive_connected = drive['vid'] in connected_vid_list

            current_drive_info = drive
            current_drive_info['connected'] = drive_connected

            # If drive is connected, collect info about config size and free space
            if drive_connected:
                current_drive_info['configSize'] = get_directory_size(os.path.join(drive['name'], self.BACKUP_CONFIG_DIR))
            else:
                current_drive_info['name'] = f"[{drive['vid']}]"
                current_drive_info['configSize'] = 20000  # Assume 20K config size

            current_drive_info['free'] = drive['capacity'] - drive['configSize']

            drive_info.append(current_drive_info)

            # Enumerate list for tracking what shares go where
            drive_share_list[drive['vid']] = []

            show_drive_info.append((current_drive_info['name'], human_filesize(drive['capacity']), drive_connected))

        self.analysis_summary_display_fn(
            title='Destination',
            payload=show_drive_info
        )

        # For each drive, smallest first, filter list of shares to those that fit
        drive_info.sort(key=lambda x: x['free'])

        all_drive_files_buffer = {drive['name']: [] for drive in master_drive_list}

        for i, drive in enumerate(drive_info):
            # Get list of sources small enough to fit on drive
            total_small_sources = {source: size for source, size in share_info.items() if size <= drive['free']}

            # Since the list of files is truncated to prevent an unreasonably large
            # number of combinations to check, we need to keep processing the file list
            # in chunks to make sure we check if all files can be fit on one drive
            sources_that_fit_on_dest = []
            processed_small_sources = []
            processed_source_size = 0
            while len(processed_small_sources) < len(total_small_sources):
                # Trim the list of small files to those that aren't already processed
                small_source_list = {source: size for (source, size) in total_small_sources.items() if source not in processed_small_sources}
                small_source_list = sorted(small_source_list.items(), key=lambda x: x[1], reverse=True)

                trimmed_small_source_list = {source[0]: source[1] for source in small_source_list[:15]}

                # Try every combination of sources that fit to find result that uses most of that drive
                largest_sum = 0
                largest_set = []
                for n in range(1, len(trimmed_small_source_list) + 1):
                    for subset in itertools.combinations(trimmed_small_source_list.keys(), n):
                        combination_total = sum(trimmed_small_source_list[share] for share in subset)

                        if (combination_total > largest_sum and combination_total <= drive['free']):
                            largest_sum = combination_total
                            largest_set = subset

                sources_that_fit_on_dest.extend([source for source in largest_set])
                remaining_small_sources = {source[0]: source[1] for source in small_source_list if source not in sources_that_fit_on_dest}
                processed_small_sources.extend([source for source in trimmed_small_source_list.keys()])
                share_info = {share: size for (share, size) in share_info.items() if share not in sources_that_fit_on_dest}

                # Subtract file size of each batch of files from the free space on the drive so the next batch sorts properly
                processed_source_size += sum([source[1] for source in small_source_list if source[0] in largest_set])

            # If not all shares fit on smallest drive at once (at least one share has to be put
            # on the next largest drive), check free space on next largest drive
            if len(sources_that_fit_on_dest) < len(small_source_list) and i < (len(drive_info) - 1):
                not_fit_total = sum(size for size in remaining_small_sources.values())
                next_drive = drive_info[i + 1]
                next_drive_free_space = next_drive['free'] - not_fit_total

                # If free space on next drive is less than total capacity of current drive, it
                # becomes more efficient to skip current drive, and put all shares on the next
                # drive instead.
                # This applies only if they can all fit on the next drive. If they have to be
                # split across multiple drives after moving them to a larger drive, then it's
                # easier to fit what we can on the small drive, to leave the larger drives
                # available for larger shares
                if not_fit_total <= next_drive['free']:
                    total_small_share_space = sum(size for size in small_source_list.values())
                    if next_drive_free_space < drive['free'] and total_small_share_space <= next_drive['free']:
                        # Next drive free space less than total on current, so it's optimal to store on next drive instead
                        drive_share_list[next_drive['vid']].extend([share for share in small_source_list.keys()])  # All small shares on next drive
                    else:
                        # Better to leave on current, but overflow to next drive
                        drive_share_list[drive['vid']].extend(sources_that_fit_on_dest)  # Shares that fit on current drive
                        drive_share_list[next_drive['vid']].extend([share for share in small_source_list.keys() if share not in sources_that_fit_on_dest])  # Remaining small shares on next drive
                else:
                    # If overflow for next drive is more than can fit on that drive, ignore it, put overflow
                    # back in pool of shares to sort, and put small drive shares only in current drive
                    drive_share_list[drive['vid']].extend(sources_that_fit_on_dest)  # Shares that fit on current drive
                    all_drive_files_buffer[drive['name']].extend([f"{drive['name']}{share}" for share in sources_that_fit_on_dest])

                    # Put remaining small shares back into pool to work with for next drive
                    share_info.update({share: size for share, size in remaining_small_sources.items()})
            else:
                # Fit all small shares onto drive
                drive_share_list[drive['vid']].extend(sources_that_fit_on_dest)

            # Calculate space used by shares, and subtract it from capacity to get free space
            used_space = sum(all_share_info[share] for share in drive_share_list[drive['vid']])
            drive_info[i]['free'] -= used_space

        def split_share(share):
            """Recurse into a share or directory, and split the contents.

            Args:
                share (String): The share to split.
            """

            # Enumerate list for tracking what shares go where
            drive_file_list = {drive['vid']: [] for drive in drive_info}

            file_info = {}
            share_path = self.get_share_source_path(share)

            try:
                for entry in os.scandir(share_path):
                    if entry.is_file():
                        new_dir_size = entry.stat().st_size
                    elif entry.is_dir():
                        new_dir_size = get_directory_size(entry.path)

                    filename = entry.path[len(share_path):].strip(os.path.sep)
                    file_info[filename] = new_dir_size
            except PermissionError:
                pass

            # For splitting shares, sort by largest free space first
            drive_info.sort(reverse=True, key=lambda x: x['free'])

            for i, drive in enumerate(drive_info):
                # Get list of files small enough to fit on drive
                total_small_files = {file: size for file, size in file_info.items() if size <= drive['free']}

                # Since the list of files is truncated to prevent an unreasonably large
                # number of combinations to check, we need to keep processing the file list
                # in chunks to make sure we check if all files can be fit on one drive
                files_that_fit_on_drive = []
                processed_small_files = []
                processed_file_size = 0
                while len(processed_small_files) < len(total_small_files):
                    # Trim the list of small files to those that aren't already processed
                    small_file_list = {file: size for (file, size) in total_small_files.items() if file not in processed_small_files}

                    # Make sure we don't end with an unreasonable number of combinations to go through
                    # by sorting by largest first, and truncating
                    # Sorting files first, since files can't be split, so it's preferred to have directories last
                    file_list = {}
                    dir_list = {}
                    for file, size in small_file_list.items():
                        if os.path.isfile(os.path.join(share_path, file)):
                            file_list[file] = size
                        elif os.path.isdir(os.path.join(share_path, file)):
                            dir_list[file] = size

                    # Sort file list by largest first, and truncate to prevent unreasonably large number of combinations
                    small_file_list = sorted(file_list.items(), key=lambda x: x[1], reverse=True)
                    small_file_list.extend(sorted(dir_list.items(), key=lambda x: x[1], reverse=True))
                    trimmed_small_file_list = {file[0]: file[1] for file in small_file_list[:15]}
                    small_file_list = {file[0]: file[1] for file in small_file_list}

                    # Try every combination of shares that fit to find result that uses most of that drive
                    largest_sum = 0
                    largest_set = []
                    for n in range(1, len(trimmed_small_file_list) + 1):
                        for subset in itertools.combinations(trimmed_small_file_list.keys(), n):
                            combination_total = sum(trimmed_small_file_list[file] for file in subset)

                            if (combination_total > largest_sum and combination_total <= drive['free'] - processed_file_size):
                                largest_sum = combination_total
                                largest_set = subset

                    files_that_fit_on_drive.extend([file for file in largest_set])
                    processed_small_files.extend([file for file in trimmed_small_file_list.keys()])
                    file_info = {file: size for (file, size) in file_info.items() if file not in largest_set}

                    # Subtract file size of each batch of files from the free space on the drive so the next batch sorts properly
                    processed_file_size += sum([size for (file, size) in small_file_list.items() if file in largest_set])

                # Assign files to drive, and subtract filesize from free space
                # Since we're sorting by largest free space first, there's no cases to move
                # to a larger drive. This means all files that can fit should be put on the
                # drive they fit on.
                drive_file_list[drive['vid']].extend(files_that_fit_on_drive)
                drive_info[i]['free'] -= processed_file_size

            share_split_summary = [{
                'share': share,
                'files': drive_file_list,
                'exclusions': [file for file in file_info.keys()]
            }]

            for file in file_info.keys():
                file_path = os.path.join(share, file)
                share_split_summary.extend(split_share(file_path))

            return share_split_summary

        # For shares larger than all drives, recurse into each share
        # share_info contains shares not sorted into drives
        drive_exclusions = {drive['name']: [] for drive in master_drive_list}
        for share in share_info.keys():
            share_path = self.get_share_source_path(share)

            if os.path.exists(share_path) and os.path.isdir(share_path):
                summary = split_share(share)

                # Build exclusion list for other drives\
                # This is done by "inverting" the file list for each drive into a list of exclusions for other drives
                for directory in summary:
                    file_list = directory['files']

                    for drive, files in file_list.items():
                        # Add files to file list
                        all_drive_files_buffer[self.DRIVE_VID_INFO[drive]['name']].extend(files)

                # Each summary contains a split share, and any split subfolders, starting with
                # the share and recursing into the directories
                for directory in summary:
                    share_name = directory['share']
                    share_files = directory['files']
                    share_exclusions = directory['exclusions']

                    all_files = share_files.copy()
                    all_files['exclusions'] = share_exclusions

                    # For each drive, gather list of files to be written to other drives, and
                    # use that as exclusions
                    for drive, files in share_files.items():
                        if len(files) > 0:
                            raw_exclusions = all_files.copy()
                            raw_exclusions.pop(drive, None)

                            # Build master full exclusion list
                            master_exclusions = [file for file_list in raw_exclusions.values() for file in file_list]

                            # Remove share if excluded in parent splitting
                            if share_name in drive_exclusions[self.DRIVE_VID_INFO[drive]['name']]:
                                drive_exclusions[self.DRIVE_VID_INFO[drive]['name']].remove(share_name)

                            # Add new exclusions to list
                            drive_exclusions[self.DRIVE_VID_INFO[drive]['name']].extend([os.path.join(share_name, file) for file in master_exclusions])
                            drive_share_list[drive].append(share_name)

        def recurse_file_list(directory):
            """Get a complete list of files in a directory.

            Args:
                directory (String): The directory to check.

            Returns:
                String[]: The file list.
            """

            file_list = []
            try:
                if len(os.scandir(directory)) > 0:
                    for entry in os.scandir(directory):
                        # For each entry, either add filesize to the total, or recurse into the directory
                        if entry.is_file():
                            file_list.append(entry.path)
                        elif entry.is_dir():
                            file_list.append(entry.path)
                            file_list.extend(recurse_file_list(entry.path))
                else:
                    # No files, so append dir to list
                    file_list.append(entry.path)
            except NotADirectoryError:
                return []
            except PermissionError:
                return []
            except OSError:
                return []
            return file_list

        # For each drive in file list buffer, recurse into each directory and build a complete file list
        all_drive_files = {drive['name']: [] for drive in master_drive_list}
        for drive, files in all_drive_files_buffer.items():
            for file in files:
                all_drive_files[drive].extend(recurse_file_list(file))

        def build_delta_file_list(drive, path, shares, exclusions):
            """Get lists of files to delete and replace from the destination drive, that no longer
            exist in the source, or have changed.

            Args:
                drive (String): The drive to check.
                path (String): The path to check.
                shares (String[]): The list of shares to check.
                exclusions (String[]): The list of files and folders to exclude.

            Returns:
                {
                    'delete' (tuple(String, int)[]): The list of files and filesizes for deleting.
                    'replace' (tuple(String, int, int)[]): The list of files and source/dest filesizes for replacement.
                }
            """

            special_ignore_list = [self.BACKUP_CONFIG_DIR, '$RECYCLE.BIN', 'System Volume Information']
            file_list = {
                'delete': [],
                'replace': []
            }
            try:
                shares_to_process = [share for share in shares if share == path or path.find(share + os.path.sep) == 0]

                for entry in os.scandir(os.path.join(drive, path)):
                    stub_path = entry.path[len(drive):].strip(os.path.sep)

                    # For each entry, either add filesize to the total, or recurse into the directory
                    if entry.is_file():
                        file_stat = entry.stat()

                        if (stub_path.find(os.path.sep) == -1  # Files should not be on root of drive
                                # or not os.path.isfile(source_path)  # File doesn't exist in source, so delete it
                                or stub_path in exclusions  # File is excluded from drive
                                or len(shares_to_process) == 0):  # File should only count if dir is share or child, not parent
                            file_list['delete'].append((drive, stub_path, file_stat.st_size))
                            self.update_file_detail_list_fn('delete', entry.path)
                        else:  # File is in share on destination drive
                            target_share = max(shares_to_process, key=len)
                            path_slug = stub_path[len(target_share):].strip(os.path.sep)
                            share_path = self.get_share_source_path(target_share)

                            source_path = os.path.join(share_path, path_slug)

                            if os.path.isfile(source_path):  # File exists on source
                                if (file_stat.st_mtime != os.path.getmtime(source_path)  # Existing file is older than source
                                        or file_stat.st_size != os.path.getsize(source_path)):  # Existing file is different size than source
                                    # If existing dest file is not same time as source, it needs to be replaced
                                    file_list['replace'].append((drive, target_share, path_slug, os.path.getsize(source_path), file_stat.st_size))
                                    self.update_file_detail_list_fn('copy', entry.path)
                            else:  # File doesn't exist on source, so delete it
                                file_list['delete'].append((drive, stub_path, file_stat.st_size))
                                self.update_file_detail_list_fn('delete', entry.path)
                    elif entry.is_dir():
                        found_share = False

                        for item in shares:
                            path_slug = stub_path[len(item):].strip(os.path.sep)
                            share_path = self.get_share_source_path(item)
                            source_path = os.path.join(share_path, path_slug)

                            if (stub_path == item  # Dir is share, so it stays
                                    or (stub_path.find(item + os.path.sep) == 0 and os.path.isdir(source_path))  # Dir is subdir inside share, and it exists in source
                                    or item.find(stub_path + os.path.sep) == 0):  # Dir is parent directory of a share we're copying, so it stays
                                # Recurse into the share
                                new_list = build_delta_file_list(drive, stub_path, shares, exclusions)
                                file_list['delete'].extend(new_list['delete'])
                                file_list['replace'].extend(new_list['replace'])
                                found_share = True
                                break

                        if not found_share and stub_path not in special_ignore_list and stub_path not in exclusions:
                            # Directory isn't share, or part of one, and isn't a special folder or
                            # exclusion, so delete it
                            file_list['delete'].append((drive, stub_path, get_directory_size(entry.path)))
                            self.update_file_detail_list_fn('delete', entry.path)
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
            return file_list

        def build_new_file_list(drive, path, shares, exclusions):
            """Get lists of files to copy to the destination drive, that only exist on the
            source.

            Args:
                drive (String): The drive to check.
                path (String): The path to check.
                shares (String[]): The list of shares the drive should contain.
                exclusions (String[]): The list of files and folders to exclude.

            Returns:
                {
                    'new' (tuple(String, int)[]): The list of file destinations and filesizes to copy.
                }
            """

            def scan_share_source_for_new_files(drive, share, path, exclusions, all_shares):
                """Get lists of files to copy to the destination drive from a given share.

                Args:
                    drive (String): The drive to check.
                    share (String): The share to check.
                    path (String): The path to check.
                    exclusions (String[]): The list of files and folders to exclude.
                    all_shares (String[]): The list of shares the drive should contain, to
                        avoid recursing into split shares.

                Returns:
                    {
                        'new' (tuple(String, int)[]): The list of file destinations and filesizes to copy.
                    }
                """

                file_list = {
                    'new': []
                }

                try:
                    share_path = self.get_share_source_path(share)
                    source_path = os.path.join(share_path, path)

                    # Check if directory has files
                    if len(os.listdir(source_path)) > 0:
                        for entry in os.scandir(source_path):
                            stub_path = entry.path[len(share_path):].strip(os.path.sep)
                            exclusion_stub_path = os.path.join(share, stub_path)
                            target_path = os.path.join(drive, share, stub_path)

                            # For each entry, either add filesize to the total, or recurse into the directory
                            if entry.is_file():
                                if (not os.path.isfile(target_path)  # File doesn't exist in destination drive
                                        and exclusion_stub_path not in exclusions):  # File isn't part of drive exclusion
                                    file_list['new'].append((drive, share, stub_path, entry.stat().st_size))
                                    self.update_file_detail_list_fn('copy', target_path)
                            elif entry.is_dir():
                                # Avoid recursing into any split share directories and double counting files
                                if exclusion_stub_path not in all_shares:
                                    if os.path.isdir(target_path):
                                        # If exists on dest, recurse into it
                                        new_list = scan_share_source_for_new_files(drive, share, stub_path, exclusions, all_shares)
                                        file_list['new'].extend(new_list['new'])
                                        # break
                                    elif exclusion_stub_path not in exclusions:
                                        # Path doesn't exist on dest, so add to list if not excluded
                                        new_list = scan_share_source_for_new_files(drive, share, stub_path, exclusions, all_shares)
                                        file_list['new'].extend(new_list['new'])
                                        # break
                    elif not os.path.isdir(os.path.join(drive, share, path)):
                        # If no files in folder on source, create empty folder in destination
                        return {
                            'new': [(drive, share, path, get_directory_size(os.path.join(source_path, path)))]
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
                return file_list

            file_list = {
                'new': []
            }

            for share in shares:
                file_list['new'].extend(scan_share_source_for_new_files(drive, share, path, exclusions, shares)['new'])

            return file_list

        # Build list of files/dirs to delete and replace
        self.delete_file_list = {}
        self.replace_file_list = {}
        self.new_file_list = {}
        purge_command_list = []
        copy_command_list = []
        display_purge_command_list = []
        display_copy_command_list = []
        for drive, shares in drive_share_list.items():
            modified_file_list = build_delta_file_list(self.DRIVE_VID_INFO[drive]['name'], '', shares, drive_exclusions[self.DRIVE_VID_INFO[drive]['name']])

            delete_items = modified_file_list['delete']
            if len(delete_items) > 0:
                self.delete_file_list[self.DRIVE_VID_INFO[drive]['name']] = delete_items
                file_delete_list = [os.path.join(drive, file) for drive, file, size in delete_items]

                display_purge_command_list.append({
                    'enabled': True,
                    'type': 'fileList',
                    'drive': self.DRIVE_VID_INFO[drive]['name'],
                    'size': sum([size for drive, file, size in delete_items]),
                    'fileList': file_delete_list,
                    'mode': 'delete'
                })

                purge_command_list.append({
                    'displayIndex': len(display_purge_command_list) + 1,
                    'type': 'fileList',
                    'drive': self.DRIVE_VID_INFO[drive]['name'],
                    'fileList': file_delete_list,
                    'payload': delete_items,
                    'mode': 'delete'
                })

            # Build list of files to replace
            replace_items = modified_file_list['replace']
            replace_items.sort(key=lambda x: x[1])
            if len(replace_items) > 0:
                self.replace_file_list[self.DRIVE_VID_INFO[drive]['name']] = replace_items
                file_replace_list = [os.path.join(drive, share, file) for drive, share, file, source_size, dest_size in replace_items]

                display_copy_command_list.append({
                    'enabled': True,
                    'type': 'fileList',
                    'drive': self.DRIVE_VID_INFO[drive]['name'],
                    'size': sum([source_size for drive, share, file, source_size, dest_size in replace_items]),
                    'fileList': file_replace_list,
                    'mode': 'replace'
                })

                copy_command_list.append({
                    'displayIndex': len(display_purge_command_list) + 1,
                    'type': 'fileList',
                    'drive': self.DRIVE_VID_INFO[drive]['name'],
                    'fileList': file_replace_list,
                    'payload': replace_items,
                    'mode': 'replace'
                })

            # Build list of new files to copy
            new_items = build_new_file_list(self.DRIVE_VID_INFO[drive]['name'], '', shares, drive_exclusions[self.DRIVE_VID_INFO[drive]['name']])['new']
            if len(new_items) > 0:
                self.new_file_list[self.DRIVE_VID_INFO[drive]['name']] = new_items
                file_copy_list = [os.path.join(drive, share, file) for drive, share, file, size in new_items]

                display_copy_command_list.append({
                    'enabled': True,
                    'type': 'fileList',
                    'drive': self.DRIVE_VID_INFO[drive]['name'],
                    'size': sum([size for drive, share, file, size in new_items]),
                    'fileList': file_copy_list,
                    'mode': 'copy'
                })

                copy_command_list.append({
                    'displayIndex': len(display_purge_command_list) + 1,
                    'type': 'fileList',
                    'drive': self.DRIVE_VID_INFO[drive]['name'],
                    'fileList': file_copy_list,
                    'payload': new_items,
                    'mode': 'copy'
                })

        # Gather and summarize totals for analysis summary
        show_file_info = []
        for i, drive in enumerate(drive_share_list.keys()):
            file_summary = []
            drive_total = {
                'running': 0,
                'delta': 0,
                'delete': 0,
                'replace': 0,
                'copy': 0,
                'new': 0
            }

            if self.DRIVE_VID_INFO[drive]['name'] in self.delete_file_list.keys():
                drive_total['delete'] = sum([size for drive, file, size in self.delete_file_list[self.DRIVE_VID_INFO[drive]['name']]])

                drive_total['running'] -= drive_total['delete']
                self.totals['delta'] -= drive_total['delete']

                file_summary.append(f"Deleting {len(self.delete_file_list[self.DRIVE_VID_INFO[drive]['name']])} files ({human_filesize(drive_total['delete'])})")

            if self.DRIVE_VID_INFO[drive]['name'] in self.replace_file_list.keys():
                drive_total['replace'] = sum([source_size for drive, share, file, source_size, dest_size in self.replace_file_list[self.DRIVE_VID_INFO[drive]['name']]])

                drive_total['running'] += drive_total['replace']
                drive_total['copy'] += drive_total['replace']
                drive_total['delta'] += sum([source_size - dest_size for drive, share, file, source_size, dest_size in self.replace_file_list[self.DRIVE_VID_INFO[drive]['name']]])

                file_summary.append(f"Updating {len(self.replace_file_list[self.DRIVE_VID_INFO[drive]['name']])} files ({human_filesize(drive_total['replace'])})")

            if self.DRIVE_VID_INFO[drive]['name'] in self.new_file_list.keys():
                drive_total['new'] = sum([size for drive, share, file, size in self.new_file_list[self.DRIVE_VID_INFO[drive]['name']]])

                drive_total['running'] += drive_total['new']
                drive_total['copy'] += drive_total['new']
                drive_total['delta'] += drive_total['new']

                file_summary.append(f"{len(self.new_file_list[self.DRIVE_VID_INFO[drive]['name']])} new files ({human_filesize(drive_total['new'])})")

            # Increment master totals
            # Double copy total to account for both copy and verify operations
            self.totals['master'] += 2 * drive_total['copy'] + drive_total['delete']
            self.totals['delete'] += drive_total['delete']
            self.totals['delta'] += drive_total['delta']

            if len(file_summary) > 0:
                show_file_info.append((self.DRIVE_VID_INFO[drive]['name'], '\n'.join(file_summary)))

        self.analysis_summary_display_fn(
            title='Files',
            payload=show_file_info
        )

        # Concat both lists into command list
        self.command_list = [cmd for cmd in purge_command_list]
        self.command_list.extend([cmd for cmd in copy_command_list])

        # Concat lists into display command list
        display_command_list = [cmd for cmd in display_purge_command_list]
        display_command_list.extend([cmd for cmd in display_copy_command_list])

        # Fix display index on command list
        for i, cmd in enumerate(self.command_list):
            self.command_list[i]['displayIndex'] = i

        self.analysis_summary_display_fn(
            title='Summary',
            payload=[(self.DRIVE_VID_INFO[drive]['name'], '\n'.join(shares), drive in connected_vid_list) for drive, shares in drive_share_list.items()]
        )

        self.display_backup_command_info_fn(display_command_list)

        self.analysis_valid = True

        if not self.CLI_MODE:
            self.update_ui_component_fn(Status.UPDATEUI_STATUS_BAR, Status.BACKUP_READY_FOR_BACKUP)
            self.update_ui_component_fn(Status.UPDATEUI_BACKUP_BTN, {'state': 'normal'})
            self.update_ui_component_fn(Status.UPDATEUI_ANALYSIS_BTN, {'state': 'normal'})

            # URGENT: Add halt flag check for unlocking tree selection
            if False:
                self.update_ui_component_fn(Status.UNLOCK_TREE_SELECTION)

            self.progress.stop_indeterminate()

        self.analysis_running = False

    # TODO: Make changes to existing @config check the existing for missing @drives, and delete the config file from drives we unselected if there's multiple drives in a config
    # TODO: If a @drive @config is overwritten with a new config file, due to the drive
    # being configured for a different backup, then we don't want to delete that file
    # In that case, the config file should be ignored. Thus, we need to delete configs
    # on unselected drives only if the config file on the drive we want to delete matches
    # the config on selected drives
    # TODO: When @drive @selection happens, drives in the @config should only be selected if the config on the other drive matches. If it doesn't don't select it by default, and warn about a conflict.
    def write_config_to_disks(self):
        """Write the current running backup config to config files on the drives."""

        if self.config['sources'] and self.config['destinations']:
            share_list = ','.join([item['dest_name'] for item in self.config['sources']])
            raw_vid_list = [drive['vid'] for drive in self.config['destinations']]
            raw_vid_list.extend(self.config['missing_drives'].keys())
            vid_list = ','.join(raw_vid_list)

            # For each drive letter connected, get drive info, and write file
            for drive in self.config['destinations']:
                # If config exists on drives, back it up first
                if os.path.isfile(os.path.join(drive['name'], self.BACKUP_CONFIG_DIR, self.BACKUP_CONFIG_FILE)):
                    shutil.move(os.path.join(drive['name'], self.BACKUP_CONFIG_DIR, self.BACKUP_CONFIG_FILE), os.path.join(drive['name'], self.BACKUP_CONFIG_DIR, self.BACKUP_CONFIG_FILE + '.old'))

                drive_config_file = Config(os.path.join(self.DRIVE_VID_INFO[drive['vid']]['name'], self.BACKUP_CONFIG_DIR, self.BACKUP_CONFIG_FILE))

                # Write shares and VIDs to config file
                drive_config_file.set('selection', 'sources', share_list)
                drive_config_file.set('selection', 'vids', vid_list)

                # Write info for each drive to its own section
                for cur_drive in self.config['destinations']:
                    drive_config_file.set(cur_drive['vid'], 'vid', cur_drive['vid'])
                    drive_config_file.set(cur_drive['vid'], 'serial', cur_drive['serial'])
                    drive_config_file.set(cur_drive['vid'], 'capacity', cur_drive['capacity'])

                # Write info for missing drives
                for drive_vid, capacity in self.config['missing_drives'].items():
                    drive_config_file.set(drive_vid, 'vid', drive_vid)
                    drive_config_file.set(drive_vid, 'serial', 'Unknown')
                    drive_config_file.set(drive_vid, 'capacity', capacity)

    def run(self):
        """Once the backup analysis is run, and drives and shares are selected, run the backup.

        This function is run in a new thread, but is only run if the backup config is valid.
        If sanity_check() returns False, the backup isn't run.
        """

        self.backup_running = True

        if not self.analysis_valid or not self.sanity_check():
            return

        if not self.CLI_MODE:
            self.update_ui_component_fn(Status.UPDATEUI_BACKUP_START)
            self.update_ui_component_fn(Status.LOCK_TREE_SELECTION)
            self.progress.set(0)
            self.progress.set_max(self.totals['master'])

            for cmd in self.command_list:
                self.cmd_info_blocks[cmd['displayIndex']]['state'].configure(text='Pending', fg=self.uicolor.PENDING)
                if cmd['type'] == 'fileList':
                    self.cmd_info_blocks[cmd['displayIndex']]['currentFileResult'].configure(text='Pending', fg=self.uicolor.PENDING)
                self.cmd_info_blocks[cmd['displayIndex']]['lastOutResult'].configure(text='Pending', fg=self.uicolor.PENDING)

        # Write config file to drives
        self.write_config_to_disks()

        self.totals['running'] = 0
        self.totals['buffer'] = 0
        self.totals['progressBar'] = 0

        timer_started = False

        for cmd in self.command_list:
            if cmd['type'] == 'fileList':
                if not self.CLI_MODE:
                    self.cmd_info_blocks[cmd['displayIndex']]['state'].configure(text='Running', fg=self.uicolor.RUNNING)

                if not timer_started:
                    timer_started = True
                    self.backup_start_time = datetime.now()

                    self.thread_manager.start(ThreadManager.KILLABLE, name='backupTimer', target=self.start_backup_timer_fn)

                if cmd['mode'] == 'delete':
                    for drive, file, size in cmd['payload']:
                        if self.thread_manager.threadlist['Backup']['killFlag']:
                            break

                        src = os.path.join(drive, file)

                        gui_options = {
                            'displayIndex': cmd['displayIndex']
                        }

                        self.do_del_fn(src, size, gui_options)

                        # If file hash was in list, remove it, and write changes to file
                        if file in self.file_hashes[drive].keys():
                            del self.file_hashes[drive][file]

                            drive_hash_file_path = os.path.join(drive, self.BACKUP_CONFIG_DIR, self.BACKUP_HASH_FILE)
                            with open(drive_hash_file_path, 'wb') as f:
                                hash_list = {'/'.join(file_name.split(os.path.sep)): hash_val for file_name, hash_val in self.file_hashes[drive].items()}
                                pickle.dump(hash_list, f)
                if cmd['mode'] == 'replace':
                    for drive, share, file, source_size, dest_size in cmd['payload']:
                        if self.thread_manager.threadlist['Backup']['killFlag']:
                            break

                        share_path = self.get_share_source_path(share)

                        src = os.path.join(share_path, file)
                        dest = os.path.join(drive, share, file)

                        gui_options = {
                            'displayIndex': cmd['displayIndex']
                        }

                        file_hashes = self.do_copy_fn(src, dest, drive, gui_options)
                        self.file_hashes[drive].update(file_hashes)

                        # Write updated hash file to drive
                        drive_hash_file_path = os.path.join(drive, self.BACKUP_CONFIG_DIR, self.BACKUP_HASH_FILE)
                        with open(drive_hash_file_path, 'wb') as f:
                            hash_list = {'/'.join(file_name.split(os.path.sep)): hash_val for file_name, hash_val in self.file_hashes[drive].items()}
                            pickle.dump(hash_list, f)
                elif cmd['mode'] == 'copy':
                    for drive, share, file, size in cmd['payload']:
                        if self.thread_manager.threadlist['Backup']['killFlag']:
                            break

                        share_path = self.get_share_source_path(share)

                        src = os.path.join(share_path, file)
                        dest = os.path.join(drive, share, file)

                        gui_options = {
                            'displayIndex': cmd['displayIndex']
                        }

                        file_hashes = self.do_copy_fn(src, dest, drive, gui_options)
                        self.file_hashes[drive].update(file_hashes)

                        # Write updated hash file to drive
                        drive_hash_file_path = os.path.join(drive, self.BACKUP_CONFIG_DIR, self.BACKUP_HASH_FILE)
                        with open(drive_hash_file_path, 'wb') as f:
                            hash_list = {'/'.join(file_name.split(os.path.sep)): hash_val for file_name, hash_val in self.file_hashes[drive].items()}
                            pickle.dump(hash_list, f)

            if self.thread_manager.threadlist['Backup']['killFlag'] and self.totals['running'] < self.totals['master']:
                if not self.CLI_MODE:
                    self.cmd_info_blocks[cmd['displayIndex']]['state'].configure(text='Aborted', fg=self.uicolor.STOPPED)
                    self.cmd_info_blocks[cmd['displayIndex']]['lastOutResult'].configure(text='Aborted', fg=self.uicolor.STOPPED)
                else:
                    print(f"{bcolor.FAIL}Backup aborted by user{bcolor.ENDC}")
                break
            else:
                if not self.CLI_MODE:
                    self.cmd_info_blocks[cmd['displayIndex']]['state'].configure(text='Done', fg=self.uicolor.FINISHED)
                    self.cmd_info_blocks[cmd['displayIndex']]['lastOutResult'].configure(text='Done', fg=self.uicolor.FINISHED)
                else:
                    print(f"{bcolor.OKGREEN}Backup finished{bcolor.ENDC}")

        self.thread_manager.kill('backupTimer')

        if not self.CLI_MODE:
            self.update_ui_component_fn(Status.UPDATEUI_BACKUP_END)
            self.update_ui_component_fn(Status.UNLOCK_TREE_SELECTION)
        self.backup_running = False

    def get_backup_start_time(self):
        """
        Returns:
            datetime: The time the backup started. (default 0)
        """

        if self.backup_start_time:
            return self.backup_start_time
        else:
            return 0

    def is_running(self):
        """
        Returns:
            bool: Whether or not the backup is actively running something.
        """

        return self.analysis_running or self.backup_running
