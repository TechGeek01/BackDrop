import threading

class Progress:
    def __init__(self, progressBar, threadsForProgressBar):
        self.progressBar = progressBar
        self.threadsForProgressBar = threadsForProgressBar

    def setMax(self, maxVal):
        self.progressBar.stop()
        self.progressBar.configure(mode='determinate', value=0, maximum=maxVal)

    def set(self, curVal):
        self.progressBar.configure(value=curVal)

    def startIndeterminate(self):
        if len(threading.enumerate()) <= self.threadsForProgressBar:
            self.progressBar.configure(mode='indeterminate')
            self.progressBar.start()

    def stopIndeterminate(self):
        if len(threading.enumerate()) <= self.threadsForProgressBar:
            self.progressBar.configure(mode='determinate')
            self.progressBar.stop()