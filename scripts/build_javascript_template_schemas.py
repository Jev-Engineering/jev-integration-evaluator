"""Generate identical strict public and packaged JS template contracts."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'jev_integration_evaluator/data/javascript-recipe-c.template.json').read_text(encoding='utf-8'))
DIGEST = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
TEXT = {'type': 'string', 'minLength': 1}
FILENAME = {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9._-]*\\.(?:mjs|cjs)$'}
ENVREF = {'type': 'string', 'pattern': '^env:[A-Za-z_][A-Za-z0-9_]*$'}


def strict(properties):
    return {'type': 'object', 'additionalProperties': False,
            'required': list(properties), 'properties': properties}


CONFIG = strict({'mode': {'const': 'off'}, 'credential_ref': {'oneOf': [{'type': 'null'}, ENVREF]}})
REFS = {'type': 'object', 'additionalProperties': False, 'properties': {'credential': ENVREF}}
REQUEST = strict({
    'schema_version': {'const': '1.0'}, 'template_id': {'const': 'javascript.recipe-c'},
    'template_version': {'const': '1.0.0'}, 'backend': {'const': 'javascript'},
    'profile': {'const': 'flat-async-recipe-c-v1'},
    'format': {'enum': ['esm', 'commonjs', 'typescript']},
    'implementation_spec': {'type': 'object'}, 'entrypoint': FILENAME,
    'package_json_sha256': DIGEST, 'package_lock_sha256': DIGEST,
    'entrypoint_sha256': DIGEST, 'reviewed_package_source_sha256': DIGEST,
    'configuration': CONFIG, 'secret_references': REFS,
    'reviewed_configuration_sha256': DIGEST,
})
TOOLING = strict({name: ({'const': '5.8.3'} if name == 'compiler_version' else
                         TEXT if name.endswith('_path') else DIGEST)
                  for name in ('node_path', 'node_sha256', 'compiler_path', 'compiler_sha256',
                               'compiler_version', 'transformer_sha256', 'runtime_sha256',
                               'probe_sha256', 'emitter_sha256', 'backend_sha256',
                               'lifecycle_sha256')})
PACKAGE = strict({'name': TEXT, 'version': TEXT, 'entrypoint': FILENAME,
                  'source_files': {'type': 'object', 'minProperties': 3, 'additionalProperties': DIGEST},
                  'source_sha256': DIGEST, 'dependency_count': {'type': 'integer', 'minimum': 0},
                  'package_json_sha256': DIGEST, 'package_lock_sha256': DIGEST,
                  'entrypoint_sha256': DIGEST})
LOCK = strict({
    'schema_version': {'const': '1.0'}, 'status': {'const': 'materialized'},
    'template_id': {'const': 'javascript.recipe-c'}, 'template_version': {'const': '1.0.0'},
    'manifest_sha256': DIGEST, 'evaluator_version': TEXT, 'renderer_sha256': DIGEST,
    'tooling': TOOLING, 'request_sha256': DIGEST, 'spec_sha256': DIGEST,
    'candidate_id': TEXT, 'format': {'enum': ['esm', 'commonjs', 'typescript']},
    'source_sha256': DIGEST, 'generated_sha256': DIGEST,
    'emitted_sha256': {'oneOf': [DIGEST, {'type': 'null'}]},
    'package': PACKAGE, 'configuration_sha256': DIGEST,
    'secret_references_sha256': DIGEST, 'lifecycle': {'const': MANIFEST['lifecycle']},
    'target_modified': {'const': False}, 'target_executed': {'const': False},
    'owned_resources': strict({name: DIGEST for name in (
        'template-manifest.json', 'template-request.json', 'implementation-spec.json',
        'package-profile.json')}),
    'planner': strict({'command': {'const': 'js-plan'},
                       'spec': {'const': 'implementation-spec.json'},
                       'tooling': TEXT, 'output': {'const': 'new external private bundle'}}),
    'lock_sha256': DIGEST,
})
SCHEMAS = {'javascript-template-request-v1': REQUEST,
           'javascript-template-manifest-v1': {'const': MANIFEST},
           'javascript-template-lock-v1': LOCK}
for name, schema in SCHEMAS.items():
    data = json.dumps({'$schema': 'https://json-schema.org/draft/2020-12/schema', **schema},
                      indent=2, sort_keys=True).encode('utf-8') + b'\n'
    for directory in ('schemas', 'jev_integration_evaluator/data'):
        (ROOT / directory / (name + '.schema.json')).write_bytes(data)
