# Herkunft der Fixtures

**Erzeugt von `scripts/record_fixtures.py`. Nicht von Hand pflegen.**

Aufgezeichnet am **2026-08-14** von der Quelle dieses Servers:
`https://cms.lobbywatch.ch/de/data/interface/v1/json` und dem woechentlichen Dump unter `cms.lobbywatch.ch`.

Ohne Datum ist «aufgezeichnet» nach zwei Jahren von «ausgedacht» nicht
mehr zu unterscheiden — die Datei sieht gleich aus.

**Es sind Ausschnitte, keine Vollabzuege.** Die Auswahlregel steht je
Datei dabei. Eine Fixture belegt die *Form* der Antwort und einen
datierten Ausschnitt ihres Inhalts — nicht den Bestand. Aussagen ueber
Vollstaendigkeit gehoeren in Live-Tests.

**Der Dump ist gekuerzt, aber nicht beschnitten.** Die Quelle liefert ein
ZIP mit einer 80-MB-JSON. Aufgezeichnet sind zwei von 243
Parlamentariern: einer mit, einer ohne Zutrittsberechtigungen. Nach
Interessenbindungen zu waehlen brachte nichts — jeder der 243 hat
zwischen 4 und 114, und das Kuerzen macht daraus ueberall dieselbe Zahl;
eine leere Liste bleibt dagegen leer. Alle 113 Skalarfelder bleiben
unveraendert; die
Beziehungslisten sind auf drei Eintraege gekuerzt, ihre Struktur samt
`organisation` und `verguetungen` ist unangetastet. Fast die ganze
Groesse steckt in `interessenbindungen` — 33 Eintraege zu je rund 10 kB.

## Befund vom 2026-08-14: die Suche liefert nichts

`search/default/{begriff}` antwortet mit HTTP 200, `success: true`,
`count: 0` und `data: null` — fuer jeden geprueften Begriff
(Bildung, Verkehr, Economiesuisse, Umwelt, Gewerkschaft). Der Pfad
ist richtig: `search/simple/...` und `search/...` liefern 404, der
Tabellen-Endpunkt nach ID antwortet normal mit knapp 60 kB.

Wirkung: `fetch_lobbygruppe` schlaegt einen **Namen** ueber die Suche
nach und liefert deshalb zurzeit fuer jeden Namen `None`. Abfragen
ueber die numerische ID sind nicht betroffen. Das ist der Stand der
Quelle an diesem Tag, kein Fehler dieses Servers — die Aufzeichnung
haelt ihn datiert fest, statt ihn zu erfinden.

Fehlerpfade — 404, Timeouts, kaputte ZIPs — bleiben handgeschrieben.
Die lassen sich nicht auf Zuruf aufzeichnen.

## `dump.zip`

- **Quelle:** `https://cms.lobbywatch.ch/sites/lobbywatch.ch/files/exports/lobbywatch_export_aggregated.json.zip`
- **Aufgezeichnet:** 2026-08-14
- **Auswahl:** ZIP mit `aggregated_essential_parlamentarier_nested.json`; 2 von 243 Parlamentariern, gewaehlt einer mit und einer ohne Zutrittsberechtigungen (Wehrli, Laurent (114 Bindungen, 1 Zutrittsberechtigungen); Lohr, Christian (48 Bindungen, 0 Zutrittsberechtigungen)). Alle Skalarfelder unveraendert, Beziehungslisten auf 3 Eintraege gekuerzt, deren Struktur unangetastet. Quelle: 16843171 B gepackt
- **Groesse:** 14487 B
- **SHA-256:** `a7d1daec29763aaf9ea9416fd3b8d2ae639ac3cf0aa28f0894a3bd7f45b34237`

## `interessengruppe.json`

- **Quelle:** `https://cms.lobbywatch.ch/de/data/interface/v1/json/table/interessengruppe/aggregated/id/1`
- **Aufgezeichnet:** 2026-08-14
- **Auswahl:** vollstaendig; Interessengruppe 1
- **Groesse:** 74314 B
- **SHA-256:** `b4f076196f7feb8889a8cb2409f31a3afc66814299f28a0420a10468a095f355`

## `search.json`

- **Quelle:** `https://cms.lobbywatch.ch/de/data/interface/v1/json/search/default/Bildung?limit=5`
- **Aufgezeichnet:** 2026-08-14
- **Auswahl:** vollstaendig; Suche nach 'Bildung' — die Quelle liefert 0 Treffer (siehe Hinweis oben)
- **Groesse:** 133 B
- **SHA-256:** `18fd4ec957422507b351a71f5a0f1a3e9f06abc6d8c50391f580f5b9a402e191`
