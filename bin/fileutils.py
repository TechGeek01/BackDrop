import os
import hashlib
import shutil

class FileUtils:
    STATUS_SUCCESS = 0x00
    STATUS_FAIL = 0x01

    LIST_TOTAL_COPY = 'total_copy'
    LIST_TOTAL_DELETE = 'total_delete'
    LIST_SUCCESS = 'copy_success'
    LIST_FAIL = 'copy_fail'
    LIST_DELETE_SUCCESS = 'delete_success'
    LIST_DELETE_FAIL = 'delete_fail'

    READINTO_BUFSIZE = 1024 * 1024  # differs from shutil.COPY_BUFSIZE on platforms != Windows

def human_filesize(num: int, suffix='B'):
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

def copy_file(source_filename, dest_filename, drive_path, pre_callback, prog_callback, fd_callback, get_backup_killflag):
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
    display_mode = 'copy'

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
            file_size = FileUtils.READINTO_BUFSIZE

        # Make sure destination path exists before copying
        path_stub = dest_filename[0:dest_filename.rindex(os.path.sep)]
        if not os.path.exists(path_stub):
            os.makedirs(path_stub)

        fdst = open(dest_filename, 'wb')
        try:
            for n in iter(lambda: f.readinto(mv), 0):
                if get_backup_killflag():
                    break

                fdst.write(mv[:n])
                h.update(mv[:n])

                copied += n
                prog_callback(c=copied, t=file_size, dm=display_mode)

                if get_backup_killflag():
                    break
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
            display_mode = 'verify'
            copied = 0

            for n in iter(lambda: f.readinto(dest_mv), 0):
                dest_hash.update(dest_mv[:n])

                copied += n
                prog_callback(c=copied, t=file_size, dm=display_mode)

        if h.hexdigest() == dest_hash.hexdigest():
            fd_callback(
                list_name=FileUtils.LIST_SUCCESS,
                filename=dest_filename
            )
        else:
            # If file wasn't copied successfully, delete it
            if os.path.isfile(dest_filename):
                os.remove(dest_filename)
            elif os.path.isdir(dest_filename):
                shutil.rmtree(dest_filename)

            fd_callback(
                list_name=FileUtils.LIST_FAIL,
                filename=dest_filename,
                error={'file': dest_filename, 'mode': 'copy', 'error': 'Source and destination hash mismatch'},
                s_hex=h.hexdigest(),
                d_hex=dest_hash.hexdigest()
            )

        if h.hexdigest() == dest_hash.hexdigest():
            return (drive_path, dest_hash.hexdigest())
        else:
            return None
    else:
        # If file wasn't copied successfully, delete it
        if os.path.isfile(dest_filename):
            os.remove(dest_filename)
        elif os.path.isdir(dest_filename):
            shutil.rmtree(dest_filename)

        fd_callback(
            list_name=FileUtils.LIST_FAIL,
            filename=dest_filename,
            error={'file': dest_filename, 'mode': 'copy', 'error': 'Source and destination filesize mismatch'}
        )

        return None

def do_copy(src, dest, drive_path, pre_callback, prog_callback, fd_callback, get_backup_killflag, display_index: int = None):
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
    """

    new_hash_list = {}

    if os.path.isfile(src):
        if not get_backup_killflag():
            new_hash = copy_file(
                source_filename=src,
                dest_filename=dest,
                drive_path=drive_path,
                pre_callback=lambda: pre_callback(di=display_index, dest_filename=dest),
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
                        pre_callback=lambda: pre_callback(di=display_index, dest_filename=dest_file),
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
