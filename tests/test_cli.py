import dicom_annotator.cli as cli


def test_cli_serve_missing_project_dir_returns_2(tmp_path):
    rc = cli.main(["serve", "--project", str(tmp_path / "does_not_exist")])
    assert rc == 2


def test_cli_serve_invokes_uvicorn(project_root, monkeypatch):
    """serve loads the project and hands a built app to uvicorn.run."""
    captured = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: captured.update({"app": app, **kw}))

    rc = cli.main(["serve", "--project", str(project_root), "--port", "9123"])

    assert rc == 0
    assert captured["app"] is not None
    assert captured["port"] == 9123
