"""Состояния конечного автомата для бета-режима."""

from enum import Enum


class BetaState(str, Enum):
    """Основные этапы бета-потока"""

    IDLE = "idle"
    DECIDING = "deciding"
    CONTENT_MENU = "content_menu"
    CONFIRM_COMMAND = "confirm_command"
    MANUAL_FORM = "manual_form"
    EXECUTING = "executing"
    DONE = "done"


__all__ = ["BetaState"]
