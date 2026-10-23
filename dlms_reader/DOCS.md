# Konfiguracja odczytu

Formularz ma cztery etapy: **Połączenie**, **Dostęp**, **Test i rejestry**
oraz **Home Assistant**. Do konfiguracji potrzebne są parametry licznika:
transport, adresy klienta i serwera oraz dane uwierzytelniania.

## Połączenie z licznikiem

1. Wybrać **Własna konfiguracja** albo zapisany profil użytkownika.
2. Podać nazwę urządzenia w HA i jego stały identyfikator.
   Zmiana identyfikatora tworzy nowe encje.
3. Wybrać transport i podać adres urządzenia.
   Dla portu szeregowego potrzebna jest pełna ścieżka, np. `/dev/serial/by-id/…`.
4. Ustawić adresy klienta i serwera zgodnie z konfiguracją licznika.

WRAPPER i HDLC to różne sposoby przesyłania danych DLMS. W trybie szeregowym
dodatek rozpoczyna komunikację bezpośrednio od HDLC; nie wykonuje wstępnej
komunikacji optycznej IEC 62056-21.

### Adresy DLMS

Dla WRAPPER podać adres serwera. Dla HDLC podać osobno **adres logiczny**
i **adres fizyczny**. Adres fizyczny identyfikuje urządzenie na magistrali;
adres logiczny wybiera urządzenie logiczne wewnątrz licznika, najczęściej `1`.
Dodatek sam wylicza adres złożony. Na przykład logiczny `1` i fizyczny `40`
dają adres złożony `168` w formacie dwubajtowym.

Adres logiczny `0` pozwala zachować adresowanie bez części logicznej.
Ten tryb obsługuje adres fizyczny od `1` do `127` w formacie jednobajtowym.
Długość adresu jest dobierana automatycznie; w parametrach zaawansowanych
można wymusić 1, 2 lub 4 bajty zgodnie z dokumentacją urządzenia.
Wcześniej zapisane adresy złożone, także w profilach, są rozdzielane
automatycznie bez zmiany parametrów połączenia.

## Dane dostępu

W etapie **Dostęp** należy wybrać uwierzytelnianie przypisane do adresu klienta.
LLS używa hasła. Mechanizmy HLS mogą wymagać hasła, kluczy i identyfikatorów
systemowych (`system title`), zależnie od wybranego wariantu.

Hasło w formacie **HEX** oznacza bajty, np. `41 42`, a nie tekst „41 42”.
Hasło tekstowe korzysta z wybranego kodowania znaków. Puste pole zachowuje
zapisane hasło lub klucz. Wczytanie innego profilu wymaga ponownego podania
danych uwierzytelniania.

Zabezpieczenie wiadomości ustawia się osobno. Przy HLS-GMAC lub szyfrowaniu
trzeba zachować stan licznika ramek. Jeden identyfikator systemowy klienta
i zestaw kluczy nie powinny służyć dwóm niezależnym czytnikom.

## Test i wybór rejestrów

1. Wybrać **Pobierz rejestry z licznika**, aby pobrać listę obiektów asocjacji.
   Pobieranie działa w tle i może trwać do dwóch minut.
2. Rozwinąć grupę **Energia**, **Moc**, **Prąd i napięcie** lub **Pozostałe parametry**.
3. Zaznaczyć rejestry do odczytu. Nowe pozycje pozostają niezaznaczone.
   Wcześniejszy wybór, nazwy i parametry HA są zachowane dla rejestrów obecnych na liście.
4. Wybrać **Zapisz ustawienia** lub **Zapisz i uruchom odczyt**.

Polskie opisy kodów mają odnośniki do opublikowanych tabel producenta.
Kody bez potwierdzonego odpowiednika zachowują opis źródłowy.
[Źródła i zakres słownika](../docs/obis-pl.md).

Lista wyboru zawiera wyłącznie rejestry pobrane z licznika. Podział wynika
z kodów OBIS; nierozpoznane kody trafiają do pozostałych parametrów.
Filtr wyszukuje po kodzie i nazwie oraz rozwija grupy z wynikami.

Lista jest zapisywana w `/data/register-catalog.json` i pozostaje dostępna
po odświeżeniu strony i ponownym uruchomieniu dodatku. Zmiana parametrów
połączenia lub dostępu wymaga ponownego pobrania listy. Wczytanie profilu
nie zastępuje pobrania rejestrów z podłączonego licznika.

Osobny przycisk **Zapisz i przetestuj połączenie** sprawdza sesję DLMS
i odczytuje do trzech wybranych rejestrów.

