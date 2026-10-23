# 0.2.5

- Dodano polskie opisy potwierdzonych kodów OBIS z tabel producenta POZYTON.
- Dodano odnośniki do dokumentów i stron tabel oraz zachowano opisy źródłowe.
- Kody bez potwierdzonego odpowiednika pozostają w oryginale; kody producentów nie są przenoszone między modelami.
- Zachowano własne nazwy rejestrów i wcześniejszą konfigurację encji.

# 0.2.4

- Lista wyboru zawiera wyłącznie rejestry pobrane z licznika.
- Dodano rozwijane grupy: Energia, Moc, Prąd i napięcie oraz Pozostałe parametry.
- Lista rejestrów pozostaje dostępna po odświeżeniu strony i ponownym uruchomieniu dodatku.
- Zmiana parametrów połączenia lub dostępu wymaga ponownego pobrania listy.
- Zachowano wcześniejsze wybory i parametry HA rejestrów obecnych w pobranej liście.

# 0.2.3

- Rozdzielono adres HDLC na część logiczną i fizyczną; adres złożony jest wyliczany automatycznie.
- Zachowano dotychczasowe adresy konfiguracji i profili użytkownika.
- Dodano wybór długości adresu HDLC: automatycznie, 1, 2 lub 4 bajty.
- Poprawiono polskie opisy, instrukcje i komunikaty formularza.
- Ujednolicono nazwy ustawień w dodatku, integracji i dokumentacji.
- Przetłumaczono komentarze w kodzie i przygotowano opisy do publikacji.

# 0.2.2

- Dodano rozpoznawanie parametrów HA na podstawie jednostki licznika i OBIS.
- Przypisano energii biernej klasę `reactive_energy`, a bilansom energii klasę `total`.
- Dodano automatyczne rozpoznawanie współczynnika mocy.
- Dodano edycję klasy urządzenia, klasy stanu i jednostki każdego rejestru.
- Zmiana jednostki przelicza też wartość; niezgodne parametry są odrzucane.
- Nieznany sposób sumowania energii nie włącza statystyk automatycznie.

# 0.2.1

- Usunięto wbudowane profile producentów i ich listy rejestrów.
- Dodano zapis własnych profili oraz import i eksport JSON bez haseł i kluczy.
- Zachowano wcześniejszy aktywny profil jako dane użytkownika.

# 0.2.0

- Dodano integrację HA pobierającą pomiary bezpośrednio z API dodatku.
- Dodano wersjonowane API tylko do odczytu, z osobnym tokenem dostępu.
- Uniezależniono odczyt licznika od brokera MQTT.
- Dodano wykrywanie przez Supervisora i konfigurację ręczną.
- Dodano przenoszenie encji MQTT z zachowaniem identyfikatorów i ustawień.

# 0.1.1

- Dodano informację o przyczynie blokady formularza i przycisk zatrzymania odczytu.
- Odróżniono trwającą operację od blokady edycji podczas odczytu.
- Ograniczono wyświetlanie liczb do pięciu miejsc po przecinku, zgodnie z językiem przeglądarki.
- Usunięto osobiste uwagi z interfejsu i dokumentacji.

# 0.1.0

- Dodano formularz Ingress, połączenia WRAPPER i HDLC oraz uwierzytelnianie LLS i HLS.
- Dodano test sesji, wybór rejestrów i MQTT Discovery.
