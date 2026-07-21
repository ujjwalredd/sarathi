def parse_content_type(value):
    main, *raw_parameters = value.split(";")
    media_type, subtype = main.split("/", 1)
    parameters = {}
    for raw_parameter in raw_parameters:
        name, parameter_value = raw_parameter.split("=", 1)
        parameters[name.strip().lower()] = parameter_value.strip().strip('"')
    return media_type.strip().lower(), subtype.strip().lower(), tuple(parameters.items())
