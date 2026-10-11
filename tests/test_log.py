from repo_scout import log


def test_setup_writes_progress_to_file(capsys):
    path = log.setup(quiet=True)
    log.log.info("поиск 1/1")
    log.log.warning("предупреждение")
    text = path.read_text()
    assert "поиск 1/1" in text and "предупреждение" in text
    err = capsys.readouterr().err
    assert "предупреждение" in err and "поиск 1/1" not in err
