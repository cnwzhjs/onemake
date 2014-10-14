#! /usr/bin/python

import os
import os.path
import sys
import thread
import threading

ROOT=os.getcwd()
ONEMAKE_ROOT=os.path.dirname(os.path.realpath(__file__))
ALL_ERRORS=[]
ALL_ERRORS_LOCK=thread.allocate_lock()

sys.path.append(ONEMAKE_ROOT + "/lib")

import build_core
import job_manager
import console_helper
import path_helper
import json_helper
import option_helper

host_profile="{0}-{1}".format(option_helper.OPTIONS['host_platform'], option_helper.OPTIONS['host_arch'])
target_profile="{0}-{1}".format(option_helper.OPTIONS['target_platform'], option_helper.OPTIONS['target_arch'])
scheme=option_helper.OPTIONS['scheme']

profile_dir_candidates = [ROOT + '/profiles', ONEMAKE_ROOT + '/profiles']

env = json_helper.load_json_in_dirs('{0}-{1}-{2}.json'.format(host_profile, target_profile, scheme), profile_dir_candidates)
if env is None:
    exit(1)
env['compiler_options'] = json_helper.load_json_in_dirs("compiler-set-{0}.json".format(env['compiler_set']), profile_dir_candidates)
if env['compiler_options'] is None:
    exit(1)


def detect_compiler_version():
    if 'cc' not in env or 'gcc' not in env['cc']:
        return

    cmd = u'{0} --version'.format(env['cc'])
    p = os.popen(cmd)
    all_result = p.read()
    if 'clang' in all_result:
        return
    version_line = all_result.split('\n')[0]
    version = version_line.split(' ')[-1]
    major, minor, release = version.split('.')
    env['compiler_version'] = {
        'full': version,
        'major': major,
        'minor': minor,
        'release': release
    }
    p.close()


detect_compiler_version()

defined_projects=json_helper.load_json("onemake.json")

def process_dict_queries(d, env):
    for key in d.keys():
        if '?' not in key:
            continue
        bare_key, query_string = tuple(key.split('?', 1))
        queries = query_string.split('&')
        is_match = True

        for query in queries:
            query_key, query_value = tuple(query.split('='))
            if query_key not in env or env[query_key] != query_value:
                is_match = False
                break
        if is_match:
            if bare_key in d:
                d[bare_key] += d[key]
            else:
                d[bare_key] = d[key]

        del d[key]

    for value in d.values():
        if isinstance(value, dict):
            process_dict_queries(value, env)

process_dict_queries(defined_projects, env)


def process_project_marco_str(project, value, env):
    value = value.replace('${SRC_DIR}', project['directory'])
    value = value.replace('${OBJECT_ROOT}', build_core.OBJECT_ROOT)
    value = value.replace('${HOST_PLATFORM}', option_helper.OPTIONS["host_platform"])
    value = value.replace('${HOST_ARCH}', option_helper.OPTIONS["host_arch"])
    value = value.replace('${TARGET_PLATFORM}', option_helper.OPTIONS["target_platform"])
    value = value.replace('${TARGET_ARCH}', option_helper.OPTIONS["target_arch"])
    if 'compiler_version' in env:
        value = value.replace('${COMPILER_VERSION}', env["compiler_version"]["full"])
        value = value.replace('${COMPILER_VERSION_MAJOR}', env["compiler_version"]["major"])
        value = value.replace('${COMPILER_VERSION_MINOR}', env["compiler_version"]["minor"])
        value = value.replace('${COMPILER_VERSION_RELEASE}', env["compiler_version"]["release"])

    return value


def process_project_marcos(project, d, env):
    for key in d.keys():
        value = d[key]

        if isinstance(value, dict):
            process_project_marcos(project, value, env)
        elif isinstance(value, str) or isinstance(value, unicode):
            d[key] = process_project_marco_str(project, value, env)
        elif isinstance(value, list):
            for i in xrange(len(value)):
                subvalue = value[i]
                if isinstance(subvalue, dict):
                    process_project_marcos(project, subvalue, env)
                elif isinstance(subvalue, str) or isinstance(subvalue, unicode):
                    value[i] = process_project_marco_str(project, subvalue, env)


