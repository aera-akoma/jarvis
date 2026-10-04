"""Load the bundled Windows C++ runtime before Qt to avoid DLL version clashes."""

import ctypes
import os
import sys


if sys.platform == "win32" and hasattr(sys, "_MEIPASS"):
    _pyside_dir = os.path.join(sys._MEIPASS, "PySide6")
    _shiboken_dir = os.path.join(sys._MEIPASS, "shiboken6")
    _dll_directory_handles = []
    _loaded_runtime_libraries = []

    # Set the bundled Qt directory ahead of system DLL search locations.
    ctypes.windll.kernel32.SetDllDirectoryW(_pyside_dir)
    for _directory in (_pyside_dir, _shiboken_dir):
        if os.path.isdir(_directory):
            _dll_directory_handles.append(os.add_dll_directory(_directory))

    # These are shipped with the PySide6 wheel. Preloading by absolute path
    # prevents Windows from binding Qt to an older system-wide VC runtime.
    for _name in (
        "MSVCP140.dll",
        "MSVCP140_1.dll",
        "MSVCP140_2.dll",
        "VCRUNTIME140.dll",
        "VCRUNTIME140_1.dll",
    ):
        _path = os.path.join(_pyside_dir, _name)
        if os.path.isfile(_path):
            _loaded_runtime_libraries.append(ctypes.WinDLL(_path))

    for _name in ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll"):
        _path = os.path.join(_pyside_dir, _name)
        if os.path.isfile(_path):
            _loaded_runtime_libraries.append(ctypes.WinDLL(_path))
