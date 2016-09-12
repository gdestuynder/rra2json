#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Copyright (c) 2016 Mozilla Corporation
# Contributors:
# Guillaume Destuynder <gdestuynder@mozilla.com>

import pytz
from datetime import datetime
from dateutil.parser import parse
from tokenize import generate_tokens
import io
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
import os

def toUTC(suspectedDate=datetime.now(), localTimeZone=None):
    '''Anything => UTC date. Magic.'''
    if (localTimeZone == None):
        if (len(os.environ['TZ']) > 0):
            localTimeZone = os.environ['TZ']
        else:
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

def list_find(data, value):
    '''Return position (index) in list of list, of the first @value found.
    The match is case insensitive.
    Returns empty list if nothing is found.
    @data = list(list(), ...)
    @value str'''
    value = value.lower()

    for x, cells in enumerate(data):
        try:
            cells_lower = [item.lower().strip().lstrip().replace('\n', ' ') for item in cells]
            y = cells_lower.index(value)
        except ValueError:
            continue
        yield x, y

def cell_value_near(s, value, xmoves=1, ymoves=0):
    '''
    Returns value of cell near the first cell found containing 'value'.
    'Near' is defined as by the (x,y) coordinates, default to "right of the value found" ie x=+1, y=0
    x=0 y=+1 would mean "under the value found".

    Ex:
       A      | B
    1| Name   | Bob
    2| Client | Jim

    cell_value_near('Name') will return 'Bob'

    Function returns empty string if nothing is found.

    @s: worksheet list data (s=[row][col]) from gspread.model.Worksheet.get_all_values()
    @value: string
    @xmoves, ymoves: number of right lateral moves to find the field value to return
    '''

    res = [match for match in list_find(s, value)][0]

    # Nothing found
    if len(res) == 0:
        return ''

    try:
        return s[res[0]+ymoves][res[1]+xmoves].strip('\n')
    except IndexError:
        return ''

def validate_entry(value, allowed):
    '''
    Check input value against a list of allowed data
    Return value or 'Unknown'.
    @allowed: list()
    @value: str
    '''
    if value in allowed:
        return value.strip('\n')
    return 'Unknown'

def quick_tokenizer(value, token_max_val=5):
    '''
    Takes a string and attempts to tokenize it, then return a list of items found.
    token_max_val is the max amount of occurence to consider a word rare enough that it must not be a token, but is
    actual data instead.
    @value: str
    @token_max_val: int
    '''
    val = []
    g= generate_tokens(StringIO(value).readline)
    if (g == None):
        debug("quick_tokenizer() could not generate tokens, returning raw value")
        return [value]
    for tn, tv, _, _, _ in g:
        if (tn < token_max_val) and (len(tv) > 0):
            val.append(tv)
    return val

def comma_tokenizer(value):
    '''Tokenize by comma (",") and trim up spaces
    @value: str
    '''
    val = []
    for i in value.split(","):
        if len(i) != 0:
            val.append(i.strip().strip("\n"))
    return val

def fuzzy_find_team_name(value):
    '''
    Takes a field that looks like a team name and attempt to find the.. actual real team name.
    '''
    newval = value.strip().split(',')[0]
    if len(newval) == 0 or newval == None:
        return value
    return newval

def normalize_data_level(value):
    '''
    Takes a data level such as "Unknown", "PUBLIC", "CONFIDENTIAL INTERNAL", etc. and attempt to normalize it.
    /!\ This function needs to be synchronized with your data_levels if they're modified.
    This function is hardcoded as having a generic map would make little sense to most outside of Mozilla, and things
    will still work if this function is not normalizing anything. Hurrai hacks!
    '''

    data_level = value.upper()
    if data_level in ['UNKNOWN']:
        return 'UNKNOWN'

    if data_level in ['PUBLIC']:
        return 'PUBLIC'

    if data_level in ['INTERNAL', 'CONFIDENTIAL INTERNAL', 'STAFF', 'NDA',
            'MOZILLA CONFIDENTIAL - STAFF AND NDA\'D MOZILLIANS ONLY']:
        return 'INTERNAL'

    if data_level in ['RESTRICTED', 'CONFIDENTIAL RESTRICTED', 'WORKGROUP', 'WORK GROUP',
            'MOZILLA CONFIDENTIAL - SPECIFIC WORK GROUPS ONLY', 'MOZILLA CONFIDENTIAL WORK GROUPS ONLY']:
        return 'RESTRICTED'

    if data_level in ['SECRET', 'CONFIDENTIAL SECRET', 'INDIVIDUAL',
            'MOZILLA CONFIDENTIAL - SPECIFIC INDIVIDUALS ONLY', 'MOZILLA CONFIDENTIAL INDIVIDUAL ONLY']:
        return 'SECRET'

    #If all else fails, do not normalize
    return value


