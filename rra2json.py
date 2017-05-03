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
import hjson as json
import json as rjson
from xml.etree import ElementTree as et
import sys
import collections
import copy
import parselib
import bugzilla
import requests
import dateutil.parser
import pickle

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

def post_rra_to_servicemap(cfg, rrajsondoc):
    url = '{proto}://{host}:{port}{endpoint}'.format(proto=cfg['proto'], host=cfg['host'],
                                                        port=cfg['port'], endpoint=cfg['endpoint'])
    payload = {'rra': rjson.dumps(rrajsondoc)}

    if len(cfg['x509cert']) > 1:
        verify=cfg['x509cert']
    elif cfg['tls_verify'] == "true":
        verify=True
    else:
        verify=False

    #Hack to get a version number, until this is fetched from the gdrive API
    rrajsondoc['version'] = dateutil.parser.parse(rrajsondoc['lastmodified']).strftime('%s')

    r = requests.post(url, data=payload, verify=verify)
    if r.status_code != requests.codes.ok:
        fatal("Failed to send RRA to servicemap (nag missing?): error code: {} message: {} rra: {}".format(r.status_code, r.content, rrajsondoc['source']))

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

def autoassign_rras(config):
    """This will search through unassigned RRA bugs and assign them automatically"""
    bcfg = config['bugzilla']

    # If no API key has been specified, just skip this
    if len(bcfg['api_key']) == 0:
        return

    b = bugzilla.Bugzilla(url=bcfg['url'], api_key=bcfg['api_key'])

    try:
        with open(bcfg['cache'], 'rb') as f:
            assign_list = pickle.load(f)
    except FileNotFoundError:
        debug("no current autoassign list found, using configured defaults")
        assign_list = list(bcfg['autoassign'])

    # Do we have any RRA in the queue?
    terms = [{'product': bcfg['product']}, {'component': bcfg['component']},
            {'status': 'NEW'}, {'status': 'UNCONFIRMED'}
            ]

    bugs = b.search_bugs(terms)['bugs']
    try:
        bugzilla.DotDict(bugs[-1])
        debug("Found {} unassigned RRA(s). Assigning work!".format(len(bugs)))
        for bug in bugs:
            # Next assignee in the list, rotate
            assignee = assign_list.pop()
            assign_list.insert(0, assignee)
            bug_up = bugzilla.DotDict()
            bug_up.assigned_to = assignee
            bug_up.status = 'ASSIGNED'
            try:
                debug("Updating bug {} assigning {}".format(bug['id'], assignee))
                b.put_bug(bug['id'], bug_up)
            except Exception as e:
                debug("Failed to update bug {}: {}".format(bug['id'], e))

        with open(bcfg['cache'], 'wb') as f:
            pickle.dump(assign_list, f)

    except IndexError:
        debug("No unassigned RRAs")

    sys.exit(1)

def fill_bug(config, nags, rrajsondoc):
    bcfg = config['bugzilla']

    # If no API key has been specified, just skip this
    if len(bcfg['api_key']) == 0:
        return

    b = bugzilla.Bugzilla(url=bcfg['url'], api_key=bcfg['api_key'])

    #Did we already report this?
    terms = [{'product': bcfg['product']}, {'component': bcfg['component']},
            {'creator': bcfg['creator']}, {'whiteboard': 'autoentry'},
            {'resolution': ''},{'status': 'NEW'}, {'status': 'ASSIGNED'},
            {'status': 'REOPENED'}, {'status': 'UNCONFIRMED'},
            {'whiteboard': 'rra2json={}'.format(rrajsondoc.source)}
            ]

    bugs = b.search_bugs(terms)['bugs']
    try:
        bugzilla.DotDict(bugs[-1])
        debug("bug for {} is already present, not re-filling".format(rrajsondoc.source))
        return
    except IndexError:
        pass

    #If not, report now
    bug = bugzilla.DotDict()
    bug.product = bcfg['product']
    bug.component = bcfg['component']
    bug.summary = "There are {} issues with an RRA".format(len(nags))
    bug.description = json.dumps(nags)
    bug.whiteboard = 'autoentry rra2json={}'.format(rrajsondoc.source)
    if 'analyst' in rrajsondoc.details.metadata:
        bug.assigned_to = rrajsondoc.details.metadata.analyst
    try:
        ret = b.post_bug(bug)
        debug("Filled bug {} {}".format(rrajsondoc.source, ret))
    except Exception as e:
        # Code 51 = assigned_to user does not exist, just assign to default then
        url, estr, ecode, edict = e.args
        if edict['code'] == 51: 
            del bug.assigned_to
            try:
                ret = b.post_bug(bug)
                debug("Filled bug {} {}".format(rrajsondoc.source, ret))
            except Exception as e1:
                debug("Filling bug failed: {}".format(e1))
        else:
            debug("Filling bug failed: {}".format(e))

