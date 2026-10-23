# Ikony DLMS/COSEM Reader

Obie ikony mają turkusową obudowę, białe wnętrze i miętowy akcent.
Dodatek wyróżnia impuls pomiarowy oraz złącza pod obudową, a integrację —
trzy połączone węzły. Oryginały to przezroczyste pliki PNG wygenerowane
narzędziem `image_gen`. Dokładne polecenia zapisano w [prompts.json](prompts.json).

## Pliki używane przez Home Assistant

- `dlms_reader/icon.png`: ikona dodatku, 128 × 128 pikseli.
- `dlms_reader/logo.png`: obraz na stronie dodatku, 256 × 256 pikseli.
- `custom_components/dlms_reader/brand/icon.png`: ikona integracji, 256 × 256 pikseli.
- `custom_components/dlms_reader/brand/icon@2x.png`: wersja o większej rozdzielczości, 512 × 512 pikseli.

Oryginały znajdują się w tym katalogu: `dlms-addon-master.png` oraz
`dlms-integration-master.png`. Kopie w rozmiarach dla HA przygotowano
programem `sips` w macOS, z zachowaniem przezroczystości. Obrazy pasują
do jasnego i ciemnego tła. Przy braku osobnego logo integracji HA używa ikony.

Wymagania opisują [dokumentacja ikon integracji](https://contributors.home-assistant.io/core/integrations/brands/)
i [zasady prezentacji dodatku](https://contributors.home-assistant.io/apps/guides/presentation/).
