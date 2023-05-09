import subprocess
import sys
import tarfile
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

        subprocess.check_output(
            [sys.executable, 'setup.py', 'sdist'], cwd=output_path,
        )
        i2_whl = next((output_path / 'dist').glob('i2-*.whl'))
        assert i2_whl, 'wheel not built from specified git repo'
        module_tar_gz = next((output_path / 'dist').glob('*.tar.gz'))
        assert module_tar_gz.is_file()
        with tarfile.open(module_tar_gz, 'r:gz') as tar:
            tar.extractall(tmp_path / 'unpacked')
        unpacked_dist = (
            tmp_path / 'unpacked' / module_tar_gz.name[: -len('.tar.gz')] / 'dist'
        )
        unpacked_i2_whl = next(unpacked_dist.glob('i2-*.whl'))
        assert (
            unpacked_i2_whl.read_bytes() == i2_whl.read_bytes()
        ), '.tar.gz does not include dependency wheel'
