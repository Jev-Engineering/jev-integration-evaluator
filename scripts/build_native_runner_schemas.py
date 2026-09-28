"""Build strict mirrored runner and observation contracts deterministically.

This writes only these contribution-owned schemas. It does not rebuild the
repository release manifest or imply full-repository validation.
"""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
HEX={'type':'string','pattern':'^[0-9a-f]{64}$'}
ID={'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$'}
REL={'type':'string','minLength':1,'maxLength':240,
     'pattern':r'^(?!/)(?!.*\\)(?!.*[\u0000-\u001f\u007f])(?!.*(?:^|/)\.\.?(/|$))[^/]+(?:/[^/]+)*$'}

def obj(properties):
    return {'type':'object','additionalProperties':False,'required':list(properties),'properties':properties}

def integer(low,high):return {'type':'integer','minimum':low,'maximum':high}

def const(value):return {'const':value}

ENV_KEYS=['python_executable','python_sha256','python_version','machine','kernel',
          'worker_sha256','supervisor_sha256','library_path','library_sha256',
          'runtime_dependencies_sha256']
environment_identity=obj({key:HEX if key.endswith('_sha256') else {'type':'string','minLength':1,'maxLength':4096}
                          for key in ENV_KEYS})
limits=obj({key:integer(*bounds) for key,bounds in {
    'wall_seconds':(1,30),'cpu_seconds':(1,20),'address_space_bytes':(67108864,536870912),
    'open_files':(16,64),'output_bytes':(64,1048576),'schedule_seconds':(1,120)}.items()})
spec=obj({
    'schema_version':const('1.0'),'backend':const('linux-chroot-seccomp-python-ro-v1'),
    'source_identity':obj({'device':integer(0,2**64-1),'inode':integer(0,2**64-1)}),
    'files':{'type':'array','minItems':1,'maxItems':256,'uniqueItems':True,
             'items':obj({'path':REL,'sha256':HEX,'bytes':integer(0,2097152),
                          'mode':{'type':'integer','enum':[292,420,365,493]}})},
    'environment_identity':environment_identity,
    'environment':{'type':'object','maxProperties':16,'additionalProperties':False,
                   'patternProperties':{'^JEV_[A-Z0-9_]{1,40}$':{'type':'string','maxLength':256,'pattern':'^[^\u0000]*$'}}},
    'schedule':{'type':'array','minItems':1,'maxItems':64,
                'items':obj({'case_id':ID,'entry':REL,'argv':{'type':'array','maxItems':32,
                    'items':{'type':'string','maxLength':1024,'pattern':'^[^\u0000]*$'}}})},
    'limits':limits,
})
file_record=obj({'path':REL,'sha256':HEX,'bytes':integer(0,2097152),
                 'mode':{'type':'integer','enum':[292,420,365,493]}})
target_environment=obj({
    'interpreter_path':{'type':'string','pattern':'^/[^\\u0000]*$','maxLength':4096},
    'interpreter_sha256':HEX,
    'dependency_root':{'type':'string','pattern':'^/[^\\u0000]*$','maxLength':4096},
    'dependency_identity':obj({'device':integer(0,2**64-1),'inode':integer(0,2**64-1)}),
    'files':{'type':'array','minItems':1,'maxItems':256,'items':file_record},
    'distributions':{'type':'array','minItems':1,'maxItems':32,'items':obj({
        'name':ID,'version':ID,'metadata_path':REL})},
})
spec11=json.loads(json.dumps(spec))
spec11['properties']['schema_version']=const('1.1')
spec11['properties']['target_environment']=target_environment
spec11['required'].append('target_environment')
spec11['properties']['isolation_capabilities']=const({
    'platform':'linux-x86_64','filesystem':'read_only_copied_snapshot',
    'network':'denied','process_creation':'denied','threads':'denied',
    'exec':'denied','target_interpreter':'same_inode_trusted_worker',
    'dependencies':'declared_pure_python_snapshot'})
spec11['required'].append('isolation_capabilities')
spec={'oneOf':[spec,spec11]}
outcomes=['exited_zero','execution_failed','timeout','output_limit','setup_failed',
    'cleanup_failed','copied_source_drift','schedule_deadline','environment_drift',
    'source_root_changed','source_drift','source_changed_during_read','unsafe_or_missing_root',
    'unsafe_or_missing_source','unsupported_source_file','source_byte_limit','unsupported_platform',
    'privileged_launcher_required','libseccomp_missing','runtime_probe_failed','absolute_root_required',
    'unsupported_target_interpreter','target_interpreter_drift','dependency_root_changed','dependency_drift',
    'prerequisite_io_error']
