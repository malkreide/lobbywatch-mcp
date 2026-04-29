# Use Cases & Examples — lobbywatch-mcp

Real-world queries by audience. Indicate per example whether an API key is required.

## 🏫 Bildung & Schule
Lehrpersonen, Schulbehörden, Fachreferent:innen

**Interessenbindungen in der Bildungskommission**
«Welche Mitglieder der ständerätlichen Bildungskommission (WBK-S) haben Verbindungen zu Bildungsverlagen oder privaten Hochschulen?»
→ `search_parlamentarier_nach_branche(branche_query="Bildung", kommission="WBK-S", limit=25)`
Warum nützlich: Erlaubt es Fachreferent:innen und Lehrpersonen, potenzielle Interessenkonflikte bei bildungspolitischen Entscheidungen zu identifizieren.

**Transparenz bei Bildungspolitiker:innen**
«Wie transparent sind die Mitglieder der nationalrätlichen Bildungskommission (WBK-N) bezüglich ihrer Nebeneinkünfte?»
→ `get_transparenzquote(kommission="WBK-N")`
Warum nützlich: Zeigt auf einen Blick, ob die Entscheidungsträger in Bildungsfragen offenlegen, wie viel sie mit ihren Mandaten verdienen.

## 👨‍👩‍👧 Eltern & Schulgemeinde
Elternräte, interessierte Erziehungsberechtigte

**Krankenkassen-Lobby und Familienpolitik**
«Welche Parlamentarier:innen haben Interessenbindungen zu Krankenkassen und Gesundheitsorganisationen, die familienpolitische Vorlagen beeinflussen könnten?»
→ `search_parlamentarier_nach_branche(branche_query="Krankenkasse", limit=10)`
Warum nützlich: Hilft Eltern zu verstehen, wer bei Entscheidungen zu Prämienverbilligungen und Gesundheitskosten welche Interessen vertritt.

**Kantonale Vertretung überprüfen**
«Welche bezahlten und aktiven Mandate hat unsere Zürcher Nationalrätin, Frau Wasserfallen?»
→ `list_interessenbindungen(name_or_id="Wasserfallen", nur_hauptberuflich=True, nur_aktiv=True)`
Warum nützlich: Ermöglicht es interessierten Elternräten, die Verbindungen der lokalen Vertreter:innen schnell und unkompliziert zu überprüfen.

## 🗳️ Bevölkerung & öffentliches Interesse
Allgemeine Öffentlichkeit, politisch und gesellschaftlich Interessierte

**Die aktivsten Lobbyist:innen im Parlament**
«Welche Parlamentarier:innen haben am meisten bezahlte Interessenbindungen?»
→ `get_ranking(kriterium="anzahl_hauptberuflich", limit=10)`
Warum nützlich: Bietet der Öffentlichkeit direkte Transparenz über die am stärksten verflochtenen Akteur:innen im Bundeshaus.

**Netzwerke von Lobbygruppen verstehen**
«Welche Organisationen und Parlamentarier:innen sind mit der Lobbygruppe 'economiesuisse' verbunden?»
→ `get_lobbygruppe(name_or_id="economiesuisse")`
Warum nützlich: Deckt die komplexen Netzwerke und den Einfluss grosser Wirtschaftsverbände auf die Gesetzgebung auf.

**Detailprüfung einer Einzelperson**
«Wie sieht das vollständige Interessenprofil und die Vergütungstransparenz von Herrn Jositsch aus?»
→ `get_parlamentarier(name_or_id="Jositsch")`
Warum nützlich: Ideal, um vor Wahlen oder Abstimmungen das Profil und die Unabhängigkeit einzelner Politiker:innen zu prüfen.

## 🤖 KI-Interessierte & Entwickler:innen
MCP-Enthusiast:innen, Forscher:innen, Prompt Engineers, öffentliche Verwaltung

**Abstimmungsverhalten vs. Interessenbindungen (Multi-Server)**
«Analysiere mit den offiziellen Parlamentsdaten, was Ständerat Jositsch in der Wintersession gesagt hat, und gleiche dies mit seinen aktuellen Lobbyverbindungen ab.»
→ `get_parlamentarier(name_or_id="Jositsch")`
→ [parlament-mcp](https://github.com/malkreide/parlament-mcp): `search_transcripts(speaker="Jositsch", session="Wintersession")`
Warum nützlich: Demonstriert die Leistungsfähigkeit von MCP, wenn offizielle Ratsdaten mit Transparenzdaten verknüpft werden, um Votings und Voten auf mögliche Befangenheiten zu scannen.

**Datenqualität und Aktualität prüfen**
«Wann wurde der Offline-Dump von Lobbywatch das letzte Mal aktualisiert, und wie viele Daten sind im Cache?»
→ `dump_status()`
Warum nützlich: Erlaubt Entwickler:innen und Forschenden, die Frische und Zuverlässigkeit der analysierten Daten sicherzustellen.

## 🔧 Technische Referenz: Tool-Auswahl nach Anwendungsfall

| Ich möchte… | Tool(s) | Auth nötig? |
| :--- | :--- | :--- |
| **das vollständige Profil einer Person sehen** | `get_parlamentarier` | Nein |
| **nur die Mandate einer Person auflisten** | `list_interessenbindungen` | Nein |
| **Politiker nach Branche/Kommission filtern** | `search_parlamentarier_nach_branche` | Nein |
| **eine Lobbygruppe und ihr Netzwerk analysieren** | `get_lobbygruppe` | Nein |
| **die Parlamentarier mit den meisten Mandaten finden** | `get_ranking` | Nein |
| **die Transparenz einer Kommission bewerten** | `get_transparenzquote` | Nein |
| **den Cache leeren und Daten aktualisieren** | `refresh_dump` / `dump_status` | Nein |
