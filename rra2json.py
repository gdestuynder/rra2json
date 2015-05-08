#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Copyright (c) 2015 Mozilla Corporation
# Contributors:
# Guillaume Destuynder <gdestuynder@mozilla.com>
# Gene Wood <gene@mozilla.com> (Authentication)

from oauth2client.client import SignedJwtAssertionCredentials
import gspread
import hjson as json
from xml.etree import ElementTree as et
import sys
import pytz
from datetime import datetime
from dateutil.parser import parse

class DotDict(dict):
    '''dict.item notation for dict()'s'''
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

    def __init__(self, dct):
        for key, value in dct.items():
            if hasattr(value, 'keys'):
                value = DotDict(value)
            self[key] = value

def fatal(msg):
    print(msg)
    sys.exit(1)

def debug(msg):
    sys.stderr.write('+++ {}\n'.format(msg))

def toUTC(suspectedDate, localTimeZone=None):
    '''Anything => UTC date. Magic.'''
    if (localTimeZone == None):
        try:
            localTimeZone = '/'.join(os.path.realpath('/etc/localtime').split('/')[-2:])
        except:
            localTimeZone = 'UTC'
    utc = pytz.UTC
    objDate = None
    if (type(suspectedDate) == str):
        objDate = parse(suspectedDate, fuzzy=True)
    elif (type(suspectedDate) == datetime):
        objDate=suspectedDate

    if (objDate.tzinfo is None):
        try:
            objDate=pytz.timezone(localTimeZone).localize(objDate)
        except pytz.exceptions.UnknownTimeZoneError:
            #Meh if all fails, I decide you're UTC!
            objDate=pytz.timezone('UTC').localize(objDate)
        objDate=utc.normalize(objDate)
    else:
        objDate=utc.normalize(objDate)
    if (objDate is not None):
        objDate=utc.normalize(objDate)

    return objDate

def gspread_authorize(email, private_key, scope, secret=None):
    '''
    Authenticate to Google Drive and return an authorization.
    '''
    private_key = private_key.encode('ascii')
    if secret:
        credentials = SignedJwtAssertionCredentials(email, private_key, [scope], secret)
    else:
        credentials = SignedJwtAssertionCredentials(email, private_key, [scope])
    return gspread.authorize(credentials)

def get_sheet_titles(gc):
    '''
    List all sheets (Atom elements)
    '''
    data = {}
    et_sheets = gc.get_spreadsheets_feed()
    et_entries = et_sheets.findall('{http://www.w3.org/2005/Atom}entry')

    for et_entry in et_entries:
        # That's where the link with sheet ID always is, basically, since it's not named as such and there's several
        # links...
        link = et_entry.findall('{http://www.w3.org/2005/Atom}link')[1].attrib['href']
        #Links look like 'https://docs.google.com/spreadsheets/d/1nNhoENKv5qR6l_Ch2loYj0D9fQ_bNCz2pbHAEYssh-X/edit'
        #Where 1nNhoENKv5qR6l_Ch2loYj0D9fQ_bNCz2pbHAEYssh-X would be the ID
        linkid = link.split('/')[-2]
        # There's just one title so yay!
        title = et_entry.findall('{http://www.w3.org/2005/Atom}title')[0].text
        data[linkid] = title
    return data

def nodots(data):
    return data.replace('.', '')

def detect_version(gc, s):
    '''
    Find a sheet called Version and something that looks like a version number in cell 1,16 (P1)
    Else, we try to guess.
    '''
    # If we're lucky there's a version number (RRA format >2.4.1)
    version = s.sheet1.cell(1,16).value
    if version != '':
        return nodots(version)

    # so that's when we're not so lucky.
    #RRA 2.4.0 doesn't have the version number but has likelihood, and has a specific cell
    #It's nearly the same as RRA 2.4.1
    if (s.sheet1.cell(1,8).value == 'Estimated\nRisk to Mozilla'):
        version = '2.4.0'
        return nodots(version)

    #RRA 2.3 has a specific cell as well
    if (s.sheet1.cell(1, 8).value == 'Impact to Mozilla'):
        version = '2.3.0'
        return nodots(version)

    #RRA 1.x has a specific cell as well - getting monotonous here!
    if (s.sheet1.cell(1,1).value == 'Project Name' and s.sheet1.title == 'Summary'):
        version = '1.0.0'
        return nodots(version)

    # Out of luck.
    return None