row=obj({'case_id':ID,'command_sha256':HEX,'outcome':{'type':'string','enum':outcomes},
    'target_launch_released':{'type':'boolean'},'isolation_established':{'type':'boolean'},
    'returncode':{'anyOf':[{'type':'null'},integer(-128,255)]},
    'stdout_bytes':integer(0,1048576),'stderr_bytes':integer(0,1048576),
    'stdout_sha256':HEX,'stderr_sha256':HEX,'elapsed_ms':integer(0,180000),
    'cleanup_complete':{'type':'boolean'}})
receipt=obj({'schema_version':const('1.0'),'backend':const('linux-chroot-seccomp-python-ro-v1'),
    'run_id':{'type':'string','format':'uuid'},'request_sha256':HEX,
    'authority_reference_sha256':HEX,'source_manifest_sha256':HEX,'environment_identity_sha256':HEX,
    'schedule_sha256':HEX,'evidence_kind':const('runner_execution_only'),
    'integration_verified':const(False),'activation_eligible':const(False),
    'source_identity_valid':{'type':'boolean'},'scheduled':integer(1,64),'recorded':integer(1,64),
    'exited_zero':integer(0,64),'cases':{'type':'array','minItems':1,'maxItems':64,'items':row}})
receipt11=json.loads(json.dumps(receipt))
receipt11['properties']['schema_version']=const('1.1')
receipt11['properties']['target_environment_sha256']=HEX
receipt11['required'].append('target_environment_sha256')
receipt={'oneOf':[receipt,receipt11]}
observed=obj({
    'reached':const(True),'result':{'type':'string','maxLength':256},
    'effects':{'type':'array','maxItems':32,'items':{'type':'string','maxLength':128}},
    'state':{'type':'object','maxProperties':32,'propertyNames':{'maxLength':64},
             'additionalProperties':{'anyOf':[{'type':'boolean'},{'type':'integer'},
                                            {'type':'string','maxLength':256}]}},
    'assessments':integer(0,32),'dependency_origin':{'type':'string','maxLength':256},
})
oracle_phase=obj({'request_sha256':HEX,'source_manifest_sha256':HEX,'attempt':integer(1,3),
                  'cases':{'type':'array','minItems':1,'maxItems':64,'items':obj({
                      'case_id':ID,'entry_sha256':HEX,'observation':observed})}})
oracle=obj({'schema_version':const('1.0'),'kind':const('native-postconditions-v1'),
            'repository_identity':HEX,'context_sha256':HEX,'bundle_digest':HEX,
            'adapter':const('json-state-v1'),'baseline':oracle_phase,'modified':oracle_phase})
observation_report=obj({'schema_version':const('1.0'),'kind':const('native-postcondition-report-v1'),
    'oracle_sha256':HEX,'repository_identity':HEX,'context_sha256':HEX,'bundle_digest':HEX,
    'scheduled':integer(1,128),'recorded':integer(1,128),
    'cases':{'type':'array','minItems':1,'maxItems':128,'items':obj({
        'phase':{'enum':['baseline','modified']},'attempt':integer(1,3),'case_id':ID,
        'execution_outcome':{'type':'string'},'postcondition_matched':{'type':'boolean'}})},
    'parity_matched':{'type':'boolean'},'postconditions_satisfied':{'type':'boolean'},
    'integration_verified':const(False),'activation_eligible':const(False)})


def main():
    for name,value in [('native-runner-spec-v1',spec),('native-runner-receipt-v1',receipt),
                       ('native-postconditions-v1',oracle),
                       ('native-postcondition-report-v1',observation_report)]:
        value={'$schema':'https://json-schema.org/draft/2020-12/schema',
               'title':name,'description':'Runner-only contribution. Cross-artifact semantic validation is mandatory.',**value}
        data=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
        for folder in [ROOT/'schemas',ROOT/'jev_integration_evaluator'/'data']:
            folder.mkdir(parents=True,exist_ok=True)
            (folder/(name+'.schema.json')).write_bytes(data)
    print('Wrote four mirrored native-runner contracts.')

if __name__=='__main__':main()
