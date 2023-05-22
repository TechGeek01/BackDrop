class Progress:
    def __init__(self, progress_bar, thread_manager):
        """
        Args:
            progress_bar (ttk.progressBar): The progrss bar to control.
            thread_manager (ThreadManager): The ThreadManager instance to check
                for threads.
        """

        self.progress_bar = progress_bar
        self._thread_manager = thread_manager
        self.mode = None
        self.max = 0

    def set(self, current: int = None, total: int = None):
        """Set the current value of the progress bar.

        Args:
            current (int): The value to set (optional).
            total (int): The max vlaue to set (optional).
        """

        params = {}
        if current is not None:
            params['value'] = current
        if total is not None and self.max != total:
            self.max = total
            params['maximum'] = total

        self.progress_bar.configure(**params)

    def start_indeterminate(self):
        """Start indeterminate mode on the progress bar if it isn't being controlled
        by another thread.
        """

        # No need to start if this isn't the first progress thread
        if len(self._thread_manager.get_progress_threads()) > 1:
            return

        # Mode should only be changed if it's not already correct
        if self.mode == 'indeterminate':
            return

        self.mode = 'indeterminate'
        self.progress_bar.configure(mode='indeterminate')
        self.progress_bar.start()

    def stop_indeterminate(self):
        """Stop indeterminate mode on the progress bar."""

        # No need to stop if this isn't the only progress thread
        if len(self._thread_manager.get_progress_threads()) > 1:
            return

        # Mode should only be changed if it's not already correct
        if self.mode == 'determinate':
            return

        self.mode = 'determinate'
        self.progress_bar.configure(mode='determinate')
        self.progress_bar.stop()
