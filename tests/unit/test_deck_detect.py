"""Steam Deck detection against fake /sys, /proc and /etc trees."""

from linux_game_benchmark.deck.detect import DeckInfo, detect_steam_deck


def _tree(tmp_path, product=None, board=None, cpu=None, pci=None, os_release=None, procs=()):
    dmi = tmp_path / "sys/devices/virtual/dmi/id"
    dmi.mkdir(parents=True)
    if product is not None:
        (dmi / "product_name").write_text(product + "\n")
    if board is not None:
        (dmi / "board_name").write_text(board + "\n")
    (tmp_path / "proc").mkdir()
    if cpu is not None:
        (tmp_path / "proc/cpuinfo").write_text(f"processor\t: 0\nmodel name\t: {cpu}\n")
    if pci is not None:
        card = tmp_path / "sys/class/drm/card0/device"
        card.mkdir(parents=True)
        (card / "device").write_text(pci + "\n")
    if os_release is not None:
        (tmp_path / "etc").mkdir()
        (tmp_path / "etc/os-release").write_text(os_release)
    for pid, comm in procs:
        (tmp_path / "proc" / str(pid)).mkdir()
        (tmp_path / "proc" / str(pid) / "comm").write_text(comm + "\n")
    return tmp_path


def test_lcd_by_dmi_name(tmp_path):
    info = detect_steam_deck(_tree(tmp_path, product="Jupiter"))
    assert info.is_deck and info.model == "LCD" and info.device_class == "steam_deck_lcd" and info.label == "LCD"


def test_oled_by_dmi_name(tmp_path):
    info = detect_steam_deck(_tree(tmp_path, product="Galileo"))
    assert info.model == "OLED" and info.device_class == "steam_deck_oled"


def test_board_name_is_used_when_the_product_name_is_empty(tmp_path):
    assert detect_steam_deck(_tree(tmp_path, product="", board="Galileo")).model == "OLED"


def test_fallback_to_the_apu_name_in_cpuinfo(tmp_path):
    assert detect_steam_deck(_tree(tmp_path, cpu="AMD Custom APU 0405")).model == "LCD"
    assert detect_steam_deck(_tree(tmp_path / "b", cpu="AMD Custom APU 0932")).model == "OLED"


def test_fallback_to_the_gpu_pci_id(tmp_path):
    assert detect_steam_deck(_tree(tmp_path, pci="0x163f")).model == "LCD"
    assert detect_steam_deck(_tree(tmp_path / "b", pci="0x1435")).model == "OLED"


def test_a_normal_pc_is_not_a_deck(tmp_path):
    info = detect_steam_deck(_tree(tmp_path, product="B650 AORUS", cpu="AMD Ryzen 7 9800X3D", pci="0x744c"))
    assert info == DeckInfo(is_deck=False) and info.device_class is None and info.label == ""


def test_steamos_version_and_game_mode(tmp_path):
    root = _tree(tmp_path, product="Jupiter", os_release='ID=steamos\nVERSION_ID="3.7.13"\n',
                 procs=[(101, "bash"), (102, "gamescope-wl")])
    info = detect_steam_deck(root)
    assert info.steamos_version == "3.7.13" and info.game_mode is True


def test_desktop_mode_and_other_distro(tmp_path):
    root = _tree(tmp_path, product="Jupiter", os_release="ID=arch\nVERSION_ID=rolling\n", procs=[(5, "plasmashell")])
    info = detect_steam_deck(root)
    assert info.is_deck and info.steamos_version == "" and info.game_mode is False


def test_missing_files_do_not_raise(tmp_path):
    assert detect_steam_deck(tmp_path / "does-not-exist").is_deck is False


# ----- every version of the Deck that is out there -----------------------------------------------------------------------

import pytest

STEAMOS = 'NAME="SteamOS"\nID=steamos\nVERSION_ID={v}\nVARIANT_ID=steamdeck\n'
OTHER_DISTROS = {
    "bazzite": 'NAME="Bazzite"\nID=bazzite\nVERSION_ID=42\n',
    "chimeraos": 'NAME="ChimeraOS"\nID=chimeraos\n',
    "holoiso": 'NAME="HoloISO"\nID=holoiso\n',
    "arch-desktop": 'NAME="Arch Linux"\nID=arch\n',
}


@pytest.mark.parametrize("version", ["3.5.19", "3.6.22", "3.7.13", "3.8.0-beta"])
@pytest.mark.parametrize("product, model, klass", [("Jupiter", "LCD", "steam_deck_lcd"), ("Galileo", "OLED", "steam_deck_oled")])
def test_both_models_on_any_steamos_release(tmp_path, product, model, klass, version):
    info = detect_steam_deck(_tree(tmp_path, product=product, os_release=STEAMOS.format(v=version)))
    assert (info.is_deck, info.model, info.device_class, info.steamos_version) == (True, model, klass, version)


@pytest.mark.parametrize("distro", sorted(OTHER_DISTROS))
@pytest.mark.parametrize("product, model", [("Jupiter", "LCD"), ("Galileo", "OLED")])
def test_a_deck_with_another_system_on_it_is_still_a_deck(tmp_path, product, model, distro):
    info = detect_steam_deck(_tree(tmp_path, product=product, os_release=OTHER_DISTROS[distro]))
    assert info.is_deck and info.model == model and info.steamos_version == ""


@pytest.mark.parametrize("evidence, model", [
    (dict(cpu="AMD Custom APU 0405"), "LCD"), (dict(cpu="AMD Custom APU 0932"), "OLED"),
    (dict(pci="0x163f"), "LCD"), (dict(pci="0x1435"), "OLED"),
    (dict(product="", board="Jupiter"), "LCD"), (dict(product="", board="Galileo"), "OLED"),
])
def test_each_single_signal_is_enough(tmp_path, evidence, model):
    assert detect_steam_deck(_tree(tmp_path, **evidence)).model == model


def test_the_model_is_not_guessed_when_signals_disagree_with_nothing(tmp_path):
    # a Deck of a model this table does not know: the APU name still proves it is a Deck, the class stays generic
    info = detect_steam_deck(_tree(tmp_path, product="Unknown", cpu="AMD Custom APU 0405"))
    assert info.is_deck and info.device_class == "steam_deck_lcd"


@pytest.mark.parametrize("product, cpu, os_release", [
    ("83L3", "AMD Ryzen Z2 Go", STEAMOS.format(v="3.7.13")),         # a handheld that runs SteamOS is not a Deck
    ("RC71L", "AMD Ryzen Z1 Extreme", STEAMOS.format(v="3.7.13")),
    ("B650 AORUS ELITE", "AMD Ryzen 7 9800X3D", STEAMOS.format(v="3.7.13")),
])
def test_other_machines_running_steamos_are_not_decks(tmp_path, product, cpu, os_release):
    info = detect_steam_deck(_tree(tmp_path, product=product, cpu=cpu, os_release=os_release))
    assert not info.is_deck and info.device_class is None
