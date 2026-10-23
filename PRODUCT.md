# Product

<!-- impeccable:product-schema 1 -->

## Platform

web — publiczny dodatek Home Assistant z interfejsem Ingress.

## Users

Użytkownicy Home Assistant konfigurujący odczyt własnych liczników DLMS/COSEM.

## Product Purpose

Konfiguracja połączenia z licznikiem i pomiary jako encje Home Assistant. Dodatek odczytuje licznik, a integracja pobiera dane z jego API. Publikację MQTT można włączyć osobno.

## Operating Context

Jedna instancja dodatku obsługuje jeden licznik. Połączenie przez TCP lub port szeregowy. Formularz ma etapy: Połączenie, Dostęp, Test i rejestry oraz Home Assistant.

## Capabilities and Constraints

- TCP WRAPPER, TCP HDLC i bezpośredni szeregowy HDLC.
- Hasła HEX lub tekstowe, LLS i mechanizmy HLS biblioteki Gurux.
- Transport, format hasła, uwierzytelnianie i zabezpieczenie wiadomości są niezależne.
- Profile tworzy użytkownik. Zawierają parametry protokołu i rejestry, bez haseł, kluczy i adresów konkretnej instalacji.
- Program nie zmienia ustawień licznika i nie wykonuje wstępnej komunikacji optycznej IEC 62056-21.

## Public Interface

Neutralne i bezosobowe teksty. Nazwy modeli wyłącznie jako dane urządzeń i etykiety profili. Bez anegdotycznych uwag o lokalnych testach.

Pomiary: maksymalnie pięć miejsc po przecinku, separatory liczb i format dat zgodne z ustawieniami językowymi przeglądarki. Prezentacja nie zmienia wartości źródłowych.

## Product Principles

Wymagane pola zależą od konfiguracji. Komunikat wyjaśnia przyczynę blokady formularza i sposób powrotu do edycji. Zapisane hasła i klucze pozostają na serwerze. Zmiana parametrów połączenia nie zmienia identyfikatorów encji; zmiana stałego identyfikatora urządzenia tworzy nowe encje.