def verify_fields_and_nag(config, rrajsondoc):
    """
    If the RRA has not been touched for a certain about of days (configurable), and some critical fields are missing,
    create a notification with the list of nags for the users to fix it.
    More nags can be added to the list, and should be inside a dict. See the "risk record" nag below for example.
    returns True if RRA can be posted, False if it cannot or should not (for ex missing fields, or exempt)
    """
    nags = []

    # Only version 250+ supports fields that we check and nag for
    if int(rrajsondoc.details.metadata.RRA_version) < 250:
        return True

    # Having a risk record is required.
    if (len(rrajsondoc.details.metadata.risk_record) < 2):
        nags.append({"title": "Risk record missing", "body": "Please add a risk record to the RRA at https://docs.google.com/spreadsheets/d/{}".format(rrajsondoc.source)})

    # Having a default data classification is required.
    if (len(rrajsondoc.details.data.default) < 2):
        nags.append({"title": "Default data classification missing", "body": "Please add a default (top-level) data classification to the RRA at https://docs.google.com/spreadsheets/d/{}".format(rrajsondoc.source)})

    # Having a name is required.
    if (len(rrajsondoc.details.metadata.service) < 2):
        nags.append({"title": "There is no service name", "body": "Please add a service name to the RRA at https://docs.google.com/spreadsheets/d/{}".format(rrajsondoc.source)})

    if len(nags) == 0:
        return True
    else:
        # Only start nagging after X days without update
        dt_now = parselib.toUTC()
        dt_updated = parselib.toUTC(rrajsondoc.lastmodified)
        delta = dt_now-dt_updated

        if (delta.days < config['rra2json']['days_before_nag']):
            return False
        # We only know how to notify via bugzilla bugs right now
        fill_bug(config, nags, rrajsondoc)
        return False

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

    # Print a notice if the nag function is disabled
    if len(config['bugzilla']['api_key']) == 0:
        debug('Notice, bugzilla nag function is disabled (no configured API key)')

    # Use this opportunity to do some house keeping!
    if len(config['bugzilla']['autoassign']) == 0:
        debug("Notice, autoassign option is disabled")
    else:
        autoassign_rras(config)


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
                if rra2jsonconfig['debug_level'] > 1:
                    import pprint
                    pp = pprint.PrettyPrinter()
                    pp.pprint(rrajsondoc)
                success = verify_fields_and_nag(config, rrajsondoc)
                if success:
                    if rra2jsonconfig['debug_level'] < 2:
                        post_rra_to_servicemap(config['servicemap'], rrajsondoc)
                    else:
                        debug('Not posting RRA - debug mode')

            debug('Parsed {}: {}'.format(sheets[s.id], rra_version))
        else:
            debug('Document {} ({}) could not be parsed and is probably not an RRA (no version detected)'.format(sheets[s.id], s.id))

    # Use this opportunity to do some house keeping!
    if len(config['bugzilla']['autoassign']) == 0:
        debug("Notice, autoassign option is disabled")
    else:
        autoassign_rras(config)

if __name__ == "__main__":
    main()
