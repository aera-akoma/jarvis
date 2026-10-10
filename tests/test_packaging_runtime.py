from pathlib import Path


def test_cryptography_runtime_bindings_are_declared_for_pyinstaller():
    spec = Path(__file__).resolve().parents[1] / 'jarvis.spec'
    source = spec.read_text(encoding='utf-8')

    assert 'cryptography.hazmat.bindings._rust' in source


def test_nsis_installer_dist_root_can_be_overridden_for_fresh_builds():
    installer = Path(__file__).resolve().parents[1] / 'installer' / 'installer.nsi'
    source = installer.read_text(encoding='utf-8')

    assert '!ifndef DIST_ROOT' in source
    assert 'File /r "${APP_DIST}\\*"' in source
    assert 'OutFile "${DIST_ROOT}\\Jarvis-Setup.exe"' in source
