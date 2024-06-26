from __future__ import annotations
import sys
import sphinx
import inspect
import subprocess
from pathlib import Path
from functools import cached_property
from sphinx.application import Sphinx
from sphinx.errors import ExtensionError, SphinxError
from typing import Dict, Any, Optional, Callable, TYPE_CHECKING
from docutils import nodes
from sphinx import addnodes
from sphinx.locale import _


if TYPE_CHECKING:
    from docutils.nodes import Node
    from sphinx.application import Sphinx


__version__ = "1.2.0"
__author__ = 'Adam Korn <hello@dailykitten.net>'

from .add_linkcode_class import add_linkcode_node_class
from .github_style import GitHubStyle
from .lexer import GitHubLexer

class LinkcodeError(SphinxError):
    category = "linkcode error"


def doctree_read(app: Sphinx, doctree: Node) -> None:
    env = app.builder.env

    resolve_target = getattr(env.config, 'linkcode_resolve', None)
    if not callable(env.config.linkcode_resolve):
        msg = 'Function `linkcode_resolve` is not given in conf.py'
        raise LinkcodeError(msg)
    assert resolve_target is not None  # for mypy

    domain_keys = {
        'py': ['module', 'fullname'],
        'c': ['names'],
        'cpp': ['names'],
        'js': ['object', 'fullname'],
    }

    for objnode in list(doctree.findall(addnodes.desc)):
        domain = objnode.get('domain')
        uris: set[str] = set()
        for signode in objnode:
            if not isinstance(signode, addnodes.desc_signature):
                continue

            # Convert signode to a specified format
            info = {}
            for key in domain_keys.get(domain, []):
                value = signode.get(key)
                if not value:
                    value = ''
                info[key] = value
            if not info:
                continue

            # Call user code to resolve the link
            uri = resolve_target(domain, info)
            if not uri:
                # no source
                continue

            if uri in uris or not uri:
                # only one link per name, please
                continue
            uris.add(uri)

            inline = nodes.inline('', _('[source]'), classes=['viewcode-link'])
            # this does not work for markdown builder
            # onlynode = addnodes.only(expr='html')
            # onlynode += nodes.reference('', '', inline, internal=False, refuri=uri)
            onlynode = nodes.reference('', '', inline, internal=False, refuri=uri)
            signode += onlynode


def setup(app: Sphinx) -> Dict[str, Any]:
    app.connect("builder-inited", add_static_path)
    app.add_config_value('linkcode_blob', 'head', True)

    linkcode_blob = get_conf_val(app, "linkcode_blob")
    linkcode_url = get_linkcode_url(
        blob=get_linkcode_revision(linkcode_blob),
        url=get_conf_val(app, 'linkcode_url'),
        context=get_conf_val(app, 'html_context'),
    )
    linkcode_func = get_conf_val(app, "linkcode_resolve")
    repo_dir = get_repo_dir()

    if not callable(linkcode_func):
        print(
            "Function `linkcode_resolve` not found in ``conf.py``; "
            "using default function from ``sphinx_github_style``"
        )
        linkcode_func = get_linkcode_resolve(linkcode_url, repo_dir)
        set_conf_val(app, 'linkcode_resolve', linkcode_func)

    app.setup_extension('sphinx_github_style.add_linkcode_class')
    app.setup_extension('sphinx_github_style.github_style')
    # app.setup_extension('sphinx.ext.linkcode')
    # app.setup_extension('sphinx.ext.custom_linkcode')
    app.connect('doctree-read', doctree_read)
    app.add_config_value('linkcode_resolve', None, '')
    app.add_lexer('python', GitHubLexer)

    return {'version': sphinx.__display_version__, 'parallel_read_safe': True}


def add_static_path(app) -> None:
    """Add the path for the ``_static`` folder"""
    app.config.html_static_path.append(
        str(Path(__file__).parent.joinpath("_static").absolute())
    )


def get_linkcode_revision(blob: str) -> str:
    """Get the blob to link to on GitHub

    .. note::

       The value of ``blob`` can be any of ``"head"``, ``"last_tag"``, or ``"{blob}"``

       * ``head`` (default): links to the most recent commit hash; if this commit is tagged, uses the tag instead
       * ``last_tag``: links to the most recent commit tag on the currently checked out branch
       * ``blob``: links to any blob you want, for example ``"master"`` or ``"v2.0.1"``
    """
    if blob == "head":
        return get_head()
    if blob == 'last_tag':
        return get_last_tag()
    # Link to the branch/tree/blob you provided, ex. "master"
    return blob


def get_head() -> str:
    """Gets the most recent commit hash or tag

    :return: The SHA or tag name of the most recent commit, or "master" if the call to git fails.
    """
    cmd = "git log -n1 --pretty=%H"
    try:
        # get most recent commit hash
        head = subprocess.check_output(cmd.split()).strip().decode('utf-8')

        # if head is a tag, use tag as reference
        cmd = "git describe --exact-match --tags " + head
        try:
            tag = subprocess.check_output(cmd.split(" ")).strip().decode('utf-8')
            return tag

        except subprocess.CalledProcessError:
            return head

    except subprocess.CalledProcessError:
        print("Failed to get head")  # so no head?
        return "master"


