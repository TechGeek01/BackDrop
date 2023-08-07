import os
import shutil
from blake3 import blake3
import subprocess
import platform
if platform.system() == 'Windows':
    import win32api
    import win32file

from bin.status import Status


class FileUtils:
    STATUS_SUCCESS = 0x00
    STATUS_FAIL = 0x01

    LIST_TOTAL_COPY = 'total_copy'
    LIST_TOTAL_DELETE = 'total_delete'
    LIST_SUCCESS = 'copy_success'
    LIST_FAIL = 'copy_fail'
    LIST_DELETE_SUCCESS = 'delete_success'
    LIST_DELETE_FAIL = 'delete_fail'

    LOCAL_DRIVE = 1
    NETWORK_DRIVE = 2

    READINTO_BUFSIZE = 1024 * 1024 * 2  # differs from shutil.COPY_BUFSIZE on platforms != Windows


def get_drive_list(system_drive, flags=0) -> list:
    """Get the list of available drives based on a selection.

    Args:
        system_drive: The drive letter or mount point for the system drive.
        flags: The flags to select drives.

    Returns:
        list: The list of drives selected.
    """

    source_avail_drive_list = []

    if platform.system() == 'Windows':
        drive_list = win32api.GetLogicalDriveStrings().split('\000')[:-1]
        drive_type_list = []
        if flags & FileUtils.NETWORK_DRIVE:
            drive_type_list.append(win32file.DRIVE_REMOTE)
        if flags & FileUtils.LOCAL_DRIVE:
            drive_type_list.append(win32file.DRIVE_FIXED)
            drive_type_list.append(win32file.DRIVE_REMOVABLE)
        source_avail_drive_list = [drive[:2] for drive in drive_list if win32file.GetDriveType(drive) in drive_type_list and drive[:2] != system_drive]
    else:
        local_selected = flags & FileUtils.LOCAL_DRIVE
        network_selected = flags & FileUtils.NETWORK_DRIVE

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
            if physical_disk != system_drive and drive != '/':
                source_avail_drive_list.append(drive)

    return source_avail_drive_list


def human_filesize(num: int, suffix=None) -> str:
    """Convert a number of bytes to a human readable format.

    Args:
        num (int): The number of bytes.
        suffix (String, optional): The suffix to use. Defaults to 'B'.

    Returns:
        String: A string representation of the filesize passed in.
    """

    if suffix is None:
        suffix = 'B'

    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.2f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def get_directory_size(directory) -> int:
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


def copy_file(source_filename, dest_filename, drive_path, pre_callback, prog_callback, fd_callback, get_backup_killflag) -> tuple:
    """Copy a source binary file to a destination.

    Args:
        source_filename (String): The source to copy.
        dest_filename (String): The destination to copy to.
        drive_path (String): The path of the destination drive to copy to.
        pre_callback (def): The function to call before copying.
        prog_callback (def): The function to call on progress change.
        fd_callback (def): The function to run after copy to update file details.
        get_backup_killflag (def): The function to use to get the backup thread kill flag.

    Returns:
        tuple:
            String: The destination drive the file was copied to.
            String: The resulting file hash if the file was copied successfully.
        None:
            If the file failed to copy, returns None.
    """

    pre_callback()
    operation = Status.FILE_OPERATION_COPY

    # Optimize the buffer for small files
    buffer_size = min(FileUtils.READINTO_BUFSIZE, os.path.getsize(source_filename))
    if buffer_size == 0:
        buffer_size = 1024

    h = blake3()
    b = bytearray(buffer_size)
    mv = memoryview(b)

    copied = 0
    with open(source_filename, 'rb', buffering=0) as f:
        try:
            file_size = os.stat(f.fileno()).st_size
        except OSError:
            file_size = FileUtils.READINTO_BUFSIZE

        # Make sure destination path exists before copying
        path_stub = dest_filename[0:dest_filename.rindex(os.path.sep)]
        if not os.path.exists(path_stub):
            os.makedirs(path_stub)

        fdst = open(dest_filename, 'wb')
        try:
            for n in iter(lambda: f.readinto(mv), 0):
                fdst.write(mv[:n])
                h.update(mv[:n])

                copied += n
                prog_callback(c=copied, t=file_size, op=operation)

                if get_backup_killflag():
                    break
        except OSError:
            pass

        fdst.close()

    # If file wasn't copied successfully, delete it
    if copied != file_size:
        if os.path.isfile(dest_filename):
            os.remove(dest_filename)
        elif os.path.isdir(dest_filename):
            shutil.rmtree(dest_filename)

        fd_callback(
            status=Status.FILE_OPERATION_FAILED,
            file=(dest_filename, file_size, Status.FILE_OPERATION_COPY, None)
        )

        return None

    # File copied in full, so copy meta, and verify
    shutil.copymode(source_filename, dest_filename)
    shutil.copystat(source_filename, dest_filename)

    dest_hash = blake3()
    dest_b = bytearray(buffer_size)
    dest_mv = memoryview(dest_b)

    with open(dest_filename, 'rb', buffering=0) as f:
        operation = Status.FILE_OPERATION_VERIFY
        copied = 0

        for n in iter(lambda: f.readinto(dest_mv), 0):
            dest_hash.update(dest_mv[:n])

            copied += n
            prog_callback(c=copied, t=file_size, op=operation)

    if h.hexdigest() == dest_hash.hexdigest():
        fd_callback(
            status=Status.FILE_OPERATION_SUCCESS,
            file=(dest_filename, file_size, Status.FILE_OPERATION_COPY, None)
        )
    else:
        # If file wasn't copied successfully, delete it
        if os.path.isfile(dest_filename):
            os.remove(dest_filename)
        elif os.path.isdir(dest_filename):
            shutil.rmtree(dest_filename)

        fd_callback(
            status=Status.FILE_OPERATION_FAILED,
            file=(dest_filename, file_size, Status.FILE_OPERATION_COPY, None)
        )

    if h.hexdigest() == dest_hash.hexdigest():
        return (drive_path, dest_hash.hexdigest())
    else:
        return None