Dodatek obsługuje liczbowe rejestry klasy 3 i 4. Dla adresowania SN każdy
rejestr musi mieć adres bazowy. Podczas odczytu i testu formularz jest
zablokowany. Przycisk **Zatrzymaj i edytuj** kończy bieżący odczyt
i udostępnia ustawienia.

## Klasy i jednostki w HA

Sekcja **Parametry HA** w każdym wierszu pokazuje ustawienia rejestru.
Wybór **Automatycznie** korzysta z jednostki licznika i kodu OBIS.

| Parametr | Znaczenie |
| --- | --- |
| Klasa urządzenia | Rodzaj wielkości, np. energia, moc lub napięcie |
| Klasa stanu | Sposób tworzenia statystyk: pomiar bieżący, suma lub suma rosnąca |
| Jednostka | Jednostka przekazywana do HA wraz z przeliczoną wartością |

Znane liczniki energii kierunkowej i taryfowej otrzymują `total_increasing`.
Bilans energii, np. `16.8.0`, używa `total`, bo może rosnąć i maleć.
Moc, napięcie, prąd i częstotliwość otrzymują `measurement`. Energia bierna
ma klasę `reactive_energy`; energia pozorna pozostaje bez osobnej klasy urządzenia.

Jeśli sposób sumowania energii jest nieznany, statystyki nie włączają się
automatycznie. Można wskazać klasę ręcznie albo wybrać **Bez statystyk**.
Zmiana jednostki przelicza wartość, np. 1500 W na 1,5 kW. Dodatek odrzuca
niezgodne jednostki. Nieznanej jednostki nie można przeliczyć bez znajomości jej znaczenia.
Zmiany obowiązują po zapisaniu ustawień i kolejnym odczycie.

## Pomiary w Home Assistant

1. [Zainstalować integrację](../custom_components/dlms_reader/README.md).
2. W etapie **Home Assistant** wybrać **Zgłoś integrację w Home Assistant**.
3. Otworzyć **Ustawienia → Urządzenia i usługi** i skonfigurować wykrytą integrację.
4. W dodatku wybrać **Zapisz i uruchom odczyt**.

Do konfiguracji ręcznej służy przycisk **Dane połączenia ręcznego**.
API wymaga osobnego tokena i działa na wewnętrznym porcie `8098`.
Token daje dostęp do pomiarów i ich parametrów, bez haseł ani kluczy DLMS.

Zapis ustawień nie wznawia odczytu. Opcja **Wznawiaj odczyt po uruchomieniu
dodatku** dotyczy kolejnego uruchomienia procesu. Uruchamianie samego dodatku
przy starcie HA ustawia się osobno w jego panelu.

Formularz pokazuje do pięciu miejsc po przecinku. Format liczb i dat wynika
z ustawień językowych przeglądarki. Encje w HA zachowują pełną precyzję danych.

## Własne profile

Sekcja **Zapis i przenoszenie profili** służy do zapisu ustawień pod własną
nazwą oraz importu i eksportu JSON. Nowa instalacja nie ma profili producentów.
Aby utworzyć kolejny profil, należy wybrać **Własna konfiguracja** i podać nazwę.

Plik `/data/profiles.json` zawiera parametry protokołu i wybrane rejestry, także
korekty klas HA. Profile nie zawierają haseł, kluczy, identyfikatorów systemowych,
adresu urządzenia ani ustawień HA i MQTT. Aktualizacja zachowuje wcześniejszy
aktywny profil jako dane użytkownika, bez zmiany połączenia i rejestrów.

## Opcjonalne MQTT

Publikacja MQTT i **MQTT Discovery** to dwa osobne ustawienia. Discovery
tworzy encje MQTT; przy korzystaniu z integracji DLMS/COSEM Reader powinno
pozostać wyłączone, aby nie powielać encji.

Pusty adres brokera oznacza pobranie danych z usługi MQTT Supervisora,
jeśli ta usługa jest dostępna. Można też podać własny broker i włączyć TLS
z weryfikacją certyfikatu. Brak brokera nie zatrzymuje odczytu przez API.
Przeniesienie starszych encji opisuje [instrukcja migracji](../custom_components/dlms_reader/README.md#migracja-encji-mqtt).

## Kopia danych

Kopia katalogu `/data` zawiera dane dostępowe i stan liczników ramek.
Trzeba ją zachować przy przenoszeniu instalacji. Plik profilu JSON nie
zastępuje kopii danych dodatku.
