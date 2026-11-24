import asyncio
from types import SimpleNamespace

from app.common.config import cfg
from app.lol import tools
from app.lol.connector import LolClientConnector


def _patchAutoBanConfig(monkeypatch, champions=(101, 102, 103)):
    values = {
        id(cfg.enableAutoBanChampion): True,
        id(cfg.autoBanChampion): list(champions),
        id(cfg.autoBanChampionTop): [],
        id(cfg.autoBanChampionJug): [],
        id(cfg.autoBanChampionMid): [],
        id(cfg.autoBanChampionBot): [],
        id(cfg.autoBanChampionSup): [],
        id(cfg.autoBanDelay): 0,
        id(cfg.pretentBan): False,
    }

    def get(item):
        return values.get(id(item), [])

    monkeypatch.setattr(tools.cfg, "get", get)


def _champSelectSession(myTeamBans=()):
    return {
        "localPlayerCellId": 5,
        "myTeam": [
            {
                "cellId": 5,
                "assignedPosition": "middle",
                "championId": 0,
                "championPickIntent": 0,
            },
            {
                "cellId": 6,
                "assignedPosition": "top",
                "championId": 0,
                "championPickIntent": 0,
            },
        ],
        "actions": [[{
            "id": 99,
            "actorCellId": 5,
            "type": "ban",
            "championId": 0,
            "isInProgress": True,
            "completed": False,
        }]],
        "bans": {
            "myTeamBans": list(myTeamBans),
            "theirTeamBans": [],
        },
    }


def test_autoBan_reloadsSessionAndSkipsChampionBannedDuringDelay(monkeypatch):
    _patchAutoBanConfig(monkeypatch)
    selection = tools.ChampionSelection()
    banned = []

    async def getSession():
        return _champSelectSession(myTeamBans=[101])

    async def banChampion(actionId, championId, completed=None):
        banned.append((actionId, championId, completed))
        return True

    monkeypatch.setattr(tools.connector, "getChampSelectSession", getSession)
    monkeypatch.setattr(tools.connector, "banChampion", banChampion)

    result = asyncio.run(tools.autoBan(_champSelectSession(), selection))

    assert result is True
    assert banned == [(99, 102, True)]
    assert selection.isChampionBanned is True


def test_autoBan_triesNextCandidateWhenLcuRejectsFirst(monkeypatch):
    _patchAutoBanConfig(monkeypatch)
    selection = tools.ChampionSelection()
    attempts = []

    async def getSession():
        return _champSelectSession()

    async def banChampion(actionId, championId, completed=None):
        attempts.append(championId)
        return championId == 102

    monkeypatch.setattr(tools.connector, "getChampSelectSession", getSession)
    monkeypatch.setattr(tools.connector, "banChampion", banChampion)

    result = asyncio.run(tools.autoBan(_champSelectSession(), selection))

    assert result is True
    assert attempts == [101, 102]
    assert selection.isChampionBanned is True


def test_autoBan_serializesOverlappingChampSelectEvents(monkeypatch):
    _patchAutoBanConfig(monkeypatch)
    selection = tools.ChampionSelection()
    attempts = []

    async def getSession():
        await asyncio.sleep(0)
        return _champSelectSession()

    async def banChampion(actionId, championId, completed=None):
        attempts.append(championId)
        await asyncio.sleep(0)
        return True

    monkeypatch.setattr(tools.connector, "getChampSelectSession", getSession)
    monkeypatch.setattr(tools.connector, "banChampion", banChampion)

    async def runConcurrentEvents():
        await asyncio.gather(
            tools.autoBan(_champSelectSession(), selection),
            tools.autoBan(_champSelectSession(), selection),
        )

    asyncio.run(runConcurrentEvents())

    assert attempts == [101]
    assert selection.isChampionBanned is True


class _FakeResponse:
    def __init__(self, status):
        self.status = status

    async def read(self):
        return b""

    async def text(self):
        return "already banned"


def test_banChampion_onlyReportsSuccessFor2xx(monkeypatch):
    async def patchRequest(path, data=None):
        return _FakeResponse(409)

    fakeConnector = SimpleNamespace()
    fakeConnector._LolClientConnector__patch = patchRequest

    result = asyncio.run(
        LolClientConnector.banChampion(fakeConnector, 99, 101, True))

    assert result is False


def test_banChampion_reportsSuccessFor2xx():
    async def patchRequest(path, data=None):
        return _FakeResponse(204)

    fakeConnector = SimpleNamespace()
    fakeConnector._LolClientConnector__patch = patchRequest

    result = asyncio.run(
        LolClientConnector.banChampion(fakeConnector, 99, 101, True))

    assert result is True
