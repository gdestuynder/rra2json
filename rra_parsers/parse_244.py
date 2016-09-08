from parselib import *
import sys
sys.path.append('rra_parsers')
import parse_243

def parse_rra(gc, sheet, name, version, rrajson, data_levels, risk_levels):
    return parse_243.parse_rra(gc, sheet, name, version, rrajson, data_levels, risk_levels)
