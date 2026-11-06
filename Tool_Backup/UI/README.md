# exinos_tool

Werkzeug zur Erfassung, Prüfung, Darstellung und Auswertung von Anlagenmodellen.

Die Kernschicht unter `src/exinos_tool/core` bleibt frei von Qt-Importen.

## CLI

```bash
python -m exinos_tool.cli pruefen beispiele/EXINOS
```

.venv\Scripts\activate          # Windows
pip install -e ".[dev,ui]"       
