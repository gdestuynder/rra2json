from parselib import *
def parse_rra(gc, sheet, name, version, rrajson, data_levels, risk_levels):
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
    #Fetch/export all data for faster processing
    #Format is sheet_data[row][col] with positions starting at 0, i.e.:
    #cell(1,2) is sheet_data[0,1]
    sheet_data = s.get_all_values()

    rrajson.source = sheet.id
    metadata = rrajson.details.metadata
    metadata.service = cell_value_near(sheet_data, 'Service name')
    if (len(metadata.service) == 0):
        return None

    metadata.scope = cell_value_near(sheet_data, 'RRA Scope')
    metadata.owner = fuzzy_find_team_name(cell_value_near(sheet_data, 'Service owner'))
    metadata.developer = fuzzy_find_team_name(cell_value_near(sheet_data, 'Developer'))
    metadata.operator = fuzzy_find_team_name(cell_value_near(sheet_data, 'Operator'))

    rrajson.summary = 'RRA for {}'.format(metadata.service)
    rrajson.timestamp = toUTC(datetime.now()).isoformat()
    rrajson.lastmodified = toUTC(s.updated).isoformat()

    data = rrajson.details.data
    try:
        data.default = normalize_data_level(cell_value_near(sheet_data, 'Data classification', xmoves=2))
    except IndexError:
        data.default = normalize_data_level(cell_value_near(sheet_data, 'Data classification of primary service', xmoves=2))

    #Find/list all data dictionnary
    i = 0
    try:
        res = [match for match in list_find(sheet_data, 'Classification')][0]
    except IndexError:
        #No data dictionary then!
        i=-1
    else:
        if len(res) == 0:
            i = -1

    # if there are more than 100 datatypes, well, that's too many anyway.
    # the 100 limit is a safeguard in case the loop goes wrong due to unexpected data in the sheet
    while ((i != -1) and (i<100)):
        i = i+1
        data_level = normalize_data_level(sheet_data[res[0]+i][res[1]])
        data_type = sheet_data[res[0]+i][res[1]-2].strip('\n')
        if data_level == '':
            #Bail out - list ended/data not found/list broken/etc.
            i = -1
            continue

        for d in data_levels:
            if data_level == d:
                try:
                    data[d].append(data_type)
                except KeyError:
                    data[d] = [data_type]

    C = rrajson.details.risk.confidentiality
    I = rrajson.details.risk.integrity
    A = rrajson.details.risk.availability

    impact = 'Impact Level'
    try:
        C.reputation.impact = validate_entry(cell_value_near(sheet_data, impact, xmoves=0, ymoves=1), risk_levels)
    except IndexError:
        impact = 'Impact to Mozilla'
        C.reputation.impact = validate_entry(cell_value_near(sheet_data, impact, xmoves=0, ymoves=1), risk_levels)
    C.reputation.rationale = cell_value_near(sheet_data, 'Rationale', xmoves=0, ymoves=1)
    C.finances.impact = validate_entry(cell_value_near(sheet_data, impact, xmoves=0, ymoves=2), risk_levels)
    C.finances.rationale = cell_value_near(sheet_data, 'Rationale', xmoves=0, ymoves=7)
    C.productivity.impact = validate_entry(cell_value_near(sheet_data, impact, xmoves=0, ymoves=3), risk_levels)
    C.productivity.rationale = cell_value_near(sheet_data, 'Rationale', xmoves=0, ymoves=4)
    I.reputation.impact = validate_entry(cell_value_near(sheet_data, impact, xmoves=0, ymoves=4), risk_levels)
    I.reputation.rationale = cell_value_near(sheet_data, 'Rationale', xmoves=0, ymoves=3)
    I.finances.impact = validate_entry(cell_value_near(sheet_data, impact, xmoves=0, ymoves=5), risk_levels)
    I.finances.rationale = cell_value_near(sheet_data, 'Rationale', xmoves=0, ymoves=9)
    I.productivity.impact = validate_entry(cell_value_near(sheet_data, impact, xmoves=0, ymoves=6), risk_levels)
    I.productivity.rationale = cell_value_near(sheet_data, 'Rationale', xmoves=0, ymoves=6)
    A.reputation.impact = validate_entry(cell_value_near(sheet_data, impact, xmoves=0, ymoves=7), risk_levels)
    A.reputation.rationale = cell_value_near(sheet_data, 'Rationale', xmoves=0, ymoves=2)
    A.finances.impact = validate_entry(cell_value_near(sheet_data, impact, xmoves=0, ymoves=8), risk_levels)
    A.finances.rationale = cell_value_near(sheet_data, 'Rationale', xmoves=0, ymoves=8)
    A.productivity.impact = validate_entry(cell_value_near(sheet_data, impact, xmoves=0, ymoves=9), risk_levels)
    A.productivity.rationale = cell_value_near(sheet_data, 'Rationale', xmoves=0, ymoves=5)

    return rrajson


