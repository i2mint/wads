import re
from itertools import chain
import pkgutil
from warnings import warn
from functools import partial
import os
import subprocess

standard_lib_dir = os.path.dirname(os.__file__)
path_sep = os.path.sep


def ensure_slash_suffix(s: str):
    if not s.endswith(path_sep):
        s += path_sep
    return s


def ensure_no_slash_suffix(s: str):
    return s.rstrip(path_sep)


def _build_git_command(command: str = "status", work_tree=".", git_dir=None):
    if command.startswith("git "):
        warn(
            "You don't need to start your command with 'git '. I know it's a git command. Removing that prefix"
        )
        command = command[len("git ") :]
    work_tree = os.path.abspath(os.path.expanduser(work_tree))
    if git_dir is None:
        git_dir = os.path.join(work_tree, ".git")
    assert os.path.isdir(git_dir), f"Didn't find the git_dir: {git_dir}"
    git_dir = ensure_no_slash_suffix(git_dir)
    if not git_dir.endswith(".git"):
        warn(f"git_dir doesn't end with `.git`: {git_dir}")
    return f'git --git-dir="{git_dir}" --work-tree="{work_tree}" {command}'


def git(command: str = "status", work_tree=".", git_dir=None):
    """Launch git commands.

    :param command: git command (e.g. 'status', 'branch', 'commit -m "blah"', 'push', etc.)
    :param work_tree: The work_tree directory (i.e. where the project is)
    :param git_dir: The .git directory (usually, and by default, will be taken to be "{work_tree}/.git/"
    :return: What ever the command line returns (decoded to string)
    """

    """

    git --git-dir=/path/to/my/directory/.git/ --work-tree=/path/to/my/directory/ add myFile
    git --git-dir=/path/to/my/directory/.git/ --work-tree=/path/to/my/directory/ commit -m 'something'

    """
    command_str = _build_git_command(command, work_tree, git_dir)
    r = subprocess.check_output(command_str, shell=True)
    if isinstance(r, bytes):
        r = r.decode()
    return r.strip()


def is_standard_lib_path(path):
    return path.startswith(standard_lib_dir)


def standard_lib_module_names(
    is_standard_lib_path=is_standard_lib_path,
    name_filt=lambda name: not name.startswith("_"),
):
    return filter(
        name_filt,
        (
            module_info.name
            for module_info in pkgutil.iter_modules()
            if is_standard_lib_path(module_info.module_finder.path)
        ),
    )


def mk_conditional_logger(condition, func=print):
    if condition:
        return func
    else:

        def do_nothing(*args, **kwargs):
            pass

        return do_nothing


def clog(condition, func=print, *args, **kwargs):
    if condition:
        func(*args, **kwargs)


def mk_replacer_from_dict(from_to_dict):
    """Make a function that does multiple replacements (in a single pass).

    >>> r = mk_replacer_from_dict({'is': 'are', 'life': 'butterflies'})
    >>> r("There is no life in the void.")
    'There are no butterflies in the void.'

    :param from_to_dict: A dict of {to_find: to_replace_by,...} pairs
    :return: A replacer function that you can apply to strings to carry out the replacements
    """

    p = re.compile("|".join(map(r"({})".format, map(re.escape, from_to_dict.keys()))))
    f = lambda x: from_to_dict[x.group(0)]

    def replacer(s):
        return p.sub(f, s)

    return replacer


def mk_import_root_replacer(from_to_dict):
    """Make a function that does multiple import name replacements.

    For a use case, see replace_import_names. This is just a helper function.

    >>> replace = mk_import_root_replacer({'foo': 'FOO', 'bar': 'BAR'})
    >>>
    >>> assert replace('from foo import BLAH') == 'from FOO import BLAH'
    >>> assert replace('from foo.bar import BLAH') == 'from FOO.bar import BLAH'
    >>> assert replace('import bar') == 'import BAR'

    Partial matches are not replaced (that's a good thing!):

    >>> assert replace('import barmitzvah as oy') == 'import barmitzvah as oy'
    >>> assert replace('from foobar import hello') == 'from foobar import hello'

    Yes, and it works with dotpaths:

    >>> replace = mk_import_root_replacer({'where.it.was': 'where.it.is.now'})
    >>> replace('import where.it.was as here')
    'import where.it.is.now as here'

    :param from_to_dict: A dict of {to_find: to_replace_by,...} pairs
    :return: A replacer function that you can apply to strings to carry out the replacements

    r"""
    t = dict(
        chain.from_iterable(
            [
                (f"(?<=from\ ){old}(?=[\.\ ])", f"{new}"),
                (f"(?<=import\ ){old}(?=[\.\s])", f"{new}"),
            ]
            for old, new in from_to_dict.items()
        )
    )

    p = re.compile("|".join(map(r"({})".format, t.keys())))
    f = lambda x: from_to_dict[x.group(0)]

    def replacer(s):
        ss = p.sub(f, s + " ")
        return ss[:-1]

    return replacer


