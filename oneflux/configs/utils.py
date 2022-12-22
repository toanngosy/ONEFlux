import argparse
import datetime as dt
import importlib
import logging
import os
import sys
import yaml

from oneflux import ONEFluxError
from oneflux.tools.partition_nt import PROD_TO_COMPARE, PERC_TO_COMPARE

log = logging.getLogger(__name__)

YAML_TEMPLATE_PATH = 'oneflux/configs/config_template.yaml'
YAML_DESCRIPTION_PATH ='oneflux/configs/config_description.yaml'
STEP_NAME_LIST = ['01_qc_visual', '02_qc_auto', '04_ustar_mp', '05_ustar_cp',
                    '06_meteo_era', '07_meteo_proc', '08_nee_proc', '09_energy_proc',
                    '10_nee_partition_nt', '11_nee_partition_dt', '12_ure',
                    '99_fluxnet2015']
def argparse_from_yaml_and_cli():
    param_dest = {}
    config_default = {}
    all_params = []
    with open(YAML_DESCRIPTION_PATH, 'r') as f:
        config_description = yaml.safe_load(f)
    with open(YAML_TEMPLATE_PATH, 'r') as f:
        config_default = yaml.safe_load(f)
    parser = argparse.ArgumentParser()
    for parser_group_name, params in config_description.items():
        group = parser.add_argument_group(parser_group_name)
        default_val = config_default.get(parser_group_name, {})
        for param_name, param_details in params.items():
            all_params.append(param_name)
            if 'type' in param_details:
                param_details['type'] = _type_from_str(param_details['type'])
            if 'choices' in param_details:
                param_details['choices'] = _parse_choices(param_details['choices'])
            if 'dest' in param_details:
                param_dest[param_name] = param_details['dest']
            if param_name in default_val:
                param_details['default'] = default_val[param_name]
                if isinstance(param_details['default'], str) and ':' in param_details['default']:
                    module, class_name = default_val[param_name].split(':')
                    param_details['default'] = _str_to_class(module, class_name)
                param_details['help'] += ' (default to {})'.format(param_details['default'])
            param_name = param_name.replace('_', '-')
            group.add_argument('--{}'.format(param_name), **param_details)
    args = parser.parse_args()
    commandline_args = [arg.strip('-_') for arg in sys.argv[1:] if '-' in arg or '--' in arg]
    configfile = args.configfile
    args_dict = vars(args)
    if configfile:
        with open(configfile, 'r') as f:
            config = yaml.safe_load(f)
        for _, params in config.items():
            for param_name, param_value in params.items():
                if param_name not in all_params:
                    raise ValueError(f'{param_name} is unknown: it has not been declared in the config_description.yaml and the default value in config_template.yaml')
                if param_name not in commandline_args:
                    if param_name in param_dest:
                        param_name = param_dest[param_name]
                    args_dict[param_name] = param_value
    return config_default, param_dest, argparse.Namespace(**args_dict)

