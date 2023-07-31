import os
import itertools
from datetime import datetime
import shutil
import pickle
import logging
import math
import time

from bin.fileutils import FileUtils, human_filesize, get_directory_size, do_delete, do_copy
from bin.config import Config
from bin.status import Status


class Backup:
    # 0xf - Kill modes
    KILL_ALL = 0xf0
    KILL_ANALYSIS = 0xf1
    KILL_BACKUP = 0xf2

    COMMAND_TYPE_FILE_LIST = 'file_list'
    COMMAND_FILE_LIST = 'file_list'

    def __init__(self, config: dict, backup_config_dir, backup_config_file,
                 analysis_pre_callback_fn, analysis_callback_fn,
                 backup_callback_fn):
        """Configure a backup to be run on a set of drives.

        Args:
            config (dict): The backup config to be processed.
            backup_config_dir (String): The directory to store backup configs on each drive.
            backup_config_file (String): The file to store backup configs on each drive.
            analysis_pre_callback_fn (def): The callback function to call before analysis.
            analysis_callback_fn (def): The callback function to call post analysis.
            backup_callback_fn (def): The callback function to call post backup.
        """

        self.progress = {
            'analysis': [],  # (list, file path)
            'buffer': {
                'copied': 0,
                'total': 0,
                'display_filename': None,
                'operation': None,
                'display_index': None
            },
            'command_display_index': None,  # The current command within a running backup
            'current': 0,  # (int) Current progress
            'current_file': None,  # (filename, filesize, operation, display index)
            'files': [],  # (filename, filesize, operation, display index)
            'since_last_update': {  # Buffer for tracking delta UI updates
                'analysis': [],  # (list, file path)
                'files': []
            },
            'total': 0,  # (int) Total for calculating progress percentage
            'delete_total': 0
        }

        self.confirm_wipe_existing_drives = False
        self.analysis_valid = False
        self.analysis_started = False
        self.analysis_running = False
        self.backup_running = False
        self.backup_start_time = datetime.now()
        self.status = Status.BACKUP_IDLE

        self.command_list = []
        self.delete_file_list = {}
        self.replace_file_list = {}
        self.new_file_list = {}

        self.config = config
        self.DRIVE_VID_INFO = {drive['vid']: drive for drive in config['destinations']}
        self.SOURCE_NAME_PATH_INFO = {source['dest_name']: source['path'] for source in config['sources']}

        self.BACKUP_CONFIG_DIR = backup_config_dir
        self.BACKUP_CONFIG_FILE = backup_config_file
        self.BACKUP_HASH_FILE = 'hashes.pkl'

        self.SPECIAL_IGNORE_LIST = [self.BACKUP_CONFIG_DIR, '$RECYCLE.BIN', 'System Volume Information']

        self.file_hashes = {drive['name']: {} for drive in self.config['destinations']}

        self.analysis_killed = False
        self.run_killed = False

        self.analysis_pre_callback_fn = analysis_pre_callback_fn
        self.analysis_callback_fn = analysis_callback_fn
        self.backup_callback_fn = backup_callback_fn

    def get_kill_flag(self) -> bool:
        """Get the kill flag status for the backup.

        Returns:
            bool: Whether or not the backup run has been killed.
        """

        return self.run_killed

    def set_working_file(self, filename=None, size: int = None, operation=None, display_index: int = None):
        """Handle updating the UI before copying a file.

        Args:
            filename (String): The filename of the destination file (optional).
            size (int): The filesize of the working file (optional).
            operation (int): The status code for the file operation (optional).
            display_index (int): The index to display the item in the GUI (optional).
        """

        # TODO: Replace current_file with buffer in self.progress
        self.progress['current_file'] = (filename, size, operation, display_index)

    def do_del_fn(self, filename, size: int, display_index: int = None):
        """Start a do_delete() call, and report to the GUI.

        Args:
            filename (String): The file or folder to delete.
            size (int): The size in bytes of the file or folder.
            display_index (int): The index to display the item in the GUI (optional).
        """

        if self.run_killed or not os.path.exists(filename):
            return

        self.set_working_file(filename, size, Status.FILE_OPERATION_DELETE, display_index)
        do_delete(filename=filename)

        if not os.path.exists(filename):
            status = Status.FILE_OPERATION_SUCCESS
        else:
            status = Status.FILE_OPERATION_FAILED

        self.update_copy_lists(status, (filename, size, Status.FILE_OPERATION_DELETE, display_index))

    def set_copy_progress(self, copied, total, display_filename=None, operation=None, display_index: int = None):
        """Set the copy progress of a transfer.

        Args:
            copied (int): the number of bytes copied.
            total (int): The total file size.
            display_filename (String): The filename to display inthe GUI (optional).
            operation (int): The mode to display the progress in (optional).
            display_index (int): The index to display the item in the GUI (optional).
        """

        self.progress['buffer']['copied'] = copied
        self.progress['buffer']['total'] = total
        self.progress['buffer']['display_filename'] = display_filename
        self.progress['buffer']['operation'] = operation
        self.progress['buffer']['display_index'] = display_index

    def update_copy_lists(self, status, file):
        """Add the copied file to the correct list.

        Args:
            status (int): The Status of the file copy state.
            file (tuple): The file to add to the list.
        """

        self.progress['buffer']['copied'] = 0
        self.progress['since_last_update']['files'].append({
            'file': file,
            'success': status == Status.FILE_OPERATION_SUCCESS,
            'timestamp': time.time()
        })

    def do_copy_fn(self, src, dest, drive_path, display_index: int = None) -> dict:
        """Start a do_copy() call and report to the GUI.

        Args:
            src (String): The source to copy.
            dest (String): The destination to copy to.
            drive_path (String): The path of the destination drive to copy to.
            display_index (int): The index to display the item in the GUI (optional).

        Return:
            dict: The hash list returned by do_copy().
        """

        # FIXME: Backup error log is not being appended to from fd_callback

        return do_copy(
            src=src,
            dest=dest,
            drive_path=drive_path,
            pre_callback=self.set_working_file,
            prog_callback=lambda c, t, op: self.set_copy_progress(
                copied=c,
                total=t,
                display_filename=dest,
                operation=op,
                display_index=display_index
            ),
            display_index=display_index,
            fd_callback=self.update_copy_lists,
            get_backup_killflag=self.get_kill_flag
        )

    def sanity_check(self) -> bool:
        """Check to make sure everything is correct before a backup.

        Before running a backup, or an analysis, both sources and drives need to be
        selected, and the drive space on selected drives needs to be larger than the
        total size of the selected sources.

        Returns:
            bool: True if conditions are good, False otherwise.
        """

        # Both file sources, and destinations must be defined
        if not self.config['destinations'] or not self.config['sources']:
            return False

        source_total = 0
        drive_total = 0

        # Sources and destinations need identifiers
        if self.config['source_mode'] in [Config.SOURCE_MODE_MULTI_DRIVE, Config.SOURCE_MODE_MULTI_PATH] and [source for source in self.config['sources'] if not source['dest_name']]:
            return False
        if self.config['dest_mode'] == Config.DEST_MODE_PATHS and [drive for drive in self.config['destinations'] if not drive['vid']]:
            return False

        # Source sizes must all be known
        if any([source['size'] is None for source in self.config['sources']]):
            return False

        source_total = sum((source['size'] for source in self.config['sources']))
        drive_total = sum((drive['capacity'] for drive in self.config['destinations']))
        config_total = drive_total + sum((size for drive, size in self.config['missing_drives'].items()))

        # Source total must be less than drive total if there are no missing drives,
        # or if there is an existing config, the source total must be less than the config total
        if not (len(self.config['missing_drives']) == 0 and source_total < drive_total) and not (source_total < config_total and self.config['splitMode']):
            return

        return True

    def get_source_source_path(self, source) -> str:
        """Convert a source name into a source path.

        Args:
            source (String): The source to convert.

        Returns:
            String: The source path for the given source.
        """

        source_base = source.split(os.path.sep)[0]
        source_slug = source[len(source_base):].strip(os.path.sep)
        source_base_path = self.SOURCE_NAME_PATH_INFO[source_base]
        source_full_path = os.path.join(source_base_path, source_slug).strip(os.path.sep)

        return source_full_path

    # IDEA: When we ignore other stuff on the drives, and delete it, have a dialog popup that summarizes what's being deleted, and ask the user to confirm
    def analyze(self):
        """Analyze the list of selected sources and drives and figure out how to split files.

        Args:
            sources (dict[]): The list of selected sources.
                name (String): The name of the source.
                size (int): The size in bytes of the source.
            drives (tuple(String)): The list of selected drives.

        This function is run in a new thread, but is only run if the backup config is valid.
        If sanity_check() returns False, the analysis isn't run.
        """

        # Sanity check for space requirements
        if not self.sanity_check():
            return

        self.analysis_killed = False
        self.analysis_running = True
        self.analysis_started = True
        self.status = Status.BACKUP_ANALYSIS_RUNNING

        self.analysis_pre_callback_fn()

        self.progress['current'] = 0
        self.progress['total'] = 0

        source_info = {source['dest_name']: source['size'] for source in self.config['sources']}
        all_source_info = source_info.copy()

        def scan_hash_files() -> dict:
            """Scan hash files, and build hash list for files.

            Returns:
                dict: The hash data to be used during analysis.
                    Key (String): The drive being referenced.
                    Value (dict): The hash list:
                        Key (String): The filename to hash.
                        Value (String): The hash of the file.
            """

            hash_data = {drive['name']: {} for drive in self.config['destinations']}
            bad_hash_files = []

            for drive in self.config['destinations']:
                drive_hash_file_path = os.path.join(drive['name'], self.BACKUP_CONFIG_DIR, self.BACKUP_HASH_FILE)

                if os.path.isfile(drive_hash_file_path):
                    write_trimmed_changes = False
                    with open(drive_hash_file_path, 'rb') as f:
                        try:
                            # Load hash list, and filter out ignored folders
                            hash_list = pickle.load(f)
                            new_hash_list = {}
                            for file_name, hash_val in hash_list.items():
                                filename_chunks = file_name.split('/')

                                if filename_chunks[0] not in self.SPECIAL_IGNORE_LIST:
                                    if os.path.isfile(os.path.join(drive['name'], file_name)):
                                        new_hash_list[os.path.join(filename_chunks)]: hash_val

                            # If trimmed list is shorter, new changes have to be written to the file
                            if len(new_hash_list) < len(hash_list):
                                write_trimmed_changes = True

                            hash_data[drive['name']] = new_hash_list
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
            for file in bad_hash_files:
                with open(file, 'wb') as f:
                    pickle.dump({}, f)

            return hash_data

        # Get hash list for all drives
        self.file_hashes = scan_hash_files()

        drive_info = []
        drive_source_list = {}
        master_drive_list = [drive for drive in self.config['destinations']]
        master_drive_list.extend([{'vid': vid, 'capacity': capacity} for vid, capacity in self.config['missing_drives'].items()])
        connected_vid_list = [drive['vid'] for drive in self.config['destinations']]
        for i, drive in enumerate(master_drive_list):
            if self.analysis_killed:
                break

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

            # Enumerate list for tracking what sources go where
            drive_source_list[drive['vid']] = set()

        # For each drive, smallest first, filter list of sources to those that fit
        drive_info.sort(key=lambda x: x['free'])

        all_drive_files_buffer = {drive['name']: set() for drive in master_drive_list}

        SOURCE_LIST_CHUNK_SIZE = 15

        for i, drive in enumerate(drive_info):
            # Get list of sources small enough to fit on drive
            total_small_sources = {source: size for source, size in source_info.items() if size <= drive['free']}
            SOURCE_LIST_LENGTH = len(total_small_sources)

            # Sort sources by largest first
            total_small_sources = sorted(total_small_sources.items(), key=lambda x: x[1], reverse=True)

            # Since the list of files is truncated to prevent an unreasonably large
            # number of combinations to check, we need to keep processing the file list
            # in chunks to make sure we check if all files can be fit on one drive
            sources_that_fit_on_dest = set()
            small_source_list = {}
            processed_small_sources = []
            processed_source_size = 0

            for chunk in range(0, math.ceil(SOURCE_LIST_LENGTH / SOURCE_LIST_CHUNK_SIZE)):
                if self.analysis_killed:
                    break

                # Trim the list of small files to those that aren't already processed
                small_source_list = {source: size for (source, size) in total_small_sources if source not in processed_small_sources}

                LIST_CHUNK_MIN = chunk * SOURCE_LIST_CHUNK_SIZE
                LIST_CHUNK_MAX = min((chunk + 1) * SOURCE_LIST_CHUNK_SIZE, SOURCE_LIST_LENGTH)

                # Truncate to prevent unreasonably large number of combinations
                trimmed_small_source_list = {source[0]: source[1] for source in total_small_sources[LIST_CHUNK_MIN:LIST_CHUNK_MAX]}

                # Try every combination of sources that fit to find result that uses most of that drive
                largest_sum = 0
                largest_set = set()
                for n in range(1, len(trimmed_small_source_list) + 1):
                    for subset in itertools.combinations(trimmed_small_source_list.keys(), n):
                        combination_total = sum(trimmed_small_source_list[source] for source in subset)

                        if (combination_total > largest_sum and combination_total <= drive['free']):
                            largest_sum = combination_total
                            largest_set = subset

                sources_that_fit_on_dest.update({source for source in largest_set})
                remaining_small_sources = {source[0]: source[1] for source in small_source_list if source not in sources_that_fit_on_dest}
                processed_small_sources.extend([source for source in trimmed_small_source_list.keys()])
                source_info = {source: size for (source, size) in source_info.items() if source not in sources_that_fit_on_dest}

                # Subtract file size of each batch of files from the free space on the drive so the next batch sorts properly
                processed_source_size += sum((size for (source, size) in small_source_list.items() if source in largest_set))

            if self.analysis_killed:
                break

            # If not all sources fit on smallest drive at once (at least one source has to be put
            # on the next largest drive), check free space on next largest drive
            if len(sources_that_fit_on_dest) < len(small_source_list) and i < (len(drive_info) - 1):
                not_fit_total = sum(size for size in remaining_small_sources.values())
                next_drive = drive_info[i + 1]
                next_drive_free_space = next_drive['free'] - not_fit_total

                # If free space on next drive is less than total capacity of current drive, it
                # becomes more efficient to skip current drive, and put all sources on the next
                # drive instead.
                # This applies only if they can all fit on the next drive. If they have to be
                # split across multiple drives after moving them to a larger drive, then it's
                # easier to fit what we can on the small drive, to leave the larger drives
                # available for larger sources
                if not_fit_total <= next_drive['free']:
                    total_small_source_space = sum(size for size in small_source_list.values())
                    if next_drive_free_space < drive['free'] and total_small_source_space <= next_drive['free']:
                        # Next drive free space less than total on current, so it's optimal to store on next drive instead
                        drive_source_list[next_drive['vid']].update({source for source in small_source_list.keys()})  # All small sources on next drive
                    else:
                        # Better to leave on current, but overflow to next drive
                        drive_source_list[drive['vid']].update(sources_that_fit_on_dest)  # Sources that fit on current drive
                        drive_source_list[next_drive['vid']].update({source for source in small_source_list.keys() if source not in sources_that_fit_on_dest})  # Remaining small sources on next drive
                else:
                    # If overflow for next drive is more than can fit on that drive, ignore it, put overflow
                    # back in pool of sources to sort, and put small drive sources only in current drive
                    drive_source_list[drive['vid']].update(sources_that_fit_on_dest)  # Sources that fit on current drive
                    all_drive_files_buffer[drive['name']].update({f"{drive['name']}{source}" for source in sources_that_fit_on_dest})

                    # Put remaining small sources back into pool to work with for next drive
                    source_info.update({source: size for source, size in remaining_small_sources.items()})
            else:
                # Fit all small sources onto drive
                drive_source_list[drive['vid']].update(sources_that_fit_on_dest)

            # Calculate space used by sources, and subtract it from capacity to get free space
            used_space = sum(all_source_info[source] for source in drive_source_list[drive['vid']])
            drive_info[i]['free'] -= used_space

        def split_source(source) -> list:
            """Recurse into a source or directory, and split the contents.

            Args:
                source (String): The source to split.

            Returns:
                dict[]: A list of sources to be split
                    source (String): The source to split
                    files (dict): The list of drive splits.
                        Key (String) is a drive volume ID,
                        Value (String[]) is a list of filenames for a given drive.
                    exclusions (String[]): The list of files to exclude from the split.
            """

            # Enumerate list for tracking what sources go where
            drive_file_list = {drive['vid']: set() for drive in drive_info}

            file_info = {}
            source_path = self.get_source_source_path(source)

            try:
                for entry in os.scandir(source_path):
                    if self.analysis_killed:
                        break
                    if entry.is_file():
                        new_dir_size = entry.stat().st_size
                    elif entry.is_dir():
                        new_dir_size = get_directory_size(entry.path)

                    filename = entry.path[len(source_path):].strip(os.path.sep)
                    file_info[filename] = new_dir_size
            except PermissionError:
                pass

            if self.analysis_killed:
                return []

            # For splitting sources, sort by largest free space first
            drive_info.sort(reverse=True, key=lambda x: x['free'])

            FILE_LIST_CHUNK_SIZE = 15

            for i, drive in enumerate(drive_info):
                # Get list of files small enough to fit on drive
                total_small_files = {file: size for file, size in file_info.items() if size <= drive['free']}
                FILE_LIST_LENGTH = len(total_small_files)

                # Sort files by largest first
                total_small_files = sorted(total_small_files.items(), key=lambda x: x[1], reverse=True)

                # Since the list of files is truncated to prevent an unreasonably large
                # number of combinations to check, we need to keep processing the file list
                # in chunks to make sure we check if all files can be fit on one drive
                files_that_fit_on_drive = set()
                small_file_list = {}
                processed_small_files = []
                processed_file_size = 0

                for chunk in range(0, math.ceil(FILE_LIST_LENGTH / FILE_LIST_CHUNK_SIZE)):
                    if self.analysis_killed:
                        break

                    # Trim the list of small files to those that aren't already processed
                    small_file_list = {file: size for (file, size) in total_small_files.items() if file not in processed_small_files}

                    LIST_CHUNK_MIN = chunk * FILE_LIST_CHUNK_SIZE
                    LIST_CHUNK_MAX = min((chunk + 1) * FILE_LIST_CHUNK_SIZE, FILE_LIST_LENGTH)

                    # Truncate to prevent unreasonably large number of combinations
                    trimmed_small_file_list = {file[0]: file[1] for file in total_small_files[LIST_CHUNK_MIN:LIST_CHUNK_MAX]}

                    # Try every combination of sources that fit to find result that uses most of that drive
                    largest_sum = 0
                    largest_set = []
                    for n in range(1, len(trimmed_small_file_list) + 1):
                        for subset in itertools.combinations(trimmed_small_file_list.keys(), n):
                            combination_total = sum((trimmed_small_file_list[file] for file in subset))

                            if (combination_total > largest_sum and combination_total <= drive['free'] - processed_file_size):
                                largest_sum = combination_total
                                largest_set = subset

                    files_that_fit_on_drive.update({file for file in largest_set})
                    processed_small_files.extend([file for file in trimmed_small_file_list])
                    file_info = {file: size for (file, size) in file_info.items() if file not in largest_set}

                    # Subtract file size of each batch of files from the free space on the drive so the next batch sorts properly
                    processed_file_size += sum((size for (file, size) in small_file_list.items() if file in largest_set))

                if self.analysis_killed:
                    break

                # Assign files to drive, and subtract filesize from free space
                # Since we're sorting by largest free space first, there's no cases to move
                # to a larger drive. This means all files that can fit should be put on the
                # drive they fit on.
                drive_file_list[drive['vid']].update(files_that_fit_on_drive)
                drive_info[i]['free'] -= processed_file_size

            if self.analysis_killed:
                return

            source_split_summary = [{
                'source': source,
                'files': drive_file_list,
                'exclusions': [file for file in file_info]
            }]

            for file in file_info:
                file_path = os.path.join(source, file)
                source_split_summary.extend(split_source(file_path))

            return source_split_summary

        # For sources larger than all drives, recurse into each source
        # source_info contains sources not sorted into drives
        drive_exclusions = {drive['name']: [] for drive in master_drive_list}
        for source in source_info:
            source_path = self.get_source_source_path(source)

            if os.path.exists(source_path) and os.path.isdir(source_path):
                summary = split_source(source)

                if self.analysis_killed:
                    break

                # Build exclusion list for other drives\
                # This is done by "inverting" the file list for each drive into a list of exclusions for other drives
                for split in summary:
                    if self.analysis_killed:
                        break

                    file_list = split['files']

                    for drive_vid, files in file_list.items():
                        # Add files to file list
                        all_drive_files_buffer[self.DRIVE_VID_INFO[drive_vid]['name']].update({os.path.join(split['source'], file) for file in files})

                # Each summary contains a split source, and any split subfolders, starting with
                # the source and recursing into the directories
                for split in summary:
                    if self.analysis_killed:
                        break

                    source_name = split['source']
                    source_files = split['files']
                    source_exclusions = split['exclusions']

                    all_files = source_files.copy()
                    all_files['exclusions'] = source_exclusions

                    # For each drive, gather list of files to be written to other drives, and
                    # use that as exclusions
                    for drive_vid, files in source_files.items():
                        if files:
                            raw_exclusions = all_files.copy()
                            raw_exclusions.pop(drive_vid, None)

                            # Build master full exclusion list
                            master_exclusions = [file for file_list in raw_exclusions.values() for file in file_list]

                            # Remove source if excluded in parent splitting
                            if source_name in drive_exclusions[self.DRIVE_VID_INFO[drive_vid]['name']]:
                                drive_exclusions[self.DRIVE_VID_INFO[drive_vid]['name']].remove(source_name)

                            # Add new exclusions to list
                            drive_exclusions[self.DRIVE_VID_INFO[drive_vid]['name']].extend([os.path.join(source_name, file) for file in master_exclusions])
                            drive_source_list[drive_vid].add(source_name)

            if self.analysis_killed:
                break

        def recurse_file_list(directory) -> set:
            """Get a complete list of files in a directory.

            Args:
                directory (String): The directory to check.

            Returns:
                set: The list of filenames in the directory.
            """

            if self.analysis_killed:
                return set()

            file_list = set()
            try:
                if os.listdir(directory):
                    for entry in os.scandir(directory):
                        # For each entry, add file to list, and recurse into path if directory
                        file_list.add(entry.path)
                        if entry.is_dir():
                            file_list.update(recurse_file_list(entry.path))
                else:
                    # No files, so append dir to list
                    file_list.add(entry.path)
            except (NotADirectoryError, PermissionError, OSError, TypeError):
                return set()
            return file_list

        def build_delta_file_list(drive, path, sources: set, exclusions: list) -> dict:
            """Get lists of files to delete and replace from the destination drive, that no longer
            exist in the source, or have changed.

            Args:
                drive (String): The drive to check.
                path (String): The path to check.
                sources (String[]): The list of sources to check.
                exclusions (String[]): The list of files and folders to exclude.

            Returns:
                dict: The file lists for deleting and replacing.
                    delete (set(tuple)): (drive, path, size).
                    replace (set(tuple)): (drive, source, path, source_path, size).
            """

            file_list = {
                'delete': set(),
                'replace': set()
            }
            try:
                if self.analysis_killed:
                    return file_list

                # Check to see if path to be scanned is a valid folder
                if path.split(os.path.sep)[0] in sources:
                    valid_source = path.split(os.path.sep)[0]
                else:
                    valid_source = None

                # For each file in the path, check things
                for entry in os.scandir(os.path.join(drive, path)):
                    stub_path = entry.path[len(drive):].strip(os.path.sep)

                    # Skip over the config folder, and OS special folders
                    if stub_path in self.SPECIAL_IGNORE_LIST:
                        continue

                    file_stat = entry.stat()

                    # Delete excluded stuff
                    if stub_path in exclusions:
                        if entry.is_dir():
                            calculated_size = get_directory_size(entry.path)
                        else:
                            calculated_size = file_stat.st_size

                        file_list['delete'].add((drive, stub_path, calculated_size))
                        self.progress['since_last_update']['analysis'].append((FileUtils.LIST_TOTAL_DELETE, entry.path))

                    root_path = stub_path.split(os.path.sep)[0]

                    # For each entry, either add filesize to the total, or recurse into the directory
                    if entry.is_dir():  # Path is directory
                        if (root_path in sources and os.path.isdir(self.get_source_source_path(stub_path))  # Dir is source or folder in source, and exists on source
                                or 0 in [item.find(stub_path + os.path.sep) for item in sources]):  # Directory is parent of source, so it stays
                            # Recurse into folder
                            new_list = build_delta_file_list(drive, stub_path, sources, exclusions)
                            file_list['delete'].update(new_list['delete'])
                            file_list['replace'].update(new_list['replace'])
                        else:
                            # Directory isn't a source, or part of one
                            file_list['delete'].add((drive, stub_path, get_directory_size(entry.path)))
                            self.progress['since_last_update']['analysis'].append((FileUtils.LIST_TOTAL_DELETE, entry.path))
                    elif entry.is_file():  # Path is file
                        if (stub_path.find(os.path.sep) == -1  # Files should not be on root of drive
                                or valid_source is None):  # File should only count if dir is source or child, not parent
                            file_list['delete'].add((drive, stub_path, file_stat.st_size))
                            self.progress['since_last_update']['analysis'].append((FileUtils.LIST_TOTAL_DELETE, entry.path))
                        else:  # File is in source on destination drive
                            path_slug = stub_path[len(valid_source):].strip(os.path.sep)
                            source_path = self.get_source_source_path(valid_source)

                            source_path = os.path.join(source_path, path_slug)

                            try:
                                source_stats = os.stat(source_path)
                            except FileNotFoundError:  # Thrown if file doesn't exist
                                # If file doesn't exist on source, delete it
                                file_list['delete'].add((drive, stub_path, file_stat.st_size))
                                self.progress['since_last_update']['analysis'].append((FileUtils.LIST_TOTAL_DELETE, entry.path))
                            else:
                                if (file_stat.st_size != source_stats.st_size  # Existing file is different size than source
                                        or file_stat.st_mtime != source_stats.st_mtime):  # Existing file is older than source
                                    # If existing dest file is not same time as source, it needs to be replaced
                                    file_list['replace'].add((drive, valid_source, path_slug, os.path.getsize(source_path), file_stat.st_size))
                                    self.progress['since_last_update']['analysis'].append((FileUtils.LIST_TOTAL_COPY, entry.path))
            except (NotADirectoryError, PermissionError, OSError):
                return {
                    'delete': set(),
                    'replace': set()
                }
            return file_list

        def build_new_file_list(drive, path, sources: set, exclusions: list) -> dict:
            """Get lists of files to copy to the destination drive, that only exist on the
            source.

            Args:
                drive (String): The drive to check.
                path (String): The path to check.
                sources (String[]): The list of sources the drive should contain.
                exclusions (String[]): The list of files and folders to exclude.

            Returns:
                dict: The file list for new files.
                    new (set(tuple)): (drive, source, path, size).
            """

            def scan_source_source_for_new_files(drive, source, path, exclusions: list, all_sources: set) -> dict:
                """Get lists of files to copy to the destination drive from a given source.

                Args:
                    drive (String): The drive to check.
                    source (String): The source to check.
                    path (String): The path to check.
                    exclusions (String[]): The list of files and folders to exclude.
                    all_sources (set): The list of sources the drive should contain, to
                        avoid recursing into split sources.

                Returns:
                    dict: The file list for new files.
                        new (set(tuple)): (drive, source, path, size).
                """

                file_list = {
                    'new': set()
                }

                try:
                    if self.analysis_killed:
                        return file_list

                    source_path = self.get_source_source_path(source)
                    source_path_len = len(source_path)
                    source_path = os.path.join(source_path, path)

                    # Check if directory has files
                    source_file_list = os.scandir(source_path)
                    for entry in source_file_list:
                        stub_path = entry.path[source_path_len:].strip(os.path.sep)
                        exclusion_stub_path = os.path.join(source, stub_path)

                        # Skip over any exclusions
                        if exclusion_stub_path in exclusions:
                            continue

                        target_path = os.path.join(drive, source, stub_path)

                        if entry.is_dir():  # Entry is directory
                            # Avoid recursing into any split sources and double counting files
                            if exclusion_stub_path in all_sources:
                                continue

                            new_list = scan_source_source_for_new_files(drive, source, stub_path, exclusions, all_sources)
                            file_list['new'].update(new_list['new'])
                        elif not os.path.isfile(target_path):  # File doesn't exist in destination drive
                            file_list['new'].add((drive, source, stub_path, entry.stat().st_size))
                            self.progress['since_last_update']['analysis'].append((FileUtils.LIST_TOTAL_COPY, target_path))

                    # If no files in folder on source, create empty folder in destination
                    if not source_file_list and not os.path.isdir(os.path.join(drive, source, path)):
                        return {
                            'new': {(drive, source, path, get_directory_size(os.path.join(source_path, path)))}
                        }
                except (NotADirectoryError, PermissionError, OSError):
                    return {
                        'new': set()
                    }
                return file_list

            file_list = {
                'new': set()
            }

            for source in sources:
                if self.analysis_killed:
                    break

                file_list['new'].update(scan_source_source_for_new_files(drive, source, path, exclusions, sources)['new'])

            return file_list

        def start_building_file_lists():
            """Build the lists of files to be copied, modified, and deleted."""

            for drive, sources in drive_source_list.items():
                if self.analysis_killed:
                    break

                modified_file_list = build_delta_file_list(self.DRIVE_VID_INFO[drive]['name'], '', sources, drive_exclusions[self.DRIVE_VID_INFO[drive]['name']])

                delete_items = modified_file_list['delete']
                if delete_items:
                    self.delete_file_list[self.DRIVE_VID_INFO[drive]['name']] = delete_items

                    purge_command_list.append({
                        'enabled': True,
                        'displayIndex': len(purge_command_list) + 1,
                        'type': Backup.COMMAND_TYPE_FILE_LIST,
                        'dest': self.DRIVE_VID_INFO[drive]['name'],
                        'size': sum((size for drive, file, size in delete_items)),
                        'list': {os.path.join(drive, file) for drive, file, size in delete_items},
                        'payload': delete_items,
                        'mode': Status.FILE_OPERATION_DELETE
                    })

                # Build list of files to replace
                replace_items = list(modified_file_list['replace'])
                replace_items.sort(key=lambda x: x[1])
                if replace_items:
                    self.replace_file_list[self.DRIVE_VID_INFO[drive]['name']] = replace_items

                    copy_command_list.append({
                        'enabled': True,
                        'displayIndex': len(purge_command_list) + 1,
                        'type': Backup.COMMAND_TYPE_FILE_LIST,
                        'dest': self.DRIVE_VID_INFO[drive]['name'],
                        'size': sum((source_size for drive, source, file, source_size, dest_size in replace_items)),
                        'list': [os.path.join(drive, source, file) for drive, source, file, source_size, dest_size in replace_items],
                        'payload': replace_items,
                        'mode': Status.FILE_OPERATION_UPDATE
                    })

                # Build list of new files to copy
                new_items = build_new_file_list(self.DRIVE_VID_INFO[drive]['name'], '', sources, drive_exclusions[self.DRIVE_VID_INFO[drive]['name']])['new']
                if new_items:
                    self.new_file_list[self.DRIVE_VID_INFO[drive]['name']] = new_items

                    copy_command_list.append({
                        'enabled': True,
                        'displayIndex': len(purge_command_list) + 1,
                        'type': Backup.COMMAND_TYPE_FILE_LIST,
                        'dest': self.DRIVE_VID_INFO[drive]['name'],
                        'size': sum((size for drive, source, file, size in new_items)),
                        'list': {os.path.join(drive, source, file) for (drive, source, file, size) in new_items},
                        'payload': new_items,
                        'mode': Status.FILE_OPERATION_COPY
                    })

        # Build list of files/dirs to delete and replace
        self.delete_file_list = {}
        self.replace_file_list = {}
        self.new_file_list = {}
        purge_command_list = []
        copy_command_list = []
        logging.debug('Delta file lists starting...')
        start_building_file_lists()
        logging.debug('Delta file lists finished')

        # Gather and summarize totals for analysis summary
        show_file_info = []
        for i, drive in enumerate(drive_source_list.keys()):
            if self.analysis_killed:
                break
            file_summary = []
            drive_total = {
                'running': 0,
                'delete': 0,
                'replace': 0,
                'copy': 0,
                'new': 0
            }

            if self.DRIVE_VID_INFO[drive]['name'] in self.delete_file_list.keys():
                drive_total['delete'] = sum((size for drive, file, size in self.delete_file_list[self.DRIVE_VID_INFO[drive]['name']]))

                drive_total['running'] -= drive_total['delete']

                file_summary.append(f"Deleting {len(self.delete_file_list[self.DRIVE_VID_INFO[drive]['name']])} files ({human_filesize(drive_total['delete'])})")

            if self.DRIVE_VID_INFO[drive]['name'] in self.replace_file_list.keys():
                drive_total['replace'] = sum((source_size for drive, source, file, source_size, dest_size in self.replace_file_list[self.DRIVE_VID_INFO[drive]['name']]))

                drive_total['running'] += drive_total['replace']
                drive_total['copy'] += drive_total['replace']

                file_summary.append(f"Updating {len(self.replace_file_list[self.DRIVE_VID_INFO[drive]['name']])} files ({human_filesize(drive_total['replace'])})")

            if self.DRIVE_VID_INFO[drive]['name'] in self.new_file_list.keys():
                drive_total['new'] = sum((size for drive, source, file, size in self.new_file_list[self.DRIVE_VID_INFO[drive]['name']]))

                drive_total['running'] += drive_total['new']
                drive_total['copy'] += drive_total['new']

                file_summary.append(f"{len(self.new_file_list[self.DRIVE_VID_INFO[drive]['name']])} new files ({human_filesize(drive_total['new'])})")

            # Increment master totals
            # Double copy total to account for both copy and verify operations
            self.progress['total'] += 2 * drive_total['copy'] + drive_total['delete']
            self.progress['delete_total'] += drive_total['delete']

            if file_summary:
                show_file_info.append((self.DRIVE_VID_INFO[drive]['name'], '\n'.join(file_summary)))

        if not self.analysis_killed:
            # Concat both lists into command list
            self.command_list = [cmd for cmd in purge_command_list]
            self.command_list.extend([cmd for cmd in copy_command_list])

            # Fix display index on command list
            for i, cmd in enumerate(self.command_list):
                self.command_list[i]['displayIndex'] = i

            self.analysis_valid = True
            self.status = Status.BACKUP_ANALYSIS_FINISHED
        else:
            self.status = Status.BACKUP_ANALYSIS_ABORTED

        self.analysis_running = False
        self.analysis_callback_fn(
            files_payload=show_file_info,
            summary_payload=[(self.DRIVE_VID_INFO[drive]['name'], '\n'.join(sources), drive in connected_vid_list) for drive, sources in drive_source_list.items()]
        )

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
            source_list = ','.join([item['dest_name'] for item in self.config['sources']])
            raw_vid_list = [drive['vid'] for drive in self.config['destinations']]
            raw_vid_list.extend(self.config['missing_drives'].keys())
            vid_list = ','.join(raw_vid_list)

            # For each drive letter connected, get drive info, and write file
            for drive in self.config['destinations']:
                # If config exists on drives, back it up first
                if os.path.isfile(os.path.join(drive['name'], self.BACKUP_CONFIG_DIR, self.BACKUP_CONFIG_FILE)):
                    shutil.move(os.path.join(drive['name'], self.BACKUP_CONFIG_DIR, self.BACKUP_CONFIG_FILE), os.path.join(drive['name'], self.BACKUP_CONFIG_DIR, f'{self.BACKUP_CONFIG_FILE}.old'))

                drive_config_file = Config(os.path.join(self.DRIVE_VID_INFO[drive['vid']]['name'], self.BACKUP_CONFIG_DIR, self.BACKUP_CONFIG_FILE))

                # Write sources and VIDs to config file
                drive_config_file.set('selection', 'sources', source_list)
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
        """Once the backup analysis is run, and drives and sources are selected, run the backup.

        This function is run in a new thread, but is only run if the backup config is valid.
        If sanity_check() returns False, the backup isn't run.
        """

        # FIXME: When stopping and starting backup after analysis in quick succession, program sometimes crashes

        if not self.analysis_valid or not self.sanity_check():
            return

        self.run_killed = False
        self.backup_running = True
        self.status = Status.BACKUP_BACKUP_RUNNING

        # Write config file to drives
        self.write_config_to_disks()

        self.progress['current'] = 0
        self.progress['current_file'] = None
        self.progress['files'] = []
        self.progress['since_last_update']['files'] = []
        self.progress['buffer'] = {
            'copied': 0,
            'total': 0,
            'display_filename': None,
            'operation': None,
            'display_index': None
        }

        timer_started = False

        for cmd in self.command_list:
            if cmd['type'] == Backup.COMMAND_TYPE_FILE_LIST:
                self.progress['command_display_index'] = cmd['displayIndex']

                if not timer_started:
                    timer_started = True
                    self.backup_start_time = datetime.now()

                if cmd['mode'] == Status.FILE_OPERATION_DELETE:
                    for drive, file, size in cmd['payload']:
                        if self.run_killed:
                            break

                        self.do_del_fn(
                            filename=os.path.join(drive, file),
                            size=size,
                            display_index=cmd['displayIndex']
                        )

                        # If file hash was in list, remove it, and write changes to file
                        if file in self.file_hashes[drive].keys():
                            del self.file_hashes[drive][file]

                            drive_hash_file_path = os.path.join(drive, self.BACKUP_CONFIG_DIR, self.BACKUP_HASH_FILE)
                            with open(drive_hash_file_path, 'wb') as f:
                                hash_list = {'/'.join(file_name.split(os.path.sep)): hash_val for file_name, hash_val in self.file_hashes[drive].items()}
                                pickle.dump(hash_list, f)
                if cmd['mode'] == Status.FILE_OPERATION_UPDATE:
                    for drive, source, file, source_size, dest_size in cmd['payload']:
                        if self.run_killed:
                            break

                        source_path = self.get_source_source_path(source)

                        dest = os.path.join(drive, source, file)

                        self.set_working_file(dest, source_size, Status.FILE_OPERATION_UPDATE, cmd['displayIndex'])
                        file_hashes = self.do_copy_fn(
                            src=os.path.join(source_path, file),
                            dest=dest,
                            drive_path=drive,
                            display_index=cmd['displayIndex']
                        )
                        self.file_hashes[drive].update(file_hashes)

                        # Write updated hash file to drive
                        drive_hash_file_path = os.path.join(drive, self.BACKUP_CONFIG_DIR, self.BACKUP_HASH_FILE)
                        with open(drive_hash_file_path, 'wb') as f:
                            hash_list = {'/'.join(file_name.split(os.path.sep)): hash_val for file_name, hash_val in self.file_hashes[drive].items()}
                            pickle.dump(hash_list, f)
                elif cmd['mode'] == Status.FILE_OPERATION_COPY:
                    for drive, source, file, size in cmd['payload']:
                        if self.run_killed:
                            break

                        source_path = self.get_source_source_path(source)

                        dest = os.path.join(drive, source, file)

                        self.set_working_file(dest, size, Status.FILE_OPERATION_COPY, cmd['displayIndex'])
                        file_hashes = self.do_copy_fn(
                            src=os.path.join(source_path, file),
                            dest=dest,
                            drive_path=drive,
                            display_index=cmd['displayIndex']
                        )
                        self.file_hashes[drive].update(file_hashes)

                        # Write updated hash file to drive
                        drive_hash_file_path = os.path.join(drive, self.BACKUP_CONFIG_DIR, self.BACKUP_HASH_FILE)
                        with open(drive_hash_file_path, 'wb') as f:
                            hash_list = {'/'.join(file_name.split(os.path.sep)): hash_val for file_name, hash_val in self.file_hashes[drive].items()}
                            pickle.dump(hash_list, f)

            self.backup_callback_fn(cmd)

            if self.run_killed:
                break

        if not self.run_killed:
            self.status = Status.BACKUP_BACKUP_FINISHED
        if self.run_killed:
            self.status = Status.BACKUP_BACKUP_ABORTED

        self.backup_running = False
        self.backup_callback_fn()

    def add_progress_delta_to_total(self):
        """Add the progress delta to the total, and reset the buffer.
        """

        # Add buffer to total
        self.progress['analysis'].extend(self.progress['since_last_update']['analysis'])
        self.progress['files'].extend(self.progress['since_last_update']['files'])

        # Clear buffer
        self.progress['since_last_update']['analysis'].clear()
        self.progress['since_last_update']['files'].clear()

    def get_progress_updates(self) -> dict:
        """Get the current progress of the backup, and file lists since the
        last update. Then, reset the last update progress.

        Returns:
            dict: The current progress of the backup
        """

        current_progress = {
            'delta': {
                'analysis': self.progress['since_last_update']['analysis'].copy(),
                'files': self.progress['since_last_update']['files'].copy()
            }
        }

        self.add_progress_delta_to_total()

        # Set progress to all processed files
        file_list = [file['file'] for file in self.progress['files']]
        self.progress['current'] = sum([filesize for (filename, filesize, operation, display_index) in file_list if operation == Status.FILE_OPERATION_DELETE])
        self.progress['current'] += sum([2 * filesize for (filename, filesize, operation, display_index) in file_list if operation == Status.FILE_OPERATION_COPY])

        # Add copy buffer to progress total
        self.progress['current'] += self.progress['buffer']['copied']

        current_progress['total'] = self.progress

        return current_progress

    def get_backup_start_time(self) -> datetime:
        """
        Returns:
            datetime: The time the backup started. (default 0)
        """

        return self.backup_start_time

    def is_running(self) -> bool:
        """
        Returns:
            bool: Whether or not the backup is actively running something.
        """

        return self.analysis_running or self.backup_running

    def kill(self, request: int = None):
        """Kill the analysis and running backup.

        Args:
            request (int): The kill request to make (optional, default KILL_ALL).
        """

        # Set parameter defaults
        if request is None:
            request = Backup.KILL_ALL

        if request == Backup.KILL_ALL:
            self.analysis_killed = True
            self.run_killed = True
        elif request == Backup.KILL_ANALYSIS:
            self.analysis_killed = True
        elif request == Backup.KILL_BACKUP:
            self.run_killed = True
