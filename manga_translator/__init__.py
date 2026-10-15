import importlib
import importlib.util

import colorama
from dotenv import load_dotenv

colorama.init(autoreset=True)
load_dotenv()

# The translation pipeline pulls in torch, OCR and detection models (~15s to import).
# Load it on first use so light consumers such as the web server, which only needs
# Config/Context, start quickly. `from manga_translator import X` keeps working.
_LIGHT_EXPORTS = {
    'Config': '.config',
    'Context': '.utils.generic',
}


def __getattr__(name):
    if name in _LIGHT_EXPORTS:
        return getattr(importlib.import_module(_LIGHT_EXPORTS[name], __name__), name)
    if name.startswith('__'):
        raise AttributeError(name)
    # `from manga_translator import <submodule>` (e.g. translators/chatgpt.py) must get the module itself
    if importlib.util.find_spec(f'{__name__}.{name}') is not None:
        return importlib.import_module(f'.{name}', __name__)
    pipeline = importlib.import_module('.manga_translator', __name__)
    try:
        return getattr(pipeline, name)
    except AttributeError:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}') from None