def get_file_hash(filename, kill_flag) -> str:
    """Get the hash of a file.

    Args:
        filename (String): The file to get the hash of.
        kill_flag (function): The function to get a kill flag.

    Returns:
        String: The blake3 hash of the file if readable. None otherwise.
    """

    # Optimize the buffer for small files
    buffer_size = min(FileUtils.READINTO_BUFSIZE, os.path.getsize(filename))
    if buffer_size == 0:
        buffer_size = 1024

    h = blake3()
    b = bytearray(buffer_size)
    mv = memoryview(b)

    with open(filename, 'rb', buffering=0) as f:
        for n in iter(lambda: f.readinto(mv), 0):
            if kill_flag():  # TODO: Refactor this into separate function
                break
            h.update(mv[:n])

    if kill_flag():
        return ''

    return h.hexdigest()


def do_copy(src, dest, drive_path, pre_callback, prog_callback, fd_callback, get_backup_killflag, display_index: int = None) -> dict:
    """Copy a source to a destination.

    Args:
        src (String): The source to copy.
        dest (String): The destination to copy to.
        drive_path (String): The path of the destination drive to copy to.
        pre_callback (def): The function to call before copying.
        prog_callback (def): The function to call on progress change.
        fd_callback (def): The function to run after copy to update file details.
        get_backup_killflag (def): The function to use to get the backup thread kill flag.
        display_index (int): The index to display the item in the GUI (optional).

    Returns:
        dict: A list of file hashes for each file copied
            Key (String): The filename to hash.
            Value (String): The hash of the file.
    """

    new_hash_list = {}

    if os.path.isfile(src):
        if not get_backup_killflag():
            new_hash = copy_file(
                source_filename=src,
                dest_filename=dest,
                drive_path=drive_path,
                pre_callback=lambda: pre_callback(display_index=display_index, filename=dest),
                prog_callback=prog_callback,
                fd_callback=fd_callback,
                get_backup_killflag=get_backup_killflag
            )

            if new_hash is not None and dest.find(new_hash[0]) == 0:
                file_path_stub = dest.split(new_hash[0])[1].strip(os.path.sep)
                new_hash_list[file_path_stub] = new_hash[1]
    elif os.path.isdir(src):
        # Make dir if it doesn't exist
        if not os.path.exists(dest):
            os.makedirs(dest)

        try:
            for entry in os.scandir(src):
                if get_backup_killflag():
                    break

                filename = entry.path.split(os.path.sep)[-1]
                if entry.is_file():
                    src_file = os.path.join(src, filename)
                    dest_file = os.path.join(dest, filename)

                    new_hash = copy_file(
                        source_filename=src_file,
                        dest_filename=dest_file,
                        drive_path=drive_path,
                        pre_callback=lambda: pre_callback(display_index=display_index, filename=dest_file),
                        prog_callback=prog_callback,
                        fd_callback=fd_callback,
                        get_backup_killflag=get_backup_killflag
                    )
                    if new_hash is not None and dest.find(new_hash[0]) == 0:
                        file_path_stub = dest.split(new_hash[0])[1].strip(os.path.sep)
                        new_hash_list[file_path_stub] = new_hash[1]
                elif entry.is_dir():
                    new_hash_list.update(
                        do_copy(
                            src=os.path.join(src, filename),
                            dest=os.path.join(dest, filename),
                            drive_path=drive_path,
                            pre_callback=pre_callback,
                            prog_callback=prog_callback,
                            fd_callback=fd_callback,
                            get_backup_killflag=get_backup_killflag
                        )
                    )

            # Handle changing attributes of folders if we copy a new folder
            shutil.copymode(src, dest)
            shutil.copystat(src, dest)
        except Exception:
            return {}

    return new_hash_list


def do_delete(filename):
    """Delete a file or directory.

    Args:
        filename (String): The file or folder to delete.
    """

    try:
        if os.path.isfile(filename):
            os.remove(filename)
        elif os.path.isdir(filename):
            shutil.rmtree(filename)
    except PermissionError:
        pass
