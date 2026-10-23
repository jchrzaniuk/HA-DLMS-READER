# Design

## Authority

Formularz rozwija konfigurator z pliku output/pdf/konfigurator-dlms.pdf. Służy do ustawienia odczytu w HA. Ikony dodatku i integracji mają wspólną turkusową obudowę oraz różne symbole: impuls pomiarowy i połączone węzły.

## Interface

Jasne tło formularza, ciemny tekst i turkusowe przyciski. Etykiety nad polami, wyjaśnienia pod nimi i cienkie linie między sekcjami. Brak dekoracyjnych wykresów i przykładowych danych udających odczyty. Krój systemowy HA; cyfry pomiarów mają jednakową szerokość.

## Flow

Połączenie → Dostęp → Test i rejestry → Home Assistant. Dodatkowe parametry są w rozwijanych sekcjach. Profile pochodzą z danych użytkownika, bez haseł i kluczy; nie ma profili producentów w kodzie. Błędy pojawiają się przy formularzu, a wynik odczytu zawiera czas. Zatrzymany odczyt i utrata połączenia mają różne komunikaty.

## Responsive and accessibility

Na wąskim ekranie pola zajmują jedną kolumnę. Fokus klawiatury jest widoczny, stan odczytu ma opis tekstowy, a kontrolki przeglądarki mają powiązane etykiety. Hasła i klucze korzystają z pól password; zapisane wartości pozostają na serwerze. Interfejs jest po polsku.
