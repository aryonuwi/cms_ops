#!/usr/bin/env python
"""Django command-line utility.

Defaults to the development settings; production processes set
DJANGO_SETTINGS_MODULE=config.settings.production explicitly.
"""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Is the virtualenv activated?"
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
