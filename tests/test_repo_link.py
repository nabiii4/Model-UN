"""The How it works page links to the public code repo (BUILD_PROMPT.md section 6.15)."""

REPO = "https://github.com/nabiii4/Model-UN"


def set_link(api, value):
    r = api.patch("/api/admin/copy", {"overrides": {"site.code_repo_url": value}})
    assert r.status_code == 200
    return api.get("/how-it-works").get_data(as_text=True)


def test_how_it_works_links_to_the_code(api):
    html = api.get("/how-it-works").get_data(as_text=True)
    assert f'href="{REPO}"' in html and 'rel="noopener"' in html and 'target="_blank"' in html


def test_editors_can_hide_or_change_the_link(api):
    api.join("Editor")
    api.become_maintainer()
    cases = [
        ("none", None),                                   # hides it
        ("javascript:alert(1)", None),                    # never a script link
        ("http://example.org/club", None),                # only https
        ("data:text/html,hi", None),
        ("https://example.org/club-code", 'href="https://example.org/club-code"'),
        ("HTTPS://example.org/caps", 'href="HTTPS://example.org/caps"'),  # schemes ignore case
        ("", f'href="{REPO}"'),                           # empty = back to the original link
    ]
    for value, expected_href in cases:
        html = set_link(api, value)
        assert ("Can I see the code?" in html) is (expected_href is not None), value
        if expected_href:
            assert expected_href in html, value
        assert 'href="javascript:' not in html and 'href="data:' not in html


def test_link_is_escaped(api):
    api.join("Sneaky")
    api.become_maintainer()
    html = set_link(api, 'https://x.example/" onmouseover="alert(1)')
    assert 'onmouseover="alert(1)"' not in html      # the quote can't break out of href="..."
    assert "&#34; onmouseover=&#34;alert(1)" in html  # it is shown as harmless text instead
