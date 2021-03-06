import types
import pydoc
import json
import os
import sys
import subprocess
import urllib2
import time
import random
from functools import partial
from ws4py.client import WebSocketBaseClient

BROWSER_JSON_PATH = os.sep.join(['..','proto','protocol.json'])

CHROME_LINUX_PATH = "/opt/google/chrome-unstable/chrome"
DEVTOOLS_JSON_HOME = 'http://127.0.0.1:{PORT}/json'


def get_browser_api_json(api_path=BROWSER_JSON_PATH):
    return json.loads(open(BROWSER_JSON_PATH,'r').read())

class ParameterAPI(object):
    UNKNOWN_TYPE = "UNKNOWN"
    def __init__(self, init_dict):
        self._raw = init_dict
        self.name = init_dict['name']
        if 'description' in init_dict:
            self.description = init_dict['description']
        else:
            self.description = ""
        if 'type' in init_dict:
            self.vtype = TypeAPI.resolve_type(init_dict['type'])
            self._vtype_strn = init_dict['type']
        elif '$ref' in init_dict:
            self.vtype = "RefType-" + init_dict['$ref']
            self._vtype_strn = init_dict['$ref']
        else:
            self.vtype = ParameterAPI.UNKNOWN_TYPE
            self._vtype_strn = self.vtype
    def __repr__(self):
        return "<Parameter {name} {typ}>".format(name=self.name, typ=self.vtype)

class CommandAPI(object):
    def __init__(self, init_dict,domain=None):
        self._raw = init_dict
        self.domain = domain
        if self.domain:
            self._domain_name = self.domain.name
        else:
            self._domain_name = "NoDomain?"
        self.name = init_dict['name']
        if 'description' in init_dict:
            self.description = init_dict['description']
        else:
            self.description = ""

        if 'parameters' in init_dict:
            self.parameters = [ParameterAPI(param) for param in init_dict['parameters']]

        if 'returns' in init_dict:
            self.returns = [ParameterAPI(retval) for retval in init_dict['returns']]

    def __repr__(self):
        return "<Command {domain}::{api}{desc}>".format(api=self.name, domain=self._domain_name, desc=(" (" + self.description + ")") if self.description  else "")

    @property
    def __doc__(self):
        return self.description + '\n\n' + '\n'.join(self.get_param_desc())

    def get_parameter_names(self):
        return [p.name for p in self.parameters]

    def get_param_desc(self):
        return ["{pname}::{ptype} | {pdesc}".format(pname=p.name,ptype=str(p._vtype_strn), pdesc=p.description) for p in self.parameters]


    def invoke(self, browser, **kwargs):
        if not isinstance(browser, Chropy):
            raise TypeError("Must provide a valid browser")


# TODO: Impl. type discovery, register the types globally or maintain a dict of them or something in Chropy?
class TypeAPI(object):
    def __init__(self, init_dict, domain):
        self.domain = domain
        if 'id' in init_dict:
            self.name = init_dict['id']
        else:
            self.name = init_dict['name']
        self._type = None
        if '$ref' in init_dict:
            self._type_ref = init_dict['$ref']
            self._type_strn = self._type_ref
        elif 'type' in init_dict:
            self._type = TypeAPI.resolve_type(init_dict['type'])
            self._type_strn = init_dict['type']
            if init_dict['type'] == 'object':
                self._properties = []
                if 'properties' in init_dict:
                    for prop in init_dict['properties']:
                        self._properties.append(TypeAPI(prop, self.domain))
        else:
            raise Exception("I don't know what this is:\n" + init_dict)

    def __repr__(self):
        return "<TypeAPI {s}>".format(s=self.friendly_name)

    @property
    def friendly_name(self):
        return self.domain + "." + self.name

    @property
    def friendly_type(self):
        return self._type_strn

    @staticmethod
    def resolve_type(type_strn):
        if type_strn == 'number' or type_strn == 'integer':
            return int
        elif type_strn == 'string':
            return str
        elif type_strn == 'array':
            return type([])
        elif type_strn == 'boolean':
            return bool
        elif type_strn == 'object' or type_strn == 'any':
            return object
        raise Exception("Unrecognized type")