def get_last_tag() -> str:
    """Get the most recent commit tag on the currently checked out branch

    :raises ExtensionError: if no tags exist on the branch
    """
    try:
        cmd = "git describe --tags --abbrev=0"
        return subprocess.check_output(cmd.split(" ")).strip().decode('utf-8')

    except subprocess.CalledProcessError:
        raise ExtensionError("``sphinx-github-style``: no tags found on current branch")


def get_linkcode_url(blob: Optional[str] = None, context: Optional[Dict] = None, url: Optional[str] = None) -> str:
    """Get the template URL for linking to highlighted GitHub source code with :mod:`sphinx.ext.linkcode`

    Formatted into the final link by a ``linkcode_resolve()`` function

    :param blob: The Git blob to link to
    :param context: The :external+sphinx:confval:`html_context` dictionary
    :param url: The base URL of the repository (ex. ``https://github.com/TDKorn/sphinx-github-style``)
    """
    if url is None:
        if context is None or not all(context.get(key) for key in ("github_user", "github_repo")):
            raise ExtensionError(
                "sphinx-github-style: config value ``linkcode_url`` is missing")
        else:
            print(
                "sphinx-github-style: config value ``linkcode_url`` is missing. "
                "Creating link from ``html_context`` values..."
            )
            url = f"https://github.com/{context['github_user']}/{context['github_repo']}"

    blob = get_linkcode_revision(blob) if blob else context.get('github_version')

    if blob is not None:
        url = url.strip("/") + f"/blob/{blob}/"  # URL should be "https://github.com/user/repo"
    else:
        raise ExtensionError(
            "sphinx-github-style: must provide a blob or GitHub version to link to")

    return url + "{filepath}#L{linestart}-L{linestop}"


def get_linkcode_resolve(linkcode_url: str, repo_dir: Optional[Path] = None) -> Callable:
    """Defines and returns a ``linkcode_resolve`` function for your package

    Used by default if ``linkcode_resolve`` isn't defined in ``conf.py``

    :param linkcode_url: The template URL to use when resolving cross-references with :mod:`sphinx.ext.linkcode`
    :param repo_dir: The root directory of the Git repository.
    """
    if repo_dir is None:
        repo_dir = get_repo_dir()

    def linkcode_resolve(domain, info):
        """Returns a link to the source code on GitHub, with appropriate lines highlighted

        :By:
            Adam Korn (https://github.com/tdkorn)
        :Adapted From:
            nlgranger/SeqTools (https://github.com/nlgranger/seqtools/blob/master/docs/conf.py)
        """
        if domain != 'py' or not info['module']:
            return None

        modname = info['module']
        fullname = info['fullname']

        submod = sys.modules.get(modname)
        if submod is None:
            return None

        obj = submod
        for part in fullname.split('.'):
            try:
                obj = getattr(obj, part)
            except AttributeError:
                return None

        if isinstance(obj, property):
            obj = obj.fget
        elif isinstance(obj, cached_property):
            obj = obj.func

        try:
            modpath = inspect.getsourcefile(inspect.unwrap(obj))
            filepath = Path(modpath).relative_to(repo_dir)
            if filepath is None:
                return
        except Exception:
            return None

        try:
            source, lineno = inspect.getsourcelines(obj)
        except Exception:
            return None

        linestart, linestop = lineno, lineno + len(source) - 1

        # Example: https://github.com/TDKorn/my-magento/blob/docs/magento/models/model.py#L28-L59
        final_link = linkcode_url.format(
            filepath=filepath.as_posix(),
            linestart=linestart,
            linestop=linestop
        )
        print(f"Final Link for {fullname}: {final_link}")
        return final_link

    return linkcode_resolve


# EXAMPLE START
def get_repo_dir() -> Path:
    """Returns the root directory of the repository

    :return: A Path object representing the working directory of the repository.
    """
    try:
        cmd = "git rev-parse --show-toplevel"
        repo_dir = Path(subprocess.check_output(cmd.split(" ")).strip().decode('utf-8'))

    except subprocess.CalledProcessError as e:
        raise RuntimeError("Unable to determine the repository directory") from e

    return repo_dir
# EXAMPLE END


def get_conf_val(app: Sphinx, attr: str, default: Optional[Any] = None) -> Any:
    """Retrieve the value of a ``conf.py`` config variable

    :param attr: the config variable to retrieve
    :param default: the default value to return if the variable isn't found
    """
    return app.config._raw_config.get(attr, getattr(app.config, attr, default))


def set_conf_val(app: Sphinx, attr: str, value: Any) -> None:
    """Set the value of a ``conf.py`` config variable

    :param attr: the config variable to set
    :param value: the variable value
    """
    app.config._raw_config[attr] = value
    setattr(app.config, attr, value)
