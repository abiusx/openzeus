# Zeus original: inventory

Source: GOG `setup_zeus_and_poseidon_2.1.0.10.exe`, unpacked with `innoextract` into `zeus-original/app/`.

| Path | What | Format |
|---|---|---|
| `Zeus.exe` | game engine and all hardcoded logic | PE32, i386 (Win32). Reverse-engineer with Ghidra. |
| `Model/Zeus_Model_*.txt` | per-difficulty building stats (cost, desirability, employees, fire/damage risk) and house evolution rules (desirability thresholds, goods needed, capacity, tax, crime, disease) | text, with the data in `{}`. The file headers document the columns. |
| `Model/Figure_model_*.txt` | unit combat stats (HP, attack, armor, missile, speed, morale) | text `{}` |
| `Model/monster_behavior_*.txt` | monster AI parameters | text |
| `Model/Sanctuary_*.txt`, `Poseidon_Pyramid_*.txt`, `palace.txt`, `statue_conan.txt` | layouts and construction stages for multi-tile monuments | text |
| `Model/Tax_Sentiment_Model.txt` | how tax rates affect sentiment | text |
| `Model/Zeus event*.txt`, `Zeus attitude advice.txt` | events, messages, advisor logic | text |
| `DATA/*.sg3` + `*.555` (90 / 103) | sprites: `.sg3` is the index (offsets, sizes, palettes), `.555` holds the RGB555 pixel data | Impressions SG format, documented by the Julius/Augustus projects and older community tools |
| `DATA/*.jpg` | menu and background images | JPEG |
| `Adventures/*.pak`, subdirs | campaigns, scenarios, tutorials (maps + scripted goals) | unknown, needs reverse engineering |
| `Zeus_Text.eng`, `Zeus_MM.eng`, `Zeus_Editor_Text.eng` | all in-game text strings and messages | Impressions text format |
| `Audio/` | music (mp3), ambient, voice, wav sfx, `sound_fxU.txt`, `music.txt` | standard |
| `Binks/` | intro videos | Bink (ffmpeg can decode) |
| `*.pdf` | manuals for the game, Poseidon, the editors, and the quick-reference card | the designer-facing description of the rules |
| `Save/` | save games | binary, unknown |
