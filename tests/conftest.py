import pytest

from menu_reader_lab.generate import generate_dataset


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory):
    """Um cardápio de cada estilo, gerado uma vez por sessão de testes."""
    path = tmp_path_factory.mktemp("synthetic")
    generate_dataset(path, n=10, seed=3)
    return path
