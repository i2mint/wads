"""Handle non python installs, depending on the system"""

# TODO: Instead of os.system, use subprocess.run?

from typing import Iterable, Callable, NewType, Union

InstallCommand = NewType("InstallCommand", str)
InstallCommandsStr = NewType("InstallCommandsStr", str)
InstallCommands = Union[InstallCommand, InstallCommandsStr, Iterable[InstallCommand]]


# TODO: Tried to make return_annotation InstallCommandsStr, but linter complained
def ensure_new_line_separated_strings(strings: InstallCommands, sep="\n") -> str:
    if isinstance(strings, str):
        return strings
    assert isinstance(strings, Iterable), f"Not an iterable: {strings}"
    return sep.join(strings)


# TODO: Tried to make return_annotation Iterable[InstallCommand], but linter complained
def ensure_iterable_of_strings(strings, sep="\n") -> Iterable[str]:
    if isinstance(strings, str):
        return strings.split(sep)
    assert isinstance(strings, Iterable), f"Not an iterable: {strings}"
    return strings


def make_install_instructions_for_readme(commands_for_os: dict) -> str:
    """

    :param commands_for_os: A dictionary containing the commands for each OS,
    where the keys are the OS names (as in ``os.name``) and the values are the
    commands, in the form of a string that can be passed to ``os.system`` to be
    executed.
    :return: A string that can included in the "How to install" section of a README.md,
    which will contain the instructions for the user to install the package,
    listing the commands for each OS.

    >>> make_install_instructions_for_readme({'Linux': 'pip install .'})
    '### Linux\\n\\n```\\npip install .\\n```\\n'

    """
    return "\n".join(
        f"### {os_name}\n\n"
        f"```\n"
        f"{ensure_new_line_separated_strings(commands)}\n"
        f"```\n"
        for os_name, commands in commands_for_os.items()
    )


def make_install_instructions_for_ci(commands_for_os: dict) -> str:
    """

    :param commands_for_os: A dictionary containing the commands for each OS,
    where the keys are the OS names (as in ``os.name``) and the values are the
    commands, in the form of a list of strings that can be passed to ``os.system`` to be
    executed.
    :return: A string that can included in a github actions ci.yml file,
    which will contain the os specific commands to install the package.

    >>> make_install_instructions_for_ci({'Linux': ['pip install .']})
    '- name: Install on Linux\\n  run: |\\n    pip install .\\n'

    """
    return "\n".join(
        f"- name: Install on {os_name}\n"
        f"  run: |\n"
        f"    {ensure_new_line_separated_strings(commands)}\n"
        for os_name, commands in commands_for_os.items()
    )


def warn_about_error(command, error_obj):
    from warnings import warn

    warn(f"Failed to run command: {command}.\nError: {error_obj}")
    return True


def raise_error(command, error_obj):
    raise RuntimeError(f"Failed to run command: {command}.\nError: {error_obj}")


def run_install_commands(
    commands_for_os: dict,
    on_error: Callable[[InstallCommand, Exception], None] = warn_about_error,
):
    """

    :param commands_for_os: A dictionary containing the commands for each OS,
    where the keys are the OS names (as in ``os.name``) and the values are the
    commands, in the form of a list of strings that can be passed to ``os.system`` to be
    executed.
    :param on_error: A function that will be called if an error occurs when running a
    command. The function should take two arguments: the command that failed to run,
    and the error object. The function should return a boolean indicating whether to
    continue running the commands or not.

    """
    import os

    os_name = os.name
    if os_name not in commands_for_os:
        raise ValueError(f"OS not supported: {os_name}")

    commands = commands_for_os[os_name]

    for command in commands:
        try:
            os.system(command)
        except Exception as e:
            if on_error(command, e):
                continue
            else:
                break
