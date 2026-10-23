# DLMS/COSEM Reader — dodatek

Dodatek odczytuje licznik DLMS/COSEM i przekazuje pomiary integracji Home
Assistant. Połączenie, dane dostępu i rejestry ustawia się w formularzu
otwieranym z panelu HA. MQTT można włączyć osobno.

Jedna instancja obsługuje jeden licznik. Dodatek nie zmienia ustawień urządzenia.
Projekt jest w fazie eksperymentalnej.

## Instalacja z repozytorium

Wymagany Home Assistant z Supervisorem i dostęp do licznika przez TCP lub
port szeregowy. Dodatek instaluje się w sklepie dodatków HA.
Integrację trzeba zainstalować osobno przez HACS jako repozytorium niestandardowe
lub skopiować jej pliki ręcznie.

1. Otworzyć sklep dodatków HA i w menu wybrać **Repozytoria**.
2. Dodać `https://github.com/jchrzaniuk/HA-DLMS-READER`.
3. Zainstalować **DLMS/COSEM Reader** z dodanego repozytorium.
4. Uruchomić dodatek i otworzyć jego interfejs.

Przy pierwszej instalacji obraz kontenera jest budowany lokalnie przez HA.
W środowisku deweloperskim można też skopiować ten katalog do
`/addons/dlms_reader` i odświeżyć lokalny sklep poleceniem `ha store reload`.

Formularz korzysta z Ingress, czyli dostępu przez panel HA. Nie wymaga
otwierania portu na hoście. Instrukcja połączenia z licznikiem znajduje się
w [dokumentacji konfiguracji](DOCS.md).

## Połączenie z Home Assistant

[Integracja DLMS/COSEM Reader](../custom_components/dlms_reader/README.md)
pobiera pomiary z API dodatku. API działa na wewnętrznym porcie `8098`,
wymaga osobnego tokena i udostępnia dane tylko do odczytu. Nie zwraca haseł
ani kluczy licznika.

MQTT jest domyślnie wyłączone w nowych instalacjach. Awaria brokera nie
przerywa odczytu licznika ani udostępniania pomiarów przez API.

## Obsługiwane funkcje

- TCP WRAPPER, HDLC przez TCP oraz bezpośredni HDLC przez port szeregowy.
- Adresowanie LN i SN; SN wymaga adresu bazowego każdego rejestru.
- Brak uwierzytelniania, LLS, HLS-AES, HLS-MD5, HLS-SHA1, HLS-SHA256 i HLS-GMAC.
- Zabezpieczenie wiadomości niezależne od uwierzytelniania; zestawy 0 i 2.
- Test połączenia i wybór pobranych rejestrów klasy 3 i 4 w rozwijanych grupach.
- Własne profile JSON oraz korekta klas HA i jednostek każdego rejestru.

Ustawienia muszą odpowiadać asocjacji licznika, czyli dostępowi przypisanemu
do wybranego adresu klienta. Nie ma wbudowanych profili producentów.
Wstępna komunikacja optyczna IEC 62056-21, podpisy ECDSA i profile obciążenia
nie są obsługiwane.

## Dane dodatku

Katalog `/data` zawiera konfigurację, profile i liczniki ramek. Pliki mają
uprawnienia `0600`. Kopia danych obejmuje hasła i klucze, dlatego nie należy
publikować jej razem z profilem urządzenia.

Przy przenoszeniu instalacji trzeba zachować dane dodatku, zwłaszcza stan
licznika ramek. Wznawianie odczytu i uruchamianie dodatku przy starcie HA
to dwa osobne ustawienia; w nowej instalacji oba są wyłączone.

Kod protokołu: [Gurux.DLMS.Python](https://github.com/Gurux/Gurux.DLMS.Python).
Polecenia do pracy nad projektem: [README repozytorium](../README.md#uruchomienie-lokalne).
