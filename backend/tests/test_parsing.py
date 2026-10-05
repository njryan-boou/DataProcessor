import pytest

from app.config import Settings
from app.services.parsing import parse_upload
from app.utils.errors import DataFlowError


def test_csv_parses_types_missing_and_quoted_fields():
    name, frame = parse_upload('../../sales.csv', b'age,name\n20,"Doe, Jane"\n,Sam\n', Settings())
    assert name == 'sales.csv'
    assert frame.shape == (2, 2)
    assert frame['age'].isna().sum() == 1
    assert frame.iloc[0]['name'] == 'Doe, Jane'


@pytest.mark.parametrize('data', [b'', b'age\n', b'a,a\n1,2\n', b'a,b\n1\n', b'a,b\n"unterminated,2', b'a\n\xff', b'a\n\x00', b'a\ninf'])
def test_invalid_csv_rejected(data):
    with pytest.raises(DataFlowError):
        parse_upload('data.csv', data, Settings())


def test_size_and_row_limits():
    with pytest.raises(DataFlowError) as error:
        parse_upload('data.csv', b'a\n' + b'x' * 1024 * 1024, Settings(max_upload_mb=1))
    assert error.value.status_code == 413
    with pytest.raises(DataFlowError):
        parse_upload('data.csv', b'a\n1\n2', Settings(max_rows=1))


def test_unsupported_file():
    with pytest.raises(DataFlowError) as error:
        parse_upload('data.xlsx', b'hello', Settings())
    assert error.value.code == 'unsupported_file'
