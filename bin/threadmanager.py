import threading
import time

class ThreadManager:
    # Define thread types for starting threads
    SINGLE = 0       # One thread at once, block if already running
    MULTIPLE = 1     # Multiple threads, name with counter, and run
    KILLABLE = 2     # Thread can be killed with a flag
    REPLACEABLE = 3  # Like SINGLE, but instead of blocking, kill and restart

    def is_alive(self, thread_name):
        """Check if a thread by a given name is active.

        Args:
            thread_name (String): The name of the thread to check.

        Returns:
            threading.Thread: If thread found by name is active.
            bool: False if thread not found, or thread is not active.
        """

        for thread in threading.enumerate():
            if thread.name == thread_name and thread.is_alive():
                return thread
        return False

    def garbage_collect(self):
        """Remove threads from threadlist that aren't active anymore."""

        self.threadlist = {name: thread for name, thread in self.threadlist.items() if thread['thread'].is_alive()}
        self.progress_threads = [thread for thread in self.progress_threads if thread.is_alive()]

    def __init__(self):
        """Create and manage threads for backup and operation."""

        self.threadlist = {}
        self.counter = 0
        self.progress_threads = []

        def thread_garbage_collect():
            """Periodically run garbage collection."""

            while 1:
                time.sleep(20)
                self.garbage_collect()

        self._gc_thread = threading.Thread(target=thread_garbage_collect, name='ThreadManager_GC', daemon=True)
        self._gc_thread.start()

    def start(self, thread_type, is_progress_thread: bool = None, callback=None, *args, **kwargs):
        """Create and start a thread if one doesn't already exist.

        Args:
            thread_type (int): The constant corresponding to the thread type to create.
            is_progress_thread (bool): Whether or not the thread controls the progress
                bar (default: False).
            callback (def, optional): For KILLABLE and REPLACEABLE threads, the function to
                run to kill the thread.

        Returns:
            String: If a thread is successfully created, the thread name is returned.
            bool: False if an active thread exists with that name.
        """

        if is_progress_thread is None:
            is_progress_thread = False

        if 'name' in kwargs:
            thread_name = kwargs['name']
        else:
            thread_name = f"thread{self.counter}"
            self.counter += 1

        def dummy():
            """A dummy function to pass as a default callback to KILLABLE threads."""

            pass

        # SINGLE: block if already running
        # MULTIPLE: run again, and increment counter
        # KILLABLE: Add flag to let it be killed
        # REPLACEABLE: SINGLE thread, but instead of blocking, kill and restart

        if thread_type == self.SINGLE or thread_type == self.KILLABLE or thread_type == self.REPLACEABLE:
            if 'name' in kwargs:
                thread_name = kwargs['name']
            else:
                self.counter += 1
                thread_name = f"thread{self.counter}"
        elif thread_type == self.MULTIPLE:
            self.counter += 1
            thread_name = f"{kwargs['name'] if 'name' in kwargs else 'thread'}_{self.counter}"

        # If the thread either isn't in the list, or isn't active, create and run the thread
        if thread_type == self.SINGLE and not self.is_alive(thread_name):
            # if thread_name not in self.threadlist.keys() or not self.threadlist[thread_name]['thread'].is_alive():
            self.threadlist[thread_name] = {
                'type': thread_type,
                'thread': threading.Thread(**kwargs)
            }

            # If thread controls progress bar, add it to list
            if is_progress_thread:
                self.progress_threads.append(self.threadlist[thread_name]['thread'])

            self.threadlist[thread_name]['thread'].start()
            return thread_name
        elif thread_type == self.MULTIPLE and not self.is_alive(thread_name):
            self.threadlist[thread_name] = {
                'type': thread_type,
                'thread': threading.Thread(**kwargs)
            }

            # If thread controls progress bar, add it to list
            if is_progress_thread:
                self.progress_threads.append(self.threadlist[thread_name]['thread'])

            self.threadlist[thread_name]['thread'].start()
            return thread_name
        elif thread_type == self.KILLABLE and not self.is_alive(thread_name):
            self.threadlist[thread_name] = {
                'type': thread_type,
                'thread': threading.Thread(**kwargs),
                'killFlag': False,
                'callback': callback if callback is not None else dummy
            }

            # If thread controls progress bar, add it to list
            if is_progress_thread:
                self.progress_threads.append(self.threadlist[thread_name]['thread'])

            self.threadlist[thread_name]['thread'].start()
            return thread_name
        elif thread_type == self.REPLACEABLE:
            # If thread is active already, kill it before starting a new thread
            replaceable_thread = self.is_alive(thread_name)
            if replaceable_thread:
                self.kill(replaceable_thread)

                # Wait until thread is killed
                while self.is_alive(thread_name):
                    pass

            self.threadlist[thread_name] = {
                'type': thread_type,
                'thread': threading.Thread(**kwargs),
                'killFlag': False,
                'callback': args[0] if args else dummy
            }

            # If thread controls progress bar, add it to list
            if is_progress_thread:
                self.progress_threads.append(self.threadlist[thread_name]['thread'])

            self.threadlist[thread_name]['thread'].start()
            return thread_name

        return False

    def kill(self, name):
        """Kill a KILLABLE or REPLACEABLE thread by name.

        Kills a thread by running the callback function defined during creation. This
        only works on KILLABLE and REPLACEABLE threads.

        Args:
            name (String): The name of the thread, as set in threadlist.
        """

        if (name in self.threadlist.keys()
                and self.threadlist[name]['thread'].is_alive()
                and (self.threadlist[name]['type'] == self.KILLABLE or self.threadlist[name]['type'] == self.REPLACEABLE)
                and self.threadlist[name]['killFlag'] is not True):
            # Thread exists, is active, is KILLABLE or REPLACEABLE, and has not been killed
            self.threadlist[name]['killFlag'] = True
            self.threadlist[name]['callback']()

    def get_progress_threads(self):
        """List the progress-influencing threads that are running.

        Returns:
            list: The list of thread instances that control the progress bar.
        """

        self.progress_threads = [thread for thread in self.progress_threads if thread.is_alive()]
        return self.progress_threads
