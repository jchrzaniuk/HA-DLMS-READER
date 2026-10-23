# DLMS/COSEM Reader — integracja

Integracja pobiera pomiary z dodatku DLMS/COSEM Reader i tworzy encje
w Home Assistant. Wszystkie encje korzystają z jednego odczytu API.
Połączenie z licznikiem obsługuje dodatek. MQTT nie jest potrzebne.

## Instalacja

Wymagany Home Assistant 2026.10 lub nowszy oraz działający
[dodatek DLMS/COSEM Reader](../../dlms_reader/README.md).
Dodatek instaluje się osobno w sklepie dodatków HA. HACS pobiera wyłącznie
integrację.

### Przez HACS

Repozytorium można dodać do HACS jako własne. Nie znajduje się jeszcze
w domyślnym katalogu HACS.

1. Otworzyć HACS i w menu wybrać **Repozytoria niestandardowe**.
2. Podać `https://github.com/jchrzaniuk/HA-DLMS-READER`.
3. Wybrać typ **Integracja** i dodać repozytorium.
4. Pobrać **DLMS/COSEM Reader**.
5. Uruchomić ponownie HA Core.

[Otwórz repozytorium w HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=jchrzaniuk&repository=HA-DLMS-READER&category=integration)

### Ręcznie

1. Skopiować katalog `custom_components/dlms_reader` do katalogu konfiguracji HA.
2. Uruchomić ponownie HA Core.

### Po instalacji

1. W dodatku wybrać **Zgłoś integrację w Home Assistant**.
2. Otworzyć **Ustawienia → Urządzenia i usługi**.
3. Skonfigurować wykrytą integrację.

Do konfiguracji ręcznej potrzebne są adres, port i token z sekcji
**Dane połączenia ręcznego** w dodatku. Adres zależy od repozytorium instalacji;
należy skopiować go z dodatku. Port API to `8098`. API działa w wewnętrznej sieci HA;
nie wymaga otwierania portu na hoście. Token daje dostęp tylko do pomiarów
i ich parametrów, bez haseł ani kluczy DLMS.

## Encje i statystyki

Jednostki, klasy urządzeń i klasy stanu pochodzą z danych dodatku.
Energia czynna używa klasy `energy`, bierna — `reactive_energy`, a moc —
`power`, `reactive_power` lub `apparent_power`. Znane liczniki energii
kierunkowej otrzymują `total_increasing`; bilans energii używa `total`.
Pomiary bieżące, np. napięcie, mają klasę `measurement`.

Parametry można zmienić w dodatku: **Test i rejestry → Parametry HA**.
Nieznany sposób sumowania energii nie włącza statystyk automatycznie.
Energia pozorna pozostaje bez osobnej klasy urządzenia, z zachowaniem jednostki.

HA otrzymuje pełną precyzję pomiarów. Integracja sugeruje wyświetlanie do
pięciu miejsc po przecinku; format liczb zależy od ustawień HA.

## Dostępność pomiarów

Encje są niedostępne, gdy odczyt jest zatrzymany, API nie odpowiada lub
pomiar jest starszy niż dopuszcza dodatek. Brak dostępu do jednego rejestru
nie blokuje pozostałych. Nowo wybrane rejestry pojawiają się bez restartu HA.
Po usunięciu rejestru z konfiguracji encja pozostaje niedostępna, żeby zachować
jej historię.

## Migracja encji MQTT

Przed dodaniem integracji:

1. Zatrzymać odczyt w dodatku.
2. Wyłączyć **Publikacja MQTT**.
3. Zapisać ustawienia i wznowić odczyt.
4. Podczas dodawania integracji zaznaczyć **Przenieś istniejące encje MQTT**.

Migracja obejmuje encje o zgodnych identyfikatorach przypisane do tego
samego urządzenia. Zachowuje `entity_id`, identyfikator wpisu rejestru,
urządzenie, nazwy, etykiety i ustawienia użytkownika. Historia i statystyki
pozostają powiązane z dotychczasowym `entity_id`.

Po przeniesieniu wpisów integracja usuwa ich konfigurację MQTT Discovery.
Nie wyłącza integracji MQTT ani innych urządzeń korzystających z brokera.
Zapis migracji znajduje się w danych HA pod kluczem
`dlms_reader.migration.<entry_id>`.

## Aktualizacja i usunięcie

Aktualizację integracji pobiera się w HACS, a następnie uruchamia ponownie
HA Core. Dodatek ma własne wersje i aktualizuje się osobno w sklepie HA.

Aby usunąć integrację, należy usunąć jej wpis w **Ustawienia → Urządzenia
i usługi**, a następnie usunąć pakiet w HACS i uruchomić ponownie HA Core.
Nie usuwa to dodatku ani jego ustawień.

## Licencja

GNU GPL, wersja 2. Pełny tekst znajduje się w [LICENSE](LICENSE).
