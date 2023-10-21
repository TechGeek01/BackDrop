""" This module contains utility functions unrelated to the UI."""

from datetime import datetime, timedelta

class Timer:
    def __init__(self, start = None, *args, **kwargs):
        """Create an updatable timer."""

        self._start = None
        self._stop = None
        self._running = False

    def start(self, time: datetime = None):
        """Start the timer.

        Args:
            time: The time to start from (optional).
        """

        self._running = True
        self._stop = None
        if time is None:
            self._start = datetime.now()
        else:
            self._start = time

    def stop(self):
        """Stop the timer."""

        self._stop = datetime.now()
        self._running = False

    @property
    def elapsed(self) -> timedelta:
        """Get the elapsed time of the timer.

        Returns:
            The elapsed time.
        """

        if self._running:
            return datetime.now() - self._start
        elif self._start is not None:
            return self._stop - self._start
        else:
            return 0


    @property
    def running(self) -> bool:
        """Check if the timer is running.

        Returns:
            bool: Whether or not the timer is running.
        """

        return self._running