for project in defined_projects.values():
    process_project_marcos(project, project, env)

if option_helper.OPTIONS.get('projects') is None:
    projects = defined_projects
else:
    projects = {}
    def add_project(name):
        if name in projects:
            return True
        if name not in defined_projects:
            return False
        projects[name] = defined_projects[name]
        if 'depends' in projects[name]:
            for depend in projects[name]['depends']:
                if not add_project(depend):
                    console_helper.fatal("project {0} not found, which is referenced by {1}".format(depend, name))
        return True
    for project in option_helper.OPTIONS.get('projects').split(','):
        if not add_project(project):
            console_helper.fatal("project {0} not found".format(project))

build_core.PROJECTS = projects
build_core.ENV = env
build_core.config(scheme=option_helper.OPTIONS['scheme'], profile=option_helper.OPTIONS['target_platform'], target=option_helper.OPTIONS['target_arch'])
build_core.prepare()


def run_cmd(cmd, log_file=None):
    if log_file:
        path_helper.mkdir_if_not_exist(path_helper.dirname(log_file))

    command_line = cmd + " > {0} 2>&1".format(log_file) if log_file else cmd

    if os.system(command_line):
        ALL_ERRORS_LOCK.acquire()
        ALL_ERRORS.append([
            "Failed to execute following command:",
            cmd,
            "Please refer to log {1}: ".format(cmd, log_file) if log_file else "Please refer to log above"
        ])
        ALL_ERRORS_LOCK.release()
        return False
    else:
        return True


def compile_file_with_compiler(project, compiler, compiler_flag_name, src, dest):
    all_flags = [env[compiler]]

    build_core.add_compiler_flag(all_flags, compiler, "output_file", dest)
    if isinstance(src, list):
        for src_file in src:
            build_core.add_compiler_flag(all_flags, compiler, "source_file", src_file)
    else:
        build_core.add_compiler_flag(all_flags, compiler, "source_file", src)

    all_flags.extend(env.get(compiler_flag_name, []))
    all_flags.extend(project.get(compiler_flag_name, []))

    return run_cmd(build_core.concat_flags(all_flags), dest + '.log')

def compile_file(project_name, src, dest):
    project = build_core.PROJECTS[project_name]
    ext = path_helper.get_ext_filename(src)

    if ext == 'c':
        return compile_file_with_compiler(project, 'cc', 'cflags', src, dest)
    elif ext in ('cc', 'cpp'):
        return compile_file_with_compiler(project, 'cxx', 'cxxflags', src, dest)

def static_library(project, dest):
    if not compile_file_with_compiler(project, 'ar', 'arflags', project['object_files'], dest):
        return False

    if 'ranlib' in env:
        return run_cmd(build_core.concat_flags([env['ranlib'], dest]), dest + '.ranlib.log')
    else:
        return True

def executable(project, dest):
    if not compile_file_with_compiler(project, 'ld', 'ldflags', project['object_files'], dest):
        return False

    for post_operations in project.get('post_operations', []):
        if post_operations == 'upx':
            if not run_cmd(build_core.concat_flags(['upx', '--best', dest])):
                return False
        else:
            return False

    return True