def replace_import_names(
    source_store,
    from_to_dict,
    target_store=None,
    dryrun=True,
    verbose=True,
    replacer_factory=mk_import_root_replacer,
    add_comment_at_the_end_of_lines_replaced=False,
):
    """Replace import names.

    Use case: You've renamed something or moved some modules (remember UNIX? Same as move!) and have to go through
    all your files and notebooks and replace those names.
    Now, if you have a nice IDE, we suggest you use refactoring instead -- as long as you have any uses in the scope.
    But sometimes it's not enough. You might have text/html documments, or jupyter notebooks, etc.
    So you can use this instead.

    Be warned though:
    - You should look at the pattern that is used to match, and make sure it won't create havoc.
    - Backup your documents so you can revert!
    - Print matches before you actually apply them all in bulk.
    - Use at your own risk!

    For examples, see the mk_import_root_replacer helper function.

    :param source_store:
    :param from_to_dict: A dict of {to_find: to_replace_by,...} pairs
    :param target_store: The store
    :param dryrun:
    :param verbose:
    :param replacer_factory: makes the replacer = replacer_factory(from_to_dict)
    :param add_comment_at_the_end_of_lines_replaced: True/False or an actual string to add at the end of replaced lines
    :return:
    """

    suffix = ""
    if add_comment_at_the_end_of_lines_replaced is False:
        suffix = ""
    elif add_comment_at_the_end_of_lines_replaced is True:
        suffix = "# line_was_edited_by_wads"
    elif isinstance(add_comment_at_the_end_of_lines_replaced, str):
        suffix = add_comment_at_the_end_of_lines_replaced
        if not suffix.startswith("#"):
            suffix = "# " + suffix
    else:
        raise TypeError(
            f"Don't know what to do with such a type of add_comment_at_the_end_of_lines_replaced: "
            f"{add_comment_at_the_end_of_lines_replaced}"
        )

    _clog = mk_conditional_logger(condition=verbose, func=print)

    if target_store is None:
        target_store = {}  # use a dict to write results
        _clog(
            "You didn't specify a target_store, so I'll write all of this in a dict and return it to you!"
        )

    if source_store == target_store:
        # TODO: Add confirmation (user input) to protect more. Make this an option (so total automatic is possible)
        _clog(
            "I just wanted you to be aware that you are using the same store for source and target."
            "This means I'm about to overwrite your files!!"
        )
        if dryrun:
            _clog("... Right now, dryrun=True, so I'm just pretending!")

    replacer = replacer_factory(from_to_dict)

    if dryrun:
        replace_prompt = "will replace"
    else:
        replace_prompt = "   replacing"
    with____prompt = "        with"

    for k, v in source_store.items():
        lines_replaced = 0

        def gen():
            nonlocal lines_replaced
            for i, line in enumerate(
                v.split("\n"), 1
            ):  # TODO: Double traversal. Find online splitter
                new_line = replacer(line) + suffix
                yield new_line
                if (
                    new_line != line
                ):  # TODO: Double traversal... could have replacer return a "replaced_something" flag
                    lines_replaced += 1
                    clog(
                        verbose or dryrun,
                        print,
                        f"{k}:{i}:\n{replace_prompt}\t{line}\n{with____prompt}\t{new_line}",
                    )

        new_v = "\n".join(gen())

        if not dryrun and lines_replaced > 0:
            target_store[k] = new_v

    return target_store


fc = dict(
    reset="\033[0m",  # alias for reset_all
    reset_all="\033[0m",
    bold="\033[1m",
    dim="\033[2m",
    underlined="\033[4m",
    blink="\033[5m",
    reverse="\033[7m",
    hidden="\033[8m",
    reset_bold="\033[21m",
    reset_dim="\033[22m",
    reset_underlined="\033[24m",
    reset_blink="\033[25m",
    reset_reverse="\033[27m",
    reset_hidden="\033[28m",
    default="\033[39m",
    black="\033[30m",
    red="\033[31m",
    green="\033[32m",
    yellow="\033[33m",
    blue="\033[34m",
    magenta="\033[35m",
    cyan="\033[36m",
    gray="\033[37m",
    dark_gray="\033[90m",
    dark_red="\033[91m",
    dark_green="\033[92m",
    dark_yellow="\033[93m",
    dark_blue="\033[94m",
    dark_magenta="\033[95m",
    dark_cyan="\033[96m",
    white="\033[97m",
    background_default="\033[49m",
    background_black="\033[40m",
    background_red="\033[41m",
    background_green="\033[42m",
    background_yellow="\033[43m",
    background_blue="\033[44m",
    background_magenta="\033[45m",
    background_cyan="\033[46m",
    background_gray="\033[47m",
    background_dark_gray="\033[100m",
    background_dark_red="\033[101m",
    background_dark_green="\033[102m",
    background_dark_yellow="\033[103m",
    background_dark_blue="\033[104m",
    background_dark_magenta="\033[105m",
    background_dark_cyan="\033[106m",
    background_white="\033[107m",
)

