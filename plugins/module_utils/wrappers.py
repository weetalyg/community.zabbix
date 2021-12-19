#!/usr/bin/env python
# -*- coding: utf-8 -*-

# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import atexit
import traceback

from ansible.module_utils.basic import missing_required_lib

from ansible_collections.community.zabbix.plugins.module_utils.api_request import ZabbixApiRequest
from ansible.module_utils.connection import ConnectionError
from ansible.module_utils.six.moves.urllib.parse import urlparse

try:
    from zabbix_api import ZabbixAPI, Already_Exists, ZabbixAPIException

    HAS_ZABBIX_API = True
except ImportError:
    ZBX_IMP_ERR = traceback.format_exc()
    HAS_ZABBIX_API = False

class ZapiWrapper(object):
    _is_httpapi = False
    _is_zabbix_api = False

    """
    A simple wrapper over the Zabbix API
    """
    def __init__(self, module, zbx=None):
        self._module = module

        if self.get_connection_type() != 'auto':
            self._module.warn('It is encuraged to keep connection_type to \'auto\'')

        if self.get_connection_type() == 'auto':
            _try_httpapi = False
            _try_zapi = True
        elif self.get_connection_type() == 'zabbix-api':
            _try_httpapi = False
            _try_zapi = True
        elif self.get_connection_type() == 'httpapi':
            _try_httpapi = True
            _try_zapi = False

        if _try_httpapi:
            if not self._module._socket_path:
                module.fail_json(msg='The required settings for httpapi connection are not provided.')

            self._module.warn('Usage of httpapi is considered experimental')
            given_params = self._module.params
            legacy_options = ['server_url', 'host', 'port', 'login_user', 'login_password', 'http_login_user', 'http_login_password']
            legacy_params = []
            for param in legacy_options:
                if param in given_params and given_params[param] is not None:
                    legacy_params.append(param)

            self._api_request = ZabbixApiRequest(self._module)
            if len(legacy_params):
                self._module.warn('If using httpapi old module options should be replaced - see documentation')
                _host = urlparse(module.params['server_url'])
                self._api_request.connection.set_option('host', _host.hostname)
                self._api_request.connection.set_option('port', _host.port)
                self._api_request.connection.set_option('remote_user', module.params['login_user'])
                self._api_request.connection.set_option('password', module.params['login_password'])
                self._api_request.connection.set_option('basic_auth_user', module.params['http_login_user'])
                self._api_request.connection.set_option('basic_auth_password', module.params['http_login_password'])

            try:
                self._zbx_api_version = self._api_request.connection.api_version()[:5]
                self._zapi = self._api_request
                self._is_zabbix_api = False
                self._is_httpapi = True
            except ConnectionError as error:
                if _try_zapi is False:
                    self._module.fail_json(msg='Initialization of httpapi failed but zabbix-api fallback disabled',
                                           exception=error)
                else:
                    self._module.warn('Initialization of httpapi failed try fallback to zabbix-api')

        if _try_zapi:
            if not HAS_ZABBIX_API:
                module.fail_json(msg=missing_required_lib('zabbix-api', url='https://pypi.org/project/zabbix-api/'),
                                 exception=ZBX_IMP_ERR)

            # check if zbx is already instantiated or not
            if zbx is not None and isinstance(zbx, ZabbixAPI):
                self._zapi = zbx
            else:
                server_url = module.params['server_url']
                http_login_user = module.params['http_login_user']
                http_login_password = module.params['http_login_password']
                validate_certs = module.params['validate_certs']
                timeout = module.params['timeout']
                self._zapi = ZabbixAPI(server_url, timeout=timeout, user=http_login_user,
                                       passwd=http_login_password, validate_certs=validate_certs)

            self.login()

            self._zbx_api_version = self._zapi.api_version()[:5]
            self._is_httpapi = False
            self._is_zabbix_api = True

        if not self._zapi or self._zapi is None:
            self._module.fail_json(msg="None of the connection type worked. See stdout/stderr for the exact error.")

    def get_connection_type(self):
        if self._module:
            return self._module.params.get('connection_type', 'auto')
        else:
            return 'auto'

    def login(self):
        # check if api already logged in
        if not self._zapi.auth != '':
            try:
                login_user = self._module.params['login_user']
                login_password = self._module.params['login_password']
                self._zapi.login(login_user, login_password)
                atexit.register(self._zapi.logout)
            except Exception as e:
                self._module.fail_json(msg="Failed to connect to Zabbix server: %s" % e)


class ScreenItem(object):
    @staticmethod
    def create(zapi_wrapper, data, ignoreExists=False):
        try:
            zapi_wrapper._zapi.screenitem.create(data)
        except Already_Exists as ex:
            if not ignoreExists:
                raise ex

    @staticmethod
    def delete(zapi_wrapper, id_list=None):
        try:
            if id_list is None:
                id_list = []
            zapi_wrapper._zapi.screenitem.delete(id_list)
        except ZabbixAPIException as ex:
            raise ex