def check_last_update(gc, s):
    '''
    Find last update of first worksheet of a spreadsheet
    Used to filter what sheets to work on (for ex "last week updates only, etc.")
    XXX TODO
    '''
    last_update = s.sheet1.updated
    return True

def cell_value_near(s, value, xmoves=1, ymoves=0):
    '''
    Returns value of cell near the first cell found containing 'value'.
    'Near' is defined as by the (x,y) coordinates, default to "right of the value found" ie x=+1, y=0
    x=0 y=+1 would mean "under the value found".

    Ex:
       A      | B
    1| Name   | Bob
    2| Client | Jim

    cell_value_rightof('Name') will return 'Bob'

    Function returns empty string if nothing is found.

    @s: worksheet
    @value: string
    @xmoves, ymoves: number of right lateral moves to find the field value to return
    '''
    try:
        c = s.find(value)
    except gspread.exceptions.CellNotFound:
        return ''

    if not c:
        return ''
    return s.cell(c.row+ymoves, c.col+xmoves).value

def validate_entry(value, allowed):
    '''
    Check input value against a list of allowed data
    Return value or 'Unknown'.
    @allowed: list()
    @value: string
    '''
    if value in allowed:
        return value
    return 'Unknown'

def parse_rra_100(gc, sheet, name, version, rrajson, data_levels, risk_levels):
    '''
    called by parse_rra virtual function wrapper
    @gc google gspread connection
    @sheet spreadsheet
    @name spreadsheet name
    @version RRA version detected
    @rrajson writable template for the JSON format of the RRA
    @data_levels list of data levels allowed
    @risk_levels list of risk levels allowed
    '''
    s = sheet.sheet1
    rrajson.source = sheet.id
    metadata = rrajson.details.metadata
    metadata.service = cell_value_near(s, 'Project Name')
    metadata.scope = cell_value_near(s, 'Scope')
    metadata.owner = cell_value_near(s, 'Project, Data owner') + ' ' + cell_value_near(s, 'Project, Data owner', xmoves=2)
    metadata.developer = cell_value_near(s, 'Developer') + ' ' + cell_value_near(s, 'Developer', xmoves=2)
    metadata.operator = cell_value_near(s, 'Operator') + ' ' + cell_value_near(s, 'Operator', xmoves=2)

    rrajson.summary = 'RRA for {}'.format(metadata.service)
    rrajson.timestamp = toUTC(datetime.now()).isoformat()
    rrajson.lastmodified = toUTC(s.updated).isoformat()

    data = rrajson.details.data
    data.default = 'Unknown'

    C = rrajson.details.risk.confidentiality
    I = rrajson.details.risk.integrity
    A = rrajson.details.risk.availability

    C.reputation.impact = validate_entry(cell_value_near(s, 'Confidentiality'), risk_levels)
    C.finances.impact = validate_entry(cell_value_near(s, 'Confidentiality', xmoves=2), risk_levels)
    C.productivity.impact = validate_entry(cell_value_near(s, 'Confidentiality', xmoves=3), risk_levels)
    I.reputation.impact = validate_entry(cell_value_near(s, 'Availability'), risk_levels)
    I.finances.impact = validate_entry(cell_value_near(s, 'Availability', xmoves=2), risk_levels)
    I.productivity.impact = validate_entry(cell_value_near(s, 'Availability', xmoves=3), risk_levels)
    # RRA v1.0.0 uses Recovery + Access Control to represent integrity.
    # Access Control is closest to real integrity, so we use that.
    A.reputation.impact = validate_entry(cell_value_near(s, 'Access Control'), risk_levels)
    A.finances.impact = validate_entry(cell_value_near(s, 'Access Control', xmoves=2), risk_levels)
    A.productivity.impact = validate_entry(cell_value_near(s, 'Access Control', xmoves=3), risk_levels)

    return rrajson


