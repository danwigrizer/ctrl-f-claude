from setuptools import setup

APP = ['app.py']
DATA_FILES = ['index.html']
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'icon.icns',
    'plist': {
        'CFBundleName': 'CTRL+F+Claude',
        'CFBundleDisplayName': 'CTRL+F+Claude',
        'CFBundleIdentifier': 'com.local.ctrl-f-claude',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
    },
    'packages': ['webview'],
    'includes': ['api'],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
