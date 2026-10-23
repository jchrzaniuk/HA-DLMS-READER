# DLMS/COSEM Reader

Odczyt liczników DLMS/COSEM w Home Assistant. Dodatek łączy się z licznikiem,
a integracja tworzy encje z jego pomiarów. MQTT jest opcjonalne.

| Element | Zadanie | Sposób instalacji |
| --- | --- | --- |
| Integracja | Pobiera pomiary z API dodatku i tworzy encje w HA | HACS: repozytorium niestandardowe lub instalacja ręczna |
| Dodatek | Odczytuje licznik i udostępnia formularz konfiguracji | Repozytorium w sklepie dodatków HA |

Projekt jest w fazie eksperymentalnej. Integrację można dodać do HACS jako
repozytorium niestandardowe. Nie znajduje się jeszcze w domyślnym katalogu HACS.

## Obsługiwane połączenia

- TCP WRAPPER, HDLC przez TCP i bezpośredni HDLC przez port szeregowy.
- Hasła zapisane w HEX lub jako tekst; LLS i HLS (AES, MD5, SHA-1, SHA-256, GMAC).
- Wybór rejestrów pobranych z licznika, podział na grupy oraz własne profile JSON.
- Rozpoznawanie jednostek i klas HA z możliwością korekty każdego rejestru.
- Przeniesienie encji MQTT z zachowaniem identyfikatorów i historii.

Jedna instancja dodatku obsługuje jeden licznik. Program odczytuje dane;
nie zmienia ustawień urządzenia. Parametry połączenia i zabezpieczeń muszą
odpowiadać konfiguracji licznika. Nie są obsługiwane: wstępna komunikacja
optyczna IEC 62056-21, podpisy ECDSA ani profile obciążenia.

## Instalacja i konfiguracja

Repozytorium dodatku: `https://github.com/jchrzaniuk/HA-DLMS-READER`.

[Dodaj repozytorium w Home Assistant](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjchrzaniuk%2FHA-DLMS-READER)

[Otwórz integrację w HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=jchrzaniuk&repository=HA-DLMS-READER&category=integration)

1. [Zainstalować dodatek](dlms_reader/README.md).
2. [Ustawić połączenie z licznikiem i wybrać rejestry](dlms_reader/DOCS.md).
3. [Zainstalować integrację i połączyć ją z dodatkiem](custom_components/dlms_reader/README.md).

Odczyt wykonuje dodatek. Integracja pobiera wspólny zestaw pomiarów dla
wszystkich encji, więc nie otwiera kolejnej sesji z licznikiem. Wartości
w formularzu mają do pięciu miejsc po przecinku. Przeglądarka określa format
liczb i dat; dane źródłowe zachowują pełną precyzję.

## Struktura repozytorium

- `dlms_reader/`: dodatek, obraz kontenera i dokumentacja użytkownika.
- `dlms_reader/app/`: konfiguracja, komunikacja DLMS, API i opcjonalne MQTT.
- `dlms_reader/app/static/`: formularz i widok pomiarów.
- `custom_components/dlms_reader/`: integracja HA i migracja encji MQTT.
- `tests/`: testy protokołu, API, interfejsu i integracji.
- `assets/branding/`: oryginały ikon i opis ich przygotowania.
- `scripts/`: narzędzia do odtwarzania danych źródłowych.
- `docs/`: źródła opisów OBIS i dokumentacja projektu.

## Uruchomienie lokalne

Wymagany Python 3.10 lub nowszy. Obraz dodatku korzysta z Pythona 3.13.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
DLMS_DATA=tmp/dlms-data .venv/bin/python -m dlms_reader.app
```

Formularz działa pod adresem `http://127.0.0.1:8099`.
Budowanie obrazu: `docker build -t dlms-reader:local dlms_reader`.
Hasła i klucze pozostają w lokalnych danych dodatku; nie należy dodawać ich
do repozytorium. Z jednego licznika powinien korzystać jeden czytnik naraz.

## Sprawdzanie zmian

Pełny zestaw testów:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Test interfejsu wymaga działającego lokalnego serwera, Playwright i Chromium:

```sh
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/browser/check_ui.py
.venv/bin/python tests/browser/check_metadata.py
.venv/bin/python tests/browser/check_hdlc_address.py
.venv/bin/python tests/browser/check_register_groups.py
.venv/bin/python tests/browser/check_obis_pl.py
```

Test profili (`tests/browser/check_profiles.py`) wymaga pustego katalogu
`DLMS_DATA`. Testy przeglądarkowe sprawdzają edycję, walidację, profile,
format liczb i widok na telefonie.

Test integracji w środowisku HA Core:

```sh
docker run --rm -v "$PWD:/workspace" -w /workspace -e PYTHONPATH=/workspace \
  --entrypoint python ghcr.io/home-assistant/home-assistant:2026.10.2 \
  tests/component/check_native.py
```

Sprawdza uwierzytelnianie, dostępność pomiarów i migrację encji, także
odtworzenie wpisów rejestru po błędzie.

Walidację HACS i hassfest oraz test w HA Core uruchamia GitHub Actions.
Archiwum do instalacji ręcznej można przygotować poleceniem:

```sh
.venv/bin/python scripts/package_integration.py --output output/dlms_reader.zip
```

Archiwum zawiera katalog `dlms_reader/`, który należy rozpakować
w `custom_components/`. Dodatek nie jest częścią tego archiwum.

## Licencja

Projekt jest udostępniany na GNU GPL, wersja 2. Pełny tekst znajduje się
w [LICENSE](LICENSE). Dodatek korzysta z biblioteki Gurux.DLMS.Python,
również objętej GPL-2.0. Dokumenty producentów wskazane jako źródła opisów
OBIS pozostają własnością ich autorów i nie są dołączone do pakietu.
