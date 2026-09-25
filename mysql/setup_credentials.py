"""Create local test credentials once, without printing or overwriting secrets."""

import os
from pathlib import Path
import secrets


def main() -> None:
    path = Path(__file__).resolve().parents[1] / '.mysql.env'
    contents = (
        'MYSQL_DATABASE=philiplessner_logs_test\n'
        'MYSQL_USER=logs_test\n'
        f'MYSQL_PASSWORD={secrets.token_hex(32)}\n'
        f'MYSQL_ROOT_PASSWORD={secrets.token_hex(32)}\n'
    )
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f'Keeping existing credentials: {path}')
        return
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(contents)
    print(f'Created credentials: {path} (owner read/write only)')


if __name__ == '__main__':
    main()