# Make a namespace out of the fc dict
from types import SimpleNamespace

fcc = SimpleNamespace(**fc)


def highlight(
    string,
    effect=fc["reverse"],
    beg_mark="[[",
    end_mark="]]",
    end_effect=fc["reset_all"],
):
    r"""Interprets a string's highlight markers to be able to make highlights in the string.

    This is meant for very simple situations. A more powerful and fast function could be made by
    using regular expressions and a map to map "codes" to "effects".

    Try this:

    >>> print(highlight("This is [[the section]] that is [[highlighted]]."))  # doctest:+SKIP

    Above, "reverse" is used as the default effect.
    But You can change that to bold blue ink on yellow background. That's three effects:
    1 (for bold), 34, for the blue foreground (ink), and 43 for the "yellow" (more like brown)
    background (paper).

    >>> my_string = "This is [[the section]] that is [[highlighted]]."
    >>> print(highlight(my_string, "\033[1;34;43m"))  # doctest:+SKIP

    \033[whaaaa?!? Yeah... well, either you do it that has-no-life-outside-unicode way.
    If so, Ansi help you!
    See [this wiki section](https://en.wikipedia.org/wiki/ANSI_escape_code#SGR_parameters).
    or [this tutorial](https://www.lihaoyi.com/post/BuildyourownCommandLinewithANSIescapecodes.html#rich-text).

    If not, we've prepared a map between human language and effect codes in the form of the
    `fc` variable of this module. It's a dict (and if you have ``py2store``, it's a mapping containing
    that dict and allowing you access through attributes too).

    >>> from wads.util import fc
    >>> list(fc)[20:25]
    ['magenta', 'cyan', 'gray', 'dark_gray', 'dark_red']

    :param string: String with highlight formatting
    :param effect: The effect to use for the highlighting (some unicode like "\033[21m")
    :param beg_mark: String that marks the beginning of the highlight
    :param end_mark: String that marks the end of the highlight
    :param end_effect: The unicode to use to reset the effect
    :return:
    """
    return string.replace(beg_mark, effect).replace(end_mark, end_effect)


# ------------------------------------------------------------------------------------ #
# A function to import objects from modules when we want to have a backup in case the
# object is not found in the first module.


def find_obj(*module_and_obj_names):
    """Find an object from specified modules, under specified names.

    This function searches for a specified object in a list of specified modules.
    It first tries to import the object from the first module specified, then the
    second, and so on, until it finds the object. If the object is not found in any
    of the specified modules, an ImportError is raised.

    Args:
        *module_and_obj_names: A list of pairs of module names and object names.
            The first module specified is searched first, then the second, and so on,
            until the object is found. Each module and object pair is specified as a
            tuple containing two strings. The first string is the module name, and the
            second string is the object name. Alternatively, the module and object pair
            can be specified as a single string containing two space-separated strings,
            where the first string is the module name and the second string is the
            object name.

    Returns:
        The imported object.

    Raises:
        ImportError: If the object cannot be found in any of the specified modules.

    >>> files = find_obj('importlib.resources files', 'importlib_resources files')
    >>> callable(files)
    True
    >>> find_obj(
    ...     'importlib no_such_obj', 'no_such_pkg x', ['wave.no_such_module', 'y']
    ... ) # doctest: +NORMALIZE_WHITESPACE
    Traceback (most recent call last):
    ...
    ImportError: All of these import attempts failed:
        from importlib import no_such_obj
        from no_such_pkg import x
        from wave.no_such_module import y

    See discussion: https://github.com/i2mint/wads/discussions/10.
    """
    module_and_obj_names = list(map(_ensure_pair, module_and_obj_names))
    for module_name, obj_name in module_and_obj_names:
        try:
            return import_obj(module_name, obj_name)
        except (ImportError, ModuleNotFoundError, AttributeError):
            continue
    from_import_statements = "\n\t" + "\n\t".join(
        map("from {} import {}".format, *zip(*module_and_obj_names))
    )
    raise ImportError(f"All of these import attempts failed:{from_import_statements}")


def import_obj(module_name: str, obj_name: str):
    """Import an object from a specified module.

    Args:
        from_ (str): The name of the module to import from.
        obj_name (str): The name of the object to import.

    Returns:
        The imported object.

    Raises:
        ImportError: If the module or object cannot be imported.
        AttributeError: If the object does not exist in the module.

    >>> spec_finder = import_obj('importlib.util', 'find_spec')
    >>> callable(spec_finder)
    True
    >>> spec_finder.__module__
    'importlib.util'

    """
    module = __import__(module_name, fromlist=[obj_name])
    obj = getattr(module, obj_name)
    return obj


def _ensure_pair(x):
    if isinstance(x, str):
        x = x.split()
    assert len(x) == 2, f"should be a pair of strings: {x}"
    return x
