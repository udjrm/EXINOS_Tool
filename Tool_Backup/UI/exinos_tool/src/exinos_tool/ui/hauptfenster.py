"""Hauptfenster: Menue, Schrittleiste und ein Stapel von Arbeitsbereichen.

Das Fenster besitzt den Controller und ist die einzige Qt-Klasse, die
dessen Methoden aufruft. Schritt 1 (Aufbau) enthaelt Bahnleiste, Bibliothek
und Leinwand sowie den Weiter-Knopf, der prueft, exportiert und zu Schritt 2
wechselt. Die uebrigen Schritte haben vorerst Platzhalter.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..app.controller import Controller
from ..app.zustand import SCHRITTNAMEN, Schritt, veraltet
from ..core.darstellung import Darstellung
from .bahnleiste import Bahnleiste
from .befund_dialog import BefundDialog
from .bibliothek import Bibliothek
from .dsm_ansicht import DsmAnsicht
from .ergebnis_ansicht import ErgebnisAnsicht
from .nwa_ansicht import NwaAnsicht
from .schrittleiste import Schrittleiste, Trennlinie
from .szene import Leinwand, LeinwandAnsicht

PROJEKT_FILTER = "Anlage-Projekt (*.anlage);;Alle Dateien (*)"


class Hauptfenster(QMainWindow):
    def __init__(self, controller: Controller) -> None:
        super().__init__()
        self.controller = controller
        self._projektpfad: Path | None = None

        self.setWindowTitle("EXINOS – Werkzeug zur Anlagensimulation")
        self.resize(1200, 800)

        # Darstellung laden (Overlay zum Pool).
        self._darstellung = self._darstellung_laden()

        self._schrittleiste = Schrittleiste()
        self._schrittleiste.schritt_gewaehlt.connect(self._schritt_wechseln)

        self._bereiche = QStackedWidget()
        self._bereich_je_schritt: dict[Schritt, QWidget] = {}
        for schritt in Schritt:
            if schritt is Schritt.AUFBAU:
                bereich = self._aufbau_bereich()
            elif schritt is Schritt.PRUEFUNG:
                bereich = self._pruefung_bereich()
            elif schritt is Schritt.NWA:
                bereich = self._nwa_bereich()
            elif schritt is Schritt.ERGEBNIS:
                bereich = ErgebnisAnsicht()
            else:
                bereich = self._platzhalter(schritt)
            self._bereich_je_schritt[schritt] = bereich
            self._bereiche.addWidget(bereich)

        zentral = QWidget()
        aufbau = QVBoxLayout(zentral)
        aufbau.setContentsMargins(0, 0, 0, 0)
        aufbau.addWidget(self._schrittleiste)
        aufbau.addWidget(Trennlinie())
        aufbau.addWidget(self._bereiche, stretch=1)
        self.setCentralWidget(zentral)

        self._menue_aufbauen()
        self._zustand_spiegeln()

    # ------------------------------------------------------------------
    # Aufbau der Bereiche
    # ------------------------------------------------------------------

    def _darstellung_laden(self) -> Darstellung:
        """Sucht pool_darstellung.json neben der Pooldatei."""
        pfad = None
        quelle = getattr(self.controller.pool, "quelle", None)
        if quelle is not None:
            pfad = Path(quelle).parent / "pool_darstellung.json"
        return Darstellung.laden(pfad, self.controller.pool)

    def _aufbau_bereich(self) -> QWidget:
        """Schritt 1: Bahnleiste oben, Bibliothek links, Leinwand rechts, Weiter unten."""
        self._bibliothek = Bibliothek(self.controller.pool)
        self._leinwand = Leinwand(self.controller, self._darstellung)
        self._leinwand.signale.geaendert.connect(self._zustand_spiegeln)
        self._ansicht = LeinwandAnsicht(self._leinwand)

        self._bahnleiste = Bahnleiste(self.controller)
        self._bahnleiste.bahnen_geaendert.connect(self._zustand_spiegeln)
        # Die aktive Bahn reicht die Leinwand durch.
        self._bahnleiste.aktive_bahn_gewechselt.connect(self._aktive_bahn_setzen)

        teiler = QSplitter(Qt.Horizontal)
        teiler.addWidget(self._bibliothek)
        teiler.addWidget(self._ansicht)
        teiler.setStretchFactor(1, 1)
        teiler.setSizes([240, 960])

        # Fusszeile mit dem Weiter-Knopf.
        fuss = QHBoxLayout()
        fuss.addStretch(1)
        self._weiter_knopf = QPushButton("Weiter  →")
        self._weiter_knopf.setMinimumWidth(140)
        self._weiter_knopf.clicked.connect(self._weiter_aus_aufbau)
        fuss.addWidget(self._weiter_knopf)

        seite = QWidget()
        aufbau = QVBoxLayout(seite)
        aufbau.setContentsMargins(0, 0, 0, 0)
        aufbau.addWidget(self._bahnleiste)
        aufbau.addWidget(teiler, stretch=1)
        aufbau.addLayout(fuss)
        return seite

    def _aktive_bahn_setzen(self, bahn_id: str) -> None:
        """Merkt die aktive Bahn fuer das Verbinden."""
        if hasattr(self._leinwand, "aktive_bahn_setzen"):
            self._leinwand.aktive_bahn_setzen(bahn_id)

    def _platzhalter(self, schritt: Schritt) -> QWidget:
        seite = QWidget()
        aufbau = QVBoxLayout(seite)
        titel = QLabel(f"Schritt: {SCHRITTNAMEN[schritt]}")
        titel.setStyleSheet("font-size: 16pt; padding: 24px;")
        hinweis = QLabel(
            "Dieser Arbeitsbereich wird in einem spaeteren Teilpaket gefuellt."
        )
        hinweis.setStyleSheet("color: palette(mid); padding: 0 24px;")
        aufbau.addWidget(titel)
        aufbau.addWidget(hinweis)
        aufbau.addStretch(1)
        return seite

    def _pruefung_bereich(self) -> QWidget:
        self._dsm = DsmAnsicht()
        self._analyse_knopf = QPushButton("Strukturanalyse starten")
        self._analyse_knopf.clicked.connect(self._struktur_analyse_starten)
        seite = QWidget()
        layout = QVBoxLayout(seite)
        layout.addWidget(QLabel("DSM-Matrix prüfen"))
        layout.addWidget(self._analyse_knopf)
        layout.addWidget(self._dsm, stretch=1)
        self._dsm.bestaetigt.connect(self._dsm_bestaetigt)
        return seite

    def _nwa_bereich(self) -> QWidget:
        self._nwa = NwaAnsicht()
        self._nwa.bestaetigt.connect(self._nwa_starten)
        return self._nwa

    def _struktur_analyse_starten(self) -> None:
        try:
            ergebnis = self.controller.struktur_analysieren()
        except Exception as fehler:
            QMessageBox.critical(self, "Strukturanalyse fehlgeschlagen", str(fehler))
            return
        if not ergebnis.erfolg:
            QMessageBox.critical(self, "Strukturanalyse fehlgeschlagen", ergebnis.meldung)
            return
        self._dsm.setzen(self.controller.dsm_matrix())
        self._nwa.setzen([])
        self._zustand_spiegeln()

    def _dsm_bestaetigt(self) -> None:
        try:
            ergebnis = self.controller.nwa_analysieren()
        except Exception as fehler:
            QMessageBox.critical(self, "NWA fehlgeschlagen", str(fehler))
            return
        if not ergebnis.erfolg:
            QMessageBox.critical(self, "NWA fehlgeschlagen", ergebnis.meldung)
            return
        self._nwa.setzen(self.controller.nwa_ergebnis())
        self._zustand_spiegeln()
        self._schrittleiste.schritt_setzen(Schritt.NWA)
        self._schritt_wechseln(Schritt.NWA)

    def _nwa_starten(self) -> None:
        try:
            ergebnis = self.controller.abc_analysieren()
        except Exception as fehler:
            QMessageBox.critical(self, "ABC-Analyse fehlgeschlagen", str(fehler))
            return
        if not ergebnis.erfolg:
            QMessageBox.critical(self, "ABC-Analyse fehlgeschlagen", ergebnis.meldung)
            return
        self._nwa.setzen(self.controller.nwa_ergebnis())
        self._bereich_je_schritt[Schritt.ERGEBNIS].setzen(
            self.controller.abc_ergebnis()
        )
        self._zustand_spiegeln()
        self._schrittleiste.schritt_setzen(Schritt.ERGEBNIS)
        self._schritt_wechseln(Schritt.ERGEBNIS)

    # ------------------------------------------------------------------
    # Menue
    # ------------------------------------------------------------------

    def _menue_aufbauen(self) -> None:
        datei = self.menuBar().addMenu("&Datei")
        self._aktion("Neu", "Ctrl+N", self._neu, datei)
        self._aktion("Oeffnen …", QKeySequence.Open, self._oeffnen, datei)
        self._aktion("Speichern", QKeySequence.Save, self._speichern, datei)
        self._aktion("Speichern unter …", "Ctrl+Shift+S", self._speichern_unter, datei)
        datei.addSeparator()
        self._aktion("Struktur exportieren (CSV) …", "Ctrl+E", self._exportieren, datei)
        datei.addSeparator()
        self._aktion("Beenden", "Ctrl+Q", self.close, datei)

        bearbeiten = self.menuBar().addMenu("&Bearbeiten")
        self._aktion_rueckgaengig = self._aktion(
            "Rueckgaengig", QKeySequence.Undo, self._rueckgaengig, bearbeiten
        )
        self._aktion_wiederholen = self._aktion(
            "Wiederholen", QKeySequence.Redo, self._wiederholen, bearbeiten
        )

    def _aktion(self, text, kurz, ziel, menue) -> QAction:
        aktion = QAction(text, self)
        if kurz is not None:
            aktion.setShortcut(kurz)
        aktion.triggered.connect(ziel)
        menue.addAction(aktion)
        return aktion

    # ------------------------------------------------------------------
    # Zustand in die Oberflaeche spiegeln
    # ------------------------------------------------------------------

    def _zustand_spiegeln(self) -> None:
        """Einzige Stelle, die Freigaben und Menuezustand aktualisiert."""
        zustand = self.controller.zustand()
        self._schrittleiste.freigaben_anwenden(
            self.controller.freigaben(), veraltet(zustand)
        )

        stapel = self.controller.befehlsstapel
        self._aktion_rueckgaengig.setEnabled(stapel.kann_rueckgaengig)
        self._aktion_wiederholen.setEnabled(stapel.kann_wiederholen)
        text_r = stapel.beschriftung_rueckgaengig
        text_w = stapel.beschriftung_wiederholen
        self._aktion_rueckgaengig.setText(
            f"Rueckgaengig: {text_r}" if text_r else "Rueckgaengig"
        )
        self._aktion_wiederholen.setText(
            f"Wiederholen: {text_w}" if text_w else "Wiederholen"
        )

        titel = "EXINOS – Werkzeug zur Anlagensimulation"
        if self._projektpfad:
            titel = f"{self._projektpfad.name} – {titel}"
        self.setWindowTitle(titel)

    def _schritt_wechseln(self, schritt: Schritt) -> None:
        self._bereiche.setCurrentWidget(self._bereich_je_schritt[schritt])

    # ------------------------------------------------------------------
    # Datei-Aktionen
    # ------------------------------------------------------------------

    def _neu(self) -> None:
        from ..core.io_projekt import Projekt

        self.controller = Controller(
            self.controller.pool,
            self.controller.backend,
            self.controller.austauschbasis,
            self.controller.kriterien,
            Projekt(),
        )
        self._projektpfad = None
        self._leinwand.controller = self.controller
        self._leinwand.neu_aufbauen()
        self._bahnleiste.controller = self.controller
        self._bahnleiste.neu_laden()
        self._schrittleiste.schritt_setzen(Schritt.AUFBAU)
        self._schritt_wechseln(Schritt.AUFBAU)
        self._zustand_spiegeln()

    def _oeffnen(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, "Projekt oeffnen", "", PROJEKT_FILTER
        )
        if not name:
            return
        try:
            self.controller = Controller.laden(
                Path(name),
                self.controller.pool,
                self.controller.backend,
                self.controller.kriterien,
                self.controller.austauschbasis,
            )
        except Exception as fehler:
            QMessageBox.critical(self, "Fehler beim Oeffnen", str(fehler))
            return
        self._projektpfad = Path(name)
        self._leinwand.controller = self.controller
        self._leinwand.neu_aufbauen()
        self._bahnleiste.controller = self.controller
        self._bahnleiste.neu_laden()
        self._zustand_spiegeln()

    def _speichern(self) -> None:
        if self._projektpfad is None:
            self._speichern_unter()
            return
        self._speichern_nach(self._projektpfad)

    def _speichern_unter(self) -> None:
        name, _ = QFileDialog.getSaveFileName(
            self, "Projekt speichern", "", PROJEKT_FILTER
        )
        if not name:
            return
        pfad = Path(name)
        if pfad.suffix != ".anlage":
            pfad = pfad.with_suffix(".anlage")
        self._speichern_nach(pfad)

    def _speichern_nach(self, pfad: Path) -> None:
        try:
            self.controller.speichern(pfad)
        except Exception as fehler:
            QMessageBox.critical(self, "Fehler beim Speichern", str(fehler))
            return
        self._projektpfad = pfad
        self._zustand_spiegeln()

    # ------------------------------------------------------------------
    # Bearbeiten
    # ------------------------------------------------------------------

    def _rueckgaengig(self) -> None:
        if self.controller.rueckgaengig():
            self._leinwand.aktualisieren()
            self._zustand_spiegeln()

    def _wiederholen(self) -> None:
        if self.controller.wiederholen():
            self._leinwand.aktualisieren()
            self._zustand_spiegeln()

    # ------------------------------------------------------------------
    # Weiter: pruefen, exportieren, Schritt wechseln
    # ------------------------------------------------------------------

    def _weiter_aus_aufbau(self) -> None:
        """Prueft, exportiert bei Erfolg und wechselt zu Schritt 2."""
        # 1. Pruefen.
        bericht = self.controller.pruefen()
        self._zustand_spiegeln()

        if not bericht.exportfaehig:
            # Blockieren und Befunde zeigen.
            BefundDialog(bericht, self).exec()
            return

        # 2. Einen eigenen, zeitgestempelten Anlagenordner unter Exports verwenden.
        self.controller.export_basis = self.controller.austauschbasis

        # 3. Exportieren.
        erfolg, meldung = self.controller.exportieren(self.controller.export_basis)
        self._zustand_spiegeln()
        if not erfolg:
            QMessageBox.warning(self, "Export nicht moeglich", meldung)
            return

        # 4. Weiter zu Schritt 2.
        QMessageBox.information(
            self,
            "Struktur exportiert",
            f"components.csv und connections.csv wurden geschrieben nach:\n{meldung}",
        )
        self._schrittleiste.schritt_setzen(Schritt.PRUEFUNG)
        self._schritt_wechseln(Schritt.PRUEFUNG)

    # ------------------------------------------------------------------
    # Export ueber das Menue (Zweitweg)
    # ------------------------------------------------------------------

    def _exportieren(self) -> None:
        """Schreibt components.csv und connections.csv in einen Zeitstempel-Ordner."""
        ziel = QFileDialog.getExistingDirectory(
            self, "Zielordner fuer den Export waehlen"
        )
        if not ziel:
            return
        erfolg, meldung = self.controller.exportieren(ziel)
        self._zustand_spiegeln()  # Pruefung lief, Freigaben aktualisieren
        if erfolg:
            QMessageBox.information(
                self,
                "Export abgeschlossen",
                f"Die Dateien wurden geschrieben nach:\n{meldung}",
            )
        else:
            QMessageBox.warning(self, "Export nicht moeglich", meldung)