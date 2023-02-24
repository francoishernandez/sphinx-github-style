import types
from typing import Type
from sphinx.application import Sphinx
from pygments.lexers.python import NumPyLexer
from inspect import getmembers, isfunction, ismethod, ismodule, isclass
from sphinx.errors import ExtensionError


def get_pkg_funcs(pkg: types.ModuleType):
    # Get funcs/meths defined in pkg.__init__
    funcs_meths = get_funcs(pkg)
    modules = getmembers(pkg, ismodule)
    # Get funcs/meths of each module in pkg
    for name, module in modules:
        funcs_meths += get_funcs(module)
        classes = getmembers(module, isclass)
        for class_name, _class in classes:
            funcs_meths += get_funcs(_class)
    # Set of all funcs/meths contained in modules used by package
    return set(funcs_meths)


def get_funcs(of):
    members = getmembers(of, isfunction or ismethod)
    return list(dict(members))


class TDKMethLexer(NumPyLexer):
    """Adds syntax highlighting for methods and functions within a python Package

    """
    name = 'TDK'
    url = 'https://github.com/TDKorn'
    aliases = ['tdk']

    EXTRA_KEYWORDS = {}

    @classmethod
    def get_pkg_lexer(cls, pkg_name: str) -> Type["TDKMethLexer"]:
        pkg = __import__(pkg_name)
        funcs = get_pkg_funcs(pkg)
        cls.EXTRA_KEYWORDS = funcs
        return cls


def setup(app: Sphinx):
    pkg_name = app.config._raw_config.get("pkg_name", getattr(app.config, "pkg_name"))
    if pkg_name is None:
        raise ExtensionError("`pkg_name` is missing from conf.py")
    app.add_lexer('python', TDKMethLexer.get_pkg_lexer(pkg_name))
