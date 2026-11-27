"""Собрать исходники Mediary для локального запуска на другом компьютере."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRS = ('config', 'diary', 'static', 'templates', 'docs', 'scripts', 'browser_tests')
ROOT_FILES = (
    'manage.py',
    'README.md',
    'requirements.txt',
    'requirements-dev.txt',
    'package.json',
    'package-lock.json',
    'pyproject.toml',
    '.gitignore',
    '.editorconfig',
)


def source_files():
    for name in ROOT_FILES:
        yield ROOT / name
    for name in SOURCE_DIRS:
        for path in sorted((ROOT / name).rglob('*')):
            if path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts:
                if path.suffix not in ('.pyc', '.log', '.sqlite3'):
                    yield path


def main():
    parser = argparse.ArgumentParser(description='Собрать архив исходников Mediary.')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / 'Mediary.zip')
    args = parser.parse_args()
    output = args.output.resolve()
    files = list(source_files())
    if output in files:
        parser.error('Архив должен находиться вне каталогов исходников.')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + '.tmp')
    try:
        with ZipFile(temporary, 'w', compression=ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, 'Mediary/' + path.relative_to(ROOT).as_posix())
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'Архив готов: {output}')
    print(f'Файлов: {len(files)}')


if __name__ == '__main__':
    main()
