#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Copyright (c) 2016 Mozilla Corporation
# Contributors:
# Guillaume Destuynder <gdestuynder@mozilla.com>
# Gene Wood <gene@mozilla.com> (Authentication)

from oauth2client.client import SignedJwtAssertionCredentials
import gspread
import os
import io
import hjson as json
from xml.etree import ElementTree as et
import sys
import mozdef_client as mozdef
import collections
import copy

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

def post_rra_to_mozdef(cfg, rrajsondoc):
    msg = mozdef.MozDefRRA('{proto}://{host}:{port}/custom/{rraindex}'.format(proto=cfg['proto'], host=cfg['host'],
        port=cfg['port'], rraindex=cfg['rraindex']))
    msg.set_fire_and_forget(False)
    msg.category = rrajsondoc.category
    msg.tags = rrajsondoc.tags
    msg.summary = rrajsondoc.summary
    msg.details = rrajsondoc.details
    msg._updatelog = {}
    msg._updatelog['lastmodified'] = rrajsondoc.lastmodified
    msg._updatelog['source'] = rrajsondoc.source
    msg._updatelog['utctimestamp'] = rrajsondoc.timestamp
    msg.send()

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

    # If the sheet is specifically marked as deprecated/etc, bail out now!
    if (s.sheet1.title.lower() in ['cancelled', 'superseded', 'deprecated', 'invalid']):
        return None

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
    Can be used to filter what sheets to work on (for ex "last week updates only, etc.")
    '''
    last_update = s.sheet1.updated
    return True

def main():
    os.environ['TZ']='UTC'
    with open('rra2json.json') as fd:
        config = json.load(fd)
        rra2jsonconfig = config['rra2json']
        authconfig = config['oauth2']
        rrajson_skel = config['rrajson']
        data_levels = config['data_levels']
        risk_levels = config['risk_levels']


    #Disable debugging messages by assigning a null/none function, if configured to do so.
    if rra2jsonconfig['debug'] != 'true':
        debug = lambda x: None
    else:
        debug = globals()['debug']

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
            # Virtual function pointer with JIT module import
            try:
                parse_module = 'parse_{}'.format(rra_version)
                m = __import__('rra_parsers', globals(), locals(), [parse_module])
                parse_rra = getattr(getattr(m, parse_module), 'parse_rra')
            except (KeyError, UnboundLocalError, AttributeError) as e:
                # If this error is reached, you want to add a new parse_rra_... function that will parse the new format!
                debug("Unsupported RRA version {}. rra2json needs to add explicit support before it can be parsed. Skipping RRA {} - id {}.".format(rra_version, sheets[s.id], s.id))
                continue

            try:
                rrajsondoc = parse_rra(gc, s, sheets[s.id], rra_version, DotDict(dict(copy.deepcopy(rrajson_skel))), list(data_levels),
                        list(risk_levels))
                if rrajsondoc == None:
                    debug('Document {} ({}) could not be parsed and is probably not an RRA'.format(sheets[s.id], s.id))
                    continue

                # Set RRA version outside of processing functions to ensure it's always set properly, regardless of how
                # parsing is done.
                rrajsondoc.details.metadata.RRA_version = rra_version
            except:
                import traceback
                traceback.print_exc()
                debug('Exception occured while parsing RRA {} - id {}'.format(sheets[s.id], s.id))
                sys.exit(1)
            else:
                if rra2jsonconfig['debug'] == 'true':
                    #Skip posting on debug
                    debug('The RRA {} will not be saved in MozDef and is displayed here:'.format(sheets[s.id]))
                    import pprint
                    pp = pprint.PrettyPrinter()
                    pp.pprint(rrajsondoc)
                else:
                    post_rra_to_mozdef(config['mozdef'], rrajsondoc)

            debug('Parsed {}: {}'.format(sheets[s.id], rra_version))
        else:
            debug('Document {} ({}) could not be parsed and is probably not an RRA (no version detected)'.format(sheets[s.id], s.id))

if __name__ == "__main__":
    main()
