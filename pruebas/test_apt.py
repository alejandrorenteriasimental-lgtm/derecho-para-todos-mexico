"""Regresión 12-11-2026: el cambio de espejo de sistema/apt.sh borraba /etc/apt/apt-mirrors.txt aunque las fuentes de
ubuntu-latest (26.04) apuntan a «mirror+file:/etc/apt/apt-mirrors.txt»; apt quedaba sin repositorios (ciclo 43053554282)."""
import pathlib, re, subprocess

RAIZ = pathlib.Path(__file__).resolve().parents[1]


def _funcion(tmp):
    s = (RAIZ / "sistema" / "apt.sh").read_text(encoding="utf-8")
    m = re.search(r'^ESPEJO=.*?^}\n', s, re.S | re.M)
    assert m, "cambiar_espejo no está definido en apt.sh"
    return m.group(0).replace("sudo ", "").replace("/etc/apt", str(tmp))


def test_cambio_de_espejo_no_deja_apt_sin_fuentes(tmp_path):
    (tmp_path / "sources.list.d").mkdir()
    fuente = tmp_path / "sources.list.d" / "ubuntu.sources"
    fuente.write_text("Types: deb\nURIs: mirror+file:/etc/apt/apt-mirrors.txt\nSuites: resolute resolute-updates\n"
                      "Types: deb\nURIs: http://azure.archive.ubuntu.com/ubuntu/\nSuites: resolute-security\n")
    (tmp_path / "apt-mirrors.txt").write_text("http://azure.archive.ubuntu.com/ubuntu/\n")
    guion = _funcion(tmp_path).replace(f"mirror\\+file:{tmp_path}", "mirror\\+file:/etc/apt") + "cambiar_espejo\n"
    subprocess.run(["bash", "-c", guion], check=True)
    espejos = tmp_path / "apt-mirrors.txt"
    assert espejos.exists(), "el archivo de espejos no debe borrarse"
    assert espejos.read_text().strip() == "http://archive.ubuntu.com/ubuntu/"
    texto = fuente.read_text()
    assert "mirror+file" not in texto and "azure" not in texto
    assert texto.count("URIs: http://archive.ubuntu.com/ubuntu/") == 2
