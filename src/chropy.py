import json
import os

BROWSER_JSON_PATH = os.sep.join(['..','proto','protocol.json'])

def get_browser_api_json(api_path=BROWSER_JSON_PATH):
    return json.loads(open(BROWSER_JSON_PATH,'r').read())

class ParameterAPI(object):
    UNKNOWN_TYPE = "UNKNOWN"
    def __init__(self, init_dict):
        self.name = init_dict['name']
        if 'type' in init_dict:
            self.vtype = init_dict['type']
        else:
            self.vtype = ParameterAPI.UNKNOWN_TYPE
    def __repr__(self):
        return "<Parameter {name} {typ}>".format(name=self.name, typ=self.vtype)

class CommandAPI(object):
    def __init__(self, init_dict,domain=None):
        self.domain = domain
        if self.domain:
            self._domain_name = self.domain.name
        else:
            self._domain_name = "NoDomain?"
        self.name = init_dict['name']
        if 'description' in init_dict:
            self.description = init_dict['description']
        if 'parameters' in init_dict:
            self.parameters = [ParameterAPI(param) for param in init_dict['parameters']]
        if 'returns' in init_dict:
            self.returns = [ParameterAPI(retval) for retval in init_dict['returns']]

    def __repr__(self):
        return "<Command {domain}::{api}>".format(api=self.name, domain=self._domain_name)



class DomainAPI(object):
    def __init__(self, init_dict):
        self.name = init_dict['domain']
        if 'commands' in init_dict:
            self._commands = [CommandAPI(cmd, domain=self) for cmd in init_dict['commands']]

    def __repr__(self):
        return "<API Domain {api}>".format(api=self.name)

    @property
    def cmdlist(self):
        return self._commands

    @property
    def commands(self):
        return dict([(d.name, d) for d in self._commands])

def build_api_objects():
    api_json = get_browser_api_json()
    domains = [DomainAPI(d) for d in api_json['domains']]
    return dict([(d.name, d) for d in domains])

api_objects = build_api_objects()

