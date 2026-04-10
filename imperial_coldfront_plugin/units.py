"""Pint unit registry with custom units for the Imperial Coldfront plugin."""

import pint

ureg = pint.UnitRegistry()
ureg.define("credit = [credit]")
