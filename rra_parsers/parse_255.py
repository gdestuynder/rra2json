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

    metadata.scope = cell_value_near(sheet_data, 'Scoped for team')
    metadata.owner = cell_value_near(sheet_data, 'Service Owner', xmoves=2, ymoves=0)
    metadata.description = cell_value_near(sheet_data, 'Description')
    try:
        metadata.analyst = cell_value_near(sheet_data, 'RRA Analyst')
    except IndexError:
        metadata.analyst = cell_value_near(sheet_data, 'Risk Analyst', xmoves=2, ymoves=0)

    metadata.contacts = comma_tokenizer(cell_value_near(sheet_data, 'Other Contacts'))

    metadata.service_provided = cell_value_near(sheet_data, 'Service provided')
    metadata.risk_record = cell_value_near(sheet_data, 'Risk Record')

    rrajson.summary = 'RRA for {}'.format(metadata.service)
    rrajson.timestamp = toUTC(datetime.now()).isoformat()
    rrajson.lastmodified = toUTC(s.updated).isoformat()

    data = rrajson.details.data
    data.default = normalize_data_level(cell_value_near(sheet_data, 'Service Data classification', xmoves=2))

    # Step two.. find/list all data dictionnary
    res = [match for match in list_find(sheet_data, 'Data Classification')][0]
    i = 0
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

    # Step three.. find all impacts and rationales
    C.reputation.impact = validate_entry(cell_value_near(sheet_data, 'Impact', xmoves=0, ymoves=1), risk_levels)
    C.productivity.impact = validate_entry(cell_value_near(sheet_data, 'Impact', xmoves=0, ymoves=2), risk_levels)
    C.finances.impact = validate_entry(cell_value_near(sheet_data, 'Impact', xmoves=0, ymoves=3), risk_levels)
    A.reputation.impact = validate_entry(cell_value_near(sheet_data, 'Impact', xmoves=0, ymoves=4), risk_levels)
    A.productivity.impact = validate_entry(cell_value_near(sheet_data, 'Impact', xmoves=0, ymoves=5), risk_levels)
    A.finances.impact = validate_entry(cell_value_near(sheet_data, 'Impact', xmoves=0, ymoves=6), risk_levels)
    I.reputation.impact = validate_entry(cell_value_near(sheet_data, 'Impact', xmoves=0, ymoves=7), risk_levels)
    I.productivity.impact = validate_entry(cell_value_near(sheet_data, 'Impact', xmoves=0, ymoves=8), risk_levels)
    I.finances.impact = validate_entry(cell_value_near(sheet_data, 'Impact', xmoves=0, ymoves=9), risk_levels)

    C.reputation.rationale = cell_value_near(sheet_data, 'Threats, use-cases, rationales', xmoves=0, ymoves=1)
    C.productivity.rationale = cell_value_near(sheet_data, 'Threats, use-cases, rationales', xmoves=0, ymoves=2)
    C.finances.rationale = cell_value_near(sheet_data, 'Threats, use-cases, rationales', xmoves=0, ymoves=3)
    A.reputation.rationale = cell_value_near(sheet_data, 'Threats, use-cases, rationales', xmoves=0, ymoves=4)
    A.productivity.rationale = cell_value_near(sheet_data, 'Threats, use-cases, rationales', xmoves=0, ymoves=5)
    A.finances.rationale = cell_value_near(sheet_data, 'Threats, use-cases, rationales', xmoves=0, ymoves=6)
    I.reputation.rationale = cell_value_near(sheet_data, 'Threats, use-cases, rationales', xmoves=0, ymoves=7)
    I.productivity.rationale = cell_value_near(sheet_data, 'Threats, use-cases, rationales', xmoves=0, ymoves=8)
    I.finances.rationale = cell_value_near(sheet_data, 'Threats, use-cases, rationales', xmoves=0, ymoves=9)

    #Depending on the weather this field is called Probability or Likelihood... the format is otherwise identical.
    try:
        probability = 'Probability'
        C.reputation.probability = validate_entry(cell_value_near(sheet_data, probability, xmoves=0, ymoves=1), risk_levels)
    except IndexError:
        probability = 'Likelihood Indicator'
        C.reputation.probability = validate_entry(cell_value_near(sheet_data, probability, xmoves=0, ymoves=1), risk_levels)

    C.productivity.probability = C.reputation.probability
    C.finances.probability = C.reputation.probability
    A.reputation.probability = validate_entry(cell_value_near(sheet_data, probability, xmoves=0, ymoves=4), risk_levels)
    A.productivity.probability = A.reputation.probability
    A.finances.probability = A.reputation.probability
    I.reputation.probability = validate_entry(cell_value_near(sheet_data, probability, xmoves=0, ymoves=7), risk_levels)
    I.productivity.probability = I.reputation.probability
    I.finances.probability = I.reputation.probability

    #Step four... parse all recommendations
    # if there are more than 100 recommendations, that's too many anyway.
    # the 100 limit is a safeguard in case the loop goes wrong due to unexpected data in the sheet
    R = rrajson.details.recommendations
    for i in range(1, 100):
        recommendation = cell_value_near(sheet_data, 'Recommendations (Follow-up in a risk record bug)', xmoves=0,
                ymoves=i)
        # risk_levels are the same as control_need levels (they're standard!), so using them for validation.
        control_need = validate_entry(cell_value_near(sheet_data, 'Recommendations (Follow-up in a risk record bug)', xmoves=8,
                ymoves=i), risk_levels)
        if (recommendation == ''):
            break
        R[control_need].append(recommendation)

    return rrajson


