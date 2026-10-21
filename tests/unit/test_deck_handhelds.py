"""Other handhelds (ROG Ally, Legion Go, MSI Claw, ...): recognised by the DMI vendor + product, sent as such to the server."""

import pytest

from linux_game_benchmark.deck import upload
from linux_game_benchmark.deck.detect import DeckInfo, detect_steam_deck

from .test_deck_detect import _tree

MODELS = [
    ("ASUSTeK COMPUTER INC.", "ROG Ally RC71L_RC71L", "", "rog_ally", "ROG Ally"),
    ("ASUSTeK COMPUTER INC.", "ROG Ally X RC72LA_RC72LA", "", "rog_ally_x", "ROG Ally X"),
    ("ASUSTeK COMPUTER INC.", "ROG Xbox Ally X RC73XA", "", "rog_xbox_ally", "ROG Xbox Ally"),
    ("LENOVO", "83E1", "Legion Go 8APU1", "legion_go", "Legion Go"),
    ("LENOVO", "83L3", "Legion Go S 8ASP2", "legion_go_s", "Legion Go S"),
    ("LENOVO", "83N0", "Legion Go 2 8ASP2", "legion_go_2", "Legion Go 2"),
    ("Micro-Star International Co., Ltd.", "Claw A1M", "", "msi_claw", "MSI Claw"),
    ("AYANEO", "AYANEO 2S", "", "ayaneo", "AYANEO"),
    ("GPD", "G1619-04", "", "gpd", "GPD"),
    ("ONE-NETBOOK", "ONEXPLAYER 2 Pro", "", "onexplayer", "ONEXPLAYER"),
]


@pytest.mark.parametrize("vendor, product, version, key, label", MODELS)
def test_known_handhelds_are_recognised(tmp_path, vendor, product, version, key, label):
    info = detect_steam_deck(_tree(tmp_path, vendor=vendor, product=product, version=version))
    assert info.is_deck and not info.valve and info.handheld == key
    assert info.device_class == key and info.label == label and info.name == label
    assert (info.vendor, info.product) == (vendor, product)


@pytest.mark.parametrize("vendor, product, version", [
    ("ASUSTeK COMPUTER INC.", "ROG Zephyrus G14 GA403", ""),
    ("LENOVO", "83DH", "Legion 5 15ARP8"),
    ("Micro-Star International Co., Ltd.", "MS-7E07", ""),
    ("Dell Inc.", "XPS 13 9340", ""),
    ("ASUSTeK COMPUTER INC.", "", ""),
])
def test_laptops_and_desktops_are_not_handhelds(tmp_path, vendor, product, version):
    info = detect_steam_deck(_tree(tmp_path, vendor=vendor, product=product, version=version))
    assert not info.is_deck and info.device_class is None and info.name == ""


def test_the_deck_stays_the_deck_and_keeps_its_dmi_strings(tmp_path):
    info = detect_steam_deck(_tree(tmp_path, vendor="Valve", product="Jupiter"))
    assert info.is_deck and info.valve and info.handheld == "" and info.model == "LCD"
    assert info.device_class == "steam_deck_lcd" and info.name == "Steam Deck LCD" and info.vendor == "Valve"


def test_deck_hardware_beats_a_handheld_name(tmp_path):
    info = detect_steam_deck(_tree(tmp_path, vendor="LENOVO", product="83E1", version="Legion Go 8APU1", pci="0x163f"))
    assert info.valve and info.model == "LCD"


SYSTEM = {"os": {"name": "Bazzite 42", "kernel": "6.12.0"}, "gpu": {"model": "AMD Radeon Graphics (RADV PHOENIX)", "driver_version": "Mesa 25.1"},
          "ram": {"total_gb": 16}, "cpu": {"model": "AMD Ryzen Z1 Extreme"}}


def test_the_upload_carries_the_dmi_strings_and_the_real_chip_names():
    ally = DeckInfo(is_deck=True, handheld="rog_ally", handheld_label="ROG Ally", vendor="ASUSTeK COMPUTER INC.", product="ROG Ally RC71L_RC71L")
    flat = upload.flatten_system(SYSTEM, ally)
    assert flat["device_class"] == "rog_ally" and flat["gpu"] == "AMD Radeon Graphics (RADV PHOENIX)" and flat["cpu"] == "AMD Ryzen Z1 Extreme"
    assert flat["device_vendor"] == "ASUSTeK COMPUTER INC." and flat["device_product"] == "ROG Ally RC71L_RC71L" and flat["device_version"] is None


def test_the_deck_upload_keeps_its_fixed_names():
    deck = DeckInfo(is_deck=True, model="OLED", vendor="Valve", product="Galileo")
    flat = upload.flatten_system(SYSTEM, deck)
    assert (flat["gpu"], flat["cpu"], flat["device_class"]) == ("Steam Deck OLED", "Steam Deck APU", "steam_deck_oled")
    assert flat["device_vendor"] == "Valve" and flat["device_product"] == "Galileo"


def test_the_api_client_forwards_the_dmi_strings():
    from unittest.mock import MagicMock, patch

    from linux_game_benchmark.api.client import BenchmarkAPIClient

    response = MagicMock(status_code=200)
    response.json.return_value = {"id": 7, "message": "ok"}
    http = MagicMock()
    http.__enter__.return_value.post.return_value = response
    legion = DeckInfo(is_deck=True, handheld="legion_go", handheld_label="Legion Go", vendor="LENOVO", product="83E1", version="Legion Go 8APU1")
    with patch("linux_game_benchmark.api.client.httpx.Client", return_value=http):
        result = BenchmarkAPIClient(base_url="http://test/api/v1").upload_benchmark(
            steam_app_id=1, game_name="X", resolution="1920x1080", system_info=upload.flatten_system(SYSTEM, legion),
            metrics={"fps_avg": 50}, frametimes=[20.0] * 10, require_auth=False)
    assert result.success
    system = http.__enter__.return_value.post.call_args.kwargs["json"]["system"]
    assert (system["device_vendor"], system["device_product"], system["device_version"]) == ("LENOVO", "83E1", "Legion Go 8APU1")
    assert system["device_class"] == "legion_go"