def parse_rra_230(gc, sheet, name, version, rrajson, data_levels, risk_levels):
    '''
    called by parse_rra virtual function wrapper
    @gc google gspread connection
    @sheet spreadsheet
    @name spreadsheet name
    @version RRA version detected
    @rrajson writable template for the JSON format of the RRA
    @data_levels list of data levels allowed
    @risk_levels list of risk levels allowed
    '''

    s = sheet.sheet1
    rrajson.source = sheet.id
    metadata = rrajson.details.metadata
    metadata.service = cell_value_near(s, 'Service name')
    metadata.scope = cell_value_near(s, 'RRA Scope')
    metadata.owner = cell_value_near(s, 'Service owner')
    metadata.developer = cell_value_near(s, 'Developer')
    metadata.operator = cell_value_near(s, 'Operator')

    rrajson.summary = 'RRA for {}'.format(metadata.service)
    rrajson.timestamp = toUTC(datetime.now()).isoformat()
    rrajson.lastmodified = toUTC(s.updated).isoformat()

    data = rrajson.details.data
    data.default = cell_value_near(s, 'Data classification', xmoves=2)

    i = 0
    try:
        c = s.find('Classification')
    except gspread.exceptions.CellNotFound:
        i = -1

    # if there are more than 100 datatypes, well, that's too many anyway.
    # the 100 limit is a safeguard in case the loop goes wrong due to unexpected data in the sheet
    while ((i != -1) and (i<100)):
        i = i+1
        # cell = data level
        # val = data name
        cell = s.cell(c.row+i, c.col)
        val = s.cell(c.row+i, c.col-2)
        if cell.value == '':
            #Bail out - list ended
            i = -1
            continue

        for d in data_levels:
            if cell.value == d:
                data[d].append(val.value)

    C = rrajson.details.risk.confidentiality
    I = rrajson.details.risk.integrity
    A = rrajson.details.risk.availability

    C.reputation.impact = validate_entry(cell_value_near(s, 'Impact Level', xmoves=0, ymoves=1), risk_levels)
    C.finances.impact = validate_entry(cell_value_near(s, 'Impact Level', xmoves=0, ymoves=2), risk_levels)
    C.productivity.impact = validate_entry(cell_value_near(s, 'Impact Level', xmoves=0, ymoves=3), risk_levels)
    I.reputation.impact = validate_entry(cell_value_near(s, 'Impact Level', xmoves=0, ymoves=4), risk_levels)
    I.finances.impact = validate_entry(cell_value_near(s, 'Impact Level', xmoves=0, ymoves=5), risk_levels)
    I.productivity.impact = validate_entry(cell_value_near(s, 'Impact Level', xmoves=0, ymoves=6), risk_levels)
    A.reputation.impact = validate_entry(cell_value_near(s, 'Impact Level', xmoves=0, ymoves=7), risk_levels)
    A.finances.impact = validate_entry(cell_value_near(s, 'Impact Level', xmoves=0, ymoves=8), risk_levels)
    A.productivity.impact = validate_entry(cell_value_near(s, 'Impact Level', xmoves=0, ymoves=9), risk_levels)

def parse_rra_240(gc, sheet, name, version, rrajson, data_levels, risk_levels):
    '''
    240 and 241 are about the same
    '''
    return parse_rra_241(gc, sheet, name, version, rrajson, data_levels, risk_levels)

