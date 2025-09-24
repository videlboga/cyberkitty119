"""Подмодуль с новым бета-режимом CyberKitty."""

from .feature_flags import (
    FEATURE_BETA_MODE,
    ROUTER_MODEL,
    ROUTER_CONF_HIGH,
    ROUTER_CONF_MID,
)

from .state import BetaState
from .router import RouterResult, route_message
