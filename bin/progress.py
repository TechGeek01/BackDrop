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

    def set_max(self, max_val: int):
        """Set the max value of the progress bar.

        Args:
            max_val (int): The max value to set.
        """

        # Only update max if it's not the same as it already was
        if self.max != max_val:
            self.max = max_val

            self.progress_bar.stop()
            self.progress_bar.configure(mode='determinate', maximum=max_val)

    def set(self, cur_val: int):
        """Set the current value of the progress bar.

        Args:
            cur_val (int): The value to set.
        """

        self.progress_bar.configure(value=cur_val)

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
