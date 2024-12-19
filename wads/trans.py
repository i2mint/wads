# TODO: notebook -> md with more parametrization, normalization, and cleaning up

# TODO: Get rid of html junk in ipynb -> md

# TODO: Transform markdown (md) relative image reference to full url ones so that they're rendered in pypi
# Example: ![png](img/output_72_1.png) -> ![png](https://github.com/thorwhalen/invest/tree/master/img/output_72_1.png)

# https://raw.githubusercontent.com/thorwhalen/invest/master/img


# TODO: Make it work with regular expressions, to be more flexible
def replace_relative_links_to_absolute(
    s: str,
    root_url: str,
    str_to_match_and_add_root_url_before: str = "\n![png](",
):
    return s.replace(
        str_to_match_and_add_root_url_before,
        root_url + str_to_match_and_add_root_url_before,
    )
