"""The How it works page links to the public code repo (BUILD_PROMPT.md section 6.15)."""

REPO = "https://github.com/nabiii4/Model-UN"


def test_how_it_works_links_to_the_code(api):
    html = api.get("/how-it-works").get_data(as_text=True)
    assert f'href="{REPO}"' in html and 'rel="noopener"' in html


def test_editors_can_hide_or_change_the_link_but_not_inject_javascript(api):
    api.join("Editor")
    api.become_maintainer()
    for value, shown in (("none", False), ("javascript:alert(1)", False), ("https://example.org/club-code", True)):
        r = api.patch("/api/admin/copy", {"overrides": {"site.code_repo_url": value}})
        assert r.status_code == 200
        html = api.get("/how-it-works").get_data(as_text=True)
        assert ("Can I see the code?" in html) is shown, value
        assert 'href="javascript:' not in html  # never a clickable javascript: link
