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
    ws = sheet.worksheet('Questions work sheet')

    #Fetch/export all data for faster processing
    #Format is sheet_data[row][col] with positions starting at 0, i.e.:
    #cell(1,2) is sheet_data[0,1]
    sheet_data = s.get_all_values()
    wsheet_data = ws.get_all_values()

    rrajson.source = sheet.id
    metadata = rrajson.details.metadata
    metadata.service = cell_value_near(sheet_data, 'Project Name')
    if (len(metadata.service) == 0):
        return None

    metadata.scope = cell_value_near(sheet_data, 'Scope')
    try:
        metadata.owner = fuzzy_find_team_name(cell_value_near(sheet_data, 'Project, Data owner') + ' ' + cell_value_near(sheet_data, 'Project, Data owner', xmoves=2))
    except IndexError:
        #<100 format, really
        metadata.owner = fuzzy_find_team_name(cell_value_near(sheet_data, 'Owner') + ' ' + cell_value_near(sheet_data, 'Owner', xmoves=2))

    metadata.developer = fuzzy_find_team_name(cell_value_near(sheet_data, 'Developer') + ' ' + cell_value_near(sheet_data, 'Developer', xmoves=2))
    metadata.operator = fuzzy_find_team_name(cell_value_near(sheet_data, 'Operator') + ' ' + cell_value_near(sheet_data, 'Operator', xmoves=2))

    rrajson.summary = 'RRA for {}'.format(metadata.service)
    rrajson.timestamp = toUTC(datetime.now()).isoformat()
    rrajson.lastmodified = toUTC(s.updated).isoformat()

    data = rrajson.details.data
    data.default = 'Unknown'

    C = rrajson.details.risk.confidentiality
    I = rrajson.details.risk.integrity
    A = rrajson.details.risk.availability

    C.reputation.impact = validate_entry(cell_value_near(sheet_data, 'Confidentiality'), risk_levels)
    C.reputation.rationale = cell_value_near(wsheet_data, 'RATIONALE', xmoves=0, ymoves=1)
    C.finances.impact = validate_entry(cell_value_near(sheet_data, 'Confidentiality', xmoves=2), risk_levels)
    C.finances.rationale = cell_value_near(wsheet_data, 'RATIONALE', xmoves=0, ymoves=7)
    C.productivity.impact = validate_entry(cell_value_near(sheet_data, 'Confidentiality', xmoves=3), risk_levels)
    C.productivity.rationale = cell_value_near(wsheet_data, 'RATIONALE', xmoves=0, ymoves=13)
    # RRA v1.0.0 uses Recovery + Access Control to represent integrity.
    # Access Control is closest to real integrity, so we use that.
    I.reputation.rationale = cell_value_near(wsheet_data, 'RATIONALE', xmoves=0, ymoves=3)+','+cell_value_near(wsheet_data, 'RATIONALE', xmoves=0, ymoves=4)
    I.finances.rationale = cell_value_near(wsheet_data, 'RATIONALE', xmoves=0, ymoves=9)+','+cell_value_near(wsheet_data, 'RATIONALE', xmoves=0, ymoves=10)
    I.productivity.rationale = cell_value_near(wsheet_data, 'RATIONALE', xmoves=0,ymoves=15)+','+cell_value_near(wsheet_data, 'RATIONALE', xmoves=0, ymoves=16)
    I.reputation.impact = validate_entry(cell_value_near(sheet_data, 'Access Control'), risk_levels)
    I.finances.impact = validate_entry(cell_value_near(sheet_data, 'Access Control', xmoves=2), risk_levels)
    I.productivity.impact = validate_entry(cell_value_near(sheet_data, 'Access Control', xmoves=3), risk_levels)
    A.reputation.impact = validate_entry(cell_value_near(sheet_data, 'Availability'), risk_levels)
    A.reputation.rationale = cell_value_near(wsheet_data, 'RATIONALE', xmoves=0, ymoves=2)
    A.finances.impact = validate_entry(cell_value_near(sheet_data, 'Availability', xmoves=2), risk_levels)
    A.finances.rationale = cell_value_near(wsheet_data, 'RATIONALE', xmoves=0, ymoves=8)
    A.productivity.impact = validate_entry(cell_value_near(sheet_data, 'Availability', xmoves=3), risk_levels)
    A.productivity.rationale = cell_value_near(wsheet_data, 'RATIONALE', xmoves=0, ymoves=14)

    return rrajson


