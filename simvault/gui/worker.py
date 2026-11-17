# Modul: simvault/gui/worker.py – lange Aufgaben im Hintergrund ausführen, ohne dass das Fenster einfriert.
#
# Aufgaben bekommen zwei Hilfsfunktionen: progress(text) für Fortschrittsmeldungen und
# should_stop() für den Abbrechen-Knopf.

import traceback

from PySide6.QtCore import QObject, QThread, Signal


class Task(QObject):
    progress = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs
        self._stop = False

    def stop(self):
        self._stop = True

    def should_stop(self):
        return self._stop

    def run(self):
        try:
            result = self._fn(*self._args, progress=self.progress.emit, should_stop=self.should_stop, **self._kwargs)
        except Exception as e:  # Fehler im Hintergrund sauber an die Oberfläche melden
            from simvault.finder import cc_finder
            if isinstance(e, cc_finder.Cancelled):
                self.failed.emit("Abgebrochen.")
            else:
                self.failed.emit(f"{type(e).__name__}: {e}\n\n{traceback.format_exc(limit=4)}")
            return
        self.finished.emit(result)


class Runner(QObject):
    """Startet jeweils eine Aufgabe in einem eigenen Thread."""
    busy_changed = Signal(bool)
    progress = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._task = None

    @property
    def busy(self):
        return self._thread is not None

    def start(self, fn, on_done=None, on_error=None, **kwargs):
        if self.busy:
            return False
        self._thread = QThread()
        self._task = Task(fn, **kwargs)
        self._task.moveToThread(self._thread)
        self._thread.started.connect(self._task.run)
        self._task.progress.connect(self.progress.emit)
        if on_done:
            self._task.finished.connect(on_done)
        if on_error:
            self._task.failed.connect(on_error)
        self._task.finished.connect(self._cleanup)
        self._task.failed.connect(self._cleanup)
        self._thread.start()
        self.busy_changed.emit(True)
        return True

    def stop(self):
        if self._task:
            self._task.stop()

    def _cleanup(self, *_):
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._task = None
        self.busy_changed.emit(False)
