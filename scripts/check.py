"""Единая точка запуска проверок; используется Python текущего окружения."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description='Проверить код и тесты Mediary.')
    parser.add_argument('--browser', action='store_true', help='Также запустить браузерные тесты.')
    parser.add_argument(
        '--browser-channel',
        choices=['chromium', 'msedge', 'chrome'],
        default='chromium',
        help='Использовать установленный браузер вместо Chromium Playwright.',
    )
    args = parser.parse_args()
    commands = [
        ['-m', 'ruff', 'check', '.'],
        ['-m', 'ruff', 'format', '--check', '.'],
        ['manage.py', 'check'],
        ['manage.py', 'makemigrations', '--check', '--dry-run'],
        ['manage.py', 'test', 'diary'],
    ]
    env = os.environ.copy()
    if args.browser:
        commands.append(['manage.py', 'test', 'browser_tests'])
        env['MEDIARY_BROWSER_CHANNEL'] = (
            '' if args.browser_channel == 'chromium' else args.browser_channel
        )
    try:
        for command in commands:
            print('> python ' + ' '.join(command), flush=True)
            subprocess.run([sys.executable, *command], cwd=ROOT, env=env, check=True)
    except subprocess.CalledProcessError as error:
        return error.returncode
    return 0


if __name__ == '__main__':
    sys.exit(main())
