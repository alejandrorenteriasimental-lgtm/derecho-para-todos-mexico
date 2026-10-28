"""Aislamiento común: ninguna prueba escribe en estado/ del repositorio real."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))


@pytest.fixture(autouse=True)
def _analisis_aislado(tmp_path, monkeypatch):
    import redactor
    monkeypatch.setattr(redactor, "ANALISIS", tmp_path / "analisis_cache")
    import planificador
    monkeypatch.setattr(planificador, "LOTE", tmp_path / "sin_lote.json")      # el lote real no altera las pruebas
    yield


@pytest.fixture(autouse=True)
def _sin_ffmpeg_en_instagram(monkeypatch):
    """Las pruebas usan MP4 falsos: la copia ajustada para Instagram se sustituye por el mismo archivo."""
    import instagram
    monkeypatch.setattr(instagram, "adaptar_reel_ig", lambda p, *a, **k: Path(p))
