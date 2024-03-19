# wads

Tools for packaging and publishing to pypi for those who just don't want to deal with it

To install (for example):
```
pip install wads
```

# Usage Examples

We're going to assume you pointed "pack" to "wads/pack.py" and "populate" to "wads/populate.py",
because it's convenient for us to do so. You can achieve this in various ways
(for example, putting the contents:
`python /Users/Thor.Whalen/Dropbox/dev/p3/proj/i/wads/wads/pack.py "$@"`
in a file named "pack" contained in your OS's script path.)


## populate

When? When you got a new project and you want to quickly set it up with the packaging goodies.

Basic usage:

```
populate PKG_DIR
```

or, assuming you're using the terminal and you're in the `PKG_DIR` root folder of the project, you can just do:

```
populate .
```

What that will do is create and populate some files for you.
Namely, it will ensure your package directory has the following files (if not present already)
```
./LICENSE
./setup.cfg
./PKG_NAME/__init__.py
./README.md
```

The `PKG_NAME` will be taken to be the same as the name of the `PKG_DIR`.

That will work, it will be minimal and will choose defaults for you.
You can overwrite many of these, of course.
For example,

```
populate -r https:///github.com/i2mint --description "Something about my project..."
```

Here are the following options:

```
positional arguments:
  pkg-dir               -

optional arguments:
  -h, --help            show this help message and exit
  --description DESCRIPTION
                        "There is a bit of an air of mystery around this project..."
  -r ROOT_URL, --root-url ROOT_URL
                        -
  -a AUTHOR, --author AUTHOR
                        -
  -l LICENSE, --license LICENSE
                        'mit'
  --description-file DESCRIPTION_FILE
                        'README.md'
  -k KEYWORDS, --keywords KEYWORDS
                        -
  --install-requires INSTALL_REQUIRES
                        -
  --include-pip-install-instruction-in-readme
                        True
  -v, --verbose         True
  -o OVERWRITE, --overwrite OVERWRITE
                        ()
  --defaults-from DEFAULTS_FROM
                        -
```

Note that by default, populate will not overwrite files that all already there.
It will edit the `setup.cfg` file if it's present (and missing some entries).

## Configuring the defaults of `populate`

Note that `defaults-from` option in the `populate` help.
That's probably the most convenient argument of all.
Go check out a file named `wads_confgis.json` in the root directory of the project.
(If you don't know how to find that file, try this command:
`python -c "import wads; print(wads)"` to get a clue).

That `wads_confgis.json` file contains key-value entries that are used in the wads package.
The `"populate_dflts"` key is used by the populate script.
If you edit that, you'll get different defaults out of the box.

But you can also add your own key-value pairs if you work on different kinds of projects that need
different kinds of defaults.
For your convenience we added a `"custom_dflts_example_you_should_change"` key to illustrate this.

## pack

The typical sequence of the methodical and paranoid could be something like this:

```
python pack.py current-configs  # see what you got
python pack.py increment-configs-version  # update (increment the version and write that in setup.cfg
python pack.py current-configs-version  # see that it worked
python pack.py current-configs  # ... if you really want to see the whole configs again (you're really paranoid)
python pack.py run-setup  # see that it worked
python pack.py twine-upload-dist  # publish
# and then go check things work...
```


If you're are great boilerplate hater you could just do:

```
pack go PKG_DIR
```

(or `pack go --version 0.0.0 PKG_DIR` if it's the very first release).

But we suggest you get familiar with what the steps are doing, so you can bend them to your liking.

# Troubleshooting

## Vesion tag misalignment

Sometimes the twine PYPI publishing may fail with such a message:

```
WARNING  Skipping PKGNAME-0.1.4-py3-none-any.whl because it appears to already exist 
WARNING  Skipping PKGNAME-0.1.4.tar.gz because it appears to already exist
```

This often means that your git tags are misaligned with the `setup.cfg` version. 
You can see your git tags here: `https://github.com/ORG/REPO/tags`.

To repair, do this:

* go to the https://pypi.org/project/ project page and note the VERSION number
* enter a VERSION number ABOVE that one in the version key of `setup.cfg`
* `git tag VERSION`
* `git push origin VERSION`
