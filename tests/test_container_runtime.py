from pathlib import Path


def test_dockerfile_copies_tapdb_template_pack() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "COPY config ./config" in dockerfile
    assert Path("config/tapdb_templates/ursa/templates.json").is_file()
