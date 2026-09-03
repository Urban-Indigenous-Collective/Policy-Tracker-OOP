"""Attorney General host matching for state crawl coverage."""

from discovery.ag_coverage import load_ag_hosts, source_matches_ag, states_missing_ag, url_matches_ag


def test_ag_hosts_cover_fifty_one_jurisdictions():
    hosts = load_ag_hosts()
    assert len(hosts) == 51
    assert "SD" in hosts
    assert hosts["SD"]["host"] == "atg.sd.gov"
    assert "pressreleases.aspx" in hosts["SD"]["listing_url"]


def test_sd_ag_listing_matches_and_governor_does_not():
    hosts = load_ag_hosts()
    assert url_matches_ag(
        "SD",
        "https://atg.sd.gov/OurOffice/Media/pressreleases.aspx",
        hosts,
    )
    assert url_matches_ag(
        "SD",
        "https://atg.sd.gov/OurOffice/Media/pressreleasesdetail.aspx?id=3147",
        hosts,
    )
    assert not url_matches_ag("SD", "https://news.sd.gov", hosts)
    assert not url_matches_ag("SD", "https://www.sd.gov/news/press-releases", hosts)


def test_shared_state_gov_hosts_require_path_prefix():
    hosts = load_ag_hosts()
    assert url_matches_ag(
        "IN",
        "https://www.in.gov/attorneygeneral/newsroom/",
        hosts,
    )
    assert not url_matches_ag("IN", "https://www.in.gov/gov/news", hosts)
    assert url_matches_ag("ME", "https://www.maine.gov/ag/news/", hosts)
    assert not url_matches_ag("ME", "https://www.maine.gov/agriculture/", hosts)
    assert url_matches_ag(
        "MA",
        "https://www.mass.gov/orgs/office-of-attorney-general-andrea-joy-campbell/news",
        hosts,
    )


def test_montana_doj_news_counts_as_ag():
    hosts = load_ag_hosts()
    source = {
        "state": "MT",
        "url": "https://dojmt.gov/news/",
        "review_needed": False,
        "name": "MT — agency press releases",
    }
    assert source_matches_ag(source, hosts)


def test_states_missing_ag_ignores_review_needed():
    hosts = {"SD": load_ag_hosts()["SD"]}
    by_state = {
        "SD": [
            {
                "state": "SD",
                "url": "https://atg.sd.gov/OurOffice/Media/pressreleases.aspx",
                "review_needed": True,
            }
        ]
    }
    assert states_missing_ag(by_state, include_review=False, hosts=hosts) == ["SD"]
    assert states_missing_ag(by_state, include_review=True, hosts=hosts) == []