def parse_rra_241(gc, sheet, name, version, rrajson, data_levels, risk_levels):
    '''
    called by parse_rra virtual function wrapper
    @gc google gspread connection
    @sheet spreadsheet
    @name spreadsheet name
    @version RRA version detected
    @rrajson writable template for the JSON format of the RRA
    @data_levels list of data levels allowed
    @risk_levels list of risk levels allowed
    '''

    s = sheet.sheet1
    rrajson.source = sheet.id
    metadata = rrajson.details.metadata
    metadata.service = cell_value_near(s, 'Service name')
    metadata.scope = cell_value_near(s, 'RRA Scope')
    metadata.owner = cell_value_near(s, 'Service owner')
    metadata.developer = cell_value_near(s, 'Developer')
    metadata.operator = cell_value_near(s, 'Operator')

    rrajson.summary = 'RRA for {}'.format(metadata.service)
    rrajson.timestamp = toUTC(datetime.now()).isoformat()
    rrajson.lastmodified = toUTC(s.updated).isoformat()

    data = rrajson.details.data
    data.default = cell_value_near(s, 'Service\nData classification', xmoves=2)
    i = 0
    try:
        c = s.find('Data Classification')
    except gspread.exceptions.CellNotFound:
        i = -1

    # if there are more than 100 datatypes, well, that's too many anyway.
    # the 100 limit is a safeguard in case the loop goes wrong due to unexpected data in the sheet
    while ((i != -1) and (i<100)):
        i = i+1
        # cell = data level
        # val = data name
        cell = s.cell(c.row+i, c.col)
        val = s.cell(c.row+i, c.col-2)
        if cell.value == '':
            #Bail out - list ended
            i = -1
            continue

        for d in data_levels:
            if cell.value == d:
                data[d].append(val.value)

    C = rrajson.details.risk.confidentiality
    I = rrajson.details.risk.integrity
    A = rrajson.details.risk.availability

    C.reputation.impact = validate_entry(cell_value_near(s, 'Impact', xmoves=0, ymoves=1), risk_levels)
    C.finances.impact = validate_entry(cell_value_near(s, 'Impact', xmoves=0, ymoves=2), risk_levels)
    C.productivity.impact = validate_entry(cell_value_near(s, 'Impact', xmoves=0, ymoves=3), risk_levels)
    I.reputation.impact = validate_entry(cell_value_near(s, 'Impact', xmoves=0, ymoves=4), risk_levels)
    I.finances.impact = validate_entry(cell_value_near(s, 'Impact', xmoves=0, ymoves=5), risk_levels)
    I.productivity.impact = validate_entry(cell_value_near(s, 'Impact', xmoves=0, ymoves=6), risk_levels)
    A.reputation.impact = validate_entry(cell_value_near(s, 'Impact', xmoves=0, ymoves=7), risk_levels)
    A.finances.impact = validate_entry(cell_value_near(s, 'Impact', xmoves=0, ymoves=8), risk_levels)
    A.productivity.impact = validate_entry(cell_value_near(s, 'Impact', xmoves=0, ymoves=9), risk_levels)

    C.reputation.probability = validate_entry(cell_value_near(s, 'Probability', xmoves=0, ymoves=1), risk_levels)
    C.finances.probability = validate_entry(cell_value_near(s, 'Probability', xmoves=0, ymoves=2), risk_levels)
    C.productivity.probability = validate_entry(cell_value_near(s, 'Probability', xmoves=0, ymoves=3), risk_levels)
    I.reputation.probability = validate_entry(cell_value_near(s, 'Probability', xmoves=0, ymoves=4), risk_levels)
    I.finances.probability = validate_entry(cell_value_near(s, 'Probability', xmoves=0, ymoves=5), risk_levels)
    I.productivity.probability = validate_entry(cell_value_near(s, 'Probability', xmoves=0, ymoves=6), risk_levels)
    A.reputation.probability = validate_entry(cell_value_near(s, 'Probability', xmoves=0, ymoves=7), risk_levels)
    A.finances.probability = validate_entry(cell_value_near(s, 'Probability', xmoves=0, ymoves=8), risk_levels)
    A.productivity.probability = validate_entry(cell_value_near(s, 'Probability', xmoves=0, ymoves=9), risk_levels)

def main():
    with open('rra2json.json') as fd:
        config = json.load(fd)
        authconfig = config['oauth2']
        rrajson_skel = config['rrajson']
        data_levels = config['data_levels']
        risk_levels = config['risk_levels']

    gc = gspread_authorize(authconfig['client_email'], authconfig['private_key'], authconfig['spread_scope'])

    if not gc:
        fatal('Authorization failed')

    # Looking at the XML feed is the only way to get sheet document title for some reason.
    sheets = get_sheet_titles(gc)
    # Do not traverse sheets manually, it's very slow due to the API delays.
    # Opening all at once, including potentially non-useful sheet is a zillion times faster as it's a single API call.
    gsheets = gc.openall()
    for s in gsheets:
        rra_version = detect_version(gc, s)
        if rra_version != None:
            #virtual function pointer
            parse_rra = globals()["parse_rra_{}".format(rra_version)]
            rrajsondoc = parse_rra(gc, s, sheets[s.id], rra_version, DotDict(dict(rrajson_skel)), list(data_levels),
                    list(risk_levels))
        else:
            debug('Document {} ({}) could not be parsed and is probably not an RRA'.format(sheets[s.id], s.id))

if __name__ == "__main__":
    main()
