import threading
import time

class ThreadManager:
    # Define thread types for starting threads
    SINGLE = 0      # One thread at once, block if already running
    MULTIPLE = 1    # Multiple threads, name with counter, and run
    KILLABLE = 2    # Thread can be killed with a flag
    REPLACEABLE = 3 # Like SINGLE, but instead of blocking, kill and restart

    threadList = {}
    counter = 0

    def is_alive(self, threadName):
        """Check if a thread by a given name is active.

        Args:
            threadName (String): The name of the thread to check.

        Returns:
            threading.Thread: If thread found by name is active.
            bool: False if thread not found, or thread is not active.
        """
        for thread in threading.enumerate():
            if thread.name == threadName and thread.is_alive():
                return thread
        return False

    def garbage_collect(self):
        """Remove threads from threadList that aren't active anymore."""
        self.threadList = {name: thread for name, thread in self.threadList.items() if thread['thread'].is_alive()}

    def __init__(self):
        def threadGarbageCollect():
            """Periodically run garbage collection."""
            while 1:
                time.sleep(20)
                self.garbage_collect()

        self.gcThread = threading.Thread(target=threadGarbageCollect, name='ThreadManager_GC', daemon=True)
        self.gcThread.start()

    def start(self, threadType, *args, **kwargs):
        """Create and start a thread if one doesn't already exist.

        Args:
            threadType (int): The constant corresponding to the thread type to create.
            callback (def, optional): For KILLABLE and REPLACEABLE threads, the function to
                run to kill the thread.

        Returns:
            String: If a thread is successfully created, the thread name is returned.
            bool: False if an active thread exists with that name.
        """
        if kwargs['name']:
            threadName = kwargs['name']
        else:
            threadName = 'thread%d' % (self.counter)
            self.counter += 1

        def dummy():
            """A dummy function to pass as a default callback to KILLABLE threads."""
            pass

        # SINGLE: block if already running
        # MULTIPLE: run again, and increment counter
        # KILLABLE: Add flag to let it be killed
        # REPLACEABLE: SINGLE thread, but instead of blocking, kill and restart

        if threadType == self.SINGLE or threadType == self.KILLABLE or threadType == self.REPLACEABLE:
            if kwargs['name']:
                threadName = kwargs['name']
            else:
                self.counter += 1
                threadName = 'thread%d' % (self.counter)
        elif threadType == self.MULTIPLE:
            self.counter += 1
            threadName = '%s_%d' % (kwargs['name'] if kwargs['name'] else 'thread', self.counter)

        # If the thread either isn't in the list, or isn't active, create and run the thread
        if threadType == self.SINGLE and not self.is_alive(threadName):
            # if threadName not in self.threadList.keys() or not self.threadList[threadName]['thread'].is_alive():
            self.threadList[threadName] = {
                'type': threadType,
                'thread': threading.Thread(**kwargs)
            }

            self.threadList[threadName]['thread'].start()
            return threadName
        elif threadType == self.MULTIPLE and not self.is_alive(threadName):
            self.threadList[threadName] = {
                'type': threadType,
                'thread': threading.Thread(**kwargs)
            }

            self.threadList[threadName]['thread'].start()
            return threadName
        elif threadType == self.KILLABLE and not self.is_alive(threadName):
            self.threadList[threadName] = {
                'type': threadType,
                'thread': threading.Thread(**kwargs),
                'killFlag': False,
                'callback': args[0] if len(args) >= 1 else dummy
            }

            self.threadList[threadName]['thread'].start()
            return threadName
        elif threadType == self.REPLACEABLE:
            # If thread is active already, kill it before starting a new thread
            replaceableThread = self.is_alive(threadName)
            if replaceableThread:
                self.kill(replaceableThread)

            self.threadList[threadName] = {
                'type': threadType,
                'thread': threading.Thread(**kwargs),
                'killFlag': False,
                'callback': args[0] if len(args) >= 1 else dummy
            }

            self.threadList[threadName]['thread'].start()
            return threadName

        return False

    def kill(self, name):
        """Kill a KILLABLE or REPLACEABLE thread by name.

        Kills a thread by running the callback function defined during creation. This
        only works on KILLABLE and REPLACEABLE threads.

        Args:
            name (String): The name of the thread, as set in threadList.
        """
        if (name in self.threadList.keys()
                and self.threadList[name]['thread'].is_alive()
                and (self.threadList[name]['type'] == self.KILLABLE or self.threadList[name]['type'] == self.REPLACEABLE)
                and self.threadList[name]['killFlag'] is not True):
            # Thread exists, is active, is KILLABLE or REPLACEABLE, and has not been killed
            self.threadList[name]['killFlag'] = True
            self.threadList[name]['callback']()

    def list(self):
        """List all threads in threadList."""
        print('   Threads   \n=============')
        for thread in self.threadList.keys():
            print('%s => %s' % (thread, '-- Alive --' if self.is_alive(thread) else 'Dead'))
