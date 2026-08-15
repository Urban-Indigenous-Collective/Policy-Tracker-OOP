from discovery.progress import DiscoveryProgress, render_bar


def test_render_bar():
    assert render_bar(0, 10) == "[>                               ]"
    assert render_bar(5, 10) == "[================>               ]"
    assert render_bar(10, 10) == "[================================]"


def test_progress_writes_summary(tmp_path):
    p = DiscoveryProgress(path=tmp_path / "progress.json")
    p.begin_legiscan(70)
    p.legiscan_query(35, 70, "year=2023 MMIP")
    assert p.percent == 50
    assert "LegiScan" in p.summary_line()
    assert (tmp_path / "progress.json").exists()
