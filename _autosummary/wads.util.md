# wads.util

wads util

### Functions

| `clog`(condition[, func])                                                                         |                                                                                      |
|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| `ensure_no_slash_suffix`(s)                                                                       |                                                                                      |
| `ensure_slash_suffix`(s)                                                                          |                                                                                      |
| [`find_obj`](#wads.util.find_obj)(\*module_and_obj_names)                 | Find an object from specified modules, under specified names.                        |
| [`git`](#wads.util.git)([command, work_tree, git_dir])               | Launch git commands.                                                                 |
| [`highlight`](#wads.util.highlight)(string[, effect, beg_mark, ...])       | Interprets a string's highlight markers to be able to make highlights in the string. |
| [`import_obj`](#wads.util.import_obj)(module_name, obj_name)                | Import an object from a specified module.                                            |
| `is_standard_lib_path`(path)                                                                      |                                                                                      |
| `mk_conditional_logger`(condition[, func])                                                        |                                                                                      |
| [`mk_import_root_replacer`](#wads.util.mk_import_root_replacer)(from_to_dict)            | Make a function that does multiple import name replacements.                         |
| [`mk_replacer_from_dict`](#wads.util.mk_replacer_from_dict)(from_to_dict)              | Make a function that does multiple replacements (in a single pass).                  |
| [`replace_import_names`](#wads.util.replace_import_names)(source_store, from_to_dict) | Replace import names.                                                                |
| `standard_lib_module_names`([...])                                                                |                                                                                      |

### wads.util.find_obj(\*module_and_obj_names)

Find an object from specified modules, under specified names.

This function searches for a specified object in a list of specified modules.
It first tries to import the object from the first module specified, then the
second, and so on, until it finds the object. If the object is not found in any
of the specified modules, an ImportError is raised.

* **Parameters:**
  **\*module_and_obj_names** – A list of pairs of module names and object names.
  The first module specified is searched first, then the second, and so on,
  until the object is found. Each module and object pair is specified as a
  tuple containing two strings. The first string is the module name, and the
  second string is the object name. Alternatively, the module and object pair
  can be specified as a single string containing two space-separated strings,
  where the first string is the module name and the second string is the
  object name.
* **Returns:**
  The imported object.
* **Raises:**
  [**ImportError**](https://docs.python.org/3/builtins/exceptions.html#ImportError) – If the object cannot be found in any of the specified modules.

```pycon
>>> files = find_obj('importlib.resources files', 'importlib_resources files')
>>> callable(files)
True
>>> find_obj(
...     'importlib no_such_obj', 'no_such_pkg x', ['wave.no_such_module', 'y']
... )
Traceback (most recent call last):
...
ImportError: All of these import attempts failed:
    from importlib import no_such_obj
    from no_such_pkg import x
    from wave.no_such_module import y
```

See discussion: [https://github.com/i2mint/wads/discussions/10](https://github.com/i2mint/wads/discussions/10).

### wads.util.git(command='status', work_tree='.', git_dir=None)

Launch git commands.

* **Parameters:**
  * **command** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – git command (e.g. ‘status’, ‘branch’, ‘commit -m “blah”’, ‘push’, etc.)
  * **work_tree** – The work_tree directory (i.e. where the project is)
  * **git_dir** – The .git directory (usually, and by default, will be taken to be “{work_tree}/.git/”
* **Returns:**
  What ever the command line returns (decoded to string)

### wads.util.highlight(string, effect='\\x1b[7m', beg_mark='[[', end_mark=']]', end_effect='\\x1b[0m')

Interprets a string’s highlight markers to be able to make highlights in the string.

This is meant for very simple situations. A more powerful and fast function could be made by
using regular expressions and a map to map “codes” to “effects”.

Try this:

```pycon
>>> print(highlight("This is [[the section]] that is [[highlighted]]."))
```

Above, “reverse” is used as the default effect.
But You can change that to bold blue ink on yellow background. That’s three effects:
1 (for bold), 34, for the blue foreground (ink), and 43 for the “yellow” (more like brown)
background (paper).

```pycon
>>> my_string = "This is [[the section]] that is [[highlighted]]."
>>> print(highlight(my_string, "\033[1;34;43m"))
```

033[whaaaa?!? Yeah… well, either you do it that has-no-life-outside-unicode way.
If so, Ansi help you!
See [this wiki section](https://en.wikipedia.org/wiki/ANSI_escape_code#SGR_parameters).
or [this tutorial](https://www.lihaoyi.com/post/BuildyourownCommandLinewithANSIescapecodes.html#rich-text).

If not, we’ve prepared a map between human language and effect codes in the form of the
`fc` variable of this module. It’s a dict (and if you have `py2store`, it’s a mapping containing
that dict and allowing you access through attributes too).

```pycon
>>> from wads.util import fc
>>> list(fc)[20:25]
['magenta', 'cyan', 'gray', 'dark_gray', 'dark_red']
```

* **Parameters:**
  * **string** – String with highlight formatting
  * **effect** – The effect to use for the highlighting (some unicode like “033[21m”)
  * **beg_mark** – String that marks the beginning of the highlight
  * **end_mark** – String that marks the end of the highlight
  * **end_effect** – The unicode to use to reset the effect
* **Returns:**

### wads.util.import_obj(module_name, obj_name)

Import an object from a specified module.

* **Parameters:**
  * **from** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – The name of the module to import from.
  * **obj_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The name of the object to import.
* **Returns:**
  The imported object.
* **Raises:**
  * [**ImportError**](https://docs.python.org/3/builtins/exceptions.html#ImportError) – If the module or object cannot be imported.
  * [**AttributeError**](https://docs.python.org/3/builtins/exceptions.html#AttributeError) – If the object does not exist in the module.

```pycon
>>> spec_finder = import_obj('importlib.util', 'find_spec')
>>> callable(spec_finder)
True
>>> spec_finder.__module__
'importlib.util'
```

### wads.util.mk_import_root_replacer(from_to_dict)

Make a function that does multiple import name replacements.

For a use case, see replace_import_names. This is just a helper function.

```pycon
>>> replace = mk_import_root_replacer({'foo': 'FOO', 'bar': 'BAR'})
>>>
>>> assert replace('from foo import BLAH') == 'from FOO import BLAH'
>>> assert replace('from foo.bar import BLAH') == 'from FOO.bar import BLAH'
>>> assert replace('import bar') == 'import BAR'
```

Partial matches are not replaced (that’s a good thing!):

```pycon
>>> assert replace('import barmitzvah as oy') == 'import barmitzvah as oy'
>>> assert replace('from foobar import hello') == 'from foobar import hello'
```

Yes, and it works with dotpaths:

```pycon
>>> replace = mk_import_root_replacer({'where.it.was': 'where.it.is.now'})
>>> replace('import where.it.was as here')
'import where.it.is.now as here'
```

* **Parameters:**
  **from_to_dict** – A dict of {to_find: to_replace_by,…} pairs
* **Returns:**
  A replacer function that you can apply to strings to carry out the replacements

### wads.util.mk_replacer_from_dict(from_to_dict)

Make a function that does multiple replacements (in a single pass).

```pycon
>>> r = mk_replacer_from_dict({'is': 'are', 'life': 'butterflies'})
>>> r("There is no life in the void.")
'There are no butterflies in the void.'
```

* **Parameters:**
  **from_to_dict** – A dict of {to_find: to_replace_by,…} pairs
* **Returns:**
  A replacer function that you can apply to strings to carry out the replacements

### wads.util.replace_import_names(source_store, from_to_dict, target_store=None, dryrun=True, verbose=True, replacer_factory=<function mk_import_root_replacer>, add_comment_at_the_end_of_lines_replaced=False)

Replace import names.

Use case: You’ve renamed something or moved some modules (remember UNIX? Same as move!) and have to go through
all your files and notebooks and replace those names.
Now, if you have a nice IDE, we suggest you use refactoring instead – as long as you have any uses in the scope.
But sometimes it’s not enough. You might have text/html documments, or jupyter notebooks, etc.
So you can use this instead.

Be warned though:

- You should look at the pattern that is used to match, and make sure it won’t create havoc.
- Backup your documents so you can revert!
- Print matches before you actually apply them all in bulk.
- Use at your own risk!

For examples, see the mk_import_root_replacer helper function.

* **Parameters:**
  * **source_store**
  * **from_to_dict** – A dict of {to_find: to_replace_by,…} pairs
  * **target_store** – The store
  * **dryrun**
  * **verbose**
  * **replacer_factory** – makes the replacer = replacer_factory(from_to_dict)
  * **add_comment_at_the_end_of_lines_replaced** – True/False or an actual string to add at the end of replaced lines
* **Returns:**
