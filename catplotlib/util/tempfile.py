import os
import weakref
import shutil
import warnings
from tempfile import NamedTemporaryFile
from tempfile import gettempdir
from glob import glob

class NamedTemporaryDirectory:

    def __init__(self, name):
        os.makedirs(name, exist_ok=True)
        self.name = name
        self._finalizer = weakref.finalize(
            self, self._cleanup, self.name,
            warn_message="Implicitly cleaning up {!r}".format(self))

    @classmethod
    def _cleanup(cls, name, warn_message):
        try:
            shutil.rmtree(name)
            warnings.warn(warn_message, ResourceWarning)
        except:
            pass

    def __repr__(self):
        return "<{} {!r}>".format(self.__class__.__name__, self.name)


class TempFileManager:
    
    _temp_dir = None
    _name = os.path.join(gettempdir(), "catplotlib_temp")
    _no_cleanup = []

    def __init__(self):
        raise RuntimeError("Not instantiable")

    @staticmethod
    def delete_on_exit():
        TempFileManager._temp_dir = NamedTemporaryDirectory(TempFileManager._name)

    @staticmethod
    def cleanup(pattern="*"):
        '''
        Manually cleans up files in the catplotlib temp directory matching the
        specified glob pattern, or all files by default. Remaining files will still
        be deleted when the interpreter exits.

        Arguments:
        'pattern' -- the file pattern to delete, or all files by default.
        '''
        for fn in glob(os.path.join(TempFileManager._name, pattern)):
            if fn not in TempFileManager._no_cleanup: 
                try:
                    os.remove(fn)
                except:
                    pass

    @staticmethod
    def mktmp(no_manual_cleanup=False, **kwargs):
        '''
        Gets a unique temporary file name located in the catplotlib temp directory.
        Accepts any arguments supported by NamedTemporaryFile. Temporary files will be
        deleted when the interpreter exits.

        Arguments:
        'no_manual_cleanup' -- prevents this file from being deleted by calls to
            TempFileManager.cleanup()
        '''
        os.makedirs(TempFileManager._name, exist_ok=True)
        temp_file_name = NamedTemporaryFile("w", dir=TempFileManager._name, delete=False, **kwargs).name
        if no_manual_cleanup:
            TempFileManager._no_cleanup.append(temp_file_name)

        return temp_file_name
