"""Small, UI-free guards for asynchronous match-detail requests."""


def isCurrentDetailRequest(requestGameId, requestPuuid,
                           selectedGameId, selectedPuuid) -> bool:
    return requestGameId == selectedGameId and requestPuuid == selectedPuuid
