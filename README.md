# VinylPremaster 1.0

Anàlisi i reparació de premàster per a vinil. Windows 7, 8, 10 i 11 de **64 bits**.

## Flux de treball (5 pestanyes)

1. **Temes** — Obrir un projecte de VinylTracklist (`.vtracklist`) o arrossegar els WAV a la cara A i B (s'ordenen alfabèticament; ▲ ▼ per canviar l'ordre). L'ordre importa: el final de cada cara (diàmetre interior) és més exigent. Botó **Analitzar**.
2. **Anàlisi** — Informe inicial en castellà (*Informe técnico de premasterizado para vinilo*): resum executiu, taula per tema amb colors, gràfics de loudness i crest, diagnòstic global, què ajustar a cada tema i com lliurar els WAV. Exportable a PDF.
3. **Reparació** — Proposta marcada segons l'anàlisi (declip, mono en graves, de-esser), editable tema a tema. Ajustos: pic real objectiu (headroom, −3 dBTP), objectiu del de-esser (−9 dB), tall del mono en graves (150 Hz), bits de sortida (*igual que l'original* o 24), carpeta de sortida. Botó **Reparar**.
4. **Resultat i escolta A/B** — Informe de reparació (abans/després, què s'ha fet, què no s'ha pogut fer, veredicte *Apto / Apto con reservas / No apto*) i reproductor A/B: original i reparat sincronitzats, canvi instantani al mateix punt, opció d'igualar nivell per sentir només el processament. Tecles: espai, A, B.
5. **Comparar versions** — Dos WAV qualssevol (p. ex. màster de vinil i de CD): mesures de tots dos, test d'anul·lació (alineació automàtica, ajust de guany, residu), MD5 de les mostres i comparació byte a byte. Informe PDF.

Els llindars i objectius es poden canviar a *Eines › Llindars i objectius*.

## Mesures

- Loudness integrat ITU-R BS.1770-4 (validat amb pyloudnorm i FFmpeg: diferència ≤ 0,05 LU)
- Pic real amb sobremostreig ×4 (×2 a 88,2/96 kHz) (validat amb FFmpeg: ≤ 0,03 dB)
- Clipping: mostres en trams plans (3 o més mostres idèntiques al màxim) i mostres a fons d'escala
- Crest factor (pic de mostra − RMS)
- Correlació L/R i energia Side/Mid per sota de 150 Hz
- Sibilància: pic d'energia 5–9 kHz en finestres de 50 ms respecte de l'RMS de la mescla

## Reparació

- **Declip**: interpolació cúbica local, màxim +3 dB sobre el tram pla; trams de més de 48 mostres no es toquen.
- **Mono en graves**: passaaltes Butterworth de 4t ordre i fase zero només al canal Side (el Mid no es toca).
- **De-esser**: banda partida 5–9 kHz de fase zero, amb objectiu en dB (màx. 12 dB de reducció).
- **Headroom**: guany uniforme per a tot el disc fins al pic real objectiu (balanç entre temes intacte). Només baixa, mai no puja.
- **Sortida**: enter amb dither TPDF. Els temes sense cap canvi es copien bit a bit.
- Els **originals no es modifiquen mai**. La carpeta de sortida no pot ser la dels originals.

## Generar l'executable

### Opció A — GitHub

1. Crear un repositori nou (p. ex. `Fobdbat/VinylPremaster`) i pujar-hi el contingut d'aquesta carpeta.
2. La web de GitHub no puja la carpeta `.github`: a *Actions*, clicar **set up a workflow yourself**, enganxar-hi el contingut de `.github/workflows/build-windows.yml` i fer *Commit changes*.
3. Quan acabi (uns 10 minuts), a *Artifacts* descarregar `VinylPremaster-windows-x64`.

### Opció B — en un PC amb Windows de 64 bits

1. Instal·lar Python 3.8.10 de 64 bits («Windows installer (64-bit)»).
2. Doble clic a `build_windows.bat`.

El resultat és una **carpeta** `VinylPremaster` amb `VinylPremaster.exe` a dins (no un sol fitxer: així arrenca ràpid malgrat numpy i scipy). Per instal·lar-lo en un altre ordinador, es copia la carpeta sencera.

## Limitacions conegudes

- Els WAV processats no conserven blocs de metadades addicionals (bext, iXML…). Les còpies idèntiques sí.
- Les xifres de sibilància i graves segueixen la definició d'aquest programa; poden no coincidir exactament amb informes fets amb altres eines.
- La qualitat del de-esser i del declip s'ha de jutjar d'oïda: per això hi ha l'escolta A/B.

## Proves

```
python -m unittest discover -s tests -p "test_*.py"
```
