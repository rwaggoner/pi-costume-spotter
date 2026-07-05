"""The edge API: everything the React dashboard talks to.

- ``routes.py``     — REST: sightings, snapshots, stats, health (06-F3)
- ``websocket.py``  — /ws/events: the bus, JSON-serialized, live (06-F2)
- ``mjpeg.py``      — /stream.mjpg: the live feed (06-F1, ADR-007)
- ``app.py``        — assembles the FastAPI app and serves the built React bundle
"""