def custom_build(dest, project):
    src_dir = build_core.ROOT + '/' + project['directory']
    object_dir = build_core.OBJECT_ROOT + '/' + project['directory']

    path_helper.mkdir_if_not_exist(object_dir)

    if project['custom_build'] == 'cmake':
        cmake_flags = project.get('cmake_flags', '')
        cmake_flags = cmake_flags.replace("${OUTPUT_ROOT}", build_core.OUTPUT_ROOT)

        make_flags = project.get('make_flags', '')

        if env.get('cross_compile'):
            cmake_flags = build_core.concat_flags(env.get('cmakeflags', [])) + ' ' + cmake_flags
            make_flags = build_core.concat_flags(env.get('makeflags', [])) + ' ' + make_flags

        if not run_cmd('cd {0} && cmake {1} {2}'.format(object_dir, src_dir, cmake_flags), project['log_file'] + '.cmake'):
            return False

        if not run_cmd('cd {0} && make {1}'.format(object_dir, make_flags), project['log_file'] + '.make'):
            return False

        return run_cmd('cp {0}/{1} {2}'.format(object_dir, project['custom_build_output_files'], path_helper.dirname(dest)))
    elif project['custom_build'] == 'configure_make':
        configure_flags = project['configure_flags'] if 'configure_flags' in project else ''
        make_flags = project['make_flags'] if 'make_flags' in project else ''

        if not run_cmd('cd {0} && {1}/configure --prefix={2} {3}'.format(object_dir, src_dir, build_core.OUTPUT_ROOT, configure_flags), project['log_file'] + '.configure'):
            return False
        if not run_cmd('cd {0} && make {1}'.format(object_dir, make_flags), project['log_file'] + '.make'):
            return False
        return run_cmd('cd {0} && make install'.format(object_dir), project['log_file'] + '.make')

def worker(thread_id):
    while True:
        result, job = job_manager.fetch_and_mark_start()
        if result == 'done':
            break
        if job:
            job_manager.JOBS_LOCK.acquire()
            jobs_done = job_manager.JOBS_COUNT['done']
            jobs_working = job_manager.JOBS_COUNT['working']
            jobs_source = job_manager.JOBS_COUNT['source']
            jobs_pending = job_manager.JOBS_COUNT['pending']
            job_manager.JOBS_LOCK.release()

            succeed = False

            if job.should_compile:
                console_helper.echo_info("[{0}/{1}] [{2}] {3}...".format(jobs_done + jobs_working - jobs_source, jobs_done + jobs_working + jobs_pending - jobs_source, job.job_type, job.dest[len(build_core.BUILD_ROOT)+1:]))

                dest_dir = path_helper.dirname(job.dest)
                path_helper.mkdir_if_not_exist(dest_dir)

                if job.job_type == 'compile':
                    succeed = compile_file(job.args, job.depends[0].dest, job.dest)
                elif job.job_type == 'static_library':
                    succeed = static_library(job.args, job.dest)
                elif job.job_type == 'source_library':
                    succeed = True
                elif job.job_type == 'copy':
                    path_helper.mkdir_if_not_exist(path_helper.dirname(job.dest))
                    succeed = run_cmd(build_core.concat_flags(["cp", job.args, job.dest]))
                elif job.job_type == "executable":
                    succeed = executable(job.args, job.dest)
                elif job.job_type == "script":
                    succeed = run_cmd(build_core.concat_flags(["cd", build_core.ROOT]) + " && " + job.args, job.args['log_file'])
                elif job.job_type == "custom_build":
                    succeed = custom_build(job.dest, job.args)
            else:
                succeed = True

            if succeed:
                job_manager.mark_done(job)
            else:
                job_manager.mark_error(job)

threads=[]

for i in xrange(int(option_helper.OPTIONS['concurrent'])):
    worker_thread = threading.Thread(None, worker, args=(i,))
    worker_thread.start()
    threads.append(worker_thread)

for worker_thread in threads:
    if not worker_thread.is_alive():
        continue
    worker_thread.join()

if job_manager.JOBS_COUNT['error']:
    console_helper.echo_error("{0} errors occurred".format(job_manager.JOBS_COUNT['error']))
    for i in xrange(len(ALL_ERRORS)):
        error_entry = ALL_ERRORS[i]
        console_helper.echo_error("Error {0}".format(i))
        for line in error_entry:
            console_helper.echo_warn("    {0}".format(line))
    exit(1)
else:
    console_helper.echo_info("all done")
