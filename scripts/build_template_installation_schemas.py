"""Write identical public and installed strict template installation schemas."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
DIGEST = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
STRING = {'type': 'string', 'minLength': 1}
PATH = STRING
BOOL = {'type': 'boolean'}
OBJECT = {'type': 'object'}
STRMAP = {'type': 'object', 'additionalProperties': STRING}
WHEEL = {'type': 'object', 'additionalProperties': False, 'required': ['filename', 'sha256'],
         'properties': {'filename': {'type': 'string', 'pattern': '^[^/\\\\]+\\.whl$'}, 'sha256': DIGEST}}
REQUIREMENT = {'type': 'object', 'additionalProperties': False,
               'required': ['name', 'version', 'wheel', 'sha256'],
               'properties': {'name': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9._-]*$'},
                              'version': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9._+!-]*$'},
                              'wheel': STRING, 'sha256': DIGEST}}


def schema(properties, *, kind=None):
    data = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
            'type': 'object', 'additionalProperties': False,
            'required': list(properties), 'properties': properties}
    if kind:
        data['properties']['kind'] = {'const': kind}
    return data


REQUEST = schema({
    'schema_version': {'const': '1.0'}, 'host_root': PATH, 'implementation_bundle': PATH,
    'trusted_modified_receipt_sha256': DIGEST, 'template_directory': PATH,
    'reviewed_package_source_sha256': DIGEST, 'reviewed_configuration_sha256': DIGEST,
    'interpreter': PATH, 'wheelhouse': PATH, 'package_directory': PATH,
    'environment_parent': PATH, 'console_script': STRING,
    'build_tools': {'type': 'object', 'additionalProperties': False,
                    'required': ['pip', 'setuptools', 'wheel'],
                    'properties': {'pip': STRING, 'setuptools': STRING, 'wheel': STRING}},
    'wheels': {'type': 'array', 'minItems': 1, 'maxItems': 256, 'items': WHEEL},
    'requirements': {'type': 'array', 'minItems': 1, 'maxItems': 256, 'items': REQUIREMENT},
    'configuration': {'type': 'object', 'additionalProperties': False, 'required': ['jev_runtime'],
                      'properties': {'jev_runtime': {'type': 'object', 'additionalProperties': False,
                                                     'required': ['mode', 'credential_ref'],
                                                     'properties': {'mode': {'const': 'off'},
                                                                    'credential_ref': {'oneOf': [
                                                                        {'type': 'null'},
                                                                        {'type': 'string', 'pattern': '^env:[A-Za-z_][A-Za-z0-9_]*$'}]}}}}},
    'secret_references': {'type': 'object', 'additionalProperties':
                          {'type': 'string', 'pattern': '^env:[A-Za-z_][A-Za-z0-9_]*$'}},
})
PROFILE = schema({'python': STRING, 'soabi': STRING, 'platform': STRING,
                  'interpreter_sha256': DIGEST, 'executable_path': PATH,
                  'sys_prefix': PATH})
PACKAGE_PLAN = schema({
    'schema_version': {'const': '1.0'}, 'kind': {'const': 'template-package-plan-v1'},
    'request': REQUEST, 'template_lock_sha256': DIGEST,
    'implementation_bundle_digest': DIGEST,
    'source_files': {'type': 'object', 'additionalProperties': DIGEST},
    'source_sha256': DIGEST, 'project_name': STRING, 'project_version': STRING,
    'entry_point': STRING, 'profile': PROFILE,
    'operations': {'const': ['copy_verified_source', 'build_offline_wheel', 'hash_and_record_wheel']},
    'target_executed': {'const': False}, 'runtime_activation_authorized': {'const': False},
    'plan_sha256': DIGEST,
})
PACKAGE_RECEIPT = schema({
    'schema_version': {'const': '1.0'}, 'kind': {'const': 'template-package-receipt-v1'},
    'plan_sha256': DIGEST, 'source_sha256': DIGEST, 'wheel_filename': STRING,
    'wheel_sha256': DIGEST, 'project_name': STRING, 'project_version': STRING,
    'entry_point': STRING, 'profile': PROFILE, 'runtime_activation_authorized': {'const': False},
    'receipt_sha256': DIGEST,
})
INSTALL_PLAN = schema({
    'schema_version': {'const': '1.0'}, 'kind': {'const': 'template-install-plan-v1'},
    'package_plan': PACKAGE_PLAN, 'package_receipt': PACKAGE_RECEIPT,
    'environment_parent': PATH, 'wheelhouse': PATH,
    'wheels': {'type': 'array', 'items': WHEEL},
    'requirements': {'type': 'array', 'items': REQUIREMENT},
    'configuration': OBJECT, 'secret_references': STRMAP, 'console_script': STRING,
    'profile': PROFILE,
    'operations': {'const': ['create_owned_venv', 'install_hash_checked_wheels',
                            'verify_metadata_and_import_origin', 'write_off_configuration']},
    'runtime_activation_authorized': {'const': False}, 'plan_sha256': DIGEST,
})
INSTALL_RECEIPT = schema({
    'schema_version': {'const': '1.0'}, 'kind': {'const': 'template-install-receipt-v1'},
    'plan_sha256': DIGEST, 'package_receipt_sha256': DIGEST, 'environment': PATH,
    'generation_id': STRING, 'configuration_sha256': DIGEST,
    'secret_references_sha256': DIGEST,
    'installed': schema({'python': PATH, 'console_script': PATH,
                         'console_script_sha256': DIGEST, 'entrypoint_origin': PATH,
                         'installed_files_sha256': DIGEST, 'distributions': STRMAP}),
    'mode': {'const': 'off'},
    'launched': {'const': False}, 'provider_reachable': {'const': False},
    'runtime_activation_authorized': {'const': False}, 'receipt_sha256': DIGEST,
})

for name, value in {
    'template-package-request-v1': REQUEST,
    'template-package-plan-v1': PACKAGE_PLAN,
    'template-package-receipt-v1': PACKAGE_RECEIPT,
    'template-install-plan-v1': INSTALL_PLAN,
    'template-install-receipt-v1': INSTALL_RECEIPT,
}.items():
    content = json.dumps(value, indent=2) + '\n'
    for directory in ('schemas', 'jev_integration_evaluator/data'):
        (ROOT / directory / (name + '.schema.json')).write_bytes(content.encode('utf-8'))
