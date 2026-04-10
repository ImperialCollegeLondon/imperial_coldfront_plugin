"""Pint unit registry with custom units for the Imperial Coldfront plugin."""

import pint

ureg: pint.UnitRegistry[float] = pint.UnitRegistry()
ureg.define("credit = [credit]")
