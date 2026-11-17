"""Kennung X-Seda24 an jeder Antwort: Die Stempeluhr erkennt daran, dass eine Antwort wirklich von unserem Server
kommt (und nicht von einem Captive Portal / einer WLAN-Anmeldeseite) - nur dann gilt ein Stempel als erledigt."""


async def server_kennung(request, call_next):
    response = await call_next(request)
    response.headers["X-Seda24"] = "1"
    return response
