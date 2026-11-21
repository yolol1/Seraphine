from app.lol.tools import getTeammates, getTeammatesFromSGPGame


def _lcu_game():
    return {
        "queueId": 420,
        "participantIdentities": [
            {
                "participantId": 1,
                "player": {
                    "puuid": "self",
                    "summonerId": 1,
                    "gameName": "Self",
                    "tagLine": "0001",
                    "profileIcon": 1,
                },
            },
            {
                "participantId": 2,
                "player": {
                    "puuid": "mate",
                    "summonerId": 2,
                    # Current LCU builds can leave summonerName empty.
                    "summonerName": "",
                    "gameName": "NewName",
                    "tagLine": "25213",
                    "profileIcon": 2,
                },
            },
        ],
        "participants": [
            {
                "participantId": 1,
                "teamId": 100,
                "stats": {"win": True, "teamEarlySurrendered": False},
            },
            {"participantId": 2, "teamId": 100},
        ],
    }


def test_lcu_teammates_use_game_name_when_summoner_name_is_empty():
    teammates = getTeammates(_lcu_game(), "self")

    assert teammates["summoners"][0]["name"] == "NewName"
    assert teammates["summoners"][0]["tagLine"] == "25213"


def test_sgp_teammates_support_riot_id_fields():
    game = {
        "json": {
            "queueId": 420,
            "participants": [
                {
                    "puuid": "self",
                    "teamId": 100,
                    "win": True,
                    "teamEarlySurrendered": False,
                    "championId": 1,
                },
                {
                    "puuid": "mate",
                    "summonerId": 2,
                    "teamId": 100,
                    "riotIdGameName": "RiotName",
                    "riotIdTagline": "14176",
                    "profileIcon": 3,
                },
            ],
        },
    }

    teammates = getTeammatesFromSGPGame(game, "self")

    assert teammates["summoners"][0]["name"] == "RiotName"
    assert teammates["summoners"][0]["tagLine"] == "14176"