class ONEFluxConfig:
    def __init__(self):
        self.config_default, self.param_dest, self.args = argparse_from_yaml_and_cli()
        self.perc = (PERC_TO_COMPARE if self.args.perc is None else self.args.perc[0])
        self.prod = (PROD_TO_COMPARE if self.args.prod is None else self.args.prod[0])

    def get_pipeline_params(self):
        params = {
            'datadir': self.args.datadir,
            'siteid': self.args.siteid,
            'sitedir': self.args.sitedir,
            'firstyear': self.args.firstyear,
            'lastyear': self.args.lastyear,
            'prod_to_compare': self.prod,
            'perc_to_compare': self.perc,
            'mcr_directory': self.args.mcr_directory,
            'timestamp': self.args.timestamp,
            'record_interval': self.args.recint,
            'version_data': self.args.versiond,
            'version_proc': self.args.versionp,
            'era_first_year': self.args.erafy,
            'era_last_year': self.args.eraly,
            'steps': {
                'qc_auto_execute': self.args.qc_auto_execute,
                'ustar_mp_execute': self.args.ustar_mp_execute,
                'user_cp_execute': self.args.user_cp_execute,
                'meteo_proc_execute': self.args.meteo_proc_execute,
                'nee_proc_execute': self.args.nee_proc_execute,
                'energy_proc_execute': self.args.energy_proc_execute,
                'nee_partition_nt_execute': self.args.nee_partition_nt_execute,
                'nee_partition_dt_execute': self.args.nee_partition_dt_execute,
                'prepare_ure_execute': self.args.prepare_ure_execute,
                'ure_execute': self.args.ure_execute,
                'fluxnet2015_execute': self.args.fluxnet2015_execute,
                'fluxnet2015_site_plots': self.args.fluxnet2015_site_plots,
                'simulation': self.args.simulation
            }
        }
        return params

    def get_partition_nt_params(self):
        params = {
            'datadir': self.args.datadir,
            'siteid': self.args.siteid,
            'sitedir': self.args.sitedir,
            'years_to_compare':range(self.args.firstyear, self.args.lastyear + 1),
            'py_remove_old': self.args.forcepy,
            'prod_to_compare': self.perc,
            'perc_to_compare': self.prod
        }
        return params

    def get_partition_dt_params(self):
        params = {
            'datadir': self.args.datadir,
            'siteid': self.args.siteid,
            'sitedir': self.args.sitedir,
            'years_to_compare':range(self.args.firstyear, self.args.lastyear + 1),
            'py_remove_old': self.args.forcepy,
            'prod_to_compare': self.perc,
            'perc_to_compare': self.prod
        }
        return params

    def export_to_yaml(self, dir=None, name=None, overwritten=False):
        saved_dict = {}
        args_dict = vars(self.args)
        for group_name, params in self.config_default.items():
            saved_dict[group_name] = {}
            for param, param_value in params.items():
                if param not in self.param_dest:
                    p = param
                    if p in args_dict and args_dict[p] != param_value:
                        saved_dict[group_name][p] = args_dict[p]
                else:
                    p = self.param_dest[param]
                    if p in args_dict and args_dict[p] != param_value:
                        saved_dict[group_name][param] = args_dict[p]
        if not name:
            name = 'run_params_{}.yaml'.format(dt.datetime.now().strftime('%d-%m-%Y_%H-%M-%S'))
        if not dir:
            path = name
        else:
            path = f'{dir}/{name}'
        if dir and not os.path.exists(dir):
            os.makedirs(dir)
        if overwritten and os.path.isfile(path):
            os.remove(path)
        with open(path, 'w') as f:
                yaml.dump(saved_dict, f, default_flow_style=False)

    def export_step_to_yaml(self, dir=None, name='config.yaml', overwritten=False):
        step = os.path.split(dir)[-1]
        if step not in STEP_NAME_LIST:
            raise ONEFluxError(f"Step does not exist: {step}")
        v = {}
        for arg in self.config_default.get(step, []):
            v[arg] = self.args.__getattribute__(arg.replace('-', '_'))
        if v:
            path = f'{dir}/{name}'
            if overwritten and os.path.isfile(path):
                os.remove(path)
            with open(path, 'w') as f:
                yaml.dump(v, f, default_flow_style=False)


    def log_msg(self):
        msg = "Using: \n"
        msg += "\tcommand ({c}) \n".format(c=self.args.command)
        msg += "\tdata-dir ({i}) \n".format(i=self.args.datadir)
        msg += "\tsite-id ({i}) \n".format(i=self.args.siteid)
        msg += "\tsite-dir ({d}) \n".format(d=self.args.sitedir)
        msg += "\tfirst-year ({y}) \n".format(y=self.args.firstyear)
        msg += "\tlast-year ({y}) \n".format(y=self.args.lastyear)
        msg += "\tperc ({i}) \n".format(i=self.perc)
        msg += "\tprod ({i}) \n".format(i=self.prod)
        msg += "\tlog-file ({f}) \n".format(f=self.args.logfile)
        msg += "\tforce-py ({i}) \n".format(i=self.args.forcepy)
        msg += "\tversionp ({i}) \n".format(i=self.args.versionp)
        msg += "\tversiond ({i}) \n".format(i=self.args.versiond)
        msg += "\tera-fy ({i}) \n".format(i=self.args.erafy)
        msg += "\tera-ly ({i}) \n".format(i=self.args.eraly)
        log.debug(msg)

    def run_check(self):
        if not os.path.isdir(os.path.join(self.args.datadir, self.args.sitedir)):
            raise ONEFluxError("Site dir not found: {d}".format(d=self.args.sitedir))

def _type_from_str(s):
    s_dict = {'str': str, 'int': int, 'float': float, 'bool': bool}
    return s_dict[s]

def _str_to_class(module, class_name):
    try:
        m = importlib.import_module(module)
        try:
            c = getattr(m, class_name)
        except AttributeError:
            raise AttributeError('Class does not exist')
    except ImportError:
        raise ImportError('Module does not exist')
    return c

def _parse_choices(choices):
    if isinstance(choices, list):
        return choices
    # import from file
    elif isinstance(choices, str):
        module, class_name = choices.split(':')
        return _str_to_class(module, class_name)
