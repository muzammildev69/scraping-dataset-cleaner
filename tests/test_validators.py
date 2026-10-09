import pytest

from dataset_cleaner import validators


@pytest.mark.parametrize(
    "value",
    [
        "john@example.com",
        "john.smith+tag@sub.example.co.uk",
        "o'brien@example.org",
        "user_name@xn--bcher-kva.example",
        "a@b.io",
    ],
)
def test_valid_emails(value):
    assert validators.is_valid_email(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "plainaddress",
        "john@example",
        "@example.com",
        "john@",
        "john@@example.com",
        "john smith@example.com",
        "john..smith@example.com",
        ".john@example.com",
        "john@-example.com",
        "john@example.c",
        "john@example.123",
        "a" * 65 + "@example.com",
    ],
)
def test_invalid_emails(value):
    assert not validators.is_valid_email(value)


def test_normalize_email_trims_and_lowercases():
    assert validators.normalize_email("  John.Smith@Example.COM \t") == "john.smith@example.com"


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com",
        "http://example.com/path/to/page?x=1&y=2#frag",
        "https://sub.example.co.uk:8443/a",
        "http://localhost:3000/",
        "http://127.0.0.1/admin",
        "http://[::1]:8080/",
        "https://user:pass@example.com/",
        "https://bücher.example/straße",
    ],
)
def test_valid_urls(value):
    assert validators.is_valid_url(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "example.com",
        "www.example.com/page",
        "not a url",
        "https://exa mple.com",
        "https://",
        "https:///path",
        "ftp://example.com/file",
        "javascript:alert(1)",
        "http://example",
        "http://999.1.1.1/",
        "https://example.com:notaport/",
        "https://example.com:99999/",
        "https://-bad-.example.com/",
        "https://example..com/",
        "https://example.com/a\nb",
    ],
)
def test_invalid_urls(value):
    assert not validators.is_valid_url(value)


def test_normalize_url_lowercases_scheme_and_host_only():
    value = "  HTTPS://Example.COM/Path/CaseSensitive?Q=Mixed&b=2#Frag  "
    assert validators.normalize_url(value) == "https://example.com/Path/CaseSensitive?Q=Mixed&b=2#Frag"


def test_normalize_url_preserves_userinfo_port_and_trailing_slash():
    assert (
        validators.normalize_url("http://User:PaSs@Host.COM:8080/")
        == "http://User:PaSs@host.com:8080/"
    )


def test_normalize_url_keeps_empty_query_and_fragment_markers():
    assert validators.normalize_url("https://example.com/a?#") == "https://example.com/a?#"


def test_normalize_url_leaves_schemeless_values_alone_by_default():
    assert validators.normalize_url(" Example.com/Path ") == "Example.com/Path"


def test_normalize_url_adds_https_when_requested():
    assert validators.normalize_url("Example.com/Path", add_scheme=True) == "https://example.com/Path"
    assert validators.normalize_url("//Example.com/x", add_scheme=True) == "https://example.com/x"
    assert validators.normalize_url("http://Example.com", add_scheme=True) == "http://example.com"


def test_normalize_url_strips_query_and_fragment_only_when_requested():
    url = "https://example.com/a/b?id=7#top"
    assert validators.normalize_url(url) == url
    assert validators.normalize_url(url, strip_params=True) == "https://example.com/a/b"
    assert validators.normalize_url("https://example.com#frag", strip_params=True) == "https://example.com"


def test_normalize_url_empty_value_stays_empty():
    assert validators.normalize_url("   ") == ""


@pytest.mark.parametrize(
    "name",
    ["email", "email_address", "contact_email", "business_email", "work_email", "email_2"],
)
def test_email_column_detection_positive(name):
    assert validators.is_email_column(name)


@pytest.mark.parametrize("name", ["email_verified", "emailed_at", "name", "mail_count", "url"])
def test_email_column_detection_negative(name):
    assert not validators.is_email_column(name)


@pytest.mark.parametrize(
    "name",
    ["url", "website", "website_url", "product_url", "profile_url", "linkedin_url", "link", "url_2"],
)
def test_url_column_detection_positive(name):
    assert validators.is_url_column(name)


@pytest.mark.parametrize("name", ["url_status", "website_rank", "email", "price"])
def test_url_column_detection_negative(name):
    assert not validators.is_url_column(name)
