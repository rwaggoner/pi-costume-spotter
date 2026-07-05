"""FrameSource adapters: where pixels come from.

``base.FrameSource`` is the port; ``synthetic``/``opencv_source``/``picamera2_source``
are the adapters (docs/decisions/008-hardware-abstraction.md). The composition root
picks one by profile + config; nothing else imports camera SDKs.
"""
