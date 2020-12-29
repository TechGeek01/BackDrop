import threading

class Progress:
    def __init__(self, progressBar, threadsForProgressBar):
        """
        Args:
            progressBar (ttk.progressBar): The progrss bar to control.
            threadsForProgressBar (int): The number of running threads at idle,
                used to trigger when the progress bar is controlled.
        """
        self.progressBar = progressBar
        self.threadsForProgressBar = threadsForProgressBar

    def setMax(self, maxVal):
        """Set the max value of the progress bar.

        Args:
            maxVal (int): The max value to set.
        """
        self.progressBar.stop()
        self.progressBar.configure(mode='determinate', value=0, maximum=maxVal)

    def set(self, curVal):
        """Set the current value of the progress bar.

        Args:
            curVal (int): The value to set.
        """
        self.progressBar.configure(value=curVal)

    def startIndeterminate(self):
        """Start indeterminate mode on the progress bar."""
        if len(threading.enumerate()) <= self.threadsForProgressBar:
            self.progressBar.configure(mode='indeterminate')
            self.progressBar.start()

    def stopIndeterminate(self):
        """Stop indeterminate mode on the progress bar."""
        if len(threading.enumerate()) <= self.threadsForProgressBar:
            self.progressBar.configure(mode='determinate')
            self.progressBar.stop()
