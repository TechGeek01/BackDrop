import os
import hashlib
import shutil

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

def copy_file(source_filename, dest_filename, drive_path, pre_callback, prog_callback, fd_callback):
    """Copy a source binary file to a destination.

    Args:
        source_filename (String): The source to copy.
        dest_filename (String): The destination to copy to.
        drive_path (String): The path of the destination drive to copy to.
        pre_callback (def): The function to call before copying.
        prog_callback (def): The function to call on progress change.
        fd_callback (def): The function to run after copy to update file details.

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
            file_size = READINTO_BUFSIZE

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
                # prog_callback returns false if break flag is set, so break out of the loop if that happens
                if not prog_callback(c=copied, t=file_size, dm=display_mode):
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
                status='success',
                filename=dest_filename
            )
        else:
            # If file wasn't copied successfully, delete it
            if os.path.isfile(dest_filename):
                os.remove(dest_filename)
            elif os.path.isdir(dest_filename):
                shutil.rmtree(dest_filename)

            fd_callback(
                status='fail',
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
            status='fail',
            filename=dest_filename,
            error={'file': dest_filename, 'mode': 'copy', 'error': 'Source and destination filesize mismatch'}
        )

        return None
