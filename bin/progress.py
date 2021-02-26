import threading

class Progress:
    def __init__(self, progress_bar, threads_for_progress_bar):
        """
        Args:
            progress_bar (ttk.progressBar): The progrss bar to control.
            threads_for_progress_bar (int): The number of running threads at idle,
                used to trigger when the progress bar is controlled.
        """

        self.progress_bar = progress_bar
        self.threads_for_progress_bar = threads_for_progress_bar

    def set_max(self, max_val):
        """Set the max value of the progress bar.

        Args:
            max_val (int): The max value to set.
        """

        self.progress_bar.stop()
        self.progress_bar.configure(mode='determinate', value=0, maximum=max_val)

    def set(self, cur_val):
        """Set the current value of the progress bar.

        Args:
            cur_val (int): The value to set.
        """

        self.progress_bar.configure(value=cur_val)

    def start_indeterminate(self):
        """Start indeterminate mode on the progress bar."""

        if len([thread for thread in threading.enumerate() if thread.name != 'Update Check']) <= self.threads_for_progress_bar:
            self.progress_bar.configure(mode='indeterminate')
            self.progress_bar.start()

    def stop_indeterminate(self):
        """Stop indeterminate mode on the progress bar."""

        if len([thread for thread in threading.enumerate() if thread.name != 'Update Check']) <= self.threads_for_progress_bar:
            self.progress_bar.configure(mode='determinate')
            self.progress_bar.stop()
