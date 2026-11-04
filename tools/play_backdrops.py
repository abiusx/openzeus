"""Copy the full-screen pictures behind the campaign screens into viewer/play/atlas/backdrops/ (git-ignored: the
original's art) for play mode (viewer/play/ui.js uiBackdrop, docs/play/campaign.md "Backdrops").

    python3 tools/play_backdrops.py      (also the world map pictures: viewer/play/atlas/world/, see world_pictures)

The exe loads them with backdrop_jpeg_load through FUN_00505310 (case 8 zeus_briefing, 9 zeus_defeat, 10 / 0x15
zeus_victory, 0x12 Zeus_FE_CampaignSelection, 0x13 Zeus_FE_MissionIntroduction, 0x14 Zeus_FE_tutorials, ...)
and shows the 1024 x 768 picture centred (fullscreen_background_b 0x00422270: source offset
((0x400 - W) / 2, (0x300 - H) / 2)). Which screen shows which, matched on the oracle shots outside the windows
(mean channel difference, the rest > 100): briefing 0x35 Zeus_FE_MissionIntroduction (10.1; 1L-europa1 s40),
adventure complete 0x43 Zeus_Victory (10.3; 1L4-complete complete), defeat 0x33 Zeus_Defeat (4.6; 1L3-time-limit
t104), the adventure list Zeus_FE_CampaignSelection (16.9; 1L-europa1 s32), the family menu Zeus_FE_ChooseGame (8.4 with
the name box, the logo and the buttons masked; next best Zeus_FE_MainMenu 13.0; newgame-flow s4), the tutorials list
Zeus_FE_tutorials (3.5; 1L-tutlist list); by the decompile: the main menu (screen 0, FUN_005900b0: case 0x11
Poseidon_FE_MainMenu; newgame-flow s1-menu) and the leader-name screen (0x36, FUN_00590150: case 5 Zeus_FE_Registry;
s2 / s3). The pictures carry the menus' boxes and slots (the name box, the tutorials' blue / magenta button slots);
the exe draws its buttons, logo and texts over them (viewer/play/newgame.js). The files are copied unchanged (the browser decodes them; the exe's decoder and its RGB555 screen
differ by a few levels).
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "zeus-original", "app", "DATA")
OUT = os.path.join(ROOT, "viewer", "play", "atlas", "backdrops")
FILES = {"briefing": "Zeus_FE_MissionIntroduction.jpg", "complete": "Zeus_Victory.jpg", "defeat": "Zeus_Defeat.jpg",
         "adventures": "Zeus_FE_CampaignSelection.JPG", "family": "Zeus_FE_ChooseGame.jpg",
         "tutorials": "Zeus_FE_tutorials.JPG", "mainmenu": "Poseidon_FE_MainMenu.JPG", "registry": "Zeus_FE_Registry.jpg"}


WORLD = os.path.join(ROOT, "viewer", "play", "atlas", "world")


def world_pictures():
    """The world map pictures Zeus_MapOfGreece01..10.JPG -> viewer/play/atlas/world/*.jpg, unchanged (data/play/world.json
    "pictures", tools/play_world.py)."""
    os.makedirs(WORLD, exist_ok=True)
    for n in range(1, 11):
        shutil.copyfile(os.path.join(DATA, f"Zeus_MapOfGreece{n:02d}.JPG"), os.path.join(WORLD, f"Zeus_MapOfGreece{n:02d}.jpg"))


def main():
    os.makedirs(OUT, exist_ok=True)
    for key, name in FILES.items():
        shutil.copyfile(os.path.join(DATA, name), os.path.join(OUT, key + ".jpg"))
        print(f"{name} -> viewer/play/atlas/backdrops/{key}.jpg")
    world_pictures()
    print("Zeus_MapOfGreece01..10.JPG -> viewer/play/atlas/world/")


if __name__ == "__main__":
    main()
