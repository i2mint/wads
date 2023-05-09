import subprocess
import sys
import tempfile
from pathlib import Path

from wads.package_module import generate_package

EXAMPLE_MODULE = Path(__file__).parent / 'data' / 'example_module.py'


def test_generate_package():

    with tempfile.TemporaryDirectory() as tmp_folder:
        tmp_path = Path(tmp_folder)
        output_path = tmp_path / 'output'
        generate_package(
            module_path=EXAMPLE_MODULE,
            install_requires=['dol', 'i2 @ git+ssh://git@github.com/i2mint/i2.git'],
            output_path=output_path,
            version='8.8.8',
        )
        i2_whl = next((output_path / 'dist').glob('i2*-.whl'))
        assert i2_whl, 'wheel not built from specified git repo'

        subprocess.check_output(
            [sys.executable, 'setup.py', 'sdist'], cwd=output_path,
        )
        module_tar_gz = next((output_path / 'dist').glob('*.tar.gz'))

        assert len(i2_whl.read_bytes()) < len(
            module_tar_gz.read_bytes()
        ), '.tar.gz does not include dependency wheel'
