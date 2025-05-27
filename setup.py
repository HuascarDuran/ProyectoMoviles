from setuptools import setup

APP = ['main.py']
DATA_FILES = [
    ('utils', ['utils/config.json', 'utils/schedule_config.json'])
]
OPTIONS = {
    'argv_emulation': True,
    'packages': ['PyQt5'],
    'includes': ['sip'],
    'iconfile': None  # Si tienes un ícono, pon aquí el nombre: 'icon.icns'
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)