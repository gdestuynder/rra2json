from parselib import *
import sys
sys.path.append('rra_parsers')
import parse_241

def parse_rra(gc, sheet, name, version, rrajson, data_levels, risk_levels):
    return parse_241.parse_rra(gc, sheet, name, version, rrajson, data_levels, risk_levels)
