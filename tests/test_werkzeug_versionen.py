"""Die ruff-Version steht an genau einer Stelle — und soll dort bleiben.

Hier ist sie es bereits: `ruff==0.16.1` im `[dev]`-Extra, und kein Workflow
nennt eine zweite. Dieser Test haelt diesen Zustand, statt ihn zu behaupten.

Der Rueckfall waere still. Ein `pip install ruff==<version>` in einem
Workflow liefe nach dem dev-Install und gewaenne gegen pyproject: Wer den
Pin dort anhebt, veraenderte die CI nicht, und wer den im Workflow anhebt,
veraenderte den lokalen Lauf nicht. Kein Gate wird davon rot — die beiden
Laeufe sind sich nur ueber die Regeln uneinig.
"""

from __future__ import annotations

import pathlib
import re
import tomllib

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_WORKFLOWS = _ROOT / ".github" / "workflows"


def _dev_abhaengigkeiten() -> list[str]:
    daten = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    return daten["project"]["optional-dependencies"]["dev"]


def test_ruff_ist_exakt_gepinnt() -> None:
    """Eine Spanne laesst lokalen Lauf und CI verschiedene Versionen fahren."""
    specs = [s for s in _dev_abhaengigkeiten() if re.match(r"^ruff\b", s)]
    assert len(specs) == 1, f"genau ein ruff-Specifier erwartet, gefunden: {specs}"
    assert re.fullmatch(r"ruff==\d+\.\d+\.\d+", specs[0]), (
        f"ruff muss als ruff==X.Y.Z gepinnt sein, gefunden {specs[0]!r}."
    )


def test_der_pin_ist_die_einzige_versionsquelle() -> None:
    """Kein Workflow darf ruff selbst installieren."""
    for workflow in sorted(_WORKFLOWS.glob("*.yml")):
        # Kommentarzeilen raus, damit ein erklaerender Hinweis auf den
        # frueheren Schritt den Test nicht selbst ausloest.
        zeilen = [z for z in workflow.read_text().splitlines() if not z.lstrip().startswith("#")]
        treffer = [z.strip() for z in zeilen if re.search(r"pip install\s+ruff", z)]
        assert not treffer, (
            f"{workflow.name} installiert ruff direkt ({treffer}). Dieser Schritt "
            "laeuft nach dem dev-Install und ueberstimmt den Pin in pyproject."
        )


def test_der_workflow_scan_findet_ueberhaupt_etwas() -> None:
    """Sichert die Pruefung oben gegen ein leeres Verzeichnis ab.

    Faende der Glob nichts, waere die Schleife leer und die Zusicherung
    trivialerweise wahr — gruen, ohne irgendetwas geprueft zu haben.
    """
    workflows = list(_WORKFLOWS.glob("*.yml"))
    assert len(workflows) >= 2, f"Workflow-Scan findet fast nichts: {workflows}"
    assert any("ruff check" in w.read_text() for w in workflows), (
        "kein Workflow ruft ruff auf — der Scan sucht am falschen Ort"
    )
