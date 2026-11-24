from app.view.detail_request import isCurrentDetailRequest


def _requestState(gameId, puuid, selectedGameId, selectedPuuid):
    return isCurrentDetailRequest(
        gameId, puuid, selectedGameId, selectedPuuid)


def test_detail_request_is_current_for_selected_game_and_puuid():
    assert _requestState(22, "player-a", 22, "player-a")


def test_stale_detail_request_is_rejected_after_game_switch():
    assert not _requestState(11, "player-a", 22, "player-a")


def test_stale_detail_request_is_rejected_after_puuid_switch():
    assert not _requestState(22, "player-a", 22, "player-b")
