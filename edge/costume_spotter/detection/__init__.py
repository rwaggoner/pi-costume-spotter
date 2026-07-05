"""Detector adapters: find people in frames.

``base.Detector`` is the port. Adapters: ``mock`` (dev, color-blob over the
synthetic scene), ``hog`` (dev, real people via webcam), ``hailo`` (the Pi's
YOLOv8-on-Hailo-8 primary — docs/decisions/001-hailo-vs-imx500.md).
"""
