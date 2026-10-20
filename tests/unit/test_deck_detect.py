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
