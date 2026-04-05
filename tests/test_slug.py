from granola.util import slugify_title


def test_slugify_normal_title() -> None:
    assert (
        slugify_title("Quarterly yoghurt budget review")
        == "quarterly-yoghurt-budget-review"
    )


def test_slugify_special_characters_and_unicode() -> None:
    assert slugify_title("  Café / budget: review?!  ") == "café-budget-review"


def test_slugify_empty_or_none() -> None:
    assert slugify_title("") == "untitled"
    assert slugify_title(None) == "untitled"


def test_slugify_leading_trailing_dashes() -> None:
    assert slugify_title("--- hello ---") == "hello"