class DomainAPI(object):
    def __init__(self, init_dict):
        self._raw = init_dict
        self.name = init_dict['domain']

        if 'types' in init_dict:
            self._types = [TypeAPI(t, self.name) for t in init_dict['types']]
        if 'commands' in init_dict:
            self._commands = [CommandAPI(cmd, domain=self) for cmd in init_dict['commands']]

        self.commands = type('commands',(),{})()
        for _cmd in self._commands:
            if _cmd not in self.__dict__:
                self.__dict__[_cmd.name] = _cmd
            else:
                    raise Exception("Overwriting something in classdict")


    def __repr__(self):
        return "<API Domain {api}>".format(api=self.name)

    @property
    def types(self):
        return self._types

    @property
    def cmdlist(self):
        return self._commands

    @property
    def command_dict(self):
        return dict([(d.name, d) for d in self._commands])

def build_api_objects():
    api_json = get_browser_api_json()
    domains = [DomainAPI(d) for d in api_json['domains']]
    return dict([(d.name, d) for d in domains])


class Chropy(object):
    def __init__(self):
        self._api_objects = build_api_objects()
        self._proc = None
        self.domains = type('domains', (), {})()
        for apiobj in self._api_objects.keys():
            self.domains.__dict__[apiobj] = self._api_objects[apiobj]

    def _running(fn):
        def wrapper(self, *args):
            if not self._is_running():
                raise Exception("Headless chrome is not running")
            return fn(self, *args)
        return wrapper

    def _is_running(self):
        if not self._proc or self._proc.poll():
            return False
        return True

    def launch_browser(self,port=None,path=None):
        if port is None:
            port = random.randint(10000,20000)
        if self._is_running():
            raise Exception("self._proc already up, create a new Chropy instance")

        if 'linux' in sys.platform:
            if path:
                self._launch_chrome_headless_linux(port,path=path)
            else:
                self._launch_chrome_headless_linux(port)

        else:
            raise Exception("Failed to launch chrome")

        self._ws = self._new_ws(self.get_first_tab()['webSocketDebuggerUrl'])

    def _new_ws(self,ws_url):
        con = WebSocketBaseClient(ws_url)
        con.connect()
        return con

    def get_first_tab(self):
        tabs = [t for t in self.get_tabs() if t['type'] == 'page']
        if len(tabs) == 0:
            raise Exception("Couldn't find tab, weird?")
        return tabs[0]

    def _launch_chrome_headless_linux(self, port,path=CHROME_LINUX_PATH, skip_check=False):
        self._port = port
        self._proc = subprocess.Popen([path,'--headless', '--remote-debugging-port=' + str(port)], stderr=subprocess.PIPE, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        if not skip_check:
            time.sleep(2.5)
            if not self._is_running():
                self._proc = None
                raise Exception("Chrome headless launch seems to have failed")

    @_running
    def get_tabs(self):
        #if not self._is_running():
        #    raise Exception("Can't talk to a dead browser...")
        return json.loads(urllib2.urlopen(DEVTOOLS_JSON_HOME.format(PORT=self._port)).read())

    @_running
    def _send_ws(data, async=False):
        """ Send data on the websocket, async don't wait for the response (we need to make sure the buffer is cleaned though, new ws for asyncs?)"""
        pass

    def _create_function(self, c_api):
        assert(isinstance(c_api, CommandAPI))
        # Two args, Chropy and CommandAPI
        y = Chropy._api_command_stub
        y_code = types.CodeType(0,
                       y.func_code.co_nlocals,
                       y.func_code.co_stacksize,
                       y.func_code.co_flags,
                       y.func_code.co_code,
                       y.func_code.co_consts,
                       y.func_code.co_names,
                       y.func_code.co_varnames,
                       "<Dynamic Code From Outer Space>",
                       str(c_api.name),
                       y.func_code.co_firstlineno,
                       y.func_code.co_lnotab)
        y.func_globals['zc_api'] = c_api
        y.func_globals['zchropy'] = self
        fn = types.FunctionType(y_code, y.func_globals, str(c_api.name))
        fn.func_doc = c_api.__doc__
        return fn

    @staticmethod
    def _api_command_stub():
        # This is one fucking ugly hack and i apologize in the name of humanity
        # These globals are injected from the sky
        cmd_api = zc_api
        chropy = zchropy



