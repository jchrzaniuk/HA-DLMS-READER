# Polskie opisy OBIS: źródła i zakres

Słownik zawiera opisy udokumentowanych kodów, a nie automatyczne tłumaczenia
tekstu biblioteki Gurux. Każdy polski opis wskazuje dokument i stronę tabeli.
Nazwy zapisane przez użytkownika pozostają osobnym elementem konfiguracji.

## Źródła

| Identyfikator | Dokument | Wykorzystanie |
| --- | --- | --- |
| `pozyton-le23-008` | [POZYTON, instrukcja LE-23, TK/3001/057/008](https://pozyton.com.pl/wp-content/uploads/2024/05/instrukcja-operatorska-le-23-4.pdf) | Polskie nazwy i kody: s. 86–87 oraz 89–91. Tabele energii, mocy, prądów, napięć, harmonicznych, THD, współczynnika mocy, częstotliwości i kątów. |
| `dlms-bluebook17` | [DLMS UA, Blue Book, wyd. 17, część 1, oficjalny wyciąg](https://www.dlms.com/wp-content/uploads/2025/06/Excerpts-DLMS-Blue-Book-Ed-17-part-1-V1.0.pdf) | Struktura OBIS i zakresy z części 5.2, 5.3, 5.5 i 5.6: kanały, identyfikatory własne producenta oraz okresy rozliczeniowe. Wyciąg nie zawiera pełnych tabel wielkości elektrycznych. |

Adresy dokumentów, ich sumy SHA-256 oraz odnośniki do stron znajdują się
w `dlms_reader/app/data/obis-pl.json`. Słownik nie jest pełnym polskim
tłumaczeniem normy PN-EN/IEC 62056-6-1. Dokumenty PDF nie są dołączone
do dodatku.

## Zasady dopasowania

- Przestrzeń danych elektrycznych `A=1` jest oddzielona od obiektów abstrakcyjnych `A=0`.
- Opisy dotyczą konkretnych pól `C.D.E` z tabeli; podobny numer nie wystarcza do przypisania nazwy.
- Energia w strefach jest rozwijana wyłącznie dla opublikowanego zakresu `E=0…4`.
- Harmoniczne prądów i napięć są rozwijane dla opublikowanego zakresu `E=1…63`. Kod `E=124` ma odrębny opis THD.
- Dla kanałów `B=1…64` dopisywany jest numer kanału według części 5.2 dokumentu DLMS UA.
- Polskie nazwy są ograniczone do `F=255`; niepotwierdzone znaczenia okresów rozliczeniowych zachowują opis źródłowy.
- Zakresy producenta i dostawcy nie są tłumaczone na podstawie instrukcji innego urządzenia. Dotyczy to również opublikowanych w instrukcji POZYTON kodów konfiguracji `128.*`.
- Kod bez udokumentowanego polskiego odpowiednika zachowuje opis biblioteki. Nie jest uzupełniany na podstawie podobieństwa nazwy ani modelu językowego.

Oryginalny opis pozostaje dostępny obok źródła polskiej nazwy w ustawieniach
rejestru. Zmiana opisu nie zmienia kodu OBIS, jednostki, skali ani parametrów HA.

## Odtworzenie słownika

Skrypt wymaga Popplera (`pdftotext`) oraz oryginalnego PDF producenta.
Najpierw sprawdza sumę SHA-256 dokumentu. Zmiana wersji PDF wymaga ponownej
weryfikacji tabel i aktualizacji źródeł.

```sh
.venv/bin/python scripts/build_obis_pl.py /ścieżka/do/instrukcji.pdf --output /tmp/obis-pl.json
cmp /tmp/obis-pl.json dlms_reader/app/data/obis-pl.json
```
