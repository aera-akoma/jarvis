from pathlib import Path


def test_cryptography_runtime_bindings_are_declared_for_pyinstaller():
    spec = Path(__file__).resolve().parents[1] / 'jarvis.spec'
    source = spec.read_text(encoding='utf-8')

    assert 'cryptography.hazmat.bindings._rust' in source
